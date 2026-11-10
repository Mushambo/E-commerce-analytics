"""
clv_analysis.py - Integrated query #1: Customer Lifetime Value (CLV) estimation & segmentation.

BUSINESS QUESTION
  "Which customers are worth the most over their expected lifetime, how engaged are they, and
   which segment should marketing prioritise for retention spend?"

DATA SOURCES
  users profile ............ MongoDB `users`          (load_users)
  purchase history ......... MongoDB `transactions`   (load_line_items, $unwind pushed down)
  engagement (sessions) .... HBase   `user_sessions`  (load_sessions: frequency, duration, pages)
  margins .................. category dimension (small, broadcast)

PROCESSING (Spark)
  1. per-user purchase facts: orders, net revenue, gross profit, AOV, recency, frequency
  2. per-user engagement facts from HBase: sessions, avg duration, pages, session->order rate
  3. monthly retention rate r estimated from the data (share of month-m buyers who buy in m+1)
       expected lifetime (months) = 1 / (1 - r), capped at 36
  4. CLV = AOV x monthly purchase frequency x gross margin % x expected lifetime
  5. RFM scores (NTILE 5) -> named segments; CLV quartile tiers
  6. outputs: output/clv_users.csv, output/clv_segments.csv, output/clv_tier_engagement.csv

    python integration/clv_analysis.py                                  # all from files
    python integration/clv_analysis.py --mongo mongo --hbase hbase      # live systems
    python integration/clv_analysis.py --hbase hbase-emulator           # HBase emulator
"""
import argparse
import os
import sys

from pyspark.sql import functions as F
from pyspark.sql.window import Window

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources  # noqa: E402
from sources import su  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--mongo", default="files", choices=["files", "mongo"])
ap.add_argument("--hbase", default="files", choices=["files", "hbase", "hbase-emulator"])
a = ap.parse_args()

spark = su.get_spark("integration_clv")
users = sources.load_users(spark, a.mongo)
items = sources.load_line_items(spark, a.mongo)
sessions = sources.load_sessions(spark, a.hbase)
margins = F.broadcast(sources.load_margins(spark).select("subcategory_id", "profit_margin"))

# observation window = span of the transaction data
bounds = items.agg(F.min("txn_time").alias("t0"), F.max("txn_time").alias("t1")).first()
window_days = max((bounds.t1 - bounds.t0).days, 1)
window_months = window_days / 30.4
print(f"Observation window: {bounds.t0:%Y-%m-%d} .. {bounds.t1:%Y-%m-%d} ({window_days} days)")

# ---------------------------------------------------------------- 1. purchase facts
items_m = items.join(margins, "subcategory_id", "left").withColumn(
    "profit", F.col("net_revenue") * F.coalesce("profit_margin", F.lit(0.25)))
purchases = (items_m.groupBy("user_id").agg(
    F.countDistinct("transaction_id").alias("orders"),
    F.round(F.sum("net_revenue"), 2).alias("revenue"),
    F.round(F.sum("profit"), 2).alias("gross_profit"),
    F.max("txn_time").alias("last_purchase"),
    F.min("txn_time").alias("first_purchase"))
    .withColumn("aov", F.round(F.col("revenue") / F.col("orders"), 2))
    .withColumn("margin_pct", F.col("gross_profit") / F.col("revenue"))
    .withColumn("recency_days", F.datediff(F.lit(bounds.t1), "last_purchase"))
    .withColumn("orders_per_month", F.col("orders") / F.lit(window_months)))

# ---------------------------------------------------------------- 2. engagement facts (HBase)
web_orders = items.filter(F.col("session_id").isNotNull()).select("session_id").distinct() \
                  .withColumn("bought", F.lit(1))
engagement = (sessions.join(web_orders, "session_id", "left").groupBy("user_id").agg(
    F.count("*").alias("sessions"),
    F.round(F.avg("duration_seconds") / 60, 1).alias("avg_session_min"),
    F.round(F.avg("n_pages"), 1).alias("avg_pages"),
    F.round(F.avg(F.col("has_cart").cast("int")), 3).alias("cart_rate"),
    F.round(F.sum(F.coalesce("bought", F.lit(0))) / F.count("*"), 3).alias("session_purchase_rate")))

# ---------------------------------------------------------------- 3. retention -> lifetime
monthly = items.select("user_id", F.date_format("txn_time", "yyyy-MM").alias("m")).distinct()
full_months = [r.m for r in monthly.groupBy("m").count().orderBy("m").collect()][1:-1]  # drop partial months
m = monthly.filter(F.col("m").isin(full_months))
nxt = m.select("user_id", F.date_format(F.add_months(F.to_date(F.concat("m", F.lit("-01"))), -1), "yyyy-MM").alias("m"),
               F.lit(1).alias("returned"))
ret = m.join(nxt, ["user_id", "m"], "left").filter(F.col("m") < max(full_months)) \
       .agg(F.avg(F.coalesce("returned", F.lit(0))).alias("r")).first().r or 0.0
