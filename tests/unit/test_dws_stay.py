"""停留识别的单元测试（D06，学生写的参考版本）。"""
import pandas as pd
from signal_insight import dws

R = 500


def sig(rows):
    df = pd.DataFrame(rows, columns=["imsi", "hm", "lac_cell", "lng", "lat"])
    df["ts"] = pd.to_datetime("2018-10-03 " + df.pop("hm"))
    return df


def test_ping_pong_is_merged():
    rows = [("u", "10:00", "A", 123.400, 41.8), ("u", "10:05", "B", 123.404, 41.8),
            ("u", "10:10", "A", 123.400, 41.8), ("u", "10:15", "B", 123.404, 41.8)]
    assert len(dws.find_segments(sig(rows), R)) == 1


def test_segment_does_not_cross_users():
    rows = [("u1", "10:00", "A", 123.4, 41.8), ("u2", "10:01", "A", 123.4, 41.8)]
    assert len(dws.find_segments(sig(rows), R)) == 2


def test_short_segment_is_not_a_stay():
    rows = [("u", "10:00", "A", 123.4, 41.8), ("u", "10:20", "A", 123.4, 41.8)]
    stay = dws.build_stay(sig(rows), {"stay": {"radius_m": R, "min_minutes": 30}}, {}, {}, {"lng": 123.4, "lat": 41.8})
    assert len(stay) == 0


def test_empty_input_gives_empty_output():
    empty = sig([]).astype({"lng": float, "lat": float})
    assert len(dws.find_segments(empty, R)) == 0
