"""
funnel_analysis.py - Integrated query #2: funnel conversion analysis (view -> cart -> checkout -> purchase).

BUSINESS QUESTION
  "Where in the journey do we lose shoppers, does it differ by device / traffic source /
   category, and how much revenue does each leak represent?"

DATA SOURCES
  session journeys & stage flags ... HBase   `user_sessions`   (pv + cart families)
  product views / cart adds per day . HBase   `product_metrics`
  purchases (ground truth) .......... MongoDB `transactions`    (session_id link, line items)

NOTE  The generator marks ~20 % of sessions "converted", but only ~62 % of those actually
      have a transaction (the generator stops creating session transactions once its
      transaction target is reached, and some fail the stock check). The funnel therefore
      uses the MongoDB transaction as the source of truth for the final stage and reports
      the gap explicitly - a good example of why cross-system reconciliation matters.

    python integration/funnel_analysis.py [--mongo files|mongo] [--hbase files|hbase|hbase-emulator]
"""
import argparse
import os
import sys

from pyspark.sql import functions as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources  # noqa: E402
from sources import su  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--mongo", default="files", choices=["files", "mongo"])
ap.add_argument("--hbase", default="files", choices=["files", "hbase", "hbase-emulator"])
a = ap.parse_args()

spark = su.get_spark("integration_funnel")
sessions = sources.load_sessions(spark, a.hbase)
items = sources.load_line_items(spark, a.mongo)
pm = sources.load_product_metrics(spark, a.hbase)
cats = sources.load_margins(spark).select("category_id", "category_name").distinct()

orders = (items.filter(F.col("session_id").isNotNull()).groupBy("session_id")
          .agg(F.sum("net_revenue").alias("order_revenue")))
s = (sessions.join(orders, "session_id", "left")
     .withColumn("purchased", F.col("order_revenue").isNotNull())
     .withColumn("flag_converted", F.col("conversion_status") == "converted")
     .cache())

# ---------------------------------------------------------------- 1. overall funnel
stages = [("1. Session", F.lit(True)), ("2. Product view", F.col("has_product_view")),
          ("3. Add to cart", F.col("has_cart")), ("4. Checkout", F.col("has_checkout") & F.col("has_cart")),
          ("5. Purchase", F.col("purchased"))]
row = s.agg(*[F.sum(c.cast("int")).alias(n) for n, c in stages],
            F.sum(F.col("flag_converted").cast("int")).alias("flag_converted")).first()
funnel = [(n, int(row[n])) for n, _ in stages]
out = []
for i, (n, v) in enumerate(funnel):
    prev = funnel[i - 1][1] if i else v
    out.append((n, v, round(100 * v / funnel[0][1], 2), round(100 * v / prev, 2), prev - v))
funnel_df = spark.createDataFrame(out, "stage string, sessions long, pct_of_sessions double, "
                                       "step_conversion_pct double, dropped long")
funnel_df.show(truncate=False)
print(f"Sessions flagged 'converted' by the generator: {row['flag_converted']:,} "
      f"vs sessions with a real transaction: {row['5. Purchase']:,}")
su.save_csv(funnel_df, "funnel_overall")

# lost revenue estimate: carts that reached checkout but did not purchase x avg web order value
aov = s.filter("purchased").agg(F.avg("order_revenue")).first()[0]
lost_checkout = row["4. Checkout"] - row["5. Purchase"]
print(f"Average web order value ${aov:,.2f}; checkout abandoners {lost_checkout:,} "
      f"=> ~${lost_checkout * aov:,.0f} unrealised revenue in the window")

# ---------------------------------------------------------------- 2. funnel by device & referrer
def by(dim):
    return (s.groupBy(dim).agg(
        F.count("*").alias("sessions"),
        F.round(100 * F.avg(F.col("has_cart").cast("int")), 2).alias("cart_pct"),
        F.round(100 * F.avg((F.col("has_checkout") & F.col("has_cart")).cast("int")), 2).alias("checkout_pct"),
        F.round(100 * F.avg(F.col("purchased").cast("int")), 2).alias("purchase_pct"),
        F.round(F.sum("order_revenue") / F.count("*"), 2).alias("revenue_per_session"))
        .orderBy(F.desc("purchase_pct")))


for dim in ["device_type", "referrer"]:
    d = by(dim)
    d.show()
    su.save_csv(d, f"funnel_by_{dim}")

# ---------------------------------------------------------------- 3. category funnel: HBase views x Mongo purchases
prod_cat = F.broadcast(su.read_clean(spark, "products").select("product_id", "category_id"))
cat_views = (pm.join(prod_cat, "product_id")
             .groupBy("category_id").agg(F.sum("views").alias("views"), F.sum("cart_adds").alias("cart_adds")))
# only web-session purchases, so numerator and denominator describe the same journeys
cat_sales = items.filter(F.col("session_id").isNotNull()).groupBy("category_id").agg(F.count("*").alias("purchased_lines"),
                                             F.sum("quantity").alias("units"),
                                             F.round(F.sum("net_revenue"), 2).alias("revenue"))
cat_funnel = (cat_views.join(cat_sales, "category_id").join(F.broadcast(cats), "category_id")
              .withColumn("view_to_cart_pct", F.round(100 * F.col("cart_adds") / F.col("views"), 2))
              .withColumn("cart_to_purchase_pct", F.round(100 * F.col("purchased_lines") / F.col("cart_adds"), 2))
              .withColumn("revenue_per_1k_views", F.round(1000 * F.col("revenue") / F.col("views"), 2))
              .orderBy(F.desc("revenue_per_1k_views")))
cat_funnel.show(30, truncate=False)
su.save_csv(cat_funnel, "funnel_by_category")

# ---------------------------------------------------------------- 4. weekly trend of conversion
weekly = (s.withColumn("week", F.date_trunc("week", F.to_timestamp("start_time")))
          .groupBy("week").agg(F.count("*").alias("sessions"),
                               F.round(100 * F.avg(F.col("purchased").cast("int")), 2).alias("purchase_pct"),
                               F.round(100 * F.avg(F.col("has_cart").cast("int")), 2).alias("cart_pct"))
          .orderBy("week"))
weekly.show(20)
su.save_csv(weekly, "funnel_weekly")
spark.stop()
