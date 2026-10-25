"""隐私：脱敏（D07）、小样本抑制（D09）、互补抑制（D13）。

隐私相关的代码只有这一个来源（docs/工程规范.md 第 9 条）：哪天规则从“显示尾号 4 位”改成“完全不显示”，
或者抑制门槛从 5 人改成 10 人，只改这里（和 settings.yaml）一处。应用层（ads.py）生成对外的表时一律调用这里。
"""
import numpy as np
import pandas as pd


def mask_id(imsi) -> str:
    """展示用户时只显示 IMSI 尾号：返回 "尾号XXXX"。图表、报告、notebook 里展示明细时都先过它。"""
    return "尾号" + str(imsi)[-4:]


def suppress(df: pd.DataFrame, count_col: str, k: int, value_cols=()) -> pd.DataFrame:
    """小样本抑制：count_col 少于 k 的行，把人数和由它算出来的 value_cols **一起**置空，并在 suppressed 列标 True。

    返回新表，不改原表。为什么置空而不是换成字符串 "<5"：换成字符串，这一列就成了文本，下游没法再求和、排序、画图；
    置空加标记列，程序能继续算，展示时再按 suppressed 显示成 “<5”（空白会被读成“这里是 0”，含义完全不同）。
    为什么占比也要一起置空：占比 × 已公布的总数 = 被藏的人数（D13）。
    这些列一律转成小数：同一列的类型不该取决于今天有没有格子被藏。k 由调用方从 settings["privacy"] 传进来。
    """
    out = df.copy()
    small = (out[count_col] < k).to_numpy()
    for c in [count_col, *value_cols]:
        out[c] = out[c].astype("float64").where(~small)
    out["suppressed"] = small
    return out


def suppress_grouped(df: pd.DataFrame, count_col: str, k: int, group, value_cols=()) -> pd.DataFrame:
    """一级抑制 + 二级（互补）抑制（D13）。

    一级：少于 k 人的格子置空（同 suppress）。
    二级：同一组（比如同一区域的各客群）如果**恰好只有一个**格子被置空，而这一组的总数又在别处公布了，
    “总数 − 其他格子之和”就是被藏的那个数——这叫差分攻击，等于没藏。
    所以再把这一组剩下的格子里**最小的那个**也置空：损失的信息最少，减出来的差额变成两个数之和，拆不开。
    """
    out = suppress(df, count_col, k, value_cols)
    for _, idx in out.groupby(group).groups.items():
        g = out.loc[idx]
        if g["suppressed"].sum() == 1 and len(g) > 1:
            j = g.loc[~g["suppressed"], count_col].idxmin()
            out.loc[j, "suppressed"] = True
            out.loc[j, [count_col, *value_cols]] = np.nan
    return out


def suppress_columns(df: pd.DataFrame, cols: dict, k: int) -> pd.DataFrame:
    """一行里有好几个人数时（比如商圈联动的“去过 / 先去 / 后去”）逐个抑制：{人数列: [由它算出的列]}。

    少于 k 的人数和它的占比一起置空，不加标记列（每个人数各自判断，一个标记列表达不了）。
    """
    out = df.copy()
    for c, derived in cols.items():
        small = (out[c] < k).to_numpy()
        for x in [c, *derived]:
            out[x] = out[x].astype("float64").where(~small)
    return out


def drop_small(df: pd.DataFrame, count_col: str, k: int) -> pd.DataFrame:
    """地图格子这类“没有就是空白”的表：少于 k 人的格子直接不输出（六边形热力，D13）。"""
    return df[df[count_col] >= k].reset_index(drop=True)
