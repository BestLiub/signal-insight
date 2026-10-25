"""应用层（ads_）：给报告和平台用的聚合表（D13）。平台只读 ads_ 和 dim_ 表，不碰明细。

纯计算（docs/工程规范.md 第 4 条）：输入是汇总层的表和维表，输出是 DataFrame，写库在 pipeline。
小样本抑制在**生成表的时候**就做完（第 9 条）：导出、截图、接口都拿不到小格子的数，而不是靠页面把它藏起来。
抑制的代码一律调用 privacy（隐私代码唯一来源），这里只决定“哪张表、按什么分组、哪些列跟着人数一起藏”。

区域可以重叠：西塔 500 米圈和太原街商圈边界有交集。这里每个区域各算各的，所以“各区域人数相加”会重复计数；
要做互斥划分（比如堆叠面积图），得先定优先级再分配。

表名和列名与旧讲师包 v2 的 ADS 相同：报告、平台的查询都按这个契约写。
"""
import json

import numpy as np
import pandas as pd

from . import geo, privacy

OUTSIDER = "外地来客"


def _k(settings):
    return settings["privacy"]["min_cell_users"]


def _evening(uad):
    return uad[uad["evening_visitor"]]


def build_area_hourly(user_hour, dim_area, area_polys, settings):
    """每个区域每小时的在场人数，以及占当小时可定位人数的比例。"""
    m = geo.area_membership(user_hour["lng"], user_hour["lat"], dim_area, area_polys)
    hit = user_hour.iloc[m["idx"]][["imsi", "hour"]].reset_index(drop=True).assign(area=m["area"].to_numpy())
    grid = pd.MultiIndex.from_product([dim_area["area"], range(24)], names=["area", "hour"])
    users = hit.groupby(["area", "hour"])["imsi"].nunique().reindex(grid, fill_value=0)
    out = users.rename("users").reset_index()
    locatable = user_hour.groupby("hour")["imsi"].nunique().reindex(range(24), fill_value=0)
    out["locatable"] = out["hour"].map(locatable)
    out["share"] = (out["users"] / out["locatable"].replace(0, np.nan)).round(4)
    return privacy.suppress(out, "users", _k(settings), value_cols=["share"])


def build_area_segment(uad, settings):
    """每个区域的傍晚访客按客群拆分。同一区域的各客群加起来就是公布的总数，所以要互补抑制。"""
    out = _evening(uad).groupby(["area", "segment"]).size().rename("users").reset_index()
    out["share"] = (out["users"] / out.groupby("area")["users"].transform("sum")).round(4)
    return privacy.suppress_grouped(out, "users", _k(settings), "area", value_cols=["share"])


def build_area_daily(uad, dim_area, settings):
    """每个区域一行的日指标：访客数、傍晚访客数、停留时长、删失比例、客源距离、外地来客占比。"""
    rows = []
    for area in dim_area["area"]:
        a = uad[uad["area"] == area]
        e = _evening(a)
        d = e["night_dist_km"].dropna()
        rows.append({
            "area": area, "visitors_all": len(a), "evening_visitors": len(e),
            "stay_min_p50": e["stay_min"].median(), "censored_share": e["after_late"].mean(),
            "arrive_hour_p50": e["arrive_hour"].median(),
            "night_known_share": e["night_dist_km"].notna().mean(),
            "night_dist_km_p50": d.median(), "night_dist_km_p90": d.quantile(0.9),
            "inbound_share": (e["segment"] == OUTSIDER).mean(),
        })
    out = pd.DataFrame(rows)
    value_cols = [c for c in out.columns if c not in ("area", "visitors_all", "evening_visitors")]
    out[value_cols] = out[value_cols].astype("float64").round(4)
    out = privacy.suppress(out, "evening_visitors", _k(settings), value_cols=value_cols)
    return privacy.suppress_columns(out, {"visitors_all": []}, _k(settings))


