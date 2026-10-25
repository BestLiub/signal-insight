"""集成测试（D13）：在迷你世界上跑完整条流水线，检查多日场景下的正确性。几秒钟跑完。"""
from contextlib import closing

import pandas as pd

from signal_mysql import database as mysql

from signal_insight import ingest, pipeline

from miniworld import D1, D2, D3, build_warehouse, fingerprint

TABLES = ["dwd_signal", "dws_stay", "dws_night", "dws_trip", "dws_user_day", "dws_stay_area", "dws_user_area_day",
          "dws_user_hour", "ads_area_hourly", "ads_area_segment", "ads_area_daily"]


def test_rerun_same_day_gives_identical_tables(tmp_path):
    wh, settings = build_warehouse(tmp_path)
    with closing(mysql.connect(wh)) as con:
        pipeline.run_partition(con, settings, D2)
        first = fingerprint(con, D2, TABLES)
        pipeline.run_partition(con, settings, D2)
        assert fingerprint(con, D2, TABLES) == first


def test_running_another_day_never_changes_this_day(tmp_path):
    """D11 的事故写成测试：先跑 D2 再跑 D1，D2 一行不变；D1 重跑过，D2 的回看窗口变了，登记为待重跑。"""
    wh, settings = build_warehouse(tmp_path)
    with closing(mysql.connect(wh)) as con:
        pipeline.run_partition(con, settings, D2)
        before = fingerprint(con, D2, TABLES)
        pipeline.run_partition(con, settings, D1)
        assert fingerprint(con, D2, TABLES) == before
        assert ingest.reg_get(con, D2)["pipeline_status"] == "stale"


def test_lookback_joins_stay_across_midnight(tmp_path):
    wh, settings = build_warehouse(tmp_path)
    with closing(mysql.connect(wh)) as con:
        pipeline.run_partition(con, settings, D1)
        pipeline.run_partition(con, settings, D2)
        stay = mysql.read_frame("SELECT * FROM dws_stay WHERE dt = ?", con, params=(D2,))
        night = mysql.read_frame("SELECT * FROM dws_night WHERE dt = ?", con, params=(D2,))
    assert stay["cross_day"].sum() == 20               # 每人一个跨午夜停留（前一晚 18 点起就在 A）
    assert (night["night_min"] == 360).all()           # 0–6 点整段都被覆盖


def test_gate_blocks_sparse_day_and_writes_nothing_downstream(tmp_path):
    wh, settings = build_warehouse(tmp_path, days=(D1, D2, D3), sparse=(D3,))
    with closing(mysql.connect(wh)) as con:
        assert pipeline.run_partition(con, settings, D3) == "blocked"
        assert con.execute("SELECT COUNT(*) FROM ads_dq_partition WHERE dt = ? AND pipeline_status = 'blocked'",
                           (D3,)).fetchone()[0] == 1
        for t in ["dwd_signal", "dws_stay", "ads_area_daily"]:
            if con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=?",
                           (t,)).fetchone()[0]:
                assert con.execute(f"SELECT COUNT(*) FROM {t} WHERE dt = ?", (D3,)).fetchone()[0] == 0


def test_areas_come_from_config_and_hotspot_is_written_once(tmp_path):
    wh, settings = build_warehouse(tmp_path)
    with closing(mysql.connect(wh)) as con:
        pipeline.run_partition(con, settings, D1)
        pipeline.run_partition(con, settings, D2)
        area = mysql.read_frame("SELECT * FROM dim_area", con).set_index("area")
        uad = mysql.read_frame("SELECT DISTINCT area FROM dws_user_area_day WHERE dt = ?", con, params=(D2,))
        ev = mysql.read_frame("SELECT area, evening_visitors FROM ads_area_daily WHERE dt = ?", con, params=(D2,)).set_index("area")
    assert set(area.index) == {"测试热点", "测试商圈"}
    assert (area.loc["测试热点", "center_lng"], area.loc["测试热点", "center_lat"]) == (123.400, 41.800)
    assert set(uad["area"]) == {"测试热点", "测试商圈"}       # 加区域只改配置，下游自动出现
    assert ev.loc["测试热点", "evening_visitors"] == 20
    assert pd.isna(ev.loc["测试商圈", "evening_visitors"])    # 16 点前就离开商圈：0 个傍晚访客，少于 5 人，抑制
