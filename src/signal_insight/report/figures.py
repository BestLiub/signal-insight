"""标准图：数据质量、清洗、客流分析。都从 ADS 表或运行记录表取数，按图表规范出图。

每个函数返回 (fig, facts)：facts 是标题里用到的关键数字，报告会把它登记进“数字溯源表”。
"""
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from signal_mysql import database as mysql

from .. import config
from ..viz import (MAIN, MAIN_LIGHT, MAIN_MID, GRAY, GRAY_DARK, RED, AMBER, INK, MUTED, FAINT,
                   finish, watermark)


def source(settings):
    return f"数据来源：沈阳移动信令样本（脱敏，2018 年国庆）；加工：signal_insight 配置 {config.config_hash(settings)}"


def _ok(con, table):
    return mysql.table_exists(con, table)


def fig_partition_overview(con, settings):
    """每个分区的数据量、门禁结论、是否完成：一行一天。"""
    t = mysql.read_frame("SELECT * FROM ads_dq_partition ORDER BY dt", con)
    if t.empty:
        return None, {}
    fig, ax = plt.subplots(figsize=(10, max(3.2, 0.5 * len(t) + 1.5)))
    col = {"done": MAIN, "blocked": RED, "failed": RED, "pending": GRAY, "stale": AMBER}
    ax.barh(t["dt"], t["rows"] / 1e4, color=[col.get(s, GRAY) for s in t["pipeline_status"]])
    for i, (n, s) in enumerate(zip(t["rows"] / 1e4, t["pipeline_status"])):
        ax.text(n + t["rows"].max() / 1e4 * 0.01, i, f"{n:,.1f} 万条 · {s}", va="center", fontsize=9)
    ax.invert_yaxis(); ax.set_xlabel("记录数（万条）"); ax.grid(axis="x")
    n_ok = int((t["pipeline_status"] == "done").sum())
    finish(fig, f"{len(t)} 个分区里 {n_ok} 个处理完成，{len(t) - n_ok} 个被拦下或待处理",
           "广告级质量看板：红 = 门禁不通过，蓝 = 完成，黄 = 待重跑", source(settings), "report_partition_overview.png")
    return fig, {"partition_rows": int(t["rows"].sum()), "partition_done": n_ok, "partition_total": len(t)}


def fig_gate_heatmap(con, settings):
    """门禁结果矩阵：行 = 分区，列 = 规则。"""
    r = mysql.read_frame("SELECT dt, rule_id, value, result FROM ads_dq_rule ORDER BY dt, rule_id", con)
    if r.empty:
        return None, {}
    dates, rules = sorted(r["dt"].unique()), sorted(r["rule_id"].unique())
    cmap = {"fail": RED, "warn": AMBER, "pass": MAIN_LIGHT}
    fig, ax = plt.subplots(figsize=(10, 1.4 + 0.5 * len(dates)))
    for i, d in enumerate(dates):
        for j, rule in enumerate(rules):
            row = r[(r["dt"] == d) & (r["rule_id"] == rule)].iloc[0]
            ax.add_patch(plt.Rectangle((j, i), 0.96, 0.9, color=cmap[row["result"]]))
            ax.text(j + 0.48, i + 0.45, f"{row['value']:.3g}", ha="center", va="center", fontsize=9,
                    color="white" if row["result"] == "fail" else INK)
    ax.set_xticks([j + 0.48 for j in range(len(rules))], rules, fontsize=9)
    ax.set_yticks([i + 0.45 for i in range(len(dates))], dates, fontsize=9)
    ax.set_xlim(0, len(rules)); ax.set_ylim(len(dates), 0); ax.grid(False)
    for sp in ax.spines.values():
        sp.set_visible(False)
    n_blocked = r.loc[r["result"] == "fail", "dt"].nunique()
    finish(fig, f"{len(dates)} 个分区里 {n_blocked} 个被门禁拦下",
           "红 = 不通过，黄 = 警告，浅蓝 = 通过；任何一条不通过，整个分区不通过", source(settings), "report_gate_heatmap.png")
    return fig, {"gate_blocked": n_blocked, "gate_total": len(dates)}


