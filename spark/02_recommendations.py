"""
02_recommendations.py - Spark batch job #2: product recommendation indicators.

A) "Customers who bought X also bought Y"  (market-basket on transaction line items)
B) "Products frequently viewed together"    (co-occurrence inside a browsing session)
C) Category-level affinity                  (same idea, aggregated - denser signal)

For every pair (X, Y) we compute the classic association-rule measures
    support(X,Y)    = baskets containing both / all baskets
    confidence(X->Y)= baskets containing both / baskets containing X
    lift(X,Y)       = confidence(X->Y) / P(Y)      (lift > 1 => positive association)
and keep the top-5 Y per X (window function) as the recommendation list.

Optimisations
  * pairs are generated with a self-join on basket_id restricted to a < b (halves the rows,
    removes self-pairs); for sessions the pairs are built from the viewed_products ARRAY with
    a higher-order function instead of a join, avoiding a shuffle of page views
  * per-item frequencies are broadcast (5 000 products / 25 categories => tiny)
  * MIN_PAIR_COUNT prunes the long tail before the window ranking
"""
import os
import sys

from pyspark.sql import functions as F
from pyspark.sql.window import Window

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spark_utils as su  # noqa: E402

spark = su.get_spark("02_recommendations")
MIN_PAIR_COUNT = int(os.getenv("MIN_PAIR_COUNT", "2"))

items = su.read_clean(spark, "transaction_items")
sessions = su.read_clean(spark, "sessions")
products = su.read_clean(spark, "products").select("product_id", "product_name", "category_name")


def association_rules(baskets, basket_col, item_col, min_count, label):
    """baskets: DataFrame(basket_col, item_col) with distinct rows. Returns rule DataFrame."""
    n_baskets = baskets.select(basket_col).distinct().count()
    item_freq = baskets.groupBy(item_col).agg(F.countDistinct(basket_col).alias("item_count"))
    a = baskets.select(F.col(basket_col).alias("b"), F.col(item_col).alias("x"))
    pairs = (a.join(a.withColumnRenamed("x", "y"), "b")
              .filter(F.col("x") < F.col("y"))
              .groupBy("x", "y").agg(F.count("*").alias("pair_count")))
    return rules_from_pairs(pairs, item_freq, item_col, n_baskets, min_count, label)


def rules_from_pairs(pairs, item_freq, item_col, n_baskets, min_count, label):
    pairs = pairs.filter(F.col("pair_count") >= min_count)
    # make the rules directional: x->y and y->x
    both = pairs.unionByName(pairs.select(F.col("y").alias("x"), F.col("x").alias("y"), "pair_count"))
    fx = F.broadcast(item_freq.select(F.col(item_col).alias("x"), F.col("item_count").alias("x_count")))
    fy = F.broadcast(item_freq.select(F.col(item_col).alias("y"), F.col("item_count").alias("y_count")))
    rules = (both.join(fx, "x").join(fy, "y")
             .withColumn("support", F.col("pair_count") / n_baskets)
             .withColumn("confidence", F.col("pair_count") / F.col("x_count"))
             .withColumn("lift", F.col("confidence") / (F.col("y_count") / n_baskets)))
    w = Window.partitionBy("x").orderBy(F.desc("lift"), F.desc("pair_count"), "y")
    top = rules.withColumn("rank", F.row_number().over(w)).filter("rank <= 5")
    print(f"\n== {label}: {n_baskets:,} baskets, {pairs.count():,} pairs with count >= {min_count}")
    top.orderBy(F.desc("pair_count"), F.desc("lift")).show(10, truncate=False)
    return top


# ---------------------------------------------------------------- A) bought together
baskets = items.select("transaction_id", "product_id").distinct()
bought = association_rules(baskets, "transaction_id", "product_id", MIN_PAIR_COUNT, "Bought together (product)")
bought_named = (bought.join(products.withColumnRenamed("product_id", "x").withColumnRenamed("product_name", "x_name")
                            .drop("category_name"), "x")
                .join(products.withColumnRenamed("product_id", "y").withColumnRenamed("product_name", "y_name")
                      .drop("category_name"), "y"))
bought_named.write.mode("overwrite").parquet(su.clean_path("reco_bought_together"))
su.save_csv(bought_named.orderBy(F.desc("pair_count"), F.desc("lift")).limit(200), "reco_bought_together_top")

# ---------------------------------------------------------------- B) viewed together (array HOF, no join)
viewed = sessions.select("session_id", F.array_distinct("viewed_products").alias("v")).filter(F.size("v") >= 2)
n_view_sessions = sessions.filter(F.size("viewed_products") >= 1).count()
view_pairs = (viewed
              .select(F.explode(F.flatten(F.transform(
                  "v", lambda x: F.transform(F.filter("v", lambda y: x < y),
                                             lambda y: F.struct(x.alias("x"), y.alias("y")))))).alias("p"))
              .groupBy(F.col("p.x").alias("x"), F.col("p.y").alias("y"))
              .agg(F.count("*").alias("pair_count")))
view_freq = (sessions.select("session_id", F.explode(F.array_distinct("viewed_products")).alias("product_id"))
             .groupBy("product_id").agg(F.count("*").alias("item_count")))
viewed_rules = rules_from_pairs(view_pairs, view_freq, "product_id", n_view_sessions,
                                MIN_PAIR_COUNT, "Viewed together (product)")
viewed_rules.write.mode("overwrite").parquet(su.clean_path("reco_viewed_together"))
su.save_csv(viewed_rules.orderBy(F.desc("pair_count")).limit(200), "reco_viewed_together_top")

# ---------------------------------------------------------------- C) category affinity (purchases)
cat_baskets = items.select("transaction_id", "category_name").distinct()
cat_rules = association_rules(cat_baskets, "transaction_id", "category_name", 1, "Bought together (category)")
su.save_csv(cat_rules.orderBy(F.desc("lift")), "reco_category_affinity")

# a lift distribution summary is the honest way to judge whether the signal is real
for name, df in [("bought", bought), ("viewed", viewed_rules), ("category", cat_rules)]:
    df.select(F.lit(name).alias("rules"), F.count("*").alias("n"), F.round(F.avg("lift"), 3).alias("avg_lift"),
              F.round(F.expr("percentile_approx(lift, 0.5)"), 3).alias("median_lift"),
              F.round(F.max("lift"), 2).alias("max_lift")).show()
spark.stop()
