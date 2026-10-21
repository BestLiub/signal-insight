"""D05 契约：db、dwd、dims、pipeline；以及“计算模块不碰数据库”。

写库的测试都在临时库 test_course_xxx 里跑（_helpers.sandbox），跑完连库删掉；
signal_insight 只读：“需要数据”的测试从那里复制 ods_ 表，你自己建的表一张都不动。
"""
import numpy as np
import pandas as pd
import pytest
from signal_mysql import database as mysql

from signal_insight import config, db, dims, dwd, pipeline
from _helpers import PKG, count_elsewhere, needs_data, ods_copy, sandbox, touches_database

COLS = ["timestamp", "imsi", "lac_id", "cell_id", "phone", "timestamp1", "tmp0", "tmp1", "nid", "npid"]
T0 = 1538524800000                      # 2018-10-03 08:00:00 北京时间（UTC 00:00）


def _raw(rows):
    return pd.DataFrame(rows, columns=COLS)


# ── db ──
def test_write_partition_is_idempotent_and_keeps_other_days(tmp_path):
    df3 = pd.DataFrame({"dt": ["2018-10-03"] * 3, "v": [1, 2, 3]})
    df4 = pd.DataFrame({"dt": ["2018-10-04"] * 2, "v": [7, 8]})
    with sandbox(tmp_path) as con:
        assert db.write_partition(con, df3, "t", "2018-10-03") == 3
        db.write_partition(con, df4, "t", "2018-10-04")
        db.write_partition(con, df3, "t", "2018-10-03")          # 重跑同一天
        got = mysql.read_frame("SELECT dt, COUNT(*) AS n FROM t GROUP BY dt ORDER BY dt", con)
        n_elsewhere = count_elsewhere(con.schema, "t")           # 写完就提交：别的连接也看得见
        indexes = mysql.index_names(con)
    assert got["dt"].tolist() == ["2018-10-03", "2018-10-04"] and got["n"].tolist() == [3, 2]
    assert n_elsewhere == 5
    assert "idx_t_dt" in indexes                                 # 分区列有索引：按 dt 删除不扫全表


def test_replace_table_is_repeatable_and_keeps_milliseconds(tmp_path):
    ts = pd.Series([pd.Timestamp("2018-10-03 08:00:01"), pd.Timestamp("2018-10-03 08:00:01.250")])
    with sandbox(tmp_path) as con:
        assert db.replace_table(con, pd.DataFrame({"ts": ts}), "t") == 2
        assert db.replace_table(con, pd.DataFrame({"ts": ts}), "t") == 2          # 再替换一次：不翻倍
        precision = con.execute("SELECT datetime_precision FROM information_schema.columns "
                                "WHERE table_schema = DATABASE() AND table_name = ? AND column_name = ?",
                                ("t", "ts")).fetchone()[0]
        as_text = [r[0] for r in con.execute("SELECT CAST(ts AS CHAR) FROM t ORDER BY ts")]
        back = mysql.read_frame("SELECT ts FROM t ORDER BY ts", con)["ts"]
        n_elsewhere = count_elsewhere(con.schema, "t")
    assert precision == 3                                                          # 存成 DATETIME(3)：真正的时间类型
    assert as_text == ["2018-10-03 08:00:01.000", "2018-10-03 08:00:01.250"]      # 毫秒为 0 也保留三位
    assert pd.api.types.is_datetime64_any_dtype(back) and back.tolist() == ts.tolist()   # 读回来就是时间，不用再解析
    assert n_elsewhere == 2


def test_append_table_adds_rows_and_new_columns(tmp_path):
    with sandbox(tmp_path) as con:
        assert db.append_table(con, pd.DataFrame({"step": ["a"], "rows_out": [1]}), "t_log") == 1
        assert db.append_table(con, pd.DataFrame({"step": ["b"], "rows_out": [2], "note": ["新列"]}), "t_log") == 1
        got = mysql.read_frame("SELECT step, rows_out, note FROM t_log ORDER BY step", con)
        n_elsewhere = count_elsewhere(con.schema, "t_log")
    assert got["step"].tolist() == ["a", "b"] and got["rows_out"].tolist() == [1, 2]
    assert pd.isna(got.loc[0, "note"]) and got.loc[1, "note"] == "新列"         # 后来多出的列自动加上，旧行为空
    assert n_elsewhere == 2


@needs_data
def test_connect_defaults_to_config_schema():
    con = db.connect()
    try:
        current = con.execute("SELECT DATABASE()").fetchone()[0]
    finally:
        con.close()
    assert current == config.DB_SCHEMA


def test_connect_accepts_another_schema(tmp_path):
    with sandbox(tmp_path) as box:
        con = db.connect(box.schema)
        try:
            current = con.execute("SELECT DATABASE()").fetchone()[0]
        finally:
            con.close()
    assert current == box.schema


# ── dwd ──
def test_to_local_adds_utc_offset():
    assert dwd.to_local(pd.Series([T0])).iloc[0] == pd.Timestamp("2018-10-03 08:00:00")


