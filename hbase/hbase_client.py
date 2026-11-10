"""
hbase_client.py - connection factory + row-key helpers shared by the HBase scripts.

Two back-ends with the SAME interface (subset of happybase):
  * real HBase via the Thrift server (happybase)           -> default
  * a tiny SQLite-backed emulator (`--emulate` / HBASE_EMULATE=1) that keeps rows sorted
    by key exactly like HBase does, so row-key design, prefix scans and range scans can be
    demonstrated on a laptop without Docker. It is NOT a replacement for HBase (no regions,
    no versions, no compression) - it only exists to make the query logic testable.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

MAX_TS = 9_999_999_999_999   # 13-digit ceiling for reverse timestamps (ms)
SEP = "|"


# ----------------------------------------------------------------- row keys
def reverse_ts(epoch_ms: int) -> str:
    return f"{MAX_TS - epoch_ms:013d}"


def session_rowkey(user_id, start_epoch_ms, session_id) -> bytes:
    return f"{user_id}{SEP}{reverse_ts(start_epoch_ms)}{SEP}{session_id}".encode()


def user_time_range(user_id, from_ms, to_ms):
    """(row_start, row_stop) covering sessions that started in [from_ms, to_ms).
    Because the timestamp is reversed, the NEWER bound gives the START row."""
    start = f"{user_id}{SEP}{reverse_ts(to_ms - 1)}".encode()
    stop = f"{user_id}{SEP}{reverse_ts(from_ms)}~".encode()   # '~' sorts after '|' and digits
    return start, stop


def product_rowkey(product_id, yyyymmdd) -> bytes:
    return f"{product_id}{SEP}{yyyymmdd}".encode()


# ----------------------------------------------------------------- emulator
class _EmuBatch:
    def __init__(self, table, batch_size=10000):
        self.t, self.buf, self.n = table, [], batch_size

    def put(self, row, data):
        self.buf.extend((self.t.name, row, c, v) for c, v in data.items())
        if len(self.buf) >= self.n:
            self.send()

    def send(self):
        self.t.conn.db.executemany("INSERT OR REPLACE INTO cells VALUES (?,?,?,?)", self.buf)
        self.t.conn.db.commit()
        self.buf = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.send()


class _EmuTable:
    def __init__(self, conn, name):
        self.conn, self.name = conn, name

    def put(self, row, data):
        with self.batch() as b:
            b.put(row, data)

    def batch(self, batch_size=10000):
        return _EmuBatch(self, batch_size)

    def row(self, row, columns=None):
        return next((d for _, d in self.scan(row_start=row, row_stop=row + b"\x00", columns=columns)), {})

    def counter_inc(self, row, column, value=1):
        cur = int(self.row(row, [column]).get(column, b"0"))
        self.put(row, {column: str(cur + value).encode()})
        return cur + value

    def scan(self, row_start=None, row_stop=None, row_prefix=None, columns=None, limit=None, **_ignored):
        if row_prefix is not None:
            row_start, row_stop = row_prefix, row_prefix + b"\xff"
        q, p = "SELECT row, col, val FROM cells WHERE tbl=?", [self.name]
        if row_start is not None:
            q += " AND row>=?"; p.append(row_start)
        if row_stop is not None:
            q += " AND row<?"; p.append(row_stop)
        q += " ORDER BY row, col"
        # columns like happybase: b"info" (whole family) or b"info:start_time" (one column)
        wanted = [f.rstrip(b":") for f in (columns or [])]

        def keep(col):
            return not wanted or any(col == f or (b":" not in f and col.startswith(f + b":")) for f in wanted)

        cur_row, cur, emitted = None, {}, 0
        for r, c, v in self.conn.db.execute(q, p):
            if not keep(c):
                continue
            if r != cur_row:
                if cur_row is not None:
                    yield cur_row, cur
                    emitted += 1
                    if limit and emitted >= limit:
                        return
                cur_row, cur = r, {}
            cur[c] = v
        if cur_row is not None and (not limit or emitted < limit):
            yield cur_row, cur


class EmulatedConnection:
    def __init__(self, path=config.HBASE_EMULATOR_DB):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS cells (tbl TEXT, row BLOB, col BLOB, val BLOB,"
                        " PRIMARY KEY (tbl, row, col)) WITHOUT ROWID")
        self.db.execute("CREATE TABLE IF NOT EXISTS meta (tbl TEXT PRIMARY KEY, families TEXT)")

    def tables(self):
        return [r[0].encode() for r in self.db.execute("SELECT tbl FROM meta")]

    def create_table(self, name, families):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (name, ",".join(families)))
        self.db.commit()

    def delete_table(self, name, disable=True):
        self.db.execute("DELETE FROM cells WHERE tbl=?", (name,))
        self.db.execute("DELETE FROM meta WHERE tbl=?", (name,))
        self.db.commit()

    def table(self, name):
        return _EmuTable(self, name if isinstance(name, str) else name.decode())


def get_connection(emulate=None):
    emulate = emulate if emulate is not None else os.getenv("HBASE_EMULATE") == "1"
    if emulate:
        return EmulatedConnection()
    import happybase
    # generous socket timeout: full-table scans of a busy single-node HBase can be slow
    return happybase.Connection(config.HBASE_HOST, port=config.HBASE_PORT,
                                timeout=int(os.getenv("HBASE_TIMEOUT_MS", "300000")))


# Families must match create_tables.hbase
TABLES = {
    "user_sessions": {"info": dict(max_versions=1, bloom_filter_type="ROW"),
                      "pv": dict(max_versions=1, time_to_live=15552000),
                      "cart": dict(max_versions=1)},
    "product_metrics": {"m": dict(max_versions=1, bloom_filter_type="ROW")},
}


def ensure_tables(conn, recreate=False):
    existing = {t.decode() for t in conn.tables()}
    for name, fams in TABLES.items():
        if name in existing and recreate:
            conn.delete_table(name, disable=True)
            existing.discard(name)
        if name not in existing:
            conn.create_table(name, fams)
            print(f"  created table {name} families={list(fams)}")
