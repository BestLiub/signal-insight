"""流水线：把一天的数据从 ODS 一键算到明细层、维表、汇总层，并留下运行记录。

编排层（docs/工程规范.md 第 3 条）：唯一同时碰“数据库”和“计算”的地方。
读库 → 调用 dwd / dims / dws 里的纯函数 → 写库，每一步由 @step 记下行数和耗时，最后写进 etl_log。
业务参数一律从 config/settings.yaml 读，传给计算函数（docs/工程规范.md 第 8 条）。

用法：
    python -m signal_insight.pipeline --day 2018-10-03
或在 notebook 里：
    from signal_insight import pipeline;   pipeline.run_day()
"""
import argparse
import functools
import time

import pandas as pd

from signal_mysql import database as mysql

from . import config, db, dims, dwd, geo
from . import dws

_LOG: list[dict] = []         # 本进程里所有步骤的记录；run_day 只取自己这一次的那一段


def _rows(x):
    """一个步骤的"行数"：DataFrame 取行数，(DataFrame, 其他) 取第一个的行数，整数原样返回。"""
    if isinstance(x, tuple):
        x = x[0]
    if isinstance(x, pd.DataFrame):
        return len(x)
    return x if isinstance(x, int) else None


def step(func):
    """装饰器：记录步骤名、输入行数、输出行数、耗时，不改函数本身的行为。

    装饰器就是“接收一个函数、返回一个新函数”的函数：调用方的写法一个字都不用改，
    但每一步都自动留下了运行记录。出了问题，看记录就知道是哪一步、处理了多少行、花了多久。
    """
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


# ── 每一步：读库的、算的、写库的分开，各自一个函数，日志里才分得清哪一步慢 ──
@step
def extract_ods(con):
    return mysql.read_frame("SELECT * FROM ods_signal", con)


@step
def clean_signal(raw, day):
    return dwd.clean_signal(raw, day)


@step
def write_dwd(con, df, day):
    return db.write_partition(con, df, "dwd_signal", day)


@step
def read_polygons(con):
    """区县边界和商圈边界（D03 选定 v2）：读一次，后面几步共用。"""
    districts = geo.rings_from_points(mysql.read_frame("SELECT * FROM ods_district_boundary", con), "district")
    aois = geo.rings_from_points(mysql.read_frame("SELECT * FROM ods_aoi_v2", con), "name")
    return districts, aois


@step
def build_dim_cell(con, districts, aois):
    return dims.build_dim_cell(mysql.read_frame("SELECT * FROM ods_cell", con), districts, aois)


@step
def build_dim_hotspot(dwd_df, dim_cell, settings):
    return dims.build_dim_hotspot(dwd_df, dim_cell, **settings["hotspot"])


@step
def write_dim_cell(con, df):
    return db.replace_table(con, df, "dim_cell")


@step
def write_dim_hotspot(con, df):
    return db.replace_table(con, df, "dim_hotspot")


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
def build_dim_metric(settings):
    return dims.build_dim_metric(settings)


@step
def build_user_hour(stay, sig, day, settings, districts, aois, hot):
    return dws.build_user_hour(stay, sig, day, settings, districts, aois, hot)


def _replace(table):
    """生成一个“整表替换某张表”的步骤；函数名带上表名，etl_log 里才分得清是哪张表。"""
    def write(con, df):
        return db.replace_table(con, df, table)
    write.__name__ = write.__qualname__ = f"write_{table}"
    return step(write)


# 汇总层现在都是整表替换：只有一天的数据，这样最简单。
write_dws_stay = _replace("dws_stay")
write_dws_night = _replace("dws_night")
write_dws_trip = _replace("dws_trip")
write_dws_user_day = _replace("dws_user_day")
write_dim_metric = _replace("dim_metric")
write_dws_user_hour = _replace("dws_user_hour")


def run_day(day: str | None = None, db_path=None) -> pd.DataFrame:
    """跑一天：读 ODS → 清洗 → 维表 → 停留 → 过夜地、出行 → 用户日特征、口径表 → 写库 → 把步骤记录写进 etl_log。返回本次运行的步骤记录。

    dwd_signal 按日期分区写（重跑幂等）；维表和汇总层整表替换。
    """
    day = day or config.ANALYSIS_DAY
    settings = config.load_settings()
    start = len(_LOG)
    batch = pd.Timestamp.now().strftime("%Y%m%d-%H%M%S-%f")      # 批次号：同一次运行的几步共用一个
    con = db.connect(db_path)
    try:
        raw = extract_ods(con)
        clean, _ = clean_signal(raw, day)
        write_dwd(con, clean, day)
        districts, aois = read_polygons(con)
        dim_cell = build_dim_cell(con, districts, aois)
        write_dim_cell(con, dim_cell)
        hotspot = build_dim_hotspot(clean, dim_cell, settings)
        write_dim_hotspot(con, hotspot)
        hot = hotspot.iloc[0]
        sig = locate(clean, dim_cell)
        stay = build_stay(sig, settings, districts, aois, hot)
        write_dws_stay(con, stay)
        night = build_night(stay, day, settings)
        write_dws_night(con, night)
        trip = build_trip(stay, settings)
        write_dws_trip(con, trip)
        write_dws_user_day(con, build_user_day(sig, stay, trip, night, day, settings))
        write_dim_metric(con, build_dim_metric(settings))
        write_dws_user_hour(con, build_user_hour(stay, sig, day, settings, districts, aois, hot))
        log = pd.DataFrame(_LOG[start:]).assign(dt=day, run_id=batch)
        db.append_table(con, log, "etl_log")
    finally:
        con.close()
    return log


def main(argv=None):
    parser = argparse.ArgumentParser(description="跑一天的流水线：ODS → dwd_signal、维表、dws_ 各表、dim_metric")
    parser.add_argument("--day", default=config.ANALYSIS_DAY, help="日期分区，形如 2018-10-03")
    parser.add_argument("--db", default=None, help="数据库路径，默认 MySQL signal_insight")
    args = parser.parse_args(argv)
    log = run_day(args.day, args.db)
    print(log[["step", "rows_in", "rows_out", "elapsed_sec"]].to_string(index=False))


if __name__ == "__main__":
    main()
