"""
query_hbase.py - example access patterns enabled by the row-key design.

  Q1  latest N sessions of a user               -> prefix scan, info family only
  Q2  a user's sessions in a time window         -> bounded range scan (reverse timestamp)
  Q3  full click-stream of one session           -> single-row get (pv + cart families)
  Q4  user engagement summary                    -> prefix scan + client-side aggregation
  Q5  product view->purchase conversion by period -> range scan on product_metrics

    python hbase/query_hbase.py --user user_000042 --product prod_00123
    python hbase/query_hbase.py --emulate --user user_000042 --from 2026-09-01 --to 2026-10-01
"""
import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hbase_client import get_connection, user_time_range  # noqa: E402


def ms(date_str):
    return int(dt.datetime.fromisoformat(date_str).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def d(cells, col):
    return cells.get(col, b"").decode()


def q1_latest_sessions(t, user, n=5):
    print(f"\nQ1  latest {n} sessions of {user}  (scan row_prefix='{user}|', columns=info)")
    rows = list(t.scan(row_prefix=f"{user}|".encode(), columns=[b"info"], limit=n))
    for key, c in rows:
        print(f"   {key.decode():<45} {d(c, b'info:start_time')[:19]}  {d(c, b'info:duration'):>5}s  "
              f"{d(c, b'info:device_type'):<7} {d(c, b'info:referrer'):<13} {d(c, b'info:conversion_status')}")
    return rows


def q2_time_window(t, user, start, end):
    row_start, row_stop = user_time_range(user, ms(start), ms(end))
    print(f"\nQ2  {user} sessions in [{start}, {end})\n    STARTROW={row_start.decode()}  STOPROW={row_stop.decode()}")
    rows = list(t.scan(row_start=row_start, row_stop=row_stop, columns=[b"info:start_time", b"info:conversion_status"]))
    for key, c in rows:
        print(f"   {d(c, b'info:start_time')[:19]}  {d(c, b'info:conversion_status')}")
    print(f"    -> {len(rows)} sessions")
    return rows


def q3_session_detail(t, rowkey):
    print(f"\nQ3  click-stream of {rowkey.decode()}  (get row, families pv + cart)")
    c = t.row(rowkey, columns=[b"pv", b"cart"])
    for col in sorted(k for k in c if k.startswith(b"pv:")):
        ptype, pid, cat, dur, ts = c[col].decode().split("|")
        print(f"   {col.decode()}  {ts[11:19]}  {ptype:<17} {pid or '-':<11} {cat or '-':<8} {dur:>5}s")
    for col in sorted(k for k in c if k.startswith(b"cart:")):
        qty, price = c[col].decode().split("|")
        print(f"   {col.decode():<16} qty={qty} price={price}")


def q4_user_summary(t, user):
    rows = list(t.scan(row_prefix=f"{user}|".encode(),
                       columns=[b"info:duration", b"info:conversion_status", b"info:n_pages", b"info:device_type"]))
    if not rows:
        print(f"\nQ4  no sessions for {user}")
        return None
    n = len(rows)
    conv = sum(d(c, b"info:conversion_status") == "converted" for _, c in rows)
    avg_dur = sum(int(d(c, b"info:duration")) for _, c in rows) / n
    avg_pages = sum(int(d(c, b"info:n_pages")) for _, c in rows) / n
    print(f"\nQ4  engagement of {user}: sessions={n} converted={conv} ({conv / n:.0%}) "
          f"avg_duration={avg_dur:.0f}s avg_pages={avg_pages:.1f}")
    return {"sessions": n, "converted": conv, "avg_duration": avg_dur, "avg_pages": avg_pages}


def q5_product_conversion(t, product, start, end):
    s, e = start.replace("-", ""), end.replace("-", "")
    print(f"\nQ5  {product} daily metrics {start}..{end}  (scan {product}|{s} -> {product}|{e})")
    tot = {"views": 0, "cart_adds": 0, "purchases": 0, "units_sold": 0, "revenue_cents": 0}
    for key, c in t.scan(row_start=f"{product}|{s}".encode(), row_stop=f"{product}|{e}".encode()):
        vals = {k: int(d(c, f"m:{k}".encode()) or 0) for k in tot}
        for k in tot:
            tot[k] += vals[k]
        print(f"   {key.decode()}  views={vals['views']:>3} cart_adds={vals['cart_adds']:>2} "
              f"purchases={vals['purchases']:>2} revenue=${vals['revenue_cents'] / 100:,.2f}")
    rate = tot["purchases"] / tot["views"] if tot["views"] else 0
    print(f"    TOTAL views={tot['views']} purchases={tot['purchases']} "
          f"view->purchase={rate:.1%} revenue=${tot['revenue_cents'] / 100:,.2f}")
    return tot


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--emulate", action="store_true")
    ap.add_argument("--user", default="user_000042")
    ap.add_argument("--product", default="prod_00123")
    ap.add_argument("--from", dest="start", default="2026-09-01")
    ap.add_argument("--to", dest="end", default="2026-10-01")
    a = ap.parse_args()
    conn = get_connection(a.emulate)
    sessions = conn.table("user_sessions")
    latest = q1_latest_sessions(sessions, a.user)
    q2_time_window(sessions, a.user, a.start, a.end)
    if latest:
        q3_session_detail(sessions, latest[0][0])
    q4_user_summary(sessions, a.user)
    q5_product_conversion(conn.table("product_metrics"), a.product, a.start, a.end)