def fig_pipeline_timing(con, settings, day):
    """一个分区最近一次运行的各步耗时。"""
    log = mysql.read_frame("SELECT step, elapsed_sec FROM etl_log WHERE dt = ? AND run_id = "
                           "(SELECT run_id FROM etl_log WHERE dt = ? ORDER BY run_at DESC LIMIT 1)", con, params=(day, day))
    if log.empty:
        return None, {}
    t = log.groupby("step")["elapsed_sec"].sum().sort_values()
    fig, ax = plt.subplots(figsize=(10, max(4.6, 0.3 * len(t) + 2)))
    ax.barh(t.index, t.values, color=[MAIN if s == t.idxmax() else GRAY for s in t.index])
    for i, v in enumerate(t.values):
        ax.text(v + t.max() * 0.01, i, f"{v:.2f} 秒", va="center", fontsize=9)
    ax.set_xlabel("秒"); ax.grid(axis="x")
    finish(fig, f"处理 {day} 共 {t.sum():.1f} 秒，最慢的一步是 {t.idxmax()}（{t.max() / t.sum():.0%}）",
           "数据来自 etl_log；耗时与机器有关，看相对大小", source(settings), "report_pipeline_timing.png")
    return fig, {"pipeline_seconds": round(float(t.sum()), 1), "slowest_step": t.idxmax()}


def fig_area_hourly(con, settings, day):
    """每个分析区域一天的在场人数曲线。"""
    h = mysql.read_frame("SELECT area, hour, users FROM ads_area_hourly WHERE dt = ? ORDER BY area, hour", con, params=(day,))
    if h.empty:
        return None, {}
    fig, ax = plt.subplots(figsize=(10, 4.6))
    for area, g in h.groupby("area"):
        ax.plot(g["hour"], g["users"], marker="o", ms=3, lw=2, label=area)
    ax.set_xticks(range(0, 24, 3), [f"{x} 点" for x in range(0, 24, 3)])
    ax.set_ylabel("人"); ax.legend(frameon=False, ncol=3)
    finish(fig, f"{day} 各分析区域的一小时曲线：峰值错开出现",
           "每人每小时一个位置；区域可以重叠，各区域人数不能相加；口径：ads_area_hourly", source(settings), "report_area_hourly.png")
    return fig, {"area_hourly_peak": int(h["users"].max())}


def fig_segment(con, settings, day):
    """各区域的客群构成（抑制后的长表）。"""
    s = mysql.read_frame("SELECT area, segment, users, suppressed FROM ads_area_segment WHERE dt = ?", con, params=(day,))
    if s.empty:
        return None, {}
    fig, ax = plt.subplots(figsize=(10, 4.6))
    areas = sorted(s["area"].unique())
    segs = sorted(s["segment"].unique())
    bottom = np.zeros(len(areas))
    colors = [MAIN, MAIN_MID, AMBER, GRAY]
    for c, seg in zip(colors, segs):
        v = np.array([s[(s["area"] == a) & (s["segment"] == seg)]["users"].fillna(0).sum() for a in areas])
        ax.bar(areas, v, bottom=bottom, label=seg, color=c)
        bottom += v
    ax.set_ylabel("人"); ax.legend(frameon=False); ax.tick_params(axis="x", rotation=20)
    finish(fig, f"{day} 各区域傍晚访客的客群构成（少于 5 人的格子已隐藏）",
           "互补抑制：同一组只藏一格时再藏最小的一格；口径：ads_area_segment", source(settings), "report_segment.png")
    return fig, {"segment_evening": int(s["users"].fillna(0).sum())}


def fig_radius(con, settings, day):
    """各区域的辐射圈层累计占比。"""
    r = mysql.read_frame("SELECT area, band, band_order, users, cum_share FROM ads_area_radius WHERE dt = ? ORDER BY area, band_order", con, params=(day,))
    if r.empty:
        return None, {}
    fig, ax = plt.subplots(figsize=(10, 4.6))
    for area, g in r.groupby("area"):
        ax.plot(g["band_order"], g["cum_share"], marker="o", lw=2, label=area)
    ax.set_xticks(range(len(r["band"].drop_duplicates())), list(r["band"].drop_duplicates()), rotation=20)
    ax.set_ylim(0, 1.05); ax.set_ylabel("累计占比"); ax.legend(frameon=False)
    finish(fig, f"{day} 各区域辐射圈层：一半的客人在多远的范围内",
           "只在能识别过夜地的人里累计；过夜地不明的人已单列；口径：ads_area_radius", source(settings), "report_radius.png")
    return fig, {"radius_known": int(r["users"].fillna(0).sum())}


