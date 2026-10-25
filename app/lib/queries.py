"""数据访问层（D14）：只读、只放行 ads_ / dim_ 表。平台不碰 dwd_、dws_、ods_。"""
import pandas as pd

from signal_mysql import database as mysql

from signal_insight import config


def connect():
    return mysql.connect(config.WAREHOUSE_SCHEMA, readonly=True)


def dates(con):
    return mysql.read_frame("SELECT DISTINCT dt FROM ads_dq_partition ORDER BY dt", con)["dt"].tolist()


def areas(con):
    return mysql.read_frame("SELECT area FROM dim_area ORDER BY area", con)["area"].tolist()


def area_daily(con, dt):
    return mysql.read_frame("SELECT * FROM ads_area_daily WHERE dt = ? ORDER BY area", con, params=(dt,))


def area_hourly(con, dt):
    return mysql.read_frame("SELECT * FROM ads_area_hourly WHERE dt = ? ORDER BY area, hour", con, params=(dt,))


def area_segment(con, dt):
    return mysql.read_frame("SELECT * FROM ads_area_segment WHERE dt = ? ORDER BY area, users DESC", con, params=(dt,))


def area_radius(con, dt):
    return mysql.read_frame("SELECT * FROM ads_area_radius WHERE dt = ? ORDER BY area, band_order", con, params=(dt,))


def area_origin(con, dt):
    return mysql.read_frame("SELECT * FROM ads_area_origin WHERE dt = ? ORDER BY area, users DESC", con, params=(dt,))


def area_linkage(con, dt):
    return mysql.read_frame("SELECT * FROM ads_area_linkage WHERE dt = ? ORDER BY area, other_area", con, params=(dt,))


def hex_hourly(con, dt):
    return mysql.read_frame("SELECT * FROM ads_hex_hourly WHERE dt = ? ORDER BY hour, q, r", con, params=(dt,))


def dq_partition(con):
    return mysql.read_frame("SELECT * FROM ads_dq_partition ORDER BY dt", con)


def dq_rule(con, dt):
    return mysql.read_frame("SELECT * FROM ads_dq_rule WHERE dt = ? ORDER BY rule_id", con, params=(dt,))


def metrics(con):
    return mysql.read_frame("SELECT * FROM dim_metric ORDER BY metric", con)
