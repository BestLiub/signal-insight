"""D14 契约：平台只读聚合表、数据访问层只放行 ads_/dim_、导出只含聚合表、7 页都能从头执行。"""
from pathlib import Path

import pytest

from signal_insight import config

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"


def test_platform_code_never_mentions_detail_tables():
    for p in APP.rglob("*.py"):
        s = p.read_text(encoding="utf-8")
        for bad in ["FROM dwd_", "FROM dws_", "FROM ods_", "JOIN dwd_", "JOIN dws_", "JOIN ods_"]:
            assert bad not in s, f"{p.relative_to(ROOT)} 碰到了明细表：{bad}"


def test_queries_module_is_read_only():
    s = (APP / "lib" / "queries.py").read_text(encoding="utf-8")
    for bad in ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "CREATE "]:
        assert bad not in s.upper()


def test_seven_pages_exist():
    pages = sorted((APP / "pages").glob("*.py"))
    assert len(pages) == 6 and (APP / "Home.py").exists()      # 总览 + 6 个分页 = 7 页
    assert {p.stem.split("_", 1)[0] for p in pages} == {"1", "2", "3", "4", "5", "6"}


def test_export_only_ads_and_dim():
    s = (ROOT / "tools" / "export_ads.py").read_text(encoding="utf-8")
    assert '.startswith(("ads_", "dim_"))' in s


def test_dockerfile_runs_the_platform():
    s = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "streamlit" in s and "app/Home.py" in s
