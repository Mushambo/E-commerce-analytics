"""
01_clean_normalize.py - Spark batch job #1: raw JSON -> clean, normalised Parquet tables.

Input : data/raw/*.json (generator output; sessions_*.json read together with a glob)
Output: data/clean/<table>/ (Parquet, snappy)

  users              one row per user, typed timestamps, flattened geo
  categories         one row per SUBCATEGORY (category hierarchy flattened)
  products           typed, + n_price_changes / first_price
  price_history      exploded price points
  sessions           one row per session, typed, enums normalised, funnel flags, partitioned by date
  page_views         exploded click-stream (one row per page view), partitioned by date
  cart_items         exploded cart contents (one row per session x product)
  transactions       order header, typed, + reconciliation flags
  transaction_items  exploded line items enriched with category & margin

Cleaning rules (all counted in output/data_quality_report.csv):
  * de-duplicate on primary keys
  * drop rows with a missing primary/foreign key or unparseable timestamp
  * trim strings, lower-case enum columns, upper-case country/state codes
  * clamp negative numbers (duration, stock, quantity, price) -> rows dropped/flagged
  * fill missing descriptive values with 'unknown' (city, subcategory)
  * repair `conversion_status`: the generator labels a session "abandoned" when the cart
    dictionary was touched, even if every quantity ended at 0 (=> cart is empty) - those are
    really "browsed"
  * flag (not drop) logical inconsistencies: last_active < registration, transaction total !=
    subtotal - discount, converted session with no transaction, orphan foreign keys
"""
import os
import sys
import time

from pyspark.sql import functions as F
from pyspark.sql.window import Window

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spark_utils as su  # noqa: E402
from spark_utils import config  # noqa: E402

spark = su.get_spark("01_clean_normalize")
RAW = config.RAW_DIR
quality = []   # (table, check, count)


def q(table, check, n):
    quality.append((table, check, int(n)))
    print(f"   [{table}] {check}: {n:,}")


def ts(col):
    """ISO-8601 string (with or without micro-seconds) -> timestamp."""
    return F.to_timestamp(F.col(col))


def dedupe(df, key, table):
    before = df.count()
    df = df.dropDuplicates([key])
    q(table, "duplicates_removed", before - df.count())
    return df


def write(df, name, partition=None):
    w = df.write.mode("overwrite")
    if partition:
        w = w.partitionBy(partition)
    w.parquet(su.clean_path(name))


t0 = time.time()
# ------------------------------------------------------------------ categories (flatten hierarchy)
print("categories")
cat_raw = spark.read.json(f"{RAW}/categories.json", schema=su.CATEGORIES_SCHEMA, multiLine=True)
categories = (cat_raw
              .select(F.trim("category_id").alias("category_id"), F.trim("name").alias("category_name"),
                      F.explode_outer("subcategories").alias("s"))
              .select("category_id", "category_name",
                      F.col("s.subcategory_id").alias("subcategory_id"),
                      F.trim("s.name").alias("subcategory_name"),
                      F.coalesce("s.profit_margin", F.lit(0.0)).alias("profit_margin")))
write(categories, "categories")
q("categories", "subcategory_rows", categories.count())

# ------------------------------------------------------------------ users
print("users")
users_raw = spark.read.json(f"{RAW}/users.json", schema=su.USERS_SCHEMA, multiLine=True)
q("users", "raw_rows", users_raw.count())
users = dedupe(users_raw, "user_id", "users")
users = (users
         .select(F.trim("user_id").alias("user_id"),
                 F.coalesce(F.initcap(F.trim("geo_data.city")), F.lit("unknown")).alias("city"),
                 F.coalesce(F.upper(F.trim("geo_data.state")), F.lit("NA")).alias("state"),
                 F.coalesce(F.upper(F.trim("geo_data.country")), F.lit("NA")).alias("country"),
                 ts("registration_date").alias("registration_date"),
                 ts("last_active").alias("last_active"))
         .filter(F.col("user_id").isNotNull() & F.col("registration_date").isNotNull())
         .withColumn("registration_month", F.date_format("registration_date", "yyyy-MM")))
users = users.cache()
q("users", "clean_rows", users.count())

