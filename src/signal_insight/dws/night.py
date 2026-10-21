"""汇总层 dws_night：过夜地（D07）。纯计算，参数从 settings["night"] 取。

过夜地 ≠ 家：只有一天数据，又是假期，住酒店的人过夜地就是酒店。报告里只叫“过夜地”。
"""
import pandas as pd

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
