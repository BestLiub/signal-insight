"""数据质量门禁（D12）：一个分区能不能进入下游。

只看“有没有数据”是不够的。真实的 10-02 分区 24 个小时都有信令，覆盖率检查会放行；
但它的数据量只有基准日的 2.8%，人均 3.5 条（基准日 91.7 条）。拦住它靠的是和基准比的**相对**指标。

纯计算（docs/工程规范.md 第 4 条）：输入原始信令和历史画像，输出画像和判断结果，不碰数据库。
规则和阈值在 settings.yaml 的 gate 段（第 8 条）；清洗规则（关键字段、IMSI 格式、判重字段）用 dwd 里的同一份（口径只有一个来源）。
"""
import json

import pandas as pd

from . import dwd


def profile_partition(raw: pd.DataFrame, cell_keys: set) -> dict:
    """给一天的原始信令做画像：行数、用户数、人均记录数、每小时记录数、关键字段缺失率、IMSI 异常率、重复率、基站关联率。"""
    n = len(raw)
    if n == 0:
        return {"rows": 0, "users": 0, "rows_per_user": 0.0, "hourly": [0] * 24, "key_null_rate": 1.0,
                "imsi_invalid_rate": 0.0, "dup_rate": 0.0, "cell_match_rate": 0.0}
    imsi = raw["imsi"].dropna().astype(str)
    has_key = raw.dropna(subset=["lac_id", "cell_id"])
    keys = has_key["lac_id"].astype("int64").astype(str) + "-" + has_key["cell_id"].astype("int64").astype(str)
    users = imsi.nunique()
    hourly = dwd.to_local(raw["timestamp"]).dt.hour.value_counts().reindex(range(24), fill_value=0)
    return {
        "rows": n,
        "users": int(users),
        "rows_per_user": round(n / users, 2) if users else 0.0,
        "hourly": [int(v) for v in hourly],
        "key_null_rate": float(raw[dwd.KEY_FIELDS].isna().any(axis=1).mean()),
        "imsi_invalid_rate": float((~imsi.str.fullmatch(dwd.IMSI_PATTERN)).sum() / n),
        "dup_rate": float(raw.duplicated(subset=dwd.ORIG_COLS).mean()),
        "cell_match_rate": float(keys.isin(cell_keys).mean()) if len(keys) else 0.0,
    }


def baseline(history: pd.DataFrame, settings: dict) -> dict:
    """基准 = 最近 baseline_days 个通过门禁的真实分区的**中位数**；一个都没有时用 bootstrap。

    history 由调用方查好传进来（列 rows、rows_per_user，已经排除了当天自己和模拟分区，按日期倒序）。
    为什么用中位数：基准里只要混进一个坏分区，平均数就被拉偏，中位数不受影响。
    """
    g = settings["gate"]
    hist = history.head(g["baseline_days"])
    if len(hist):
        return {"rows": float(hist["rows"].median()), "rows_per_user": float(hist["rows_per_user"].median()),
                "source": f"最近 {len(hist)} 个通过门禁的真实分区"}
    b = g["bootstrap"]
    return {"rows": float(b["rows"]), "rows_per_user": float(b["rows_per_user"]), "source": "bootstrap（配置）"}


def evaluate(profile: dict, base: dict, settings: dict) -> pd.DataFrame:
    """逐条规则判断：pass/warn/fail。返回规则结果表（规则、名称、指标、值、阈值、结果）。"""
    g = settings["gate"]
    values = dict(profile)
    values["volume_ratio"] = profile["rows"] / base["rows"] if base["rows"] else 0.0
    values["rpu_ratio"] = profile["rows_per_user"] / base["rows_per_user"] if base["rows_per_user"] else 0.0
    # “有效小时”不是“有数据的小时”：10-02 24 小时都有信令，但每小时只有正常日的百分之几
    hourly_mean = base["rows"] / 24
    values["valid_hours"] = int(sum(h >= g["valid_hour_ratio"] * hourly_mean for h in profile["hourly"]))
    rows = []
    for r in g["rules"]:
        v = values[r["metric"]]
        if "fail_below" in r:
            status = "fail" if v < r["fail_below"] else "warn" if v < r["warn_below"] else "pass"
            threshold = f"< {r['fail_below']} 不通过；< {r['warn_below']} 警告"
        else:
            status = "fail" if v > r["fail_above"] else "warn" if v > r["warn_above"] else "pass"
            threshold = f"> {r['fail_above']} 不通过；> {r['warn_above']} 警告"
        rows.append({"rule_id": r["id"], "rule_name": r["name"], "metric": r["metric"], "value": round(float(v), 6),
                     "threshold": threshold, "result": status})
    return pd.DataFrame(rows)


def overall(results: pd.DataFrame) -> str:
    """整体结论：**只要有一条 fail，整个分区就 fail**。不加权、不投票：门禁的职责是挡住坏数据，不是综合评价。"""
    s = set(results["result"])
    return "fail" if "fail" in s else "warn" if "warn" in s else "pass"


def profile_row(profile: dict, base: dict) -> pd.DataFrame:
    """画像写库用的一行（每小时记录数存成 JSON）。"""
    return pd.DataFrame([{**{k: v for k, v in profile.items() if k != "hourly"},
                          "hourly_json": json.dumps(profile["hourly"]),
                          "baseline_rows": base["rows"], "baseline_source": base["source"]}])