lifetime_months = min(1 / (1 - ret), 36) if ret < 1 else 36
print(f"Monthly buyer retention r = {ret:.3f} -> expected lifetime = {lifetime_months:.1f} months")

# ---------------------------------------------------------------- 4/5. CLV + RFM
clv = (users.join(purchases, "user_id", "left").join(engagement, "user_id", "left")
       .fillna(0, ["orders", "revenue", "gross_profit", "aov", "orders_per_month", "sessions"])
       .withColumn("recency_days", F.coalesce("recency_days", F.lit(window_days)))
       .withColumn("clv", F.round(F.col("aov") * F.col("orders_per_month")
                                  * F.coalesce("margin_pct", F.lit(0.0)) * F.lit(lifetime_months), 2)))

buyers = clv.filter("orders > 0")
clv = clv.join(buyers.select(
    "user_id",
    F.ntile(5).over(Window.orderBy(F.desc("recency_days"))).alias("R"),   # recent -> 5
    F.ntile(5).over(Window.orderBy("orders", "revenue")).alias("F"),
    F.ntile(5).over(Window.orderBy("revenue")).alias("M"),
    F.ntile(4).over(Window.orderBy("clv")).alias("clv_quartile")), "user_id", "left")

clv = clv.withColumn("segment",
    F.when(F.col("orders") == 0, "No purchase")
     .when((F.col("R") >= 4) & (F.col("F") >= 4) & (F.col("M") >= 4), "Champions")
     .when((F.col("F") >= 4) & (F.col("R") >= 3), "Loyal")
     .when((F.col("R") <= 2) & (F.col("M") >= 4), "At risk - high value")
     .when((F.col("R") <= 2), "Hibernating")
     .when((F.col("F") <= 2) & (F.col("R") >= 4), "New / promising")
     .otherwise("Needs attention")) \
    .withColumn("clv_tier", F.element_at(F.array(*[F.lit(x) for x in ["Bronze", "Silver", "Gold", "Platinum"]]),
                                         F.coalesce("clv_quartile", F.lit(1)).cast("int")))
clv = clv.cache()

segments = (clv.groupBy("segment").agg(
    F.count("*").alias("users"),
    F.round(F.avg("clv"), 2).alias("avg_clv"),
    F.round(F.sum("clv"), 0).alias("total_clv"),
    F.round(F.avg("revenue"), 2).alias("avg_revenue_90d"),
    F.round(F.avg("orders"), 2).alias("avg_orders"),
    F.round(F.avg("recency_days"), 1).alias("avg_recency_days"),
    F.round(F.avg("sessions"), 1).alias("avg_sessions"),
    F.round(F.avg("session_purchase_rate"), 3).alias("avg_session_purchase_rate"))
    .withColumn("share_of_clv_pct", F.round(100 * F.col("total_clv") / F.sum("total_clv").over(Window.partitionBy()), 1))
    .orderBy(F.desc("avg_clv")))
segments.show(truncate=False)

tiers = (clv.filter("orders > 0").groupBy("clv_tier").agg(
    F.count("*").alias("users"), F.round(F.avg("clv"), 2).alias("avg_clv"),
    F.round(F.min("clv"), 2).alias("min_clv"), F.round(F.max("clv"), 2).alias("max_clv"),
    F.round(F.avg("sessions"), 1).alias("avg_sessions"), F.round(F.avg("avg_session_min"), 1).alias("avg_session_min"),
    F.round(F.avg("avg_pages"), 1).alias("avg_pages"), F.round(F.avg("cart_rate"), 3).alias("cart_rate"),
    F.round(F.avg("session_purchase_rate"), 3).alias("session_purchase_rate"),
    F.round(F.avg("aov"), 2).alias("avg_aov"), F.round(F.avg("orders"), 2).alias("avg_orders"))
    .orderBy("min_clv"))
tiers.show(truncate=False)

corr = clv.filter("orders > 0").select(
    F.round(F.corr("sessions", "clv"), 3).alias("corr_sessions_clv"),
    F.round(F.corr("avg_session_min", "clv"), 3).alias("corr_duration_clv"),
    F.round(F.corr("cart_rate", "clv"), 3).alias("corr_cart_rate_clv"))
corr.show()

su.save_csv(clv.select("user_id", "country", "registration_month", "orders", "revenue", "gross_profit", "aov",
                       "recency_days", "sessions", "avg_session_min", "avg_pages", "session_purchase_rate",
                       "R", "F", "M", "clv", "clv_tier", "segment"), "clv_users")
su.save_csv(segments, "clv_segments")
su.save_csv(tiers, "clv_tier_engagement")
su.save_csv(corr, "clv_correlations")
spark.createDataFrame([(ret, lifetime_months, window_days)], "monthly_retention double, lifetime_months double, window_days int") \
     .toPandas().to_csv(os.path.join(su.config.OUTPUT_DIR, "clv_parameters.csv"), index=False)
spark.stop()
