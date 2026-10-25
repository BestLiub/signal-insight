"""平台冒烟测试（D14）：不开浏览器、不装 streamlit / plotly 也能跑。

用假的 streamlit、plotly 把 app/ 下每一页从头执行到尾；数据用小型 DataFrame，数据库不参与。
"""
import importlib.util
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"


class _Sidebar:
    def selectbox(self, *a, **k):
        return (a[1][0] if len(a) > 1 and a[1] else None)

    def caption(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass


class _Col:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_streamlit():
    st = types.SimpleNamespace()
    st.set_page_config = lambda **k: None
    st.title = lambda *a, **k: None
    st.caption = lambda *a, **k: None
    st.info = lambda *a, **k: None
    st.warning = lambda *a, **k: None
    st.stop = lambda: None
    st.metric = lambda *a, **k: None
    st.dataframe = lambda *a, **k: None
    st.plotly_chart = lambda *a, **k: None
    st.selectbox = lambda *a, **k: (a[1][0] if len(a) > 1 and a[1] else None)
    st.columns = lambda n: [_Col() for _ in range(n)]
    st.sidebar = _Sidebar()
    return st


class _Fig:
    def update_layout(self, **k):
        return self

    def update_yaxes(self, **k):
        return self

    def add_annotation(self, **k):
        return self


def _fake_plotly():
    class Exp:
        def __getattr__(self, name):
            return lambda *a, **k: _Fig()

    class Go:
        Figure = _Fig
        Heatmap = lambda *a, **k: None
    px = Exp()
    go = Go()
    return types.SimpleNamespace(express=px, graph_objects=go)


@pytest.fixture(scope="module", autouse=True)
def _stubs():
    sys.modules["streamlit"] = _fake_streamlit()
    sys.modules["plotly"] = _fake_plotly()
    sys.modules["plotly.express"] = sys.modules["plotly"].express
    sys.modules["plotly.graph_objects"] = sys.modules["plotly"].graph_objects
    sys.path.insert(0, str(APP))
    yield
    sys.path.remove(str(APP))


@pytest.fixture(autouse=True)
def _fake_queries(monkeypatch):
    import lib.queries as Q
    monkeypatch.setattr(Q, "connect", lambda: object())
    monkeypatch.setattr(Q, "dates", lambda con: ["2018-10-03"])
    monkeypatch.setattr(Q, "areas", lambda con: ["西塔", "太原街商圈"])
    monkeypatch.setattr(Q, "area_daily", lambda con, dt: pd.DataFrame({
        "area": ["西塔"], "visitors_all": [100], "evening_visitors": [50], "stay_min_p50": [60.0],
        "censored_share": [0.2], "arrive_hour_p50": [18.0], "night_known_share": [0.7],
        "night_dist_km_p50": [2.0], "night_dist_km_p90": [5.0], "inbound_share": [0.1], "suppressed": [False]}))
    monkeypatch.setattr(Q, "area_hourly", lambda con, dt: pd.DataFrame({
        "area": ["西塔"] * 24, "hour": range(24), "users": list(range(10, 34)), "suppressed": [False] * 24}))
    monkeypatch.setattr(Q, "area_segment", lambda con, dt: pd.DataFrame({
        "area": ["西塔"], "segment": ["市内来访"], "users": [10.0], "share": [0.5], "suppressed": [False]}))
    monkeypatch.setattr(Q, "area_radius", lambda con, dt: pd.DataFrame({
        "area": ["西塔"], "band": ["1.5 公里内"], "band_order": [0], "users": [10.0], "cum_share": [0.5]}))
    monkeypatch.setattr(Q, "area_origin", lambda con, dt: pd.DataFrame({
        "area": ["西塔"], "origin": ["和平区"], "users": [10.0], "share": [0.5], "suppressed": [False]}))
    monkeypatch.setattr(Q, "area_linkage", lambda con, dt: pd.DataFrame({
        "area": ["西塔"], "other_area": ["太原街商圈"], "evening_visitors": [50], "users_any": [9.0],
        "users_before": [8.0], "users_after": [7.0], "share_any": [0.18], "share_before": [0.16], "share_after": [0.14]}))
    monkeypatch.setattr(Q, "hex_hourly", lambda con, dt: pd.DataFrame({
        "hour": [19], "q": [0], "r": [0], "users": [10], "center_lng": [123.41], "center_lat": [41.81], "size_m": [550]}))
    monkeypatch.setattr(Q, "dq_partition", lambda con: pd.DataFrame({
        "dt": ["2018-10-03"], "rows": [100], "users": [10], "volume_ratio": [1.0], "valid_hours": [24],
        "gate_status": ["pass"], "pipeline_status": ["done"], "is_synthetic": [0]}))
    monkeypatch.setattr(Q, "dq_rule", lambda con, dt: pd.DataFrame({
        "dt": ["2018-10-03"], "rule_id": ["G01"], "value": [1.0], "result": ["pass"]}))
    monkeypatch.setattr(Q, "metrics", lambda con: pd.DataFrame({
        "metric": ["西塔停留"], "definition": ["…"], "version": ["v2.2.0"]}))


def _run(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)


def test_home_runs():
    _run(APP / "Home.py")


@pytest.mark.parametrize("page", sorted((APP / "pages").glob("*.py")), ids=lambda p: p.stem)
def test_each_page_runs(page):
    _run(page)


def test_queries_only_touch_ads_and_dim_tables():
    text = (APP / "lib" / "queries.py").read_text(encoding="utf-8")
    for bad in ["FROM dwd_", "FROM dws_", "FROM ods_", "JOIN dwd_", "JOIN dws_", "JOIN ods_"]:
        assert bad not in text, f"平台只能读 ads_ / dim_：发现了 {bad}"
