"""命令行入口：python -m signal_insight <命令>（D11）。

    python -m signal_insight init                 建生产库：从 signal.db 复制 ODS，生成维表
    python -m signal_insight ingest data/landing/x.parquet   把一个上游分区文件并进生产库
    python -m signal_insight run --date 2018-10-03           在生产库上跑一天（可以给多个日期）
    python -m signal_insight status               看生产库里每天的数据和处理情况
    python -m signal_insight dims                 改了热点或口径参数后重建维表

为什么要命令行：定时任务、同事、服务器都不会打开 notebook。命令行是这个系统对外的“按钮”。
"""
import argparse
import sys
from contextlib import closing

import pandas as pd

from signal_mysql import database as mysql

from . import config, db, ingest, pipeline


def status(con) -> pd.DataFrame:
    """每个日期：ODS 有多少行、明细和停留各有多少行、最近一次是什么时候用哪版配置跑的。"""
    out = ingest.ods_dates(con).rename("ODS 行数").to_frame()
    for table, name in [("dwd_signal", "明细行数"), ("dws_stay", "停留数")]:
        if db.table_exists(con, table):
            out[name] = mysql.read_frame(
                f"SELECT dt, COUNT(*) AS n FROM {table} GROUP BY dt", con).set_index("dt")["n"]
    if db.table_exists(con, "etl_log"):
        last = mysql.read_frame(
            "SELECT dt, MAX(run_at) AS 最近运行, MAX(config_version) AS 配置版本 FROM etl_log GROUP BY 1", con)
        out = out.join(last.set_index("dt"))
    return out.fillna({"明细行数": 0, "停留数": 0}).reset_index().rename(columns={"index": "日期", "dt": "日期"})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="signal_insight", description="信令客流洞察：生产库的流水线")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="建生产库（从 signal.db 复制 ODS）并生成维表")
    p = sub.add_parser("ingest", help="把一个上游分区文件并进生产库")
    p.add_argument("file")
    p = sub.add_parser("run", help="在生产库上跑一天或几天")
    p.add_argument("--date", nargs="+", required=True, help="一个或多个日期，形如 2018-10-03")
    sub.add_parser("status", help="生产库里每天的数据和处理情况")
    sub.add_parser("dims", help="重建维表（改了热点或口径参数之后）")
    args = ap.parse_args(argv)

    settings = config.load_settings()
    print(f"配置版本 {config.config_hash(settings)}")
    if args.cmd == "init":
        ingest.init_warehouse()
    if not mysql.schema_exists(config.WAREHOUSE_SCHEMA):
        print("还没有生产库：先运行 python -m signal_insight init", file=sys.stderr)
        return 1
    with closing(db.connect(config.WAREHOUSE_SCHEMA)) as con:
        if args.cmd in ("init", "dims"):
            pipeline.refresh_dims(con, settings)
            print("维表已生成：dim_cell、dim_hotspot、dim_metric")
        elif args.cmd == "ingest":
            dates = ingest.ingest_partition(con, args.file)
            print("入库：" + "，".join(f"{d} {n:,} 行" for d, n in dates.items()))
        elif args.cmd == "run":
            run_id = pipeline.new_run_id()
            for dt in args.date:
                log = pipeline.run_partition(con, settings, dt, run_id)
                print(f"{dt}：{len(log)} 步，共 {log['elapsed_sec'].sum():.1f} 秒")
        if args.cmd in ("init", "status", "ingest", "run"):
            print(status(con).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
