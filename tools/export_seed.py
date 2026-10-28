"""导出给 Docker 演示用的最小数据集（D14 之后）。

平台只读 ads_ 与 dim_，所以这里也只导这些表：聚合结果已经做过小样本抑制，
不含任何可识别到个人的信息。原始明细、dws_ 表一概不导。

    python tools/export_seed.py                 # 写到 deploy/db/
    python tools/export_seed.py --dates 2018-10-03

生成两个文件，由 MySQL 容器启动时按文件名顺序自动执行：
    01-schema.sql   建库、建表
    02-data.sql     数据
"""
import argparse

import pandas as pd
from pathlib import Path

from signal_mysql import database as mysql

from signal_insight import config

# 平台用到的表；dim_cell（4.9 万行）与边界表平台不读，不导
DIM_TABLES = ["dim_area", "dim_metric", "dim_hotspot"]
ADS_TABLES = ["ads_area_daily", "ads_area_hourly", "ads_area_segment", "ads_area_radius", "ads_area_origin",
              "ads_area_linkage", "ads_hex_hourly", "ads_od_district",
              "ads_dq_partition", "ads_dq_rule", "ads_dq_clean_steps"]
BATCH = 200


def q(name):
    return "`" + name + "`"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", nargs="+", default=["2018-10-03", "2018-10-04", "2018-10-05", "2018-10-06"])
    ap.add_argument("--out", type=Path, default=config.PROJECT_ROOT / "deploy" / "db")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    schema, data = [], ["-- 平台只读聚合表，已做小样本抑制，不含个人信息",
                        "SET NAMES utf8mb4;", "USE `signal_warehouse`;"]

    with mysql.connect(config.WAREHOUSE_SCHEMA, readonly=True) as con:
        raw = con.sa.connection.dbapi_connection
        cursor = raw.cursor()
        # 会话默认开了 ANSI_QUOTES，SHOW CREATE TABLE 会把标识符输出成双引号；
        # 目标库没有这个模式，导出的 DDL 会语法错误。这里临时关掉。
        cursor.execute("SET SESSION sql_mode='STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'")
        for t in DIM_TABLES + ADS_TABLES:
            cursor.execute(f"SHOW CREATE TABLE {q(t)}")
            row = cursor.fetchone()
            schema.append(f"\n-- {t}\nDROP TABLE IF EXISTS {q(t)};\n{row[1]};")

            cols = [r[1] for r in mysql.column_result(con, t)]
            where, params = "", []
            if "dt" in cols:
                where = " WHERE dt IN (" + ",".join(["?"] * len(args.dates)) + ")"
                params = list(args.dates)
            frame = mysql.read_frame(f"SELECT * FROM {q(t)}{where}", con, params=params)
            if frame.empty:
                continue
            head = f"INSERT INTO {q(t)} (" + ", ".join(q(c) for c in cols) + ") VALUES "
            for i in range(0, len(frame), BATCH):
                chunk = frame.iloc[i:i + BATCH].itertuples(index=False, name=None)
                values = [cursor.mogrify("(" + ",".join(["%s"] * len(cols)) + ")",
                                         tuple(None if pd.isna(v) else v for v in row))
                          for row in chunk]
                values = [v.decode("utf-8") if isinstance(v, bytes) else v for v in values]
                data.append(head + ",\n".join(values) + ";")
            print(f"{t:22s} {len(frame):>7,} 行")

    (out / "01-schema.sql").write_text(
        "SET NAMES utf8mb4;\n"
        "CREATE DATABASE IF NOT EXISTS `signal_warehouse` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;\n"
        "USE `signal_warehouse`;\n" + "\n".join(schema) + "\n", encoding="utf-8")
    (out / "02-data.sql").write_text("\n".join(data) + "\n", encoding="utf-8")

    for f in sorted(out.glob("*.sql")):
        print(f"写出 {f.name}: {f.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
