"""导出对外版生产库（D14）：只导出 ads_ 和 dim_ 表，抑制已经在生成时做完。

    python tools/export_ads.py [输出路径]
默认写到 data/export/signal_public.db（不进 Git）。平台/Docker 只读这个库，不接触明细。
"""
import sqlite3
import sys
from pathlib import Path

from signal_mysql import database as mysql

from signal_insight import config


def main(argv=None):
    argv = argv or sys.argv[1:]
    out = Path(argv[0]) if argv else config.PROJECT_ROOT / "data" / "export" / "signal_public.db"
    out.parent.mkdir(parents=True, exist_ok=True)
    with mysql.connect(config.WAREHOUSE_SCHEMA, readonly=True) as con:
        names = [t for t in mysql.table_names(con) if t.startswith(("ads_", "dim_"))]
        with sqlite3.connect(out) as sq:
            for t in names:
                df = mysql.read_frame(f"SELECT * FROM {t}", con)
                df.to_sql(t, sq, if_exists="replace", index=False)
                print(f"{t}: {len(df):,} 行")
    print("已导出：", out)
    return out


if __name__ == "__main__":
    main()
