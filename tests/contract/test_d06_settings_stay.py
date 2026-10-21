"""D06 契约：settings.yaml 与 load_settings；geo.dist_m；dws.find_segments、build_stay；热点参数不再有默认值。"""
import inspect
import numpy as np
import pandas as pd
import pytest
from signal_insight import config, dims, dws, geo
from _helpers import dws_files, numeric_constants

SETTINGS = {"stay": {"radius_m": 500, "min_minutes": 30}}
SQ = np.array([[123.0, 41.0], [124.0, 41.0], [124.0, 42.0], [123.0, 42.0]])


def _sig(rows):
    """rows: (imsi, 'HH:MM', lac_cell, lng, lat)"""
    df = pd.DataFrame(rows, columns=["imsi", "hm", "lac_cell", "lng", "lat"])
    df["ts"] = pd.to_datetime("2018-10-03 " + df.pop("hm"), format="ISO8601")
    return df


# ── 配置 ──
def test_settings_file_is_under_config_and_has_stay_and_hotspot():
    assert config.SETTINGS_PATH == config.PROJECT_ROOT / "config" / "settings.yaml"
    s = config.load_settings()
    assert s["stay"]["radius_m"] > 0 and s["stay"]["min_minutes"] > 0
    assert {"name", "top_n", "radius_m"} <= set(s["hotspot"])


def test_load_settings_reads_the_file_each_time(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("stay:\n  radius_m: 500\n", encoding="utf-8")
    assert config.load_settings(p)["stay"]["radius_m"] == 500
    p.write_text("stay:\n  radius_m: 1000\n", encoding="utf-8")
    assert config.load_settings(p)["stay"]["radius_m"] == 1000


def test_load_settings_rejects_gbk_files(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_bytes("hotspot:\n  name: 西塔\n".encode("gbk"))
    with pytest.raises(UnicodeDecodeError):
        config.load_settings(p)


def test_hotspot_parameters_have_no_defaults():
    """docs/工程规范.md 第 8 条：默认参数里的业务数字也是业务数字。"""
    params = inspect.signature(dims.build_dim_hotspot).parameters
    for name in ["top_n", "name", "radius_m"]:
        assert params[name].default is inspect.Parameter.empty, f"build_dim_hotspot 的 {name} 不应有默认值"


# ── 距离 ──
def test_dist_m_matches_vectorized_haversine():
    assert abs(geo.dist_m(41.8, 123.4, 41.81, 123.42) - geo.haversine(41.8, 123.4, 41.81, 123.42)) < 1e-6


# ── 切段 ──
def test_ping_pong_between_two_nearby_sites_is_one_segment():
    a, b = (123.400, 41.800), (123.403, 41.800)                        # 两站相距约 250 米
    rows = [("u1", f"10:{m:02d}", "A" if m % 2 == 0 else "B", *(a if m % 2 == 0 else b)) for m in range(0, 50, 5)]
    seg = dws.find_segments(_sig(rows), 500)
    assert len(seg) == 1 and seg.loc[0, "n_records"] == 10


def test_segments_never_cross_users():
    rows = [("u1", "10:00", "A", 123.4, 41.8), ("u1", "11:00", "A", 123.4, 41.8),
            ("u2", "11:30", "A", 123.4, 41.8), ("u2", "12:30", "A", 123.4, 41.8)]
    seg = dws.find_segments(_sig(rows), 500)
    assert seg["imsi"].tolist() == ["u1", "u2"]


def test_find_segments_does_not_depend_on_input_order():
    """函数自己排序；同一个人同一时刻两条不同基站的记录，按 lac_cell 决胜，结果和输入顺序无关。"""
    rows = [("u1", "10:00", "A", 123.400, 41.80), ("u1", "10:30", "B", 123.400, 41.80),
            ("u1", "10:30", "C", 123.430, 41.80), ("u1", "11:00", "C", 123.430, 41.80),
            ("u2", "09:00", "A", 123.400, 41.80)]
    sig = _sig(rows)
    base = dws.find_segments(sig, 500)
    for seed in range(5):
        pd.testing.assert_frame_equal(dws.find_segments(sig.sample(frac=1, random_state=seed), 500), base)


# ── 停留表 ──
def test_build_stay_keeps_only_long_segments_with_fixed_columns():
    rows = [("u1", "08:00:00.250", "A", 123.5, 41.5), ("u1", "08:45:00.900", "A", 123.5, 41.5),      # 45 分钟：停留
            ("u1", "09:30", "B", 123.9, 41.9), ("u1", "09:40", "B", 123.9, 41.9),                    # 10 分钟：经过
            ("u2", "10:00", "C", 125.0, 45.0), ("u2", "11:00", "C", 125.0, 45.0)]                    # 落在区县外
    stay = dws.build_stay(_sig(rows), SETTINGS, {"甲区": [SQ]}, {}, {"lng": 123.5, "lat": 41.5})
    assert list(stay.columns) == ["imsi", "stay_seq", "start_time", "end_time", "duration_min", "lng", "lat",
                                  "n_records", "district", "aoi", "dist_xita_m"]
    assert stay["imsi"].tolist() == ["u1", "u2"] and stay["stay_seq"].tolist() == [1, 1]
    assert stay.loc[0, "start_time"] == pd.Timestamp("2018-10-03 08:00:00")             # 精确到秒
    assert stay["district"].tolist() == ["甲区", "市外"] and stay.loc[0, "dist_xita_m"] == 0
    assert not stay.duplicated(["imsi", "stay_seq"]).any()


def test_build_stay_reads_thresholds_from_settings():
    rows = [("u1", "08:00", "A", 123.5, 41.5), ("u1", "08:45", "A", 123.5, 41.5)]
    hot = {"lng": 123.5, "lat": 41.5}
    assert len(dws.build_stay(_sig(rows), {"stay": {"radius_m": 500, "min_minutes": 60}}, {}, {}, hot)) == 0
    assert len(dws.build_stay(_sig(rows), {"stay": {"radius_m": 500, "min_minutes": 30}}, {}, {}, hot)) == 1


def test_no_business_numbers_in_dws():
    """docs/工程规范.md 第 8 条：500 米、30 分钟只在 settings.yaml。"""
    for f in dws_files():
        assert not numeric_constants(f) & {500, 30}, f"{f.name} 里写死了业务数字"
