"""D12 契约：质量门禁、基准、回看窗口、分区登记与入库幂等（讲师版未随文档发出，这里按文档契约重写）。"""
import pandas as pd
import pytest

from signal_mysql import database as mysql
from signal_insight import config, gate, ingest, pipeline, dws
from _helpers import needs_data, ods_copy, sandbox


def _raw(n, hour=12, invalid=0):
    ts = pd.Timestamp("2018-10-03 12:00") - pd.Timedelta(hours=8) + pd.Timedelta(hours=hour)
    ms = int(ts.timestamp() * 1000)
    rows = [{"timestamp": ms, "imsi": f"{i:018d}", "lac_id": 1, "cell_id": 1,
             "phone": "", "timestamp1": ms, "nid": 0, "npid": 0} for i in range(n)]
    for i in range(invalid):
        rows[i]["imsi"] = f"bad{i}"          # 非法，但仍是一个独立的 IMSI
    return pd.DataFrame(rows)


def test_profile_partition_counts_rates():
    raw = _raw(100, invalid=5)
    p = gate.profile_partition(raw, {"1-1"})
    assert p["rows"] == 100 and p["users"] == 100      # users 统计原始 IMSI 去重，不剔除格式异常
    assert p["imsi_invalid_rate"] == pytest.approx(0.05)
    assert p["cell_match_rate"] == 1.0 and p["key_null_rate"] == 0.0


def test_baseline_uses_median_and_bootstrap():
    s = config.load_settings()
    hist = pd.DataFrame({"rows": [100, 200, 100000], "rows_per_user": [10, 20, 10000]})
    base = gate.baseline(hist, s)
    assert base["rows"] == 200 and base["rows_per_user"] == 20      # 中位数不受坏分区影响
    empty = gate.baseline(pd.DataFrame(columns=["rows", "rows_per_user"]), s)
    assert empty["rows"] == s["gate"]["bootstrap"]["rows"] and empty["source"].startswith("bootstrap")


def test_evaluate_all_rules_and_overall():
    s = config.load_settings()
    profile = gate.profile_partition(_raw(100), {"1-1"})
    base = {"rows": 1_000_000, "rows_per_user": 1000, "source": "test"}   # 数据量只有基准的万分之一
    res = gate.evaluate(profile, base, s)
    assert len(res) == 7 and (res["result"] == "fail").any()
    assert gate.overall(res) == "fail"
    good = gate.profile_partition(_raw(1_000_000), {"1-1"})
    good["hourly"] = [41_667] * 24                       # 24 小时都有足够的数据
    ok = gate.evaluate(good, {"rows": 1_000_000, "rows_per_user": 1, "source": "test"}, s)
    assert gate.overall(ok) == "pass"


def test_build_stay_cross_midnight():
    t = pd.to_datetime
    times = pd.date_range("2018-10-03 23:50", "2018-10-04 00:20", freq="5min")
    sig = pd.DataFrame({"imsi": "u1", "ts": times, "lac_cell": "1-1", "lng": 123.41, "lat": 41.81})
    s = config.load_settings()
    hot = {"lng": 123.41, "lat": 41.81}
    stay = dws.build_stay(sig, s, {}, {}, hot, day="2018-10-04")
    assert len(stay) == 1 and bool(stay.loc[0, "cross_day"])
    assert 0 < stay.loc[0, "duration_in_day_min"] < stay.loc[0, "duration_min"]


def test_registry_transitions(tmp_path):
    with sandbox(tmp_path) as con:
        ingest.register_arrivals(con, {"2018-10-03": 100})
        assert ingest.reg_get(con, "2018-10-03")["pipeline_status"] == "pending"
        ingest.reg_set(con, "2018-10-03", pipeline_status="done")
        ingest.register_arrivals(con, {"2018-10-03": 10})
        r = ingest.reg_get(con, "2018-10-03")
        assert r["pipeline_status"] == "stale" and r["rows_ods"] == 110
        assert "2018-10-03" in ingest.todo(con)


@needs_data
def test_ingest_same_file_twice_is_idempotent(tmp_path):
    with ods_copy(tmp_path) as src, sandbox(tmp_path / "wh") as wh:
        ingest.init_warehouse(src.schema, wh.schema)
        before = int(wh.execute("SELECT COUNT(*) FROM ods_signal").fetchone()[0])
        first = ingest.ingest_partition(wh, tmp_path)              # 用同一个 schema 当“上游分区”
        mid = int(wh.execute("SELECT COUNT(*) FROM ods_signal").fetchone()[0])
        second = ingest.ingest_partition(wh, tmp_path)
        after = int(wh.execute("SELECT COUNT(*) FROM ods_signal").fetchone()[0])
    assert first.sum() > 0 and mid > before
    assert len(second) == 0 and after == mid                     # 同一个指纹只入库一次


@needs_data
def test_gate_blocks_short_day_and_keeps_good_day(tmp_path):
    with ods_copy(tmp_path) as src, sandbox(tmp_path / "wh") as wh:
        ingest.init_warehouse(src.schema, wh.schema)
        settings = config.load_settings()
        pipeline.refresh_dims(wh, settings)
        assert pipeline.run_partition(wh, settings, "2018-10-03") == "done"
        before = int(wh.execute("SELECT COUNT(*) FROM dws_stay WHERE dt='2018-10-03'").fetchone()[0])
        assert pipeline.run_partition(wh, settings, "2018-10-02") == "blocked"
        reg = ingest.registry(wh).set_index("dt")
        assert reg.loc["2018-10-02", "gate_status"] == "fail"
        assert reg.loc["2018-10-02", "pipeline_status"] == "blocked"
        assert int(wh.execute("SELECT COUNT(*) FROM dws_stay WHERE dt='2018-10-02'").fetchone()[0]) == 0
        assert int(wh.execute("SELECT COUNT(*) FROM dws_stay WHERE dt='2018-10-03'").fetchone()[0]) == before
