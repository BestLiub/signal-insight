"""MySQL 接入：ODS 源库初始化、Parquet 分区、指纹、登记和水印。"""
from pathlib import Path
from datetime import datetime
import hashlib
import json

import pandas as pd

from signal_mysql import database as mysql

from . import config, db


def _now():
    return datetime.now().isoformat(timespec="seconds")


def file_sha1(path):
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def migrate(con):
    con.execute(
        "CREATE TABLE IF NOT EXISTS partition_registry("
        "dt VARCHAR(10) PRIMARY KEY, is_synthetic BIGINT NOT NULL DEFAULT 0, rows_ods BIGINT, "
        "gate_status VARCHAR(32), pipeline_status VARCHAR(32) NOT NULL DEFAULT 'arrived', "
        "config_version VARCHAR(100), run_id VARCHAR(100), updated_at VARCHAR(40), note TEXT"
        ") ENGINE=InnoDB")
    con.execute(
        "CREATE TABLE IF NOT EXISTS ods_load_log("
        "batch_id VARCHAR(100), source_file TEXT, `rows` BIGINT, dates TEXT, "
        "is_synthetic BIGINT, loaded_at VARCHAR(40), file_sha1 CHAR(40)"
        ") ENGINE=InnoDB")
    con.commit()


def init_warehouse(source=None, warehouse=None):
    src = mysql.schema_name(source or config.DB_SCHEMA)
    wh = mysql.schema_name(warehouse or config.WAREHOUSE_SCHEMA)
    mysql.create_schema(wh)
    s = mysql.connect(src)
    w = mysql.connect(wh)
    try:
        for name in mysql.table_names(s, "ods_"):
            if not mysql.table_exists(w, name):
                w.execute(f"CREATE TABLE {mysql.ident(name)} LIKE {mysql.ident(src)}.{mysql.ident(name)}")
                w.commit()
                w.execute(f"INSERT INTO {mysql.ident(name)} SELECT * FROM {mysql.ident(src)}.{mysql.ident(name)}")
                w.commit()
        migrate(w)
        db.ensure_indexes(w)
        known = set(registry(w)["dt"])
        register_arrivals(w, {day: n for day, n in ods_dates(w).items() if day not in known})
    finally:
        s.close()
        w.close()
    return wh


def registry(con):
    migrate(con)
    return mysql.read_frame("SELECT * FROM partition_registry ORDER BY dt", con)


def reg_get(con, dt):
    row = con.execute("SELECT * FROM partition_registry WHERE dt=?", (dt,)).fetchone()
    return dict(row) if row else None


def reg_set(con, dt, **values):
    allowed = {"is_synthetic", "rows_ods", "gate_status", "pipeline_status", "config_version", "run_id", "note"}
    if not set(values) <= allowed:
        raise ValueError("未知登记字段")
    names = ["dt", *values, "updated_at"]
    params = [dt, *values.values(), _now()]
    updates = ",".join(mysql.ident(k) + "=VALUES(" + mysql.ident(k) + ")" for k in names if k != "dt")
    con.execute(
        "INSERT INTO partition_registry(" + ",".join(mysql.ident(k) for k in names)
        + ") VALUES(" + ",".join("?" for _ in names) + ") ON DUPLICATE KEY UPDATE " + updates,
        params)
    con.commit()


def ods_dates(con):
    return (mysql.read_frame(
        "SELECT DATE(FROM_UNIXTIME(timestamp/1000+28800)) AS dt, COUNT(*) AS n FROM ods_signal GROUP BY 1 ORDER BY 1", con)
        .assign(dt=lambda d: d["dt"].astype(str)).set_index("dt")["n"])


def register_arrivals(con, dates_counts=None, is_synthetic=False):
    dates_counts = dates_counts or ods_dates(con).to_dict()
    for dt, n in dates_counts.items():
        cur = reg_get(con, dt)
        if cur is None:
            reg_set(con, dt, rows_ods=int(n), is_synthetic=int(is_synthetic), pipeline_status="pending")
        else:
            status = "stale" if cur["pipeline_status"] in ("done", "blocked") else cur["pipeline_status"]
            reg_set(con, dt, rows_ods=int(cur["rows_ods"] or 0) + int(n), pipeline_status=status,
                    note="收到迟到数据，需要重跑")


def todo(con):
    rows = registry(con)
    return rows.loc[rows["pipeline_status"].isin(["pending", "stale", "failed"]), "dt"].tolist()


def ingest_partition(con, path):
    path = Path(path)
    if path.is_file():
        frame = pd.read_parquet(path)
        meta_path = path.with_suffix(".meta.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        digest = file_sha1(path)
    elif mysql.schema_exists(path):
        # MySQL → MySQL 接入也用于隔离集成测试；Path 只是 schema 的唯一标签。
        source = mysql.connect(mysql.schema_name(path), readonly=True)
        try:
            frame = mysql.read_frame("SELECT * FROM ods_signal", source)
            row = source.execute("SELECT value FROM _meta WHERE `key`='synthetic'").fetchone() if mysql.table_exists(source, "_meta") else None
            meta = {"is_synthetic": bool(row and str(row[0]) == "1")}
        finally:
            source.close()
        digest = hashlib.sha1(pd.util.hash_pandas_object(frame, index=False).values.tobytes()).hexdigest()
    else:
        raise FileNotFoundError(path.name)
    try:
        migrate(con)
        expected = [r[1] for r in mysql.columns(con, "ods_signal")]
        if set(frame.columns) != set(expected):
            raise ValueError("分区列与 MySQL ODS 不一致")
        if con.execute("SELECT 1 FROM ods_load_log WHERE file_sha1=?", (digest,)).fetchone():
            return pd.Series(dtype="int64")
        frame = frame[expected]
        days = (pd.to_datetime(frame["timestamp"], unit="ms") + pd.Timedelta(hours=8)).dt.strftime("%Y-%m-%d").value_counts().sort_index()
        synthetic = bool(meta.get("is_synthetic", False))
        if synthetic:
            for day in days.index:
                existing = reg_get(con, day)
                if existing and not existing["is_synthetic"]:
                    raise ValueError("模拟分区不能落入已有真实日期")
        # 入库追加和登记日志同一事务；DDL 已在 migrate 阶段完成。
        try:
            mysql.write_frame(frame, "ods_signal", con, if_exists="append", index=False)
            con.execute(
                "INSERT INTO ods_load_log(batch_id, source_file, `rows`, dates, is_synthetic, loaded_at, file_sha1) "
                "VALUES(?,?,?,?,?,?,?)",
                (_now(), path.name, len(frame), json.dumps(meta.get("dates", [])),
                 int(meta.get("is_synthetic", False)), _now(), digest))
            con.commit()
        except Exception:
            con.rollback()
            raise
        register_arrivals(con, days.to_dict(), synthetic)
        return days
    finally:
        con.rollback()


STATUS_ZH = {"arrived": "已到达", "done": "完成", "blocked": "门禁拦截", "failed": "失败", "stale": "待重跑"}
