"""汇总层：停留 × 区域 dws_stay_area、用户 × 区域日特征 dws_user_area_day（D13）。纯计算，参数从 settings 取。

D08 的宽表里，西塔、太原街、中街各有几列（xita_stay_min、visit_taiyuan……）：加一个区域就要加列、改代码。
这里换成长表：区域是 area 列的一个取值。加区域只改配置（dims.build_dim_area），这两个函数一行不改。
"""
import pandas as pd

from .. import geo
from .user_day import segment_by_night, segment_with_inbound

STAY_AREA_COLS = ["imsi", "stay_seq", "area", "dist_center_m"]


def build_stay_area(stay: pd.DataFrame, dim_area: pd.DataFrame, area_polys: dict) -> pd.DataFrame:
    """停留 × 区域（长表）：一个停留落在哪些分析区域里。区域可以重叠，所以一个停留可以有好几行。"""
    m = geo.area_membership(stay["lng"], stay["lat"], dim_area, area_polys)
    keys = stay[["imsi", "stay_seq"]].reset_index(drop=True)
    return pd.concat([keys.iloc[m["idx"]].reset_index(drop=True), m[["area", "dist_center_m"]]], axis=1)[STAY_AREA_COLS]


def build_user_area_day(stay: pd.DataFrame, stay_area: pd.DataFrame, user_day: pd.DataFrame, night: pd.DataFrame,
                        dim_area: pd.DataFrame, day: str, settings: dict) -> pd.DataFrame:
    """用户 × 区域日特征（长表）：每人在每个到过的区域一行。

    傍晚访客、删失（visitor.late_hour 之后仍在）、到达时刻的口径和 D08 相同，只是“西塔”换成了每个区域。
    客群标签也在这里：“周边居民”是相对某个区域而言的，所以过夜地距离量到**这个区域的中心**。
    两个口径都留着：segment_by_night 只看过夜地（D08 的规则），segment 是修正口径（外地来客）。
    """
    v = settings["visitor"]
    d0 = pd.Timestamp(day)
    sa = stay_area.merge(stay[["imsi", "stay_seq", "start_time", "end_time", "duration_min"]], on=["imsi", "stay_seq"])
    g = sa.groupby(["imsi", "area"])
    out = pd.DataFrame({"n_stays": g.size(), "stay_min": g["duration_min"].sum(),
                        "first_arrive": g["start_time"].min(), "last_leave": g["end_time"].max()})
    evening = sa[sa["end_time"] >= d0 + pd.Timedelta(hours=v["evening_hour"])]
    out["evening_visitor"] = out.index.isin(pd.MultiIndex.from_frame(evening[["imsi", "area"]]))
    out["after_late"] = out["last_leave"] >= d0 + pd.Timedelta(hours=v["late_hour"])
    out["arrive_hour"] = ((out["first_arrive"] - d0).dt.total_seconds() / 3600).round(2)
    out = out.reset_index()

    n = night.set_index("imsi")
    center = dim_area.set_index("area")
    dist_m = geo.haversine(out["imsi"].map(n["night_lat"]), out["imsi"].map(n["night_lng"]),
                           out["area"].map(center["center_lat"]), out["area"].map(center["center_lng"]))
    out["night_dist_km"] = pd.Series(dist_m, index=out.index).round() / 1000   # 精确到米：先判断、后展示
    out["night_district"] = out["imsi"].map(n["night_district"])
    out["inbound"] = out["imsi"].map(user_day.set_index("imsi")["inbound"]).fillna(False).astype(bool)
    out["segment_by_night"] = segment_by_night(out["night_dist_km"], out["night_district"], v["near_km"])
    out["segment"] = segment_with_inbound(out["segment_by_night"], out["inbound"])
    return out
