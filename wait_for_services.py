"""wait_for_services.py - block until MongoDB and the HBase Thrift server accept connections.
HBase needs 30-90 s after `docker compose up` before Thrift answers; running the loaders earlier
fails with TTransportException.   python wait_for_services.py [--timeout 300]
"""
import argparse
import sys
import time

import config

ap = argparse.ArgumentParser()
ap.add_argument("--timeout", type=int, default=300)
a = ap.parse_args()
deadline = time.time() + a.timeout


def wait(name, check):
    while True:
        try:
            check()
            print(f"  {name}: ready")
            return
        except Exception as e:  # noqa: BLE001
            if time.time() > deadline:
                sys.exit(f"  {name}: NOT reachable after {a.timeout}s ({e.__class__.__name__}: {e})")
            print(f"  {name}: waiting ({e.__class__.__name__})")
            time.sleep(5)


def mongo():
    from pymongo import MongoClient
    MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=3000).admin.command("ping")


def hbase():
    import happybase
    c = happybase.Connection(config.HBASE_HOST, port=config.HBASE_PORT, timeout=5000)
    c.tables()
    c.close()


print(f"Checking MongoDB ({config.MONGO_URI}) and HBase Thrift ({config.HBASE_HOST}:{config.HBASE_PORT})")
wait("MongoDB", mongo)
wait("HBase", hbase)
