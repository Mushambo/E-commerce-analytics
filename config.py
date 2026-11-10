"""Central configuration. Every value can be overridden with an environment variable."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

RAW_DIR = os.getenv("RAW_DIR", os.path.join(ROOT, "data", "raw"))          # generator output
CLEAN_DIR = os.getenv("CLEAN_DIR", os.path.join(ROOT, "data", "clean"))    # Spark parquet output
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(ROOT, "output"))        # analysis results (csv)
FIG_DIR = os.getenv("FIG_DIR", os.path.join(ROOT, "report", "figures"))   # charts

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "ecommerce")

HBASE_HOST = os.getenv("HBASE_HOST", "localhost")
HBASE_PORT = int(os.getenv("HBASE_PORT", "9090"))   # HBase Thrift server port
# When no HBase server is available, scripts can use a local SQLite-backed emulator
HBASE_EMULATOR_DB = os.getenv("HBASE_EMULATOR_DB", os.path.join(ROOT, "data", "hbase_emulator.sqlite"))

SPARK_MASTER = os.getenv("SPARK_MASTER", "local[*]")
SPARK_DRIVER_MEMORY = os.getenv("SPARK_DRIVER_MEMORY", "4g")

for d in (CLEAN_DIR, OUTPUT_DIR, FIG_DIR):
    os.makedirs(d, exist_ok=True)
