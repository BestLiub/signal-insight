"""过夜地与出行的单元测试（D07，学生写的参考版本）。"""
import pandas as pd
from signal_insight import dws

S = {"night": {"start_hour": 0, "end_hour": 6, "min_overlap_minutes": 60},
     "trip": {"min_dist_m": 500}}


def stay(rows):
    df = pd.DataFrame(rows, columns=["imsi", "stay_seq", "start_time", "end_time", "lng", "lat"])
    for c in ["start_time", "end_time"]:
        df[c] = pd.to_datetime(df[c])
    return df.assign(district="甲区", aoi=None, dist_xita_m=0.0)


def test_stay_across_midnight_counts_only_after_midnight():
    night = dws.build_night(stay([("u", 1, "2018-10-02 23:00", "2018-10-03 01:30", 123.4, 41.8)]), "2018-10-03", S)
    assert night.loc[0, "night_min"] == 90


def test_close_stays_make_no_trip():
    s = stay([("u", 1, "2018-10-03 08:00", "2018-10-03 09:00", 123.400, 41.8),
              ("u", 2, "2018-10-03 10:00", "2018-10-03 11:00", 123.402, 41.8)])
    assert len(dws.build_trip(s, S)) == 0
