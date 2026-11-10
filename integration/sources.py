"""
sources.py - data-access layer for the integrated analytics (Part 3).

Every loader returns a Spark DataFrame with the SAME columns whatever the source, so the
analysis code does not care where the data physically lives:

    source="files"   cleaned Parquet produced by spark/01_clean_normalize.py (default, no servers)
    source="mongo"   MongoDB via pymongo, with the heavy lifting PUSHED DOWN into an
                     aggregation pipeline so only compact results cross the network
    source="hbase"   HBase via the Thrift server (happybase) - prefix/range scans
    source="hbase-emulator"  same scans against the local SQLite HBase emulator

At larger scale replace the pymongo/happybase readers with the native connectors
(mongo-spark-connector `spark.read.format("mongodb")`, hbase-spark `format("org.apache.hadoop.hbase.spark")`)
which read partitions in parallel on the executors instead of through the driver.
"""
import os
import sys

from pyspark.sql import functions as F
from pyspark.sql.types import (BooleanType, DoubleType, LongType, StringType, StructField, StructType,
                               TimestampType)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "spark"))
sys.path.insert(0, os.path.join(ROOT, "hbase"))
import config  # noqa: E402
import spark_utils as su  # noqa: E402


# ------------------------------------------------------------------ helpers
def _mongo_db():
    from pymongo import MongoClient
    c = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
    c.admin.command("ping")
    return c[config.MONGO_DB]


def _hbase(source):
    from hbase_client import get_connection
    return get_connection(emulate=(source == "hbase-emulator"))


def _dec(v):
    return v.decode() if isinstance(v, bytes) else v


# ------------------------------------------------------------------ users (MongoDB)
USER_COLS = ["user_id", "country", "registration_date", "registration_month"]


def load_users(spark, source="files"):
    if source == "files":
        return su.read_clean(spark, "users").select(*USER_COLS)
    if source == "mongo":
        rows = [(d["_id"], d["geo_data"]["country"], d["registration_date"],
                 d["registration_date"].strftime("%Y-%m"))
                for d in _mongo_db().users.find({}, {"geo_data.country": 1, "registration_date": 1})]
        schema = StructType([StructField("user_id", StringType()), StructField("country", StringType()),
                             StructField("registration_date", TimestampType()),
                             StructField("registration_month", StringType())])
        return spark.createDataFrame(rows, schema)
    raise ValueError(source)


# ------------------------------------------------------------------ line items (MongoDB)
ITEM_COLS = ["transaction_id", "user_id", "session_id", "txn_time", "product_id", "category_id",
             "subcategory_id", "quantity", "net_revenue"]


def load_line_items(spark, source="files"):
    if source == "files":
        items = su.read_clean(spark, "transaction_items")
        sess = su.read_clean(spark, "transactions").select("transaction_id", "session_id")
        return items.join(sess, "transaction_id").select(*ITEM_COLS)
    if source == "mongo":
        # $unwind + $project run inside MongoDB; the discount is pro-rated per item server-side
        pipeline = [
            {"$unwind": "$items"},
            {"$project": {"_id": 0, "transaction_id": "$_id", "user_id": 1, "session_id": 1, "timestamp": 1,
                          "product_id": "$items.product_id", "category_id": "$items.category_id",
                          "subcategory_id": "$items.subcategory_id", "quantity": "$items.quantity",
                          "net_revenue": {"$multiply": ["$items.subtotal",
                                                        {"$subtract": [1, {"$divide": ["$discount", "$subtotal"]}]}]}}},
        ]
        rows = [(d["transaction_id"], d["user_id"], d.get("session_id"), d["timestamp"], d["product_id"],
                 d["category_id"], d["subcategory_id"], int(d["quantity"]), float(d["net_revenue"]))
                for d in _mongo_db().transactions.aggregate(pipeline, allowDiskUse=True)]
        schema = StructType([StructField(c, t) for c, t in zip(ITEM_COLS, [
            StringType(), StringType(), StringType(), TimestampType(), StringType(), StringType(),
            StringType(), LongType(), DoubleType()])])
        return spark.createDataFrame(rows, schema)
    raise ValueError(source)



