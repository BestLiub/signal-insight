"""一次性：把讲师发的 signal.db (SQLite) 搬进 MySQL signal_insight。"""
import sqlite3, sys
from pathlib import Path
import pandas as pd
from signal_mysql import database as mysql
SQLITE_PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "data/signal.db")
SCHEMA = "signal_insight"
if not SQLITE_PATH.exists():
    raise SystemExit(f"找不到文件: {SQLITE_PATH.resolve()}")
mysql.create_schema(SCHEMA)
src = sqlite3.connect(SQLITE_PATH)
dst = mysql.connect(SCHEMA)
tables = pd.read_sql(
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ods_%' "
    "ORDER BY name",
    src,
)["name"].tolist()
print(f"从 {SQLITE_PATH} 读到 {len(tables)} 张 ODS 表: {tables}")
for t in tables:
    df = pd.read_sql(f"SELECT * FROM {t}", src)
    mysql.write_frame(df, t, dst, if_exists="replace", index=False)
    dst.commit()
    n_mysql = dst.execute(f"SELECT COUNT(*) FROM {mysql.ident(t)}").fetchone()[0]
    status = "OK" if n_mysql == len(df) else "FAIL"
    print(f"  [{status}] {t}: SQLite {len(df):>7} -> MySQL {n_mysql:>7}")
src.close(); dst.close()
print("\n迁移完成")