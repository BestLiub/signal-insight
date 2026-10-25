"""汇总层 dws_stay：停留识别（D06）。

纯计算（docs/工程规范.md 第 4 条）：输入带坐标的信令，输出停留表；多边形、热点由调用方传进来，这里不读库。
参数（半径、最短时长）从 settings["stay"] 取，代码里不写业务数字（docs/工程规范.md 第 8 条）。
"""
import numpy as np
import pandas as pd

from .. import geo

EPOCH = pd.Timestamp("1970-01-01")
STAY_COLS = ["imsi", "stay_seq", "start_time", "end_time", "duration_min", "lng", "lat",
             "n_records", "district", "aoi", "dist_xita_m"]


def find_segments(sig: pd.DataFrame, radius_m: float) -> pd.DataFrame:
    """把每个人按时间排好的信令切成“段”：离当前段质心不超过 radius_m 就并入，否则开新段。

    sig 至少要有 imsi、ts、lac_cell、lng、lat。**函数里自己排序**，不依赖调用方排好（D06 契约）：
    按 imsi、ts，同一时刻再按 lac_cell。同一个人同一毫秒有两条不同基站的记录时（全量里有 2 组），
    谁先谁后会改变切段结果；加上 lac_cell 决胜，结果就和输入顺序无关。

    比到质心而不是上一个点：一串每次都走 400 米的点不会被一直并成一段（“温水煮青蛙”）。
    内层循环用 numpy 数组和标量版 dist_m：df.iloc[i] 比 arr[i] 慢上百倍。
    返回每段一行：imsi、t_start、t_end（秒）、lat、lng（质心）、n_records、duration_min。
    """
    df = sig.sort_values(["imsi", "ts", "lac_cell"], kind="stable")
    imsi = df["imsi"].to_numpy()
    t = (df["ts"] - EPOCH).dt.total_seconds().to_numpy()
    lat, lng = df["lat"].to_numpy(), df["lng"].to_numpy()
    rows, i, n = [], 0, len(df)
    while i < n:
        sum_lat, sum_lng, k, j = lat[i], lng[i], 1, i
        while j + 1 < n and imsi[j + 1] == imsi[i]:                  # 段不跨用户
            if geo.dist_m(sum_lat / k, sum_lng / k, lat[j + 1], lng[j + 1]) > radius_m:
                break
            j += 1
            sum_lat, sum_lng, k = sum_lat + lat[j], sum_lng + lng[j], k + 1
        rows.append((imsi[i], t[i], t[j], sum_lat / k, sum_lng / k, k))
        i = j + 1
    seg = pd.DataFrame(rows, columns=["imsi", "t_start", "t_end", "lat", "lng", "n_records"])
    seg["duration_min"] = (seg["t_end"] - seg["t_start"]) / 60
    return seg


def build_stay(sig: pd.DataFrame, settings: dict, districts: dict, aois: dict, hot,
               day: str | None = None) -> pd.DataFrame:
    """停留表 dws_stay：持续不少于 stay.min_minutes 的段，补上顺序号、起止时刻、区县、商圈、到热点的距离。

    hot 是热点的一行（有 lng、lat），由调用方从 dim_hotspot 取。
    起止时刻精确到秒（与 D06 notebook 一致）；时长保留一位小数；主键 imsi + stay_seq。

    day（D12 回看窗口）：sig 里可能带着前一天最后几小时的信令。给了 day 时：
      · 只保留结束时刻在 day 当天或之后的停留——完全落在前一天的属于前一天的分区，不能重复写进今天；
      · 多两列：cross_day（开始于前一天）、duration_in_day_min（落在当天的那部分时长，按天汇总时用它，
        否则同一段停留会在两天里各算一次）。
    不给 day 时行为与 D06 完全相同（开发库、单日）。
    """
    p = settings["stay"]
    seg = find_segments(sig, p["radius_m"])
    keep = seg["duration_min"] >= p["min_minutes"]
    if day is not None:
        keep &= seg["t_end"] >= (pd.Timestamp(day) - EPOCH).total_seconds()
    stay = seg[keep].reset_index(drop=True)
    stay["stay_seq"] = stay.groupby("imsi").cumcount() + 1
    stay["start_time"] = pd.to_datetime(stay["t_start"], unit="s").dt.floor("s")
    stay["end_time"] = pd.to_datetime(stay["t_end"], unit="s").dt.floor("s")
    stay["duration_min"] = stay["duration_min"].round(1)
    stay["district"] = pd.Series(geo.point_in_polygons(stay["lng"], stay["lat"], districts)).fillna("市外")
    stay["aoi"] = geo.point_in_polygons(stay["lng"], stay["lat"], aois)
    stay["dist_xita_m"] = geo.haversine(stay["lat"], stay["lng"], hot["lat"], hot["lng"]).round()
    if day is None:
        return stay[STAY_COLS]
    d0 = (pd.Timestamp(day) - EPOCH).total_seconds()
    stay["cross_day"] = stay["t_start"] < d0
    stay["duration_in_day_min"] = ((stay["t_end"] - np.maximum(stay["t_start"], d0)) / 60).round(1)
    return stay[STAY_COLS + ["cross_day", "duration_in_day_min"]]
