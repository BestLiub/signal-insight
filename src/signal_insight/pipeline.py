"""流水线：把一天的数据从 ODS 一键算到明细层、维表、汇总层，并留下运行记录。

编排层（docs/工程规范.md 第 3 条）：唯一同时碰“数据库”和“计算”的地方。业务参数一律从 config/settings.yaml 读（第 8 条）。

D11 起有两种库、两个入口（第 10 条）：
  · 开发库 MySQL signal_insight：探索用，只放分析日（config.ANALYSIS_DAY）。run_day() 在这里跑，单日表整表替换。
    传别的日期会直接报错——D11 的事故就是把第二天跑进了单日表，结果不报错、第一天的结论悄悄没了。
  · 生产库 MySQL signal_warehouse：多日。run_partition() 在这里跑，所有明细和汇总表按 dt 分区写（同一个事务里先删后写）。
    命令行 python -m signal_insight run --date … 调的就是它。
每次运行有一个运行编号；etl_log 里记下每一步的行数、耗时、运行编号和配置版本（config.config_hash）。
"""
import argparse
import functools
import time
import uuid

import pandas as pd

from signal_mysql import database as mysql

from . import config, db, dims, dwd, dws, geo

DWS_TABLES = ["dws_stay", "dws_night", "dws_trip", "dws_user_day", "dws_user_hour"]
_LOG: list[dict] = []         # 本进程里所有步骤的记录；每次运行只取自己那一段


def _rows(x):
    """一个步骤的“行数”：DataFrame 取行数，(DataFrame, 其他) 取第一个的行数，整数原样返回。"""
    if isinstance(x, tuple):
        x = x[0]
    if isinstance(x, pd.DataFrame):
        return len(x)
    return x if isinstance(x, int) else None


