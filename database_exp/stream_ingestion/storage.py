"""跨表事务与整批发布；各表的 schema、写入 SQL、导出 SQL 在各自模块。"""

from datetime import timedelta
import json
import os
from pathlib import Path
import shutil
import tempfile

import accounts
import market
import trades

TABLE_MODULES = (market, trades, accounts)


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


def create_tables(db):
    market.create_table(db)
    trades.create_table(db)
    accounts.create_table(db)


def write_tick(db, batch, *, tick, received_at, ingested_at, market_params, trade_params, account_params):
    """各表写入不自行提交，由这里保证三表一起成功或回滚。"""
    context = dict(tick=tick, received_at=received_at, ingested_at=ingested_at)
    db.execute("BEGIN TRANSACTION")
    try:
        counts = {
            market.TABLE_NAME: market.write_records(db, batch.market_records, params=market_params, **context),
            trades.TABLE_NAME: trades.write_records(db, batch.trade_records, params=trade_params, **context),
            accounts.TABLE_NAME: accounts.write_records(db, batch.account_records, params=account_params, **context),
        }
        db.execute("COMMIT")
        return counts
    except BaseException:
        db.execute("ROLLBACK")
        raise


def export_batch(db, root, *, start_tick, end_tick, simulation_start, tick_seconds, export_seconds):
    name = f"batch_{start_tick:06d}_{end_tick:06d}"
    destination = root / name
    if destination.exists():
        raise FileExistsError(f"批次已存在，拒绝覆盖：{destination}")
    staging = Path(tempfile.mkdtemp(prefix=f".{name}-", dir=root))
    transaction_active = False
    try:
        db.execute("BEGIN TRANSACTION")
        transaction_active = True
        counts = {
            module.TABLE_NAME: module.export_parquet(
                db, staging / f"{module.TABLE_NAME}.parquet", start_tick=start_tick, end_tick=end_tick,
            )
            for module in TABLE_MODULES
        }
        db.execute("COMMIT")
        transaction_active = False
        write_json(staging / "manifest.json", {
            "start_tick": start_tick, "end_tick_exclusive": end_tick,
            "start_time": (simulation_start + timedelta(seconds=start_tick * tick_seconds)).isoformat(),
            "end_time_exclusive": (simulation_start + timedelta(seconds=end_tick * tick_seconds)).isoformat(),
            "complete_interval": (end_tick - start_tick) * tick_seconds == export_seconds,
            "rows": counts,
        })
        staging.rename(destination)
        print(f"EXPORT {name}: {counts}", flush=True)
        return name
    except BaseException:
        if transaction_active:
            db.execute("ROLLBACK")
        shutil.rmtree(staging, ignore_errors=True)
        raise