def test_clean_signal_order_steps_and_key_format():
    raw = _raw([
        [T0, "460000000000000001", 16789.0, 67567924.0, "86100", T0, None, " ", 4, "#*#1"],
        [T0, "460000000000000001", 16789.0, 67567924.0, "86100", T0, None, " ", 4, "#*#1"],   # 完全重复
        [T0, None, 16789.0, 1.0, "86100", T0, None, " ", 4, "#*#1"],                          # 缺 imsi
        [T0, "46000000000000*002", 16789.0, 1.0, "86100", T0, None, " ", 4, "#*#1"],          # 格式异常
        [T0 - 86_400_000, "460000000000000003", 1.0, 2.0, "86100", T0, None, " ", 4, "#*#1"],  # 10-02
        [T0 + 60_000, "460000000000000000", 2.0, 3.0, "86100", T0, None, " ", 5, "#*#1"],
    ])
    out, steps = dwd.clean_signal(raw, "2018-10-03")
    assert [s["rows_removed"] for s in steps] == [1, 1, 1, 1]
    assert steps[-1]["rows_after"] == len(out) == 2
    assert list(out.columns) == ["imsi", "ts", "dt", "lac_id", "cell_id", "nid", "lac_cell"]
    assert out["imsi"].tolist() == ["460000000000000000", "460000000000000001"]        # 按 imsi、ts 排好序
    assert set(out["lac_cell"]) == {"16789-67567924", "2-3"}                           # 不能拼出 "16789.0-…"
    assert (out["dt"] == "2018-10-03").all()


def test_clean_signal_does_not_modify_input():
    raw = _raw([[T0, "460000000000000001", 1.0, 2.0, "86100", T0, None, " ", 4, "#"]])
    before = raw.copy()
    dwd.clean_signal(raw, "2018-10-03")
    pd.testing.assert_frame_equal(raw, before)


# ── dims ──
def test_build_dim_cell_sites_districts_and_unique_key():
    sq = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=float)
    ods_cell = pd.DataFrame({"lng": [1, 1, 50, np.nan], "lat": [1, 1, 50, 1], "lac_cell": ["1-1", "1-2", "2-1", "3-1"]})
    dim = dims.build_dim_cell(ods_cell, {"甲区": [sq]}, {"商圈A": [sq / 2]})
    assert list(dim.columns) == ["lac_cell", "site_id", "lng", "lat", "district", "aoi"]
    assert dim["lac_cell"].tolist() == ["1-1", "1-2", "2-1"]                          # 缺坐标的扇区去掉
    assert dim["site_id"].tolist() == ["S00001", "S00001", "S00002"]                   # 坐标相同 = 一个站点
    assert dim["district"].tolist() == ["甲区", "甲区", "市外"]
    assert dim["aoi"].iloc[0] == "商圈A" and pd.isna(dim["aoi"].iloc[2])


def test_build_dim_hotspot_weights_top_sites_by_users():
    dim_cell = pd.DataFrame({"lac_cell": ["a", "b"], "site_id": ["S1", "S2"], "lng": [0.0, 10.0], "lat": [0.0, 0.0]})
    d = pd.DataFrame({"imsi": ["u1", "u2", "u3", "u1"], "lac_cell": ["a", "a", "a", "b"]})
    hot = dims.build_dim_hotspot(d, dim_cell, top_n=2, name="西塔", radius_m=500)   # 参数写全：D06 起没有默认值
    assert hot.loc[0, "name"] == "西塔" and hot.loc[0, "radius_m"] == 500
    assert np.isclose(hot.loc[0, "lng"], 2.5)                                          # (0×3 + 10×1) / 4


# ── 计算模块不碰数据库（docs/工程规范.md 第 4 条，D05 起强制）──
@pytest.mark.parametrize("module", ["dwd.py", "dims.py", "geo.py"])
def test_computation_modules_do_not_touch_the_database(module):
    assert not touches_database(PKG / module), f"{module} 是计算模块，不应读写数据库"


def test_pipeline_step_records_rows_and_time():
    @pipeline.step
    def demo(df):
        return df.head(2)

    out = demo(pd.DataFrame({"a": range(5)}))
    assert len(out) == 2 and demo.__name__ == "demo"          # functools.wraps：名字不变


# ── 整条流水线（需要数据；在只放了 ods_ 表的临时库里跑）──
@needs_data
def test_run_day_reconciles_and_is_idempotent(tmp_path):
    with ods_copy(tmp_path) as con:
        log1 = pipeline.run_day("2018-10-03", con.schema)        # 第二个参数给库名：流水线写进临时库
        pipeline.run_day("2018-10-03", con.schema)               # 重跑同一天
        n_dwd = con.execute("SELECT COUNT(*) FROM dwd_signal WHERE dt = '2018-10-03'").fetchone()[0]
        n_users = con.execute("SELECT COUNT(DISTINCT imsi) FROM dwd_signal").fetchone()[0]
        n_cell = con.execute("SELECT COUNT(*) FROM dim_cell").fetchone()[0]
        hot = con.execute("SELECT name FROM dim_hotspot").fetchone()[0]
        runs = con.execute("SELECT COUNT(DISTINCT run_id) FROM etl_log").fetchone()[0]
    assert (n_dwd, n_users, n_cell, hot) == (515_931, 5_644, 49_948, "西塔")
    assert runs == 2
    assert {"step", "rows_out", "elapsed_sec"} <= set(log1.columns)
