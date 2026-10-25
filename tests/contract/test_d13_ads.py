"""D13 契约测试：分析区域、客群规则、隐私抑制、应用层。"""
import numpy as np
import pandas as pd
import pytest

from signal_insight import ads, config, dims, dws, geo, privacy

from _helpers import PKG, called_names, touches_database

SETTINGS = config.load_settings()
SQUARE = np.array([(0.0, 0.0), (0.02, 0.0), (0.02, 0.02), (0.0, 0.02)])


def _settings(areas):
    return {**SETTINGS, "areas": areas}


def test_dim_area_comes_from_settings_and_hotspot_coordinates_are_written_once():
    s = _settings([{"name": "热点", "kind": "hotspot"},
                   {"name": "站点", "kind": "circle", "lng": 0.5, "lat": 0.5, "radius_m": 300},
                   {"name": "商圈", "kind": "polygon"}])
    dim, poly = dims.build_dim_area(s, {"商圈": [SQUARE]})
    a = dim.set_index("area")
    h = SETTINGS["hotspot"]
    assert (a.loc["热点", "center_lng"], a.loc["热点", "center_lat"], a.loc["热点", "radius_m"]) == (h["lng"], h["lat"], h["radius_m"])
    assert a.loc["站点", "kind"] == "circle" and a.loc["站点", "radius_m"] == 300
    assert np.isclose(a.loc["商圈", "center_lng"], 0.01) and np.isclose(a.loc["商圈", "center_lat"], 0.01)
    assert set(poly["area"]) == {"商圈"}                      # 只有多边形区域有顶点
    with pytest.raises(ValueError, match="找不到"):
        dims.build_dim_area(_settings([{"name": "不存在的商圈", "kind": "polygon"}]), {})


def test_area_membership_allows_overlapping_areas():
    dim, poly = dims.build_dim_area(_settings([{"name": "圆", "kind": "circle", "lng": 0.01, "lat": 0.01, "radius_m": 500},
                                               {"name": "方", "kind": "polygon"}]), {"方": [SQUARE]})
    m = geo.area_membership([0.01, 0.5], [0.01, 0.5], dim, {"方": [SQUARE]})
    assert sorted(m.loc[m["idx"] == 0, "area"]) == ["圆", "方"] and (m["idx"] != 1).all()   # 一个点可以同时属于两个区域


def test_segment_rule_judges_before_rounding_and_in_fixed_order():
    """D13 需求卡 13.2：1.499 公里是周边居民；先判“不明”，再判“市外”，再判距离。"""
    out = dws.segment_by_night([1.499, 1.5, np.nan, 0.2], ["和平区", "和平区", None, "市外"], 1.5)
    assert list(out) == ["周边居民", "市内来访", "过夜地不明", "市外来访"]
    assert list(dws.segment_with_inbound(out, [False, True, False, False])) == ["周边居民", "外地来客", "过夜地不明", "外地来客"]


def test_suppress_blanks_derived_columns_too_and_always_returns_float():
    df = pd.DataFrame({"格子": list("abc"), "users": [3, 5, 12], "share": [0.15, 0.25, 0.6]})
    out = privacy.suppress(df, "users", 5, value_cols=["share"])
    assert np.isnan(out.loc[0, "share"]) and out.loc[1, "share"] == 0.25    # 占比 × 总数 = 人数：要一起藏
    none = privacy.suppress(df.iloc[1:], "users", 5)
    assert none["users"].dtype == "float64"                    # 没有格子被藏，类型也一样


def test_complementary_suppression_blocks_differencing():
    """总数公布时，同组只藏一个格子，“总数 − 其他格子”就能算出来；互补抑制保证至少藏两个。"""
    uad = pd.DataFrame({"imsi": [f"u{i}" for i in range(35)], "area": "甲", "evening_visitor": True,
                        "segment": ["市内来访"] * 20 + ["周边居民"] * 8 + ["外地来客"] * 5 + ["过夜地不明"] * 2})
    out = ads.build_area_segment(uad, SETTINGS)
    assert out["users"].isna().sum() >= 2
    assert len(uad) - out["users"].sum() > 2                   # 差出来的是两个格子之和，不是那 2 个人
    one = privacy.suppress_grouped(pd.DataFrame({"g": ["x"] * 3, "users": [3, 9, 20]}), "users", 5, "g")
    assert one["suppressed"].tolist() == [True, True, False]   # 藏的是剩下格子里最小的那个


def test_linkage_handles_area_pair_without_shared_visitors():
    """回归测试：某对区域没有共同访客时，sb[[...]] 会变成“选 0 列”（开发时真实出现过）。"""
    t = pd.Timestamp("2018-10-03 18:00")
    stay = pd.DataFrame({"imsi": ["u1", "u2"], "stay_seq": [1, 1], "start_time": [t, t], "end_time": [t + pd.Timedelta(hours=2)] * 2})
    stay_area = pd.DataFrame({"imsi": ["u1", "u2"], "stay_seq": [1, 1], "area": ["甲", "乙"], "dist_center_m": [0, 0]})
    uad = pd.DataFrame({"imsi": ["u1", "u2"], "area": ["甲", "乙"], "evening_visitor": [True, True]})
    out = ads.build_area_linkage(stay, stay_area, uad, "2018-10-03", SETTINGS)
    assert len(out) == 0 or out["users_any"].isna().all()      # 0 人 < 5，被抑制；没有可配对的区域时为空表


def test_radius_bands_cover_every_evening_visitor():
    uad = pd.DataFrame({"imsi": [f"u{i}" for i in range(40)], "area": "甲", "evening_visitor": True,
                        "night_dist_km": [0.5, 2, 4, 8, 15, 30, np.nan, 1.49] * 5})
    out = ads.build_area_radius(uad, SETTINGS)
    assert out["users"].sum() == 40
    assert out.loc[out["band"] == "1.5 公里内", "users"].iloc[0] == 10


def test_area_daily_suppresses_small_areas():
    uad = pd.DataFrame({"imsi": ["a", "b", "c"], "area": "甲", "evening_visitor": True, "stay_min": [60, 90, 120],
                        "after_late": False, "arrive_hour": 18.0, "night_dist_km": 2.0, "segment": "市内来访"})
    out = ads.build_area_daily(uad, pd.DataFrame({"area": ["甲"]}), SETTINGS)
    assert out["suppressed"].iloc[0] and out["stay_min_p50"].isna().iloc[0] and out["visitors_all"].isna().iloc[0]


def test_hex_bin_and_center_round_trip():
    rng = np.random.default_rng(0)
    lng, lat = 123.41 + rng.uniform(-0.1, 0.1, 2000), 41.81 + rng.uniform(-0.08, 0.08, 2000)
    q, r = geo.hex_bin(lng, lat, 123.41, 41.81, 550)
    cl, ca = geo.hex_center(q, r, 123.41, 41.81, 550)
    q2, r2 = geo.hex_bin(cl, ca, 123.41, 41.81, 550)
    assert (q == q2).all() and (r == r2).all() and geo.haversine(lat, lng, ca, cl).max() <= 550 * 1.001


@pytest.mark.parametrize("module", ["ads.py", "dws/area.py"])
def test_new_computation_modules_do_not_touch_the_database(module):
    assert not touches_database(PKG / module), f"{module} 是计算模块，不应读写数据库"


def test_ads_suppresses_through_privacy():
    """隐私代码唯一来源（docs/工程规范.md 第 9 条）：应用层不自己写“少于 k 就置空”，一律调 privacy。"""
    assert {"suppress", "suppress_grouped"} <= called_names(PKG / "ads.py")