def radius_band_labels(bands):
    """辐射圈层的档位名：[1.5, 3, …] → “1.5 公里内”“1.5–3 公里”…“20 公里以上”“过夜地不明”。"""
    labels = [f"{bands[0]:g} 公里内"]
    labels += [f"{a:g}–{b:g} 公里" for a, b in zip(bands[:-1], bands[1:])]
    labels += [f"{bands[-1]:g} 公里以上", "过夜地不明"]
    return labels


def build_area_radius(uad, settings):
    """辐射圈层：傍晚访客的过夜地离区域中心多远。cum_share 只在能识别过夜地的人里累计。"""
    bands = settings["ads"]["radius_bands_km"]
    labels = radius_band_labels(bands)
    e = _evening(uad).copy()
    cut = pd.cut(e["night_dist_km"], [-np.inf, *bands, np.inf], labels=labels[:-1], right=False)
    e["band"] = cut.astype(object).where(e["night_dist_km"].notna(), labels[-1])
    grid = pd.MultiIndex.from_product([sorted(e["area"].unique()), labels], names=["area", "band"])
    out = e.groupby(["area", "band"]).size().reindex(grid, fill_value=0).rename("users").reset_index()
    out["band_order"] = out["band"].map({b: i for i, b in enumerate(labels)})
    out["share"] = (out["users"] / out.groupby("area")["users"].transform("sum")).round(4)
    known = out[out["band"] != labels[-1]].copy()
    known["cum_share"] = (known.groupby("area")["users"].cumsum()
                          / known.groupby("area")["users"].transform("sum")).round(4)
    out = out.merge(known[["area", "band", "cum_share"]], on=["area", "band"], how="left")
    out = privacy.suppress_grouped(out, "users", _k(settings), "area", value_cols=["share"])
    # 累计占比也会泄露：相邻两档的累计占比相减就是被藏那一档的占比。从第一个被藏的档起，后面的累计占比都置空
    first = out[out["suppressed"] & out["cum_share"].notna()].groupby("area")["band_order"].min()
    out["cum_share"] = out["cum_share"].where(~(out["band_order"] >= out["area"].map(first).fillna(np.inf)))
    return out


def build_area_origin(uad, settings):
    """客源区县：傍晚访客的过夜地在哪个区县。"""
    e = _evening(uad).copy()
    e["origin"] = e["night_district"].fillna("过夜地不明")
    out = e.groupby(["area", "origin"]).size().rename("users").reset_index()
    out["share"] = (out["users"] / out.groupby("area")["users"].transform("sum")).round(4)
    out = out.sort_values(["area", "users"], ascending=[True, False])
    return privacy.suppress_grouped(out, "users", _k(settings), "area", value_cols=["share"])


def build_area_linkage(stay, stay_area, uad, day, settings):
    """商圈联动：A 的傍晚访客里，当天也在 B 停留过的人；以及“先去 B 再来 A”“离开 A 后去 B”的人。

    先去 B：B 的停留在 A 傍晚那次停留开始之前结束（和 D10 需求卡的口径相同）；
    后去 B：B 的停留在当天最后离开 A 之后才开始。B 的停留如果同时也在 A 里，不算“去了 B”。
    """
    v = settings["visitor"]
    s = stay_area.merge(stay[["imsi", "stay_seq", "start_time", "end_time"]], on=["imsi", "stay_seq"])
    evening_cut = pd.Timestamp(day) + pd.Timedelta(hours=v["evening_hour"])
    rows = []
    areas = sorted(s["area"].unique())
    for a in areas:
        ev = _evening(uad[uad["area"] == a]).set_index("imsi")
        if ev.empty:
            continue
        sa = s[(s["area"] == a) & s["imsi"].isin(ev.index)]
        ex = sa[sa["end_time"] >= evening_cut].groupby("imsi")["start_time"].min()   # 傍晚那次到达
        last = sa.groupby("imsi")["end_time"].max()
        in_a = set(sa["imsi"] + "#" + sa["stay_seq"].astype(str))                     # A 的停留（人#序号）
        for b in areas:
            if b == a:
                continue
            sb = s[(s["area"] == b) & s["imsi"].isin(ev.index)]
            only_b = sb[~(sb["imsi"] + "#" + sb["stay_seq"].astype(str)).isin(in_a)]
            before = only_b[only_b["end_time"] <= only_b["imsi"].map(ex)]["imsi"].nunique()
            after = only_b[only_b["start_time"] >= only_b["imsi"].map(last)]["imsi"].nunique()
            rows.append({"area": a, "other_area": b, "evening_visitors": len(ev),
                         "users_any": sb["imsi"].nunique(), "users_before": before, "users_after": after})
    out = pd.DataFrame(rows, columns=["area", "other_area", "evening_visitors", "users_any", "users_before", "users_after"])
    for c in ["users_any", "users_before", "users_after"]:
        out[c.replace("users", "share")] = (out[c] / out["evening_visitors"]).round(4)
    return privacy.suppress_columns(out, {c: [c.replace("users", "share")] for c in
                                          ["users_any", "users_before", "users_after"]}, _k(settings))[
        ["area", "other_area", "evening_visitors", "users_any", "users_before", "users_after",
         "share_any", "share_before", "share_after"]]


