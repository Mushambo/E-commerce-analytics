"""Shared Spark helpers: session builder and EXPLICIT schemas for the raw JSON files.

Why explicit schemas?  With multiLine JSON, schema inference makes Spark read every file
twice (once to infer, once to load). For the 4 GB of session files that doubles I/O and can
infer wrong types (e.g. a price that happens to be an integer). Declaring the schema is the
single most effective optimisation for this pipeline.
"""
import os
import sys

from pyspark.sql import SparkSession
from pyspark.sql.types import (ArrayType, BooleanType, DoubleType, LongType, MapType, StringType,
                               StructField, StructType)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402


def get_spark(app_name):
    spark = (SparkSession.builder
             .appName(app_name)
             .master(config.SPARK_MASTER)
             .config("spark.driver.memory", config.SPARK_DRIVER_MEMORY)
             # small local cluster -> fewer shuffle partitions than the default 200
             .config("spark.sql.shuffle.partitions", os.getenv("SHUFFLE_PARTITIONS", "16"))
             .config("spark.sql.adaptive.enabled", "true")            # AQE: coalesce/skew handling
             .config("spark.sql.session.timeZone", "UTC")
             .config("spark.sql.parquet.compression.codec", "snappy")
             .getOrCreate())
    spark.sparkContext.setLogLevel(os.getenv("SPARK_LOG_LEVEL", "ERROR"))  # hide harmless WARN noise
    return spark


def clean_path(name):
    return os.path.join(config.CLEAN_DIR, name)


def read_clean(spark, name):
    return spark.read.parquet(clean_path(name))


def save_csv(df, name):
    """Small result sets -> single CSV in output/ (for charts and the report)."""
    path = os.path.join(config.OUTPUT_DIR, f"{name}.csv")
    df.toPandas().to_csv(path, index=False)
    return path


S = StringType()
geo = StructType([StructField("city", S), StructField("state", S), StructField("country", S)])

USERS_SCHEMA = StructType([
    StructField("user_id", S), StructField("geo_data", geo),
    StructField("registration_date", S), StructField("last_active", S)])

CATEGORIES_SCHEMA = StructType([
    StructField("category_id", S), StructField("name", S),
    StructField("subcategories", ArrayType(StructType([
        StructField("subcategory_id", S), StructField("name", S), StructField("profit_margin", DoubleType())])))])

PRODUCTS_SCHEMA = StructType([
    StructField("product_id", S), StructField("name", S), StructField("category_id", S),
    StructField("subcategory_id", S), StructField("base_price", DoubleType()),
    StructField("current_stock", LongType()), StructField("is_active", BooleanType()),
    StructField("price_history", ArrayType(StructType([StructField("price", DoubleType()), StructField("date", S)]))),
    StructField("creation_date", S)])

SESSIONS_SCHEMA = StructType([
    StructField("session_id", S), StructField("user_id", S),
    StructField("start_time", S), StructField("end_time", S), StructField("duration_seconds", LongType()),
    StructField("geo_data", StructType(geo.fields + [StructField("ip_address", S)])),
    StructField("device_profile", StructType([StructField("type", S), StructField("os", S), StructField("browser", S)])),
    StructField("viewed_products", ArrayType(S)),
    StructField("page_views", ArrayType(StructType([
        StructField("timestamp", S), StructField("page_type", S), StructField("product_id", S),
        StructField("category_id", S), StructField("view_duration", LongType())]))),
    # cart_contents is an object whose KEYS are product ids -> a map, not a struct
    StructField("cart_contents", MapType(S, StructType([StructField("quantity", LongType()),
                                                        StructField("price", DoubleType())]))),
    StructField("conversion_status", S), StructField("referrer", S)])

TRANSACTIONS_SCHEMA = StructType([
    StructField("transaction_id", S), StructField("session_id", S), StructField("user_id", S),
    StructField("timestamp", S),
    StructField("items", ArrayType(StructType([
        StructField("product_id", S), StructField("quantity", LongType()),
        StructField("unit_price", DoubleType()), StructField("subtotal", DoubleType())]))),
    StructField("subtotal", DoubleType()), StructField("discount", DoubleType()),
    StructField("total", DoubleType()), StructField("payment_method", S), StructField("status", S)])
