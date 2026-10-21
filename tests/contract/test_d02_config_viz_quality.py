"""D02 契约：config、viz（主题与出图收尾）、quality.dq_record。"""
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest
from signal_mysql import database as mysql

from signal_insight import config, quality, viz
from _helpers import PKG, imported_names, sandbox

SCHEMA_DEFAULTS = {"SIGNAL_INSIGHT_SCHEMA": "signal_insight",
                   "SIGNAL_CHECKPOINT_SCHEMA": "signal_checkpoint",
                   "SIGNAL_WAREHOUSE_SCHEMA": "signal_warehouse"}


def _schemas_in_fresh_process(**env) -> list[str]:
    """在全新的进程里 import config，读出三个库名；env 里给的环境变量覆盖当前终端的设置。"""
    clean = {k: v for k, v in os.environ.items() if k not in SCHEMA_DEFAULTS}
    code = "from signal_insight import config; print(config.DB_SCHEMA, config.CHECKPOINT_SCHEMA, config.WAREHOUSE_SCHEMA)"
    out = subprocess.run([sys.executable, "-c", code], env={**clean, **env}, capture_output=True, text=True, check=True)
    return out.stdout.split()


# ── config ──
def test_config_paths_are_derived_from_file_location_not_cwd():
    assert (config.PROJECT_ROOT / "src" / "signal_insight" / "config.py").resolve() == Path(config.__file__).resolve()
    assert config.DATA_DIR == config.PROJECT_ROOT / "data"
    assert config.IMAGE_DIR == config.PROJECT_ROOT / "image"


def test_config_schemas_are_names_with_course_defaults():
    """库是 MySQL 服务器上的名字，不是 data/ 里的文件。默认值固定；环境变量可以覆盖，设成空白时回落到默认。"""
    assert all(isinstance(s, str) and s for s in (config.DB_SCHEMA, config.CHECKPOINT_SCHEMA, config.WAREHOUSE_SCHEMA))
    assert _schemas_in_fresh_process() == list(SCHEMA_DEFAULTS.values())
    assert _schemas_in_fresh_process(SIGNAL_INSIGHT_SCHEMA="   ")[0] == "signal_insight"
    assert _schemas_in_fresh_process(SIGNAL_INSIGHT_SCHEMA="my_signal")[0] == "my_signal"


def test_config_reads_no_credentials():
    """config.py 要进 Git：账号、密码只在 .env.ps1 里，由 signal_mysql 去读；config 只认三个库名变量。"""
    tree = ast.parse((PKG / "config.py").read_text(encoding="utf-8"))
    env_like = {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]+", n.value)}
    extra = env_like - set(SCHEMA_DEFAULTS)
    assert not extra, f"config.py 不应读这些环境变量（账号、密码留给 signal_mysql）：{sorted(extra)}"


def test_config_constants():
    assert config.UTC_OFFSET_HOURS == 8
    assert config.ANALYSIS_DAY == "2018-10-03"
    assert config.SOURCE_NOTE.startswith("数据来源")


def test_config_is_the_bottom_layer():
    """docs/工程规范.md 第 3 条：config 不 import 项目里的任何模块，连 signal_mysql 也不 import（它只说库叫什么，不管怎么连）。"""
    bad = [n for n in imported_names(PKG / "config.py") if n.startswith((".", "signal_insight", "signal_mysql"))]
    assert not bad, f"config.py 不应 import 项目内模块：{bad}"


# ── viz ──
def test_importing_viz_does_not_touch_rcparams():
    """docs/工程规范.md 第 7 条：import 的时候不做事。在全新的进程里 import，rcParams 必须一项都不变。"""
    code = ("import matplotlib; snap = lambda: {k: str(v) for k, v in matplotlib.rcParams.items()}; "
            "before = snap(); import signal_insight.viz; after = snap(); "
            "diff = sorted(k for k in before if before[k] != after[k]); print('CHANGED', diff) if diff else print('SAME')")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert "SAME" in out, f"import signal_insight.viz 改了这些全局设置：{out.strip()}"


def test_palette_constants_exist():
    for name in ["MAIN", "MAIN_LIGHT", "MAIN_DARK", "MAIN_MID", "GRAY", "GRAY_DARK", "RED", "AMBER", "INK", "MUTED", "FAINT"]:
        assert isinstance(getattr(viz, name), str) and getattr(viz, name).startswith("#")
    assert viz.SEG_COLOR["过夜地不明"] == viz.GRAY            # “不明”永远是灰色


def test_apply_theme_returns_fonts_and_sets_rcparams():
    fonts = viz.apply_theme()
    assert isinstance(fonts, list) and fonts[-1] == "DejaVu Sans"
    assert list(plt.rcParams["font.family"]) == fonts


def test_finish_puts_title_first_and_returns_none_without_path():
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(["a", "b"], [1, 2])
    assert viz.finish(fig, "标题 42%", "副标题", "来源") is None
    assert fig.texts[0].get_text() == "标题 42%"            # 读回断言靠这一条
    assert {t.get_text() for t in fig.texts} >= {"标题 42%", "副标题", "来源"}
    plt.close(fig)


def test_finish_saves_into_image_dir_and_supports_constrained_layout():
    fig, ax = plt.subplots(figsize=(6, 4), layout="constrained")
    ax.plot([0, 1], [0, 1])
    name = "_contract_test_finish.png"
    out = viz.finish(fig, "标题", "副标题第一行\n第二行", "来源", name)
    try:
        assert Path(out) == config.IMAGE_DIR / name and Path(out).exists()
    finally:
        Path(out).unlink(missing_ok=True)
        plt.close(fig)


# ── quality.dq_record（在临时库里记，不碰 signal_insight 里真正的稽核表）──
def test_dq_record_overwrites_same_check_id(tmp_path):
    with sandbox(tmp_path) as con:
        quality.dq_record(con, "X-1", "完整性", "检查项", "表.字段", "结果 A", "警告")
        quality.dq_record(con, "X-1", "完整性", "检查项", "表.字段", "结果 B", "通过", evidence="证据", decision="处理")
        quality.dq_record(con, "X-2", "唯一性", "检查项", "表.字段", "结果 C", "不通过")
        df = mysql.read_frame("SELECT * FROM dq_check_result ORDER BY check_id", con)
    assert list(df.columns) == ["check_id", "dimension", "item", "field", "result", "status", "evidence", "decision"]
    assert df["check_id"].tolist() == ["X-1", "X-2"]
    assert df.loc[0, "result"] == "结果 B" and df.loc[0, "evidence"] == "证据" and df.loc[0, "decision"] == "处理"


def test_dq_record_rejects_unknown_status(tmp_path):
    with sandbox(tmp_path) as con:
        with pytest.raises(ValueError):
            quality.dq_record(con, "X-1", "完整性", "检查项", "表.字段", "结果", "还行")
        assert not mysql.table_exists(con, "dq_check_result")      # 状态不合法：一行都不写
