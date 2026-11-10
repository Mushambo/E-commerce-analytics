"""Memory-friendly iteration over the generator's JSON-array files."""
import glob
import json
import os

try:
    import ijson  # streaming parser: constant memory even for multi-GB files
except ImportError:  # pragma: no cover
    ijson = None


def iter_json_array(path):
    """Yield the elements of a JSON array file one by one."""
    if ijson is not None:
        with open(path, "rb") as f:
            # use_float=True -> plain floats instead of Decimal (BSON/HBase friendly)
            for obj in ijson.items(f, "item", use_float=True):
                yield obj
    else:
        with open(path) as f:
            for obj in json.load(f):
                yield obj


def session_files(raw_dir):
    """sessions_0.json, sessions_1.json, ... in numeric order."""
    files = glob.glob(os.path.join(raw_dir, "sessions_*.json"))
    return sorted(files, key=lambda p: int(os.path.basename(p).split("_")[1].split(".")[0]))


def iter_sessions(raw_dir, limit=None):
    n = 0
    for path in session_files(raw_dir):
        for s in iter_json_array(path):
            yield s
            n += 1
            if limit and n >= limit:
                return
