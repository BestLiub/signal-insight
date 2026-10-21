"""D08 契约：dws 变成包；客群标签的判断顺序；用户日宽表；口径表由配置渲染。"""
import numpy as np
import pandas as pd
import pytest
from signal_insight import config, dims, dws
from _helpers import PKG

V = {"visitor": {"evening_hour": 17, "late_hour": 23, "near_km": 1.5,
                 "linked_aois": {"visit_taiyuan": "太原街商圈", "visit_zhongjie": "中街商圈"}},
     "hotspot": {"radius_m": 500}}


def test_dws_is_a_package_and_old_imports_still_work():
    assert (PKG / "dws" / "__init__.py").exists() and not (PKG / "dws.py").exists()
    from signal_insight.dws import build_night, build_stay, build_trip, find_segments  # noqa: F401
    assert callable(dws.build_user_day) and callable(dws.classify_segment)


def test_classify_segment_checks_unknown_first():
    """NaN 和任何数比较都是 False：先判“不明”，否则识别不出过夜地的人会被归成“市内来访”。"""
    ud = pd.DataFrame({"night_dist_xita_km": [np.nan, 0.5, 1.0, 2.0],
                       "night_district": [None, "市外", "和平区", "皇姑区"]})
    assert dws.classify_segment(ud, V).tolist() == ["过夜地不明", "市外来访", "周边居民", "市内来访"]
    wider = {**V, "visitor": {**V["visitor"], "near_km": 3.0}}
    assert dws.classify_segment(ud, wider).tolist()[3] == "周边居民"


def test_build_user_day_one_row_per_user_with_labels():
    t = pd.to_datetime
    sig = pd.DataFrame({"imsi": ["u1", "u1", "u2", "u2"],
                        "ts": t(["2018-10-03 08:00", "2018-10-03 18:00", "2018-10-03 07:00", "2018-10-03 12:00"]),
                        "lng": [123.4, 123.4, 120.0, 123.4], "lat": [41.8, 41.8, 40.0, 41.8],
                        "district": ["和平区", "和平区", "市外", "和平区"]})
    stay = pd.DataFrame({"imsi": ["u1"], "stay_seq": [1], "start_time": t(["2018-10-03 16:00"]),
                         "end_time": t(["2018-10-03 18:00"]), "duration_min": [120.0], "lng": [123.4], "lat": [41.8],
                         "n_records": [3], "district": ["和平区"], "aoi": ["太原街商圈"], "dist_xita_m": [200.0]})
    trip = pd.DataFrame(columns=["imsi", "dist_m"])
    night = pd.DataFrame({"imsi": ["u1"], "night_lng": [123.4], "night_lat": [41.8], "night_district": ["和平区"],
                          "night_dist_xita_m": [800.0], "night_min": [300.0]})
    ud = dws.build_user_day(sig, stay, trip, night, "2018-10-03", V).set_index("imsi")
    assert len(ud) == 2
    assert ud.loc["u1", "is_evening_visitor"] and ud.loc["u1", "visit_taiyuan"] and not ud.loc["u1", "visit_zhongjie"]
    assert ud.loc["u1", "segment"] == "周边居民" and ud.loc["u2", "segment"] == "过夜地不明"
    assert ud.loc["u2", "inbound"] and ud.loc["u2", "segment_v2"] == "外地来客"          # 当天从市外进城
    assert ud.loc["u2", "n_stays"] == 0                                         # 没有停留的人不丢，记 0


def test_render_replaces_placeholders_and_rejects_unknown_ones():
    s = {"stay": {"min_minutes": 30}, "visitor": {"near_km": 1.5}}
    assert dims.render("≥ {stay.min_minutes} 分钟，{visitor.near_km} 公里", s) == "≥ 30 分钟，1.5 公里"
    with pytest.raises(KeyError):
        dims.render("{stay.radius_m}", s)


def test_dim_metric_is_rendered_from_the_settings_file():
    settings = config.load_settings()
    m = dims.build_dim_metric(settings)
    assert list(m.columns) == ["metric", "meaning", "definition", "params", "source_table", "version"]
    assert len(m) == len(settings["metrics"]) and not m.apply(lambda c: c.str.contains("{", regex=False)).any().any()
    assert (m["version"] == f"v{settings['version']}").all()


def test_user_day_code_has_no_area_names():
    """联动商圈来自 settings：代码里不写“太原街商圈”。"""
    assert "太原街" not in (PKG / "dws" / "user_day.py").read_text(encoding="utf-8").split('"""', 2)[-1]
