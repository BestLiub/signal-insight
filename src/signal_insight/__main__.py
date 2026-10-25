"""命令行入口：python -m signal_insight <命令>（D11）。

    python -m signal_insight init                 建生产库：从 signal.db 复制 ODS，生成维表
    python -m signal_insight ingest data/landing/x.db        把一个上游分区文件并进生产库
    python -m signal_insight run --date 2018-10-03           在生产库上跑一天（可以给多个日期）
    python -m signal_insight run --todo                      跑所有待处理、待重跑、出错的日期（D12；定时任务就调它）
    python -m signal_insight run --start 2018-10-01 --end 2018-10-06   回填一段日期（D12）
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
    """分区登记表（D12）：每个日期的数据量、门禁结论、流水线状态、配置版本、备注。"""
    r = ingest.registry(con)
    r["status"] = r["pipeline_status"].map(ingest.STATUS_ZH)
    r["模拟"] = r["is_synthetic"].map({1: "是", 0: ""})
    return r[["dt", "模拟", "rows_ods", "gate_status", "status", "config_version", "note"]].rename(
        columns={"dt": "日期", "rows_ods": "ODS 行数", "gate_status": "门禁", "config_version": "配置版本",
                 "note": "备注"}).fillna("")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="signal_insight", description="信令客流洞察：生产库的流水线")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="建生产库（从 signal.db 复制 ODS）并生成维表")
    p = sub.add_parser("ingest", help="把一个上游分区文件并进生产库")
    p.add_argument("file")
    p = sub.add_parser("run", help="在生产库上跑一天、几天、一段（回填）或全部待处理的日期")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", nargs="+", help="一个或多个日期，形如 2018-10-03")
    g.add_argument("--todo", action="store_true", help="所有待处理、待重跑、出错的日期")
    g.add_argument("--start", help="回填的起始日期（配合 --end）")
    p.add_argument("--end", help="回填的结束日期（含）")
    sub.add_parser("status", help="生产库里每天的数据和处理情况")
    p = sub.add_parser("report", help="生成 Word 报告：数据质量评估 / 数据清洗与加工说明 / 图表包")
    p.add_argument("kind", nargs="?", choices=["quality", "cleaning", "pack"], default="quality")
    p.add_argument("--start", help="质量报告：起始日期")
    p.add_argument("--end", help="质量报告：结束日期（含）")
    p.add_argument("--date", help="清洗报告 / 图表包：分析日")
    p.add_argument("--no-sensitivity", action="store_true", help="清洗报告：不跑敏感性分析")
    p = sub.add_parser("pack", help="图表包：某一天的图、关键数字、报告骨架（D15）")
    p.add_argument("--date", default=config.ANALYSIS_DAY)
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
        if args.cmd == "pack":
            from .report.pack import build_figure_pack
            print("已生成：", build_figure_pack(settings, args.date))
        elif args.cmd in ("init", "dims"):
            pipeline.refresh_dims(con, settings)
            print("维表已生成：dim_cell、dim_hotspot、dim_metric")
        elif args.cmd == "ingest":
            dates = ingest.ingest_partition(con, args.file)
            print("入库：" + "，".join(f"{d} {n:,} 行" for d, n in dates.items()))
        elif args.cmd == "report":
            if args.kind == "quality":
                from .report.quality import build_quality_report
                out = build_quality_report(settings, start=args.start, end=args.end)
            elif args.kind == "cleaning":
                if not args.date:
                    ap.error("report cleaning 需要 --date")
                from .report.cleaning import build_cleaning_report
                out = build_cleaning_report(settings, args.date, with_sensitivity=not args.no_sensitivity)
            else:
                if not args.date:
                    ap.error("report pack 需要 --date")
                from .report.pack import build_figure_pack
                out = build_figure_pack(settings, args.date)
            print("已生成：", out)
        elif args.cmd == "run":
            if args.date:
                dates = args.date
            elif args.todo:
                dates = ingest.todo(con)
            else:
                if not args.end:
                    ap.error("--start 需要配合 --end")
                dates = [d.strftime("%Y-%m-%d") for d in pd.date_range(args.start, args.end)]
            if not dates:
                print("没有需要处理的日期")
            res = pipeline.run_dates(con, settings, dates)
            for dt, st in res.items():
                print(f"{dt}：{ingest.STATUS_ZH.get(st, st)}")
            if any(str(v).startswith("failed") for v in res.values()):
                print(status(con).to_string(index=False))
                return 1
        if args.cmd in ("init", "status", "ingest", "run"):
            print(status(con).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
