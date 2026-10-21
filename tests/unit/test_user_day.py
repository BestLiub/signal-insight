"""客群标签的单元测试（D08，学生写的参考版本）。"""
import numpy as np
import pandas as pd
from signal_insight import dws

S = {"visitor": {"near_km": 1.5}}


def test_unknown_night_place_is_not_in_city():
    ud = pd.DataFrame({"night_dist_xita_km": [np.nan], "night_district": [None]})
    assert dws.classify_segment(ud, S).iloc[0] == "过夜地不明"


def test_outside_city_beats_near():
    ud = pd.DataFrame({"night_dist_xita_km": [0.3], "night_district": ["市外"]})
    assert dws.classify_segment(ud, S).iloc[0] == "市外来访"
