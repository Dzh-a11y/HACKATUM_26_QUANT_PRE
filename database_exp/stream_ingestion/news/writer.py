"""逐条追加 JSONL。"""

import json
import os
from pathlib import Path

from .parser import parse_record


def write_records(path, records, *, tick, received_at, ingested_at, params):
    parsed = [parse_record(raw, tick=tick, received_at=received_at, ingested_at=ingested_at, params=params) for raw in records]
    if not parsed:
        return 0
    with Path(path).open("a", encoding="utf-8", newline="\n") as file:
        for record in parsed:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        file.flush()
        if params.fsync:
            os.fsync(file.fileno())
    return len(parsed)
