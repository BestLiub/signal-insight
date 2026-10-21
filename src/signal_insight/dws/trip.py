"""汇总层 dws_trip：出行（D07）。纯计算，参数从 settings["trip"] 取。

出行 = 同一个人相邻两个停留之间的移动。起点取上一个停留的质心和结束时刻，终点取下一个停留的质心和开始时刻。
dist_m 是直线距离；duration_min 是两次停留之间的全部时间（偏长）。所以速度只能粗看（D07 需求卡 7.6）。
"""
import pandas as pd

from .. import geo

TRIP_COLS = ["imsi", "trip_seq", "o_seq", "d_seq", "depart_time", "arrive_time", "duration_min", "dist_m",
             "o_lng", "o_lat", "d_lng", "d_lat", "o_district", "d_district", "o_aoi", "d_aoi",
             "o_dist_xita_m", "d_dist_xita_m"]


def build_trip(stay: pd.DataFrame, settings: dict) -> pd.DataFrame:
    """把每个人相邻的两个停留连成一次出行；两个质心相距不到 trip.min_dist_m 的不算（同一个地方被切成了两段）。"""
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
