"""D07 契约：privacy.mask_id；dws.build_night、build_trip。"""
import pandas as pd
from signal_insight import dws, privacy
from _helpers import PKG, dws_files, numeric_constants, touches_database

S = {"night": {"start_hour": 0, "end_hour": 6, "min_overlap_minutes": 60},
     "trip": {"min_dist_m": 500}}


def _stay(rows):
    """rows: (imsi, stay_seq, start, end, lng, lat)"""
    df = pd.DataFrame(rows, columns=["imsi", "stay_seq", "start_time", "end_time", "lng", "lat"])
    df["start_time"], df["end_time"] = pd.to_datetime(df["start_time"]), pd.to_datetime(df["end_time"])
    df["duration_min"] = (df["end_time"] - df["start_time"]).dt.total_seconds() / 60
    df["district"], df["aoi"], df["dist_xita_m"] = "甲区", None, 1000.0
    df["n_records"] = 5
    return df


def test_mask_id_keeps_only_last_four_digits():
    assert privacy.mask_id("460000009507329090") == "尾号9090"
    assert not touches_database(PKG / "privacy.py")


def test_night_counts_only_overlap_with_night_window():
    stay = _stay([("u1", 1, "2018-10-02 22:00", "2018-10-03 03:00", 123.4, 41.8),      # 跨 0 点：只算 0–3 点，180 分钟
                  ("u1", 2, "2018-10-03 04:00", "2018-10-03 05:30", 123.5, 41.8),      # 90 分钟
                  ("u2", 1, "2018-10-03 05:30", "2018-10-03 09:00", 123.4, 41.8)])     # 只重叠 30 分钟：识别不出
    night = dws.build_night(stay, "2018-10-03", S)
    assert list(night.columns) == ["imsi", "night_lng", "night_lat", "night_district", "night_dist_xita_m", "night_min"]
    assert night["imsi"].tolist() == ["u1"] and night.loc[0, "night_min"] == 180 and night.loc[0, "night_lng"] == 123.4


def test_night_window_comes_from_settings():
    stay = _stay([("u1", 1, "2018-10-03 05:30", "2018-10-03 09:00", 123.4, 41.8)])
    later = {"night": {"start_hour": 0, "end_hour": 8, "min_overlap_minutes": 60}}
    assert len(dws.build_night(stay, "2018-10-03", S)) == 0
    assert len(dws.build_night(stay, "2018-10-03", later)) == 1


def test_trip_needs_min_distance_and_has_fixed_columns():
    stay = _stay([("u1", 1, "2018-10-03 08:00", "2018-10-03 09:00", 123.400, 41.80),
                  ("u1", 2, "2018-10-03 09:30", "2018-10-03 10:30", 123.403, 41.80),    # 约 250 米：不算出行
                  ("u1", 3, "2018-10-03 11:00", "2018-10-03 12:00", 123.450, 41.80)])   # 约 4 公里：一次出行
    trip = dws.build_trip(stay, S)
    assert len(trip.columns) == 18 and trip.columns[:4].tolist() == ["imsi", "trip_seq", "o_seq", "d_seq"]
    assert trip[["o_seq", "d_seq", "trip_seq"]].values.tolist() == [[2, 3, 1]]
    assert trip.loc[0, "duration_min"] == 30 and trip.loc[0, "dist_m"] > 3_500


def test_no_business_numbers_in_dws():
    for f in dws_files():
        assert not numeric_constants(f) & {500, 30}, f"{f.name} 里写死了业务数字"
