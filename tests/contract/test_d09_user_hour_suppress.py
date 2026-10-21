"""D09 契约：dws.build_user_hour；privacy.suppress；整条流水线的对账（需要数据）。"""
import numpy as np
import pandas as pd
from signal_insight import config, dws, pipeline, privacy
from _helpers import needs_data, ods_copy

H = {"hourly": {"min_cover_minutes": 30}}


def test_suppress_blanks_small_cells_and_flags_them():
    df = pd.DataFrame({"格子": ["a", "b", "c"], "n_users": [3, 5, 12]})
    out = privacy.suppress(df, "n_users", 5)
    assert out["suppressed"].tolist() == [True, False, False]
    assert np.isnan(out.loc[0, "n_users"]) and out.loc[1, "n_users"] == 5        # 正好等于 k 的不抑制
    assert df["n_users"].tolist() == [3, 5, 12]                                  # 不改原表


def test_user_hour_prefers_stays_and_does_not_fill_gaps():
    t = pd.to_datetime
    stay = pd.DataFrame({"imsi": ["u1"], "start_time": t(["2018-10-03 08:10"]), "end_time": t(["2018-10-03 09:50"]),
                         "lng": [123.40], "lat": [41.80]})
    sig = pd.DataFrame({"imsi": ["u1"] * 3, "ts": t(["2018-10-03 08:20", "2018-10-03 11:05", "2018-10-03 11:40"]),
                        "lng": [123.0, 123.50, 123.52], "lat": [41.0, 41.90, 41.92]})
    uh = dws.build_user_hour(stay, sig, "2018-10-03", H, {}, {}, {"lng": 123.40, "lat": 41.80})
    assert uh["hour"].tolist() == [8, 9, 11]                # 10 点没有信令：不补
    assert uh["src"].tolist() == ["停留", "停留", "信令"]
    assert np.isclose(uh.loc[2, "lng"], 123.51) and uh.loc[0, "dist_xita_m"] == 0   # 中位数是浮点：用 isclose 比
    assert list(uh.columns) == ["imsi", "lng", "lat", "hour", "src", "district", "aoi", "dist_xita_m"]


def test_report_dir():
    assert config.REPORT_DIR == config.PROJECT_ROOT / "reports"


@needs_data
def test_pipeline_reconciles_all_tables(tmp_path):
    with ods_copy(tmp_path) as con:
        pipeline.run_day("2018-10-03", con.schema)
        n = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
             for t in ["dws_stay", "dws_night", "dws_trip", "dws_user_day", "dws_user_hour", "dim_metric"]}
        evening = con.execute("SELECT COUNT(*) FROM dws_user_day WHERE is_evening_visitor").fetchone()[0]
    assert n == {"dws_stay": 19_015, "dws_night": 3_607, "dws_trip": 11_055, "dws_user_day": 5_644,
                 "dws_user_hour": 102_859, "dim_metric": 9}
    assert evening == 3_310