def build_hex_hourly(user_hour, dim_area, settings):
    """每小时的六边形热力。少于 k 人的格子直接不输出（地图上就是空白）。"""
    h = settings["ads"]["hex"]
    o = dim_area.set_index("area").loc[h["origin_area"]]
    d = geo.haversine(user_hour["lat"], user_hour["lng"], o["center_lat"], o["center_lng"])
    uh = user_hour[d <= h["max_km"] * 1000]
    q, r = geo.hex_bin(uh["lng"], uh["lat"], o["center_lng"], o["center_lat"], h["size_m"])
    g = uh.assign(q=q, r=r).groupby(["hour", "q", "r"])["imsi"].nunique().rename("users").reset_index()
    g = privacy.drop_small(g, "users", _k(settings))
    g["center_lng"], g["center_lat"] = geo.hex_center(g["q"], g["r"], o["center_lng"], o["center_lat"], h["size_m"])
    g["size_m"] = h["size_m"]
    return g


def build_od_district(trip, settings):
    """区县之间的出行量（按出发、到达停留所在区县）。"""
    g = trip.groupby(["o_district", "d_district"]).agg(trips=("imsi", "size"), users=("imsi", "nunique")).reset_index()
    return privacy.suppress(g, "users", _k(settings), value_cols=["trips"])[
        ["o_district", "d_district", "trips", "users", "suppressed"]]


# ── 数据质量看板用的三张表：被门禁拦下的分区也有 ──

def build_dq_partition(profile, results, base, gate_status, pipeline_status, is_synthetic):
    """分区健康表：一天一行。"""
    vol = results.set_index("metric")["value"]
    return pd.DataFrame([{
        "rows": profile["rows"], "users": profile["users"], "rows_per_user": profile["rows_per_user"],
        "volume_ratio": vol.get("volume_ratio"), "valid_hours": vol.get("valid_hours"),
        "dup_rate": profile["dup_rate"], "cell_match_rate": profile["cell_match_rate"],
        "n_fail": int((results["result"] == "fail").sum()), "n_warn": int((results["result"] == "warn").sum()),
        "gate_status": gate_status, "pipeline_status": pipeline_status,
        "baseline_source": base["source"], "is_synthetic": int(is_synthetic),
        "hourly_json": json.dumps(profile["hourly"])}])


def build_dq_rule(results, is_synthetic):
    """门禁每条规则的结果：质量页的规则表、质量报告第 4 章。"""
    return results[["rule_id", "rule_name", "value", "threshold", "result"]].assign(is_synthetic=int(is_synthetic))


def build_dq_clean_steps(steps, is_synthetic):
    """清洗每一步剔除了多少行（dwd.clean_signal 的第二个返回值）：《数据清洗与加工说明》用。"""
    s = pd.DataFrame(steps)
    s["rows_before"] = s["rows_after"] + s["rows_removed"]
    out = s[["step", "rows_before", "rows_removed", "rows_after"]]
    out.insert(0, "step_no", range(1, len(out) + 1))
    return out.assign(is_synthetic=int(is_synthetic))