def _scan_in_ranges(source, table, columns, prefixes, batch_size=200, retries=4):
    """Scan an HBase table as many short row-key RANGE scans instead of one full-table scan.

    A single full scan through the Thrift gateway keeps one scanner open for minutes, which a
    single-node HBase in Docker can stall on (TimeoutError). Short range scans - the access path
    the row-key design is built for - finish quickly, and a failed range is simply retried on a
    fresh connection, so the job is robust. Yields (rowkey, cells).
    """
    import time
    conn = _hbase(source)
    for i, start in enumerate(prefixes):
        stop = prefixes[i + 1] if i + 1 < len(prefixes) else None
        for attempt in range(1, retries + 1):
            try:
                rows = list(conn.table(table).scan(row_start=start.encode(),
                                                   row_stop=stop.encode() if stop else None,
                                                   columns=columns, batch_size=batch_size))
                break
            except Exception as e:  # noqa: BLE001 - Thrift timeout / broken pipe
                if attempt == retries:
                    raise
                print(f"   range {start}: {e.__class__.__name__}, retry {attempt}/{retries - 1}")
                time.sleep(3 * attempt)
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
                conn = _hbase(source)
        for row in rows:
            yield row
        if (i + 1) % 20 == 0:
            print(f"   {table}: {i + 1}/{len(prefixes)} key ranges scanned")


# user ids are user_000000..user_009999 -> 100 ranges of 100 users; products prod_00000..prod_04999
USER_RANGES = [f"user_{i:04d}" for i in range(100)]
PRODUCT_RANGES = [f"prod_{i:03d}" for i in range(50)]


# ------------------------------------------------------------------ session engagement (HBase)
SESSION_SCHEMA = StructType([
    StructField("user_id", StringType()), StructField("session_id", StringType()),
    StructField("start_time", StringType()), StructField("duration_seconds", LongType()),
    StructField("n_pages", LongType()), StructField("device_type", StringType()),
    StructField("referrer", StringType()), StructField("conversion_status", StringType()),
    StructField("has_product_view", BooleanType()), StructField("has_cart", BooleanType()),
    StructField("has_checkout", BooleanType())])


def load_sessions(spark, source="files"):
    """One row per session with engagement & funnel-stage flags."""
    if source == "files":
        s = su.read_clean(spark, "sessions")
        return s.select("user_id", "session_id", F.col("start_time").cast("string"), "duration_seconds",
                        "n_pages", "device_type", "referrer", "conversion_status", "has_product_view",
                        (F.col("n_cart_products") > 0).alias("has_cart"), "has_checkout")
    if source in ("hbase", "hbase-emulator"):
        rows = []
        # info + cart, and pv for the funnel-stage flags, read as 100 user-id key ranges
        for key, c in _scan_in_ranges(source, "user_sessions", [b"info", b"pv", b"cart"], USER_RANGES):
            user_id, _, session_id = key.decode().split("|")
            pages = {_dec(v).split("|", 1)[0] for k, v in c.items() if k.startswith(b"pv:")}
            rows.append((user_id, session_id, _dec(c[b"info:start_time"]), int(c[b"info:duration"]),
                         int(c[b"info:n_pages"]), _dec(c[b"info:device_type"]), _dec(c[b"info:referrer"]),
                         _dec(c[b"info:conversion_status"]), "product_detail" in pages,
                         any(k.startswith(b"cart:") for k in c), "checkout" in pages))
        print(f"   scanned {len(rows):,} session rows from HBase ({source})")
        return spark.createDataFrame(rows, SESSION_SCHEMA)
    raise ValueError(source)


# ------------------------------------------------------------------ product daily metrics (HBase)
def load_product_metrics(spark, source="files"):
    """product_id, date, views, cart_adds."""
    if source == "files":
        pv = (su.read_clean(spark, "page_views").filter("page_type = 'product_detail' AND product_id IS NOT NULL")
              .groupBy("product_id", F.col("view_date").alias("date")).agg(F.count("*").alias("views")))
        ca = (su.read_clean(spark, "cart_items").groupBy("product_id", F.to_date("start_time").alias("date"))
              .agg(F.count("*").alias("cart_adds")))
        return pv.join(ca, ["product_id", "date"], "full").fillna(0, ["views", "cart_adds"])
    if source in ("hbase", "hbase-emulator"):
        rows = []
        for key, c in _scan_in_ranges(source, "product_metrics", [b"m:views", b"m:cart_adds"],
                                      PRODUCT_RANGES, batch_size=2000):
            pid, d = key.decode().split("|")
            rows.append((pid, d, int(c.get(b"m:views", b"0")), int(c.get(b"m:cart_adds", b"0"))))
        print(f"   scanned {len(rows):,} product-day rows from HBase ({source})")
        df = spark.createDataFrame(rows, "product_id string, d string, views long, cart_adds long")
        return df.select("product_id", F.to_date("d", "yyyyMMdd").alias("date"), "views", "cart_adds")
    raise ValueError(source)


def load_margins(spark):
    """Small dimension table (subcategory -> margin, category name) - broadcast in joins."""
    return su.read_clean(spark, "categories")
