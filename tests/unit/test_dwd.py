"""dwd 的单元测试：D02、D05 notebook 里的对账格搬到这里，不打开 notebook 也能一条命令全跑。

（参考写法：学生自己写，条目可以不同，但 D02 的对账数字都要覆盖到。）
只用只读连接读 signal_insight 的 ods_signal，不往库里写任何东西。
"""
import pandas as pd
import pytest
from signal_mysql import database as mysql

from signal_insight import config, dwd


def _ods_available() -> bool:
    try:
        con = mysql.connect(config.DB_SCHEMA, readonly=True)
    except Exception:                    # 终端没载入 .env.ps1、MySQL 没启动、库还没迁移……
        return False
    try:
        return mysql.table_exists(con, "ods_signal")
    finally:
        con.close()


needs_data = pytest.mark.skipif(not _ods_available(), reason=f"需要 MySQL 库 {config.DB_SCHEMA} 里的 ods_signal")


@pytest.fixture(scope="module")
def cleaned():
    con = mysql.connect(config.DB_SCHEMA, readonly=True)
    try:
        raw = mysql.read_frame("SELECT * FROM ods_signal", con)
    finally:
        con.close()
    return dwd.clean_signal(raw, config.ANALYSIS_DAY)


@needs_data
def test_d02_reconciliation_numbers(cleaned):
    out, steps = cleaned
    assert len(out) == 515_931                                   # D02 需求卡 2.6
    assert out["imsi"].nunique() == 5_644
    assert [s["rows_removed"] for s in steps] == [24, 8, 2_568, 14_297]
    assert [s["rows_after"] for s in steps] == [532_804, 532_796, 530_228, 515_931]


@needs_data
def test_clean_output_types(cleaned):
    out, _ = cleaned
    assert pd.api.types.is_datetime64_any_dtype(out["ts"])
    assert out["ts"].dt.strftime("%Y-%m-%d").eq(config.ANALYSIS_DAY).all()
    assert out["lac_cell"].str.fullmatch(r"\d+-\d+").all()


def test_empty_input_gives_empty_output():
    cols = ["timestamp", "imsi", "lac_id", "cell_id", "phone", "timestamp1", "tmp0", "tmp1", "nid", "npid"]
    raw = pd.DataFrame({c: pd.Series([], dtype="object") for c in cols}).astype({"timestamp": "int64", "imsi": "string"})
    out, steps = dwd.clean_signal(raw, config.ANALYSIS_DAY)
    assert len(out) == 0 and all(s["rows_removed"] == 0 for s in steps)
