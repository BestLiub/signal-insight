"""汇总层 dws_user_day：用户日特征宽表与客群标签（D08）。纯计算，参数从 settings 取。

一个人一行。下游（标签、分析、平台、下一门机器学习课）都从这张表按人取数，不用每次去 join 四五张明细表。
"""
import numpy as np
import pandas as pd

from .. import geo

UNKNOWN, OUTSIDE_CITY, NEAR, IN_CITY, OUTSIDER = "过夜地不明", "市外来访", "周边居民", "市内来访", "外地来客"
OUT_OF_CITY = "市外"                                   # dim_cell、dws_stay 里落不进任何区县的标记


def segment_by_night(dist_km, night_district, near_km) -> np.ndarray:
    """客群规则本身（D08 定；D13 的区域表也用它，规则只有这一份）。**判断顺序固定**：不明 → 市外 → 周边 → 其余市内。

    顺序本身就是业务规则：np.select 取第一个成立的条件。先判“不明”还因为 NaN 和数字比较永远是 False——
    要是先写 dist < 1.5，识别不出过夜地的人会掉进 default，被错归成“市内来访”（讲师卡易错点）。
    dist_km 由调用方算好传进来：**要先判断、后取整**（D13 需求卡 13.2：先取整，1.496 公里会被算成 1.50）。
    """
    dist_km = pd.Series(dist_km).to_numpy(dtype=float)
    return np.select([np.isnan(dist_km), pd.Series(night_district).to_numpy() == OUT_OF_CITY, dist_km < near_km],
                     [UNKNOWN, OUTSIDE_CITY, NEAR], default=IN_CITY)


def segment_with_inbound(by_night, inbound) -> np.ndarray:
    """修正口径（D08 需求卡 8.4）：当天从外地进城的人、过夜地在市外的人，都算“外地来客”。"""
    by_night = np.asarray(by_night, dtype=object)
    return np.where(np.asarray(inbound, dtype=bool) | (by_night == OUTSIDE_CITY), OUTSIDER, by_night)


def classify_segment(user_day: pd.DataFrame, settings: dict) -> pd.Series:
    """按过夜地给人分类（D08 的宽表）：距离量到西塔中心。规则见 segment_by_night。"""
    return pd.Series(segment_by_night(user_day["night_dist_xita_km"], user_day["night_district"],
                                      settings["visitor"]["near_km"]),
                     index=user_day.index, name="segment")


def build_user_day(sig_day: pd.DataFrame, stay: pd.DataFrame, trip: pd.DataFrame, night: pd.DataFrame,
                   day: str, settings: dict) -> pd.DataFrame:
    """用户日特征宽表 dws_user_day：活跃、停留与出行、过夜地、西塔相关、客群标签，一人一行。

    sig_day：带坐标和区县的信令（imsi、ts、lng、lat、district）；其余是 D06、D07 的三张表。
    先用全量用户建好行，再把各表 groupby 的结果按 imsi 对齐填进去：没有停留、没有出行的人不会被悄悄丢掉。
    数值列保留两位小数；客群标签在取整之后判断（和 D08 notebook 一致）。
    """
    v = settings["visitor"]
    radius = settings["hotspot"]["radius_m"]
    d0 = pd.Timestamp(day)
    night = night.set_index("imsi")
    users = pd.Index(sorted(sig_day["imsi"].unique()), name="imsi")
    out = pd.DataFrame(index=users)
    # 活跃
    g = sig_day.groupby("imsi")
    out["n_records"] = g.size()
    out["first_seen"] = g["ts"].min().dt.strftime("%H:%M")
    out["last_seen"] = g["ts"].max().dt.strftime("%H:%M")
    out["active_hours"] = sig_day["ts"].dt.hour.groupby(sig_day["imsi"]).nunique()
    # 停留与出行
    gs = stay.groupby("imsi")
    out["n_stays"] = gs.size()
    out["stay_total_min"] = gs["duration_min"].sum()
    out["max_stay_min"] = gs["duration_min"].max()
    out["n_trips"] = trip.groupby("imsi").size()
    out["trip_total_km"] = trip.groupby("imsi")["dist_m"].sum() / 1000
    # 回转半径：按停留时长加权的重心，再求各停留点到重心距离的加权均方根
    w = stay["duration_min"]
    wsum = w.groupby(stay["imsi"]).sum()
    c_lng = (stay["lng"] * w).groupby(stay["imsi"]).sum() / wsum
    c_lat = (stay["lat"] * w).groupby(stay["imsi"]).sum() / wsum
    d_c = geo.haversine(stay["lat"], stay["lng"], stay["imsi"].map(c_lat), stay["imsi"].map(c_lng))
    out["gyration_km"] = np.sqrt((w * d_c ** 2).groupby(stay["imsi"]).sum() / wsum) / 1000
    # 过夜地
    out["night_district"] = night["night_district"]
    out["night_dist_xita_km"] = night["night_dist_xita_m"] / 1000
    # 西塔相关：西塔停留 = 质心在热点 radius 内的停留；傍晚访客 = 有西塔停留在 evening_hour 之后仍在
    xita = stay[stay["dist_xita_m"] <= radius]
    gx = xita.groupby("imsi")
    visitors = xita.loc[xita["end_time"] >= d0 + pd.Timedelta(hours=v["evening_hour"]), "imsi"].unique()
    out["xita_stay_min"] = gx["duration_min"].sum()
    out["xita_arrive_hour"] = (gx["start_time"].min() - d0).dt.total_seconds() / 3600
    out["is_evening_visitor"] = out.index.isin(visitors)
    last_leave = gx["end_time"].max()
    out["xita_after_23"] = out.index.isin(last_leave[last_leave >= d0 + pd.Timedelta(hours=v["late_hour"])].index)
    for col, aoi in v["linked_aois"].items():                         # 当天去没去过联动商圈
        out[col] = out.index.isin(stay.loc[stay["aoi"] == aoi, "imsi"])
    fill0 = ["n_stays", "stay_total_min", "max_stay_min", "n_trips", "trip_total_km", "xita_stay_min"]
    out[fill0] = out[fill0].fillna(0)
    out = out.round(2)
    # 客群标签：按过夜地（D08 需求卡 8.3）
    out["segment"] = classify_segment(out, settings)
    # 修正（需求卡 8.4）：当天第一条信令在市域外、之后进入市域的，是当天从外地进城的人
    s = sig_day.sort_values(["imsi", "ts"], kind="stable")
    first_district = s.groupby("imsi")["district"].first().reindex(out.index)
    in_city = s.loc[s["district"] != OUT_OF_CITY, "imsi"].unique()
    out["inbound"] = (first_district == OUT_OF_CITY).to_numpy() & out.index.isin(in_city)
    out["segment_v2"] = segment_with_inbound(out["segment"], out["inbound"])
    return out.reset_index()
