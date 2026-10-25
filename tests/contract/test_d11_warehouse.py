"""D11 契约：配置哈希；分区写入在同一个事务里；生产库与入库；多日流水线不冲掉别的日期；开发库只放分析日；图表检查；依赖检查。"""
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pytest

from signal_mysql import database as mysql
from signal_insight import config, db, ingest, pipeline, viz
from _helpers import PKG, needs_data, ods_copy, sandbox


# ── 配置哈希 ──
def test_config_hash_depends_on_values_not_text(tmp_path):
    a = tmp_path / "a.yaml"; b = tmp_path / "b.yaml"; c = tmp_path / "c.yaml"
    a.write_text('version: "2.0.0"\nstay:\n  radius_m: 500\n  min_minutes: 30\n', encoding="utf-8")
    b.write_text('# 加一行注释、调换键的顺序\nversion: "2.0.0"\nstay:\n  min_minutes: 30\n  radius_m: 500\n', encoding="utf-8")
    c.write_text('version: "2.0.0"\nstay:\n  radius_m: 500\n  min_minutes: 20\n', encoding="utf-8")
    ha, hb, hc = (config.config_hash(config.load_settings(p)) for p in (a, b, c))
    assert ha == hb != hc and ha.startswith("2.0.0+") and len(ha) == len("2.0.0+") + 8


def test_paths_for_warehouse_and_landing():
    assert isinstance(config.WAREHOUSE_SCHEMA, str) and config.WAREHOUSE_SCHEMA
    assert config.LANDING_DIR == config.DATA_DIR / "landing"


# ── 事务 ──
def test_failed_write_keeps_the_old_partition(tmp_path):
    with sandbox(tmp_path) as con:
        db.write_partition(con, pd.DataFrame({"v": [1, 2, 3]}), "t", "D1")
        db.write_partition(con, pd.DataFrame({"v": [4, 5]}), "t", "D2")
        with pytest.raises(Exception):          # 上游把字段改成了嵌套结构：数据库存不了，插入必然失败
            db.write_partition(con, pd.DataFrame({"v": [{"嵌套": 1}]}), "t", "D2")
        got = mysql.read_frame("SELECT dt, COUNT(*) AS n FROM t GROUP BY dt ORDER BY dt", con)
    assert got["n"].tolist() == [3, 2]           # D2 的旧数据还在：删除被一起回滚


def test_partition_column_first_and_indexed(tmp_path):
    with sandbox(tmp_path) as con:
        db.write_partition(con, pd.DataFrame({"v": [1]}), "t", "D1")
        cols = [r[1] for r in mysql.column_result(con, "t")]
        idx = [r[1] for r in mysql.index_result(con, "t")]
    assert cols[0] == "dt" and any("dt" in i for i in idx)


def test_write_partition_refuses_single_day_tables(tmp_path):
    with sandbox(tmp_path) as con:
        db.replace_table(con, pd.DataFrame({"v": [1]}), "t")
        with pytest.raises(ValueError):
            db.write_partition(con, pd.DataFrame({"v": [2]}), "t", "D1")


def test_append_table_adds_new_columns(tmp_path):
    with sandbox(tmp_path) as con:
        db.append_table(con, pd.DataFrame({"step": ["a"]}), "log")
        db.append_table(con, pd.DataFrame({"step": ["b"], "config_version": ["2.0.0+x"]}), "log")
        got = mysql.read_frame("SELECT * FROM log", con)
    assert got["step"].tolist() == ["a", "b"] and pd.isna(got.loc[0, "config_version"])


# ── 开发库只放分析日 ──
def test_run_day_refuses_other_days():
    with pytest.raises(ValueError, match="生产库"):
        pipeline.run_day("2018-10-04")


# ── 图表检查 ──
def test_lint_passes_a_finished_figure_and_flags_bad_ones(tmp_path):
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(["a", "b"], [1, 2])
    viz.finish(fig, "西塔 19 点 2,037 人", "口径", config.SOURCE_NOTE, "lint_demo.png")
    assert viz.lint.lint_figure(fig) == []
    bad, ax1 = plt.subplots(figsize=(6, 4))
    ax1.twinx()
    ax1.set_title("没有数字的标题")
    problems = viz.lint.lint_figure(bad)
    assert any("viz.finish" in p for p in problems) and any("双轴" in p for p in problems)
    plt.close("all")


# ── 依赖检查 ──
def test_dependency_check_passes():
    r = subprocess.run([sys.executable, str(PKG.parents[1] / "tools" / "check_deps.py")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout


# ── 生产库：多日不互相覆盖（需要数据）──
@needs_data
def test_second_day_does_not_touch_the_first(tmp_path):
    """跑完第二天，第一天的结果一行不变。只看库里的结果，不依赖 run_partition 的返回值（D12 起它返回分区状态）。"""
    with ods_copy(tmp_path) as src, sandbox(tmp_path / "wh") as wh, sandbox(tmp_path / "part") as part:
        ingest.init_warehouse(src.schema, wh.schema)
        # 造一个“上游分区”：10-03 整天平移到 10-04（数据量正常，D12 的门禁会放行）
        raw = mysql.read_frame(
            "SELECT * FROM ods_signal WHERE timestamp>=1538496000000 AND timestamp<1538582400000", src)
        mysql.write_frame(raw.assign(timestamp=raw["timestamp"] + 86_400_000), "ods_signal", part,
                          if_exists="append", index=False)
        settings = config.load_settings()
        pipeline.refresh_dims(wh, settings)
        pipeline.run_partition(wh, settings, "2018-10-03")
        before = mysql.read_frame("SELECT * FROM dws_user_day WHERE dt='2018-10-03'", wh)
        dates = ingest.ingest_partition(wh, tmp_path / "part")
        pipeline.run_partition(wh, settings, "2018-10-04")
        after = mysql.read_frame("SELECT * FROM dws_user_day WHERE dt='2018-10-03'", wh)
        n04 = wh.execute("SELECT COUNT(*) FROM dws_user_day WHERE dt='2018-10-04'").fetchone()[0]
        versions = {r[0] for r in wh.execute("SELECT DISTINCT config_version FROM etl_log")}
    assert dates.index.tolist() == ["2018-10-04"]
    assert len(before) == 5_644 and int(before["is_evening_visitor"].sum()) == 3_310
    pd.testing.assert_frame_equal(before, after)     # 跑完 10-04，10-03 一行不变
    assert n04 > 5_000 and versions == {config.config_hash(settings)}
