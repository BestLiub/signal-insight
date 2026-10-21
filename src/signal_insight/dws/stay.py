"""汇总层（dws_）：停留识别（D06）、过夜地与出行（D07）。

纯计算（docs/工程规范.md 第 4 条）：输入带坐标的信令，输出停留表；多边形、热点由调用方传进来，这里不读库。
参数从 settings 取，代码里不写业务数字（docs/工程规范.md 第 8 条）。
现在汇总层有三张表，一个文件就够；表多了（超过 3 张或约 300 行）就拆成同名文件夹（docs/工程规范.md 第 5 条）。
"""
import numpy as np
import pandas as pd

from . import geo

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


def build_stay(sig: pd.DataFrame, settings: dict, districts: dict, aois: dict, hot) -> pd.DataFrame:
    """停留表 dws_stay：持续不少于 stay.min_minutes 的段，补上顺序号、起止时刻、区县、商圈、到热点的距离。

    hot 是热点的一行（有 lng、lat），由调用方从 dim_hotspot 取。
    起止时刻精确到秒（与 D06 notebook 一致）；时长保留一位小数；主键 imsi + stay_seq。
    """
    p = settings["stay"]
    seg = find_segments(sig, p["radius_m"])
    stay = seg[seg["duration_min"] >= p["min_minutes"]].reset_index(drop=True)
    stay["stay_seq"] = stay.groupby("imsi").cumcount() + 1
    stay["start_time"] = pd.to_datetime(stay["t_start"], unit="s").dt.floor("s")
    stay["end_time"] = pd.to_datetime(stay["t_end"], unit="s").dt.floor("s")
    stay["duration_min"] = stay["duration_min"].round(1)
    stay["district"] = pd.Series(geo.point_in_polygons(stay["lng"], stay["lat"], districts)).fillna("市外")
    stay["aoi"] = geo.point_in_polygons(stay["lng"], stay["lat"], aois)
    stay["dist_xita_m"] = geo.haversine(stay["lat"], stay["lng"], hot["lat"], hot["lng"]).round()
    return stay[STAY_COLS]


NIGHT_COLS = ["imsi", "night_lng", "night_lat", "night_district", "night_dist_xita_m", "night_min"]


def build_night(stay: pd.DataFrame, day: str, settings: dict) -> pd.DataFrame:
    """每人一个过夜地：与夜间时段重叠最长、且重叠不少于 night.min_overlap_minutes 的那个停留。

    两个区间重叠多少：min(结束, 区间右端) − max(开始, 区间左端)，负数当 0。
    识别不出过夜地的人不在这张表里——后面所有基于它的比例，分母都是“能识别的人”。
    """
    p = settings["night"]
    d0 = pd.Timestamp(day)
    start, end = d0 + pd.Timedelta(hours=p["start_hour"]), d0 + pd.Timedelta(hours=p["end_hour"])
    overlap = stay["end_time"].clip(upper=end) - stay["start_time"].clip(lower=start)
    s = stay.assign(night_min=(overlap.dt.total_seconds() / 60).clip(lower=0))
    night = s[s["night_min"] >= p["min_overlap_minutes"]].sort_values("night_min").groupby("imsi").tail(1)
    night = night.rename(columns={"lng": "night_lng", "lat": "night_lat", "district": "night_district",
                                  "dist_xita_m": "night_dist_xita_m"})
    return night[NIGHT_COLS].reset_index(drop=True)


TRIP_COLS = ["imsi", "trip_seq", "o_seq", "d_seq", "depart_time", "arrive_time", "duration_min", "dist_m",
             "o_lng", "o_lat", "d_lng", "d_lat", "o_district", "d_district", "o_aoi", "d_aoi",
             "o_dist_xita_m", "d_dist_xita_m"]


def build_trip(stay: pd.DataFrame, settings: dict) -> pd.DataFrame:
    """每个人相邻的两个停留连成一次出行；两个质心相距不到 trip.min_dist_m 的不算（同一个地方被切成了两段）。"""
    s = stay.sort_values(["imsi", "stay_seq"])
    nxt = s.groupby("imsi").shift(-1)                                # 同一个人的下一个停留
    trip = pd.DataFrame({
        "imsi": s["imsi"], "o_seq": s["stay_seq"], "d_seq": nxt["stay_seq"],
        "depart_time": s["end_time"], "arrive_time": nxt["start_time"],
        "o_lng": s["lng"], "o_lat": s["lat"], "d_lng": nxt["lng"], "d_lat": nxt["lat"],
        "o_district": s["district"], "d_district": nxt["district"], "o_aoi": s["aoi"], "d_aoi": nxt["aoi"],
        "o_dist_xita_m": s["dist_xita_m"], "d_dist_xita_m": nxt["dist_xita_m"],
    }).dropna(subset=["d_seq"])                                      # 最后一个停留后面没有出行
    trip["dist_m"] = geo.haversine(trip["o_lat"], trip["o_lng"], trip["d_lat"], trip["d_lng"]).round()
    trip = trip[trip["dist_m"] >= settings["trip"]["min_dist_m"]].copy()
    trip["duration_min"] = ((trip["arrive_time"] - trip["depart_time"]).dt.total_seconds() / 60).round(1)
    trip["trip_seq"] = trip.groupby("imsi").cumcount() + 1
    trip["d_seq"] = trip["d_seq"].astype(int)
    return trip[TRIP_COLS].reset_index(drop=True)