def step(func):
    """装饰器：记录步骤名、输入行数、输出行数、耗时，不改函数本身的行为（D05）。"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        rows_in = next((_rows(a) for a in args if isinstance(a, pd.DataFrame)), None)
        t0 = time.perf_counter()
        out = func(*args, **kwargs)
        _LOG.append({"step": func.__name__, "rows_in": rows_in, "rows_out": _rows(out),
                     "elapsed_sec": round(time.perf_counter() - t0, 3),
                     "run_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")})
        return out
    return wrapper


def new_run_id() -> str:
    """运行编号：时间 + 6 位随机串。同一次运行的所有步骤、所有分区共用一个。"""
    return f"{pd.Timestamp.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


# ── 读 ──
@step
def extract_ods(con):
    """开发库：整张 ods_signal（里面只有 10-01～10-03）。"""
    return mysql.read_frame("SELECT * FROM ods_signal", con)


@step
def extract_day(con, day):
    """生产库：只取北京时间 day 这一天。条件写在 timestamp 上，走 D11 建的索引；不能先读全表再筛。"""
    start = int((pd.Timestamp(day) - pd.Timedelta(hours=config.UTC_OFFSET_HOURS)).timestamp() * 1000)
    return mysql.read_frame("SELECT * FROM ods_signal WHERE timestamp >= ? AND timestamp < ?", con,
                               params=(start, start + 86_400_000))


@step
def read_polygons(con):
    """区县边界和商圈边界（D03 选定 v2）：读一次，后面几步共用。"""
    districts = geo.rings_from_points(mysql.read_frame("SELECT * FROM ods_district_boundary", con), "district")
    aois = geo.rings_from_points(mysql.read_frame("SELECT * FROM ods_aoi_v2", con), "name")
    return districts, aois


# ── 算 ──
@step
def clean_signal(raw, day):
    return dwd.clean_signal(raw, day)


@step
def build_dim_cell(con, districts, aois):
    return dims.build_dim_cell(mysql.read_frame("SELECT * FROM ods_cell", con), districts, aois)


def locate(dwd_df, dim_cell):
    """信令补上坐标和区县：关联不上基站的 8 条不参与空间分析（D03 的决定）。"""
    return dwd_df.merge(dim_cell[["lac_cell", "site_id", "lng", "lat", "district"]], on="lac_cell", how="inner")


@step
def build_stay(sig, settings, districts, aois, hot):
    return dws.build_stay(sig, settings, districts, aois, hot)


@step
def build_night(stay, day, settings):
    return dws.build_night(stay, day, settings)


@step
def build_trip(stay, settings):
    return dws.build_trip(stay, settings)


@step
def build_user_day(sig, stay, trip, night, day, settings):
    return dws.build_user_day(sig, stay, trip, night, day, settings)


@step
def build_user_hour(stay, sig, day, settings, districts, aois, hot):
    return dws.build_user_hour(stay, sig, day, settings, districts, aois, hot)


def compute_dws(clean, dim_cell, hot, day, settings, districts, aois) -> dict:
    """汇总层的五张表：两种库算法完全一样，只是写法不同。"""
    sig = locate(clean, dim_cell)
    stay = build_stay(sig, settings, districts, aois, hot)
    night = build_night(stay, day, settings)
    trip = build_trip(stay, settings)
    return {"dws_stay": stay, "dws_night": night, "dws_trip": trip,
            "dws_user_day": build_user_day(sig, stay, trip, night, day, settings),
            "dws_user_hour": build_user_hour(stay, sig, day, settings, districts, aois, hot)}


# ── 写 ──
@step
def write_dwd(con, df, day):
    return db.write_partition(con, df, "dwd_signal", day)


def _writer(table, how):
    """生成“写某张表”的步骤；函数名带上表名，etl_log 里才分得清是哪张表。"""
    if how == "replace":
        def write(con, df, day=None):
            return db.replace_table(con, df, table)
    else:
        def write(con, df, day):
            return db.write_partition(con, df, table, day)
    write.__name__ = write.__qualname__ = f"write_{table}"
    return step(write)


REPLACE = {t: _writer(t, "replace") for t in DWS_TABLES + ["dim_cell", "dim_hotspot", "dim_metric"]}
PARTITION = {t: _writer(t, "partition") for t in DWS_TABLES}


def _finish_log(con, start, day, run_id, settings):
    log = pd.DataFrame(_LOG[start:]).assign(dt=day, run_id=run_id, config_version=config.config_hash(settings))
    db.append_table(con, log, "etl_log")      # 老的 etl_log 没有“配置版本”列：append_table 会先加列
    return log


def refresh_dims(con, settings, polygons=None) -> None:
    """重建维表：dim_cell（基站）、dim_hotspot（热点，来自配置）、dim_metric（口径，来自配置）。

    维表不分日期：init 时建一次；改了热点或口径参数后再跑一次（命令行 python -m signal_insight dims）。
    polygons：调用方已经读好的 (区县, 商圈) 多边形；不给就自己读一次。
    """
    districts, aois = polygons or read_polygons(con)
    REPLACE["dim_cell"](con, build_dim_cell(con, districts, aois))
    REPLACE["dim_hotspot"](con, dims.dim_hotspot_from_settings(settings))
    REPLACE["dim_metric"](con, dims.build_dim_metric(settings))
    mysql.ensure_index(con, "idx_dim_cell_pk", "dim_cell", ["lac_cell"], unique=True)


def run_partition(con, settings: dict, dt: str, run_id: str | None = None) -> pd.DataFrame:
    """生产库上跑一天：明细层和汇总层按 dt 分区写，别的日期不受影响。维表只读（init 时建好）。

    返回本次运行的步骤记录（也追加进 etl_log）。
    """
    run_id = run_id or new_run_id()
    start = len(_LOG)
    raw = extract_day(con, dt)
    clean, _ = clean_signal(raw, dt)
    write_dwd(con, clean, dt)
    districts, aois = read_polygons(con)
    dim_cell = mysql.read_frame("SELECT * FROM dim_cell", con)
    hot = mysql.read_frame("SELECT * FROM dim_hotspot", con).iloc[0]
    for table, df in compute_dws(clean, dim_cell, hot, dt, settings, districts, aois).items():
        PARTITION[table](con, df, dt)
    return _finish_log(con, start, dt, run_id, settings)


def run_day(day: str | None = None, db_path=None) -> pd.DataFrame:
    """开发库上跑分析日（D05–D10 的 notebook 都在调用它）：单日表整表替换，结果与 D10 完全相同。

    D11 起只接受分析日：传别的日期直接报错，指向生产库。签名没变——改签名就得改所有调用它的 notebook（D06 的教训）。
    """
    day = day or config.ANALYSIS_DAY
    if day != config.ANALYSIS_DAY:
        raise ValueError(f"开发库只放分析日 {config.ANALYSIS_DAY}，不能跑 {day}：汇总表是单日表，跑第二天会把第一天整张冲掉。"
                         f"多日请在生产库上跑：python -m signal_insight run --date {day}")
    settings = config.load_settings()
    run_id = new_run_id()
    start = len(_LOG)
    con = db.connect(db_path)
    try:
        raw = extract_ods(con)
        clean, _ = clean_signal(raw, day)
        write_dwd(con, clean, day)
        districts, aois = read_polygons(con)               # 读一次，维表和汇总层共用
        refresh_dims(con, settings, (districts, aois))
        dim_cell = mysql.read_frame("SELECT * FROM dim_cell", con)
        hot = mysql.read_frame("SELECT * FROM dim_hotspot", con).iloc[0]
        for table, df in compute_dws(clean, dim_cell, hot, day, settings, districts, aois).items():
            REPLACE[table](con, df)
        log = _finish_log(con, start, day, run_id, settings)
    finally:
        con.close()
    return log


def main(argv=None):
    parser = argparse.ArgumentParser(description="在开发库上跑分析日（多日请用 python -m signal_insight run）")
    parser.add_argument("--day", default=config.ANALYSIS_DAY, help="只能是分析日")
    parser.add_argument("--db", default=None, help="数据库路径，默认 MySQL signal_insight")
    args = parser.parse_args(argv)
    log = run_day(args.day, args.db)
    print(log[["step", "rows_in", "rows_out", "elapsed_sec"]].to_string(index=False))


if __name__ == "__main__":
    main()
