"""生成明确标注的模拟分区（Parquet + .meta.json）；生产数仓仍是 MySQL。

改编自讲师版：源数据限定为分析日一整天（默认 10-03），可以按小时切分，
这样生成的模拟分区能通过 D12 的门禁，也能模拟“0–13 点缺失 + 补传”。

    python tools/make_landing.py --day 2018-10-05 --out data/landing/ods_signal_2018-10-05.parquet
    python tools/make_landing.py --day 2018-10-06 --hours 14-23 --out .../ods_signal_2018-10-06.parquet
    python tools/make_landing.py --day 2018-10-06 --hours 0-13  --out .../ods_signal_2018-10-06_补传.parquet
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from signal_mysql import database as mysql

from signal_insight import config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True, help="目标日期，必须是专门的模拟日期")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--source-day", default=config.ANALYSIS_DAY, help="从哪一天的真实信令取样")
    ap.add_argument("--hours", default="0-23", help="保留的本地小时，形如 14-23 或 0-13")
    args = ap.parse_args()

    h0, h1 = (int(x) for x in args.hours.split("-"))
    con = mysql.connect(config.DB_SCHEMA, readonly=True)
    try:
        raw = mysql.read_frame("SELECT * FROM ods_signal", con)
    finally:
        con.close()

    local = pd.to_datetime(raw["timestamp"], unit="ms") + pd.Timedelta(hours=config.UTC_OFFSET_HOURS)
    raw = raw[(local.dt.strftime("%Y-%m-%d") == args.source_day) & local.dt.hour.between(h0, h1)].copy()
    if raw.empty:
        raise SystemExit(f"{args.source_day} {h0}-{h1} 点没有信令")

    local = pd.to_datetime(raw["timestamp"], unit="ms") + pd.Timedelta(hours=config.UTC_OFFSET_HOURS)
    shift = (pd.Timestamp(args.day) + pd.Timedelta(hours=h0) - local.min()).total_seconds() * 1000
    for col in ["timestamp", "timestamp1"]:
        raw[col] = raw[col] + int(shift)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(args.out, index=False)
    args.out.with_suffix(".meta.json").write_text(
        json.dumps({"is_synthetic": True, "dates": [args.day], "hours": args.hours}, ensure_ascii=False),
        encoding="utf-8")
    print(f"模拟分区已生成：{args.day} {args.hours} 点，{len(raw):,} 行")


if __name__ == "__main__":
    main()
