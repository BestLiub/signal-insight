"""《数据清洗与加工说明》：某一天从 ODS 到应用层的加工过程与客流结论。"""
from contextlib import closing

import pandas as pd
from signal_mysql import database as mysql

from .. import config, dws
from ..report import figures as F
from . import docx_kit as D
from .facts import FactLog

RADIUS_TRIALS = (300, 500, 800, 1000)
MINUTE_TRIALS = (15, 30, 60)


def sensitivity(con, settings, date):
    """参数敏感性：半径 × 最短时长各试几档，看人均停留点数变多少（D06 那张表，由代码重算）。

    读的是当天的清洗明细（dwd_signal × dim_cell）和配置里的其他参数，口径与 D06 完全一致：
    只有半径和最短时长在变，分母始终是当天的用户数。
    """
    sig = mysql.read_frame(
        "SELECT s.imsi, s.ts, c.lng, c.lat FROM dwd_signal s "
        "JOIN dim_cell c ON s.lac_cell = c.lac_cell WHERE s.dt = ?",
        con, params=(date,), parse_dates=["ts"]).sort_values(["imsi", "ts"])
    hot = mysql.read_frame("SELECT * FROM dim_hotspot", con).iloc[0]
    users = sig["imsi"].nunique()
    rows = []
    for radius in RADIUS_TRIALS:
        for minutes in MINUTE_TRIALS:
            trial = {**settings, "stay": {**settings["stay"], "radius_m": radius, "min_minutes": minutes}}
            stays = len(dws.build_stay(sig, trial, {}, {}, hot))
            rows.append({"radius_m": radius, "min_minutes": minutes, "stays": stays, "users": users,
                         "stays_per_user": round(stays / users, 2) if users else 0.0})
    return pd.DataFrame(rows)


def build_cleaning_report(settings, date, with_sensitivity=True):
    facts = FactLog()
    with closing(mysql.connect(config.WAREHOUSE_SCHEMA)) as con:
        reg = mysql.read_frame("SELECT * FROM ads_dq_partition WHERE dt = ?", con, params=(date,))
        doc = D.new_doc("数据清洗与加工说明")
        D.para(doc, F.source(settings, extra=f"分析日 {date}"))
        D.heading(doc, "一、这一天是怎么加工出来的")
        D.para(doc, "ODS 原样读取 → 门禁（画像、基准、7 条规则）→ 清洗（顺序与 D02 一致）→ "
                    "停留、过夜地、出行 → 用户日特征、每人每小时 → 区域长表 → 应用层（生成时做小样本抑制）。")
        if not reg.empty:
            D.table(doc, reg)
            facts.add("分区记录数", int(reg["rows"].iloc[0]), "ads_dq_partition.rows")
        fig, f = F.fig_clean_funnel(con, settings, date)
        if fig is not None:
            D.picture(doc, config.IMAGE_DIR / "report_clean_funnel.png")
            facts.add("清洗剔除行数", f["clean_removed"], "ads_dq_clean_steps")
        fig, f = F.fig_pipeline_timing(con, settings, date)
        if fig is not None:
            D.picture(doc, config.IMAGE_DIR / "report_pipeline_timing.png")
            facts.add("处理耗时（秒）", f["pipeline_seconds"], "etl_log")

        D.heading(doc, "二、客流结论")
        for fn, caption in [(F.fig_area_hourly, "各分析区域的一天"), (F.fig_segment, "客群构成"),
                            (F.fig_radius, "辐射圈层"), (F.fig_linkage, "商圈联动"), (F.fig_origin, "客源区县")]:
            fig, f = fn(con, settings, date)
            if fig is not None:
                D.picture(doc, config.IMAGE_DIR / f"report_{caption if False else fn.__name__.replace('fig_', '')}.png")
                for k, v in f.items():
                    facts.add(k, v, fn.__name__)
        fig, f = F.fig_hex_map(con, settings, date)
        if fig is not None:
            D.picture(doc, config.IMAGE_DIR / "report_hex_map.png")
            for k, v in f.items():
                facts.add(k, v, "ads_hex_hourly")

        D.heading(doc, "三、参数敏感性")
        if with_sensitivity:
            sens = sensitivity(con, settings, date)
            base_r, base_m = settings["stay"]["radius_m"], settings["stay"]["min_minutes"]
            at_base_m = sens[sens["min_minutes"] == base_m].set_index("radius_m")["stays_per_user"]
            at_base_r = sens[sens["radius_m"] == base_r].set_index("min_minutes")["stays_per_user"]
            D.para(doc, f"只改半径（最短时长取配置值 {base_m} 分钟）：人均停留点数 "
                        f"{at_base_m.min():.1f}–{at_base_m.max():.1f} 个；只改最短时长（半径取配置值 "
                        f"{base_r} 米）：{at_base_r.min():.1f}–{at_base_r.max():.1f} 个。"
                        f"半径的影响小（300–1000 米结果差别不大），最短时长的影响大，必须写进口径。")
            D.table(doc, sens.pivot(index="radius_m", columns="min_minutes",
                                    values="stays_per_user").round(2).reset_index())
            facts.add("半径敏感区间（人均停留）", f"{at_base_m.min():.1f}–{at_base_m.max():.1f}",
                      "本章敏感性计算：最短时长取配置值，半径 300–1000 米")
            facts.add("时长敏感区间（人均停留）", f"{at_base_r.min():.1f}→{at_base_r.max():.1f}",
                      "本章敏感性计算：半径取配置值，最短时长 15–60 分钟")

        D.heading(doc, "四、局限")
        D.bullets(doc, [
            "样本是中国移动的用户，且按傍晚到访圈选：结论只对这群人成立，不能代表全市客流。",
            "只有一天，而且是国庆假期：工作日、周末的节律需要补数据对照。",
            "位置是基站级的，城区误差几百米；区域边界附近的人可能被分错区域。",
            "小样本抑制会隐藏少于 5 人的格子；各区域可以重叠，人数不能相加。",
        ])
    D.heading(doc, "五、数字溯源")
    D.table(doc, facts.frame())
    out = config.REPORT_DIR / f"数据清洗与加工说明_{date}.docx"
    return D.save(doc, out)
