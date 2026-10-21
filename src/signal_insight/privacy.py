"""隐私：脱敏（D07）、小样本抑制（D09）。

隐私相关的代码只有这一个来源（docs/工程规范.md 第 9 条）：哪天规则从“显示尾号 4 位”
改成“完全不显示”，只改这里一处。
"""
import pandas as pd


def mask_id(imsi) -> str:
    """展示用户时只显示 IMSI 尾号：返回 "尾号XXXX"。图表、报告、notebook 里展示明细时都先过它。"""
    return "尾号" + str(imsi)[-4:]


def suppress(df: pd.DataFrame, count_col: str, k: int) -> pd.DataFrame:
    """小样本抑制：count_col 少于 k 的行，把数字置空，并在 suppressed 列标 True。返回新表，不改原表。

    为什么置空而不是换成字符串 "<5"：换成字符串，这一列就成了文本，下游没法再求和、排序、画图；
    置空加标记列，程序能继续算，展示时再按 suppressed 显示成 "<5"。
    k 由调用方从 settings["privacy"]["min_cell_users"] 传进来。
    """
    out = df.copy()
    small = out[count_col] < k
    out[count_col] = out[count_col].where(~small)
    out["suppressed"] = small.to_numpy()
    return out