# ------------------------------------------------------------------ products
print("products")
prod_raw = spark.read.json(f"{RAW}/products.json", schema=su.PRODUCTS_SCHEMA, multiLine=True)
prod = dedupe(prod_raw, "product_id", "products")
q("products", "missing_subcategory_filled", prod.filter(F.col("subcategory_id").isNull()).count())
q("products", "negative_price_or_stock", prod.filter((F.col("base_price") < 0) | (F.col("current_stock") < 0)).count())
products = (prod
            .filter(F.col("product_id").isNotNull() & (F.col("base_price") >= 0))
            .select("product_id", F.trim("name").alias("product_name"), "category_id",
                    F.coalesce("subcategory_id", F.lit("unknown")).alias("subcategory_id"),
                    F.round("base_price", 2).alias("current_price"),
                    F.greatest("current_stock", F.lit(0)).alias("current_stock"),
                    F.coalesce("is_active", F.lit(False)).alias("is_active"),
                    ts("creation_date").alias("creation_date"),
                    (F.size("price_history") - 1).alias("n_price_changes"),
                    F.col("price_history")[0]["price"].alias("first_price"))
            .join(categories.select("subcategory_id", "category_name", "subcategory_name", "profit_margin"),
                  "subcategory_id", "left"))
write(products, "products")
price_history = (prod.select("product_id", F.posexplode("price_history").alias("seq", "p"))
                 .select("product_id", "seq", F.col("p.price").alias("price"), ts("p.date").alias("effective_date")))
write(price_history, "price_history")

# ------------------------------------------------------------------ sessions
print("sessions (all sessions_*.json files)")
sess_raw = spark.read.json(f"{RAW}/sessions_*.json", schema=su.SESSIONS_SCHEMA, multiLine=True)
q("sessions", "raw_rows", sess_raw.count())
sess = dedupe(sess_raw, "session_id", "sessions")
bad = sess.filter(F.col("user_id").isNull() | ts("start_time").isNull() | (F.col("duration_seconds") <= 0))
q("sessions", "invalid_rows_dropped", bad.count())
sess = sess.filter(F.col("user_id").isNotNull() & ts("start_time").isNotNull() & (F.col("duration_seconds") > 0))
q("sessions", "orphan_user_id", sess.join(users, "user_id", "left_anti").count())

pages = F.col("page_views.page_type")
cart_qty = F.aggregate(F.map_values("cart_contents"), F.lit(0).cast("long"), lambda acc, v: acc + v["quantity"])
sessions = (sess.select(
        "session_id", "user_id",
        ts("start_time").alias("start_time"), ts("end_time").alias("end_time"),
        F.col("duration_seconds"),
        F.lower(F.trim("device_profile.type")).alias("device_type"),
        F.trim("device_profile.os").alias("os"), F.trim("device_profile.browser").alias("browser"),
        F.upper("geo_data.country").alias("country"), F.col("geo_data.ip_address").alias("ip_address"),
        F.lower(F.trim("referrer")).alias("referrer"),
        F.lower(F.trim("conversion_status")).alias("raw_status"),
        F.size("page_views").alias("n_pages"),
        F.size("viewed_products").alias("n_products_viewed"),
        F.coalesce(F.size(F.map_keys("cart_contents")), F.lit(0)).alias("n_cart_products"),
        F.coalesce(cart_qty, F.lit(0)).alias("cart_units"),
        F.array_contains(pages, "product_detail").alias("has_product_view"),
        F.array_contains(pages, "cart").alias("has_cart_page"),
        F.array_contains(pages, "checkout").alias("has_checkout"),
        F.array_contains(pages, "confirmation").alias("has_confirmation"),
        F.col("viewed_products"))
    .withColumn("conversion_status",
                F.when((F.col("raw_status") == "abandoned") & (F.col("n_cart_products") == 0), "browsed")
                 .otherwise(F.col("raw_status")))
    .withColumn("session_date", F.to_date("start_time")))
q("sessions", "status_repaired_abandoned_to_browsed",
  sessions.filter(F.col("raw_status") != F.col("conversion_status")).count())
write(sessions.drop("raw_status"), "sessions", partition="session_date")

page_views = (sess.select("session_id", "user_id", F.posexplode("page_views").alias("seq", "pv"))
              .select("session_id", "user_id", "seq", ts("pv.timestamp").alias("view_time"),
                      F.lower("pv.page_type").alias("page_type"), F.col("pv.product_id").alias("product_id"),
                      F.col("pv.category_id").alias("category_id"),
                      F.greatest(F.col("pv.view_duration"), F.lit(0)).alias("view_duration"))
              .withColumn("view_date", F.to_date("view_time")))
