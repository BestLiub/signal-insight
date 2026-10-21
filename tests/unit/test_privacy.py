"""小样本抑制的单元测试（D09，学生写的参考版本）。"""
import pandas as pd
from signal_insight import privacy


def test_exactly_k_is_kept():
    out = privacy.suppress(pd.DataFrame({"n": [5]}), "n", 5)
    assert out.loc[0, "n"] == 5 and not out.loc[0, "suppressed"]


def test_original_is_not_modified():
    df = pd.DataFrame({"n": [1, 9]})
    privacy.suppress(df, "n", 5)
    assert df["n"].tolist() == [1, 9] and "suppressed" not in df