def fig_linkage(con, settings, day):
    """商圈联动：A 的傍晚访客里，先去过 / 后去过 B 的比例。"""
    l = mysql.read_frame("SELECT area, other_area, share_before, share_after FROM ads_area_linkage WHERE dt = ?", con, params=(day,))
    if l.empty:
        return None, {}
    fig, ax = plt.subplots(figsize=(10, max(3.6, 0.4 * len(l) + 1.5)))
    labels = [f"{r.area} ← {r.other_area}" for r in l.itertuples()]
    y = np.arange(len(l))
    ax.barh(y - 0.18, l["share_before"].fillna(0), height=0.36, color=MAIN, label="先去")
    ax.barh(y + 0.18, l["share_after"].fillna(0), height=0.36, color=MAIN_MID, label="后去")
    ax.set_yticks(y, labels, fontsize=9); ax.legend(frameon=False); ax.grid(axis="x")
    finish(fig, f"{day} 商圈联动：先去 / 后去的访客占比",
           "一人可属多类，比例不能相加；少于 5 人的格子已隐藏；口径：ads_area_linkage", source(settings), "report_linkage.png")
    return fig, {"linkage_pairs": len(l)}


def fig_hex_map(con, settings, day, hour=None):
    """六边形热力：某一小时（默认高峰小时）的格子人数。"""
    h = mysql.read_frame("SELECT hour, users, center_lng, center_lat, size_m FROM ads_hex_hourly WHERE dt = ?", con, params=(day,))
    if h.empty:
        return None, {}
    hour = int(h.groupby("hour")["users"].sum().idxmax()) if hour is None else hour
    g = h[h["hour"] == hour]
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(g["center_lng"], g["center_lat"], s=g["users"] / g["users"].max() * 260 + 20,
               c=g["users"], cmap="Blues", alpha=0.75, edgecolors="white", linewidths=0.4)
    ax.set_aspect(1 / np.cos(np.radians(g["center_lat"].mean())))
    ax.set_xlabel("经度"); ax.set_ylabel("纬度")
    finish(fig, f"{day} {hour} 点：中心城区六边形热力（少于 5 人的格子不显示）",
           "六边形边长 550 米；颜色越深人越多；口径：ads_hex_hourly", source(settings), "report_hex_map.png")
    return fig, {"hex_hour": hour, "hex_cells": len(g)}


def fig_origin(con, settings, day):
    """客源区县：傍晚访客的过夜地分布。"""
    o = mysql.read_frame("SELECT area, origin, users FROM ads_area_origin WHERE dt = ?", con, params=(day,))
    if o.empty:
        return None, {}
    fig, ax = plt.subplots(figsize=(10, 4.6))
    for area, g in o.groupby("area"):
        g = g.sort_values("users", ascending=False).head(10)
        ax.barh(g["origin"], g["users"], label=area, alpha=0.7)
    ax.invert_yaxis(); ax.set_xlabel("人"); ax.legend(frameon=False)
    finish(fig, f"{day} 各区域客源区县前 10 位",
           "少于 5 人的区县已隐藏；口径：ads_area_origin", source(settings), "report_origin.png")
    return fig, {"origin_rows": len(o)}


def fig_clean_funnel(con, settings, day):
    """清洗漏斗：每一步剔除了多少行。"""
    c = mysql.read_frame("SELECT * FROM ads_dq_clean_steps WHERE dt = ? ORDER BY step_no", con, params=(day,))
    if c.empty:
        return None, {}
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.bar(c["step_no"], c["rows_removed"], color=MAIN)
    for i, (n, r) in enumerate(zip(c["rows_removed"], c["rows_after"])):
        ax.text(c["step_no"].iloc[i], n, f"剔 {n:,}，余 {r:,}", ha="center", va="bottom", fontsize=8.5)
    ax.set_xticks(c["step_no"], c["step"], rotation=20)
    ax.set_ylabel("剔除行数")
    finish(fig, f"{day} 清洗共剔除 {int(c['rows_removed'].sum()):,} 行",
           "顺序与 D02 一致；口径：ads_dq_clean_steps", source(settings), "report_clean_funnel.png")
    return fig, {"clean_removed": int(c["rows_removed"].sum()), "clean_kept": int(c["rows_after"].iloc[-1])}