write(page_views, "page_views", partition="view_date")

cart_items = (sess.select("session_id", "user_id", ts("start_time").alias("start_time"),
                          F.explode("cart_contents").alias("product_id", "c"))
              .select("session_id", "user_id", "start_time", "product_id",
                      F.col("c.quantity").alias("quantity"), F.col("c.price").alias("price"))
              .filter(F.col("quantity") > 0))
write(cart_items, "cart_items")

# ------------------------------------------------------------------ transactions
print("transactions")
txn_raw = spark.read.json(f"{RAW}/transactions.json", schema=su.TRANSACTIONS_SCHEMA, multiLine=True)
q("transactions", "raw_rows", txn_raw.count())
txn = dedupe(txn_raw, "transaction_id", "transactions")
txn = txn.filter(F.col("user_id").isNotNull() & ts("timestamp").isNotNull() & (F.size("items") > 0))
item_sum = F.aggregate("items", F.lit(0.0), lambda acc, i: acc + i["subtotal"])
transactions = (txn.select(
        "transaction_id", "session_id", "user_id", ts("timestamp").alias("txn_time"),
        F.size("items").alias("n_items"),
        F.aggregate("items", F.lit(0).cast("long"), lambda acc, i: acc + i["quantity"]).alias("units"),
        F.round("subtotal", 2).alias("subtotal"), F.round(F.coalesce("discount", F.lit(0.0)), 2).alias("discount"),
        F.round("total", 2).alias("total"),
        F.lower("payment_method").alias("payment_method"), F.lower("status").alias("status"),
        F.when(F.col("session_id").isNull(), "offline_or_app").otherwise("web_session").alias("channel"),
        (F.abs(F.col("total") - (F.col("subtotal") - F.coalesce("discount", F.lit(0.0)))) > 0.011).alias("flag_total_mismatch"),
        (F.abs(item_sum - F.col("subtotal")) > 0.011).alias("flag_items_mismatch"))
    .withColumn("txn_date", F.to_date("txn_time"))
    .withColumn("txn_month", F.date_format("txn_time", "yyyy-MM")))
q("transactions", "total_mismatch_flagged", transactions.filter("flag_total_mismatch").count())
q("transactions", "items_sum_mismatch_flagged", transactions.filter("flag_items_mismatch").count())
q("transactions", "orphan_user_id", transactions.join(users, "user_id", "left_anti").count())
write(transactions, "transactions")

# line items with the discount pro-rated so item revenue sums to the order total
transaction_items = (txn.select("transaction_id", "user_id", ts("timestamp").alias("txn_time"),
                                "subtotal", "discount", F.explode("items").alias("i"))
                     .select("transaction_id", "user_id", "txn_time", F.col("i.product_id").alias("product_id"),
                             F.col("i.quantity").alias("quantity"), F.col("i.unit_price").alias("unit_price"),
                             F.col("i.subtotal").alias("gross_revenue"),
                             F.round(F.col("i.subtotal") * (1 - F.coalesce("discount", F.lit(0.0)) / F.col("subtotal")), 2)
                              .alias("net_revenue"))
                     .join(F.broadcast(products.select("product_id", "category_id", "category_name",
                                                       "subcategory_id", "profit_margin")), "product_id", "left")
                     .withColumn("est_profit", F.round(F.col("net_revenue") * F.col("profit_margin"), 2))
                     .withColumn("txn_date", F.to_date("txn_time")))
q("transaction_items", "orphan_product_id", transaction_items.filter(F.col("category_id").isNull()).count())
write(transaction_items, "transaction_items")

# converted sessions that never produced a transaction (inventory check failed in the generator)
conv = spark.read.parquet(su.clean_path("sessions")).filter("conversion_status = 'converted'")
q("sessions", "converted_without_transaction",
  conv.join(transactions.filter(F.col("session_id").isNotNull()), "session_id", "left_anti").count())
q("users", "last_active_before_registration", users.filter(F.col("last_active") < F.col("registration_date")).count())
write(users, "users")

# ------------------------------------------------------------------ quality report
spark.createDataFrame(quality, ["table", "check", "count"]).toPandas().to_csv(
    os.path.join(config.OUTPUT_DIR, "data_quality_report.csv"), index=False)
print(f"\nClean tables written to {config.CLEAN_DIR} in {time.time() - t0:.0f}s")
spark.stop()
