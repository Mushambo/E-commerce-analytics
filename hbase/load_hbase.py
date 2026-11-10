"""
load_hbase.py - load session click-stream into `user_sessions` and daily product
performance into `product_metrics` (schema: create_tables.hbase).

    python hbase/load_hbase.py                       # real HBase via Thrift (HBASE_HOST:9090)
    python hbase/load_hbase.py --limit 200000        # subset of sessions
    python hbase/load_hbase.py --emulate             # SQLite emulator, no server needed
"""
import argparse
import datetime as dt
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from common.json_stream import iter_json_array, iter_sessions  # noqa: E402
from hbase_client import ensure_tables, get_connection, product_rowkey, session_rowkey  # noqa: E402


def epoch_ms(iso):
    return int(dt.datetime.fromisoformat(iso).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def day(iso):
    return iso[:10].replace("-", "")


def b(x):
    return b"" if x is None else str(x).encode()


def session_cells(s):
    """Convert one session JSON document into HBase cells {b'cf:qualifier': b'value'}."""
    dev, geo = s["device_profile"], s["geo_data"]
    cells = {
        b"info:session_id": b(s["session_id"]),
        b"info:start_time": b(s["start_time"]),
        b"info:end_time": b(s["end_time"]),
        b"info:duration": b(s["duration_seconds"]),
        b"info:device_type": b(dev["type"]), b"info:os": b(dev["os"]), b"info:browser": b(dev["browser"]),
        b"info:city": b(geo["city"]), b"info:state": b(geo["state"]),
        b"info:country": b(geo["country"]), b"info:ip": b(geo["ip_address"]),
        b"info:referrer": b(s["referrer"]),
        b"info:conversion_status": b(s["conversion_status"]),
        b"info:n_pages": b(len(s["page_views"])),
        b"info:viewed_products": b(",".join(s["viewed_products"])),
    }
    for i, pv in enumerate(s["page_views"]):     # sparse, variable number of columns
        cells[f"pv:{i:03d}".encode()] = "|".join(
            str(x or "") for x in (pv["page_type"], pv["product_id"], pv["category_id"],
                                   pv["view_duration"], pv["timestamp"])).encode()
    for pid, c in s["cart_contents"].items():
        cells[f"cart:{pid}".encode()] = f"{c['quantity']}|{c['price']}".encode()
    return cells


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=config.RAW_DIR)
    ap.add_argument("--limit", type=int, default=None, help="max sessions to load")
    ap.add_argument("--emulate", action="store_true")
    ap.add_argument("--recreate", action="store_true", help="drop & recreate tables first")
    a = ap.parse_args()

    conn = get_connection(a.emulate)
    ensure_tables(conn, recreate=a.recreate)
    sessions_t = conn.table("user_sessions")
    metrics_t = conn.table("product_metrics")

    # product -> day -> metric accumulators (pre-aggregation is far cheaper than
    # one RPC/increment per event during a bulk load)
    metrics = defaultdict(lambda: defaultdict(int))
    t0, n = time.time(), 0
    with sessions_t.batch(batch_size=2000) as batch:
        for s in iter_sessions(a.raw, a.limit):
            batch.put(session_rowkey(s["user_id"], epoch_ms(s["start_time"]), s["session_id"]), session_cells(s))
            for pv in s["page_views"]:
                if pv["page_type"] == "product_detail" and pv["product_id"]:
                    metrics[(pv["product_id"], day(pv["timestamp"]))]["views"] += 1
            for pid in s["cart_contents"]:
                metrics[(pid, day(s["start_time"]))]["cart_adds"] += 1
            n += 1
            if n % 50000 == 0:
                print(f"  {n:,} sessions ({time.time() - t0:.0f}s)")
    print(f"user_sessions: {n:,} rows loaded in {time.time() - t0:.0f}s")

    for t in iter_json_array(os.path.join(a.raw, "transactions.json")):
        for it in t["items"]:
            m = metrics[(it["product_id"], day(t["timestamp"]))]
            m["purchases"] += 1
            m["units_sold"] += it["quantity"]
            m["revenue_cents"] += int(round(it["subtotal"] * 100))

    with metrics_t.batch(batch_size=5000) as batch:
        for (pid, d), m in metrics.items():
            batch.put(product_rowkey(pid, d), {f"m:{k}".encode(): b(v) for k, v in m.items()})
    print(f"product_metrics: {len(metrics):,} product-day rows loaded ({time.time() - t0:.0f}s total)")


if __name__ == "__main__":
    main()
