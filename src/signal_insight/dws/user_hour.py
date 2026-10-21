"""汇总层 dws_user_hour：每人每小时一个位置（D09）。纯计算，参数从 settings["hourly"] 取。

位置的来源分两档：有停留覆盖这个小时 ≥ hourly.min_cover_minutes，用覆盖最久的停留的质心；
否则用这个小时所有信令位置的中位数。这个小时一条信令都没有：不可定位，不硬补。
"""
import numpy as np
import pandas as pd

from .. import geo


def build_user_hour(stay: pd.DataFrame, sig_day: pd.DataFrame, day: str, settings: dict,
                    districts: dict, aois: dict, hot) -> pd.DataFrame:
    """返回每个“人 × 小时”一行：imsi、lng、lat、hour、src（停留 / 信令）、district、aoi、dist_xita_m。"""
    min_cover = settings["hourly"]["min_cover_minutes"]
    d0 = pd.Timestamp(day)
    sh = (stay["start_time"] - d0).dt.total_seconds() / 3600
    eh = (stay["end_time"] - d0).dt.total_seconds() / 3600
    parts = []
    for h in range(24):
        cover = (np.minimum(eh, h + 1) - np.maximum(sh, h)).clip(lower=0) * 60    # 这个停留覆盖第 h 小时多少分钟
        m = cover >= min_cover
        parts.append(stay.loc[m, ["imsi", "lng", "lat"]].assign(hour=h, cover=cover[m]))
    by_stay = (pd.concat(parts).sort_values("cover", ascending=False)
               .drop_duplicates(["imsi", "hour"]).drop(columns="cover").assign(src="停留"))
    by_sig = (sig_day.assign(hour=sig_day["ts"].dt.hour)
              .groupby(["imsi", "hour"], as_index=False)[["lng", "lat"]].median())
    by_sig = by_sig.merge(by_stay[["imsi", "hour"]], how="left", indicator=True)      # 反连接：没被停留覆盖的
    by_sig = by_sig[by_sig["_merge"] == "left_only"].drop(columns="_merge").assign(src="信令")
    uh = pd.concat([by_stay, by_sig], ignore_index=True)
    uh["district"] = pd.Series(geo.point_in_polygons(uh["lng"], uh["lat"], districts)).fillna("市外").to_numpy()
    uh["aoi"] = geo.point_in_polygons(uh["lng"], uh["lat"], aois)
    uh["dist_xita_m"] = geo.haversine(uh["lat"], uh["lng"], hot["lat"], hot["lng"])
    return uh.sort_values(["imsi", "hour"], ignore_index=True)
