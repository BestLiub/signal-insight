"""D03 契约：quality.profile。"""
import numpy as np
import pandas as pd

from signal_insight import quality


def test_profile_one_row_per_column_with_fixed_columns():
    df = pd.DataFrame({"a": [1, 2, None], "b": ["x", " ", None]})
    p = quality.profile(df)
    assert list(p.columns) == ["field", "dtype", "n_missing", "missing_rate", "n_unique", "example"]
    assert p["field"].tolist() == ["a", "b"]


def test_profile_counts_blank_strings_as_missing():
    p = quality.profile(pd.DataFrame({"b": ["x", " ", "", None]})).set_index("field")
    assert p.loc["b", "n_missing"] == 3
    assert np.isclose(p.loc["b", "missing_rate"], 0.75)


def test_profile_handles_empty_frame():
    p = quality.profile(pd.DataFrame({"a": pd.Series([], dtype=float)}))
    assert p.loc[0, "n_missing"] == 0 and p.loc[0, "missing_rate"] == 0
