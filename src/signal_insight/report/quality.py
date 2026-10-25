"""《数据质量评估报告》：分区、门禁、字段画像、已知问题、使用建议；一条命令重新生成。

读者是数据提供方和技术负责人：他们关心“能不能用、问题出在哪、怎么处理的”，
所以结论在最前面、证据在后面、原始记录在附录（D13 需求卡 13.8）。
"""
from contextlib import closing

import pandas as pd
import yaml
from signal_mysql import database as mysql

from .. import config
from . import docx_kit as D
from . import figures as F
from .common import fmt_int, source_line
from .facts import FactLog

SUMMARY_COLS = {"dt": "日期", "rows": "记录数", "users": "用户数", "volume_ratio": "量比",
                "valid_hours": "有效小时", "n_fail": "不通过", "n_warn": "警告",
                "gate_status": "门禁", "pipeline_status": "流水线", "is_synthetic": "模拟"}
PROFILE_COLS = {"rows": "记录数", "users": "用户数", "rows_per_user": "人均记录数",
                "key_null_rate": "关键字段缺失率", "imsi_invalid_rate": "IMSI 格式异常率",
                "dup_rate": "完全重复率", "cell_match_rate": "基站关联率"}


def _rule_table(settings):
    rows = []
    for r in settings["gate"]["rules"]:
        if "fail_below" in r:
            threshold = f"< {r['fail_below']} 不通过；< {r['warn_below']} 警告"
        else:
            threshold = f"> {r['fail_above']} 不通过；> {r['warn_above']} 警告"
        rows.append({"规则": r["id"], "名称": r["name"], "指标": r["metric"], "阈值": threshold})
    return pd.DataFrame(rows)


def _issues():
    path = config.PROJECT_ROOT / "config" / "known_issues.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else []


def build_quality_report(settings, start=None, end=None):
    facts = FactLog()
    issues = _issues()
    with closing(mysql.connect(config.WAREHOUSE_SCHEMA)) as con:
        part = mysql.read_frame("SELECT * FROM ads_dq_partition ORDER BY dt", con)
        if start:
            part = part[part["dt"] >= start]
        if end:
            part = part[part["dt"] <= end]
        dts = part["dt"].tolist()
        done = part.loc[part["pipeline_status"] == "done", "dt"].tolist()
        n_blocked = int((part["pipeline_status"] == "blocked").sum())
        n_real = int((part.loc[part["pipeline_status"] == "done", "is_synthetic"] == 0).sum())

        doc = D.new_doc("数据质量评估报告")
        D.para(doc, source_line(settings))

        # ── 1 结论摘要 ──
        D.heading(doc, "1　结论摘要")
        span = f"{dts[0]} 至 {dts[-1]}" if dts else "—"
        D.para(doc, f"本次评估覆盖 {len(part)} 个分区（{span}）：处理完成 {len(done)} 个，"
                    f"其中真实分区 {n_real} 个、模拟分区 {len(done) - n_real} 个；被门禁拦下 {n_blocked} 个。")
        D.para(doc, "通过门禁的分区可以用于分析；被拦下的分区下游一行都没有写，原因见第 4 章。"
                    "数据本身的限制登记在第 6 章，能回答什么、不能回答什么见第 7 章。")
        facts.add("覆盖分区数", len(part), "ads_dq_partition 行数")
        facts.add("通过门禁的分区数", len(done), "ads_dq_partition.pipeline_status")

        # ── 2 评估方法 ──
        D.heading(doc, "2　评估方法")
        D.heading(doc, "2.1　质量维度", 2)
        D.bullets(doc, [
            "完整性：关键字段（imsi、lac_id、cell_id）缺失率。",
            "规范性：IMSI 是否为 18 位纯数字。",
            "唯一性：全部原始字段完全重复的记录比例。",
            "一致性：两个时间戳之差、基站编号能否关联上维表。",
            "时效性：每小时记录数是否均匀，有效小时数是否够。",
        ])
        D.heading(doc, "2.2　门禁规则与阈值", 2)
        D.para(doc, "阈值全部来自 config/settings.yaml 的 gate 段；改阈值不改代码。")
        D.table(doc, _rule_table(settings))
        D.heading(doc, "2.3　基准怎么定", 2)
        b = settings["gate"]["bootstrap"]
        D.para(doc, f"基准 = 最近 {settings['gate']['baseline_days']} 个通过门禁的真实分区的中位数，"
                    f"不用平均数——一天的数据错得离谱时，平均数会被它拽走。"
                    f"还没有任何通过门禁的分区时，用 bootstrap 值（{fmt_int(b['rows'])} 行、"
                    f"人均 {b['rows_per_user']} 条）。")
        facts.add("基准行数（bootstrap）", b["rows"], "config/settings.yaml gate.bootstrap.rows")
        facts.add("基准行数（本次中位数）", int(part["rows"].median()) if len(part) else 0,
                  "ads_dq_partition.rows 的中位数")
        facts.add("已知问题条数", len(issues), "config/known_issues.yaml")

        # ── 3 分区总览 ──
        D.heading(doc, "3　分区总览")
        if len(part):
            D.table(doc, part[[c for c in SUMMARY_COLS if c in part.columns]].rename(columns=SUMMARY_COLS))
            fig, info = F.fig_partition_overview(con, settings)
            if fig is not None:
                D.picture(doc, config.IMAGE_DIR / "report_partition_overview.png")
                D.para(doc, f"图：每日记录数与基准（共 {info['partition_rows']:,} 条记录）。")
        else:
            D.para(doc, "没有可评估的分区。")

        # ── 4 门禁规则明细 ──
        D.heading(doc, "4　门禁规则明细")
        rules = pd.DataFrame()
        if dts:
            rules = mysql.read_frame(
                "SELECT dt, rule_id, rule_name, value, threshold, result FROM ads_dq_rule "
                "WHERE dt >= ? AND dt <= ? ORDER BY dt, rule_id", con, params=(min(dts), max(dts)))
        if len(rules):
            D.table(doc, rules.rename(columns={"dt": "日期", "rule_id": "规则", "rule_name": "名称",
                                               "value": "取值", "threshold": "阈值", "result": "结果"}))
            bad = rules[rules["result"] == "fail"]
            D.para(doc, f"不通过的规则共 {len(bad)} 条，见上表标 fail 的行。" if len(bad) else "所有规则均未触发不通过。")
            fig, info = F.fig_gate_heatmap(con, settings)
            if fig is not None:
                D.picture(doc, config.IMAGE_DIR / "report_gate_heatmap.png")
        else:
            D.para(doc, "没有门禁规则记录。")

        # ── 5 通过分区的字段级画像 ──
        D.heading(doc, "5　通过分区的字段级画像")
        prof = mysql.read_frame("SELECT * FROM dq_partition_profile ORDER BY dt", con)
        prof = prof[prof["dt"].isin(done)] if len(prof) else prof
        if len(prof):
            for i, (_, r) in enumerate(prof.iterrows(), 1):
                D.heading(doc, f"5.{i}　{r['dt']}", 2)
                D.table(doc, pd.DataFrame([{PROFILE_COLS[k]: r[k] for k in PROFILE_COLS if k in prof.columns}]))
            D.para(doc, "缺失率与异常率都按记录数计算；基站关联率的分母是有关键字段的记录。")
        else:
            D.para(doc, "没有通过门禁的分区，无法给出字段级画像。")

        # ── 6 已知问题清单 ──
        D.heading(doc, "6　已知问题清单")
        if issues:
            D.para(doc, "前十二天验收时发现的问题登记在 config/known_issues.yaml；质量报告这一章从这里生成。")
            D.heading(doc, "6.1　问题详情", 2)
            D.table(doc, pd.DataFrame([{k: x.get(k, "") for k in ("id", "title", "found", "status")}
                                       for x in issues])
                    .rename(columns={"id": "编号", "title": "问题", "found": "发现于", "status": "状态"}))
            D.table(doc, pd.DataFrame([{k: x.get(k, "") for k in ("id", "detail", "impact", "handling")}
                                       for x in issues])
                    .rename(columns={"id": "编号", "detail": "现象", "impact": "影响", "handling": "处理"}))
        else:
            D.para(doc, "尚未登记已知问题。")

        # ── 7 使用建议 ──
        D.heading(doc, "7　使用建议")
        D.para(doc, "能回答：")
        D.bullets(doc, [
            "国庆当天到过西塔一带的这群人，几点来、待多久、从多远来、还去了哪个商圈。",
            "某一天的加工过程是否正常（门禁、清洗、行数），以及和前几天比有没有异常。",
        ])
        D.para(doc, "不能回答：")
        D.bullets(doc, [
            "全市人口分布或全市客流总量：样本不是随机抽样，按傍晚到访圈选。",
            "工作日、周末的差异：只有国庆一天真实数据。",
            "精确到个人的轨迹或身份：对外数据已做小样本抑制。",
        ])

        # ── 附录 ──
        D.heading(doc, "附录 A　数字溯源表")
        D.para(doc, "报告里出现的每个数字，都记着来自哪张表、怎么算的。")
        D.table(doc, facts.frame())
        D.heading(doc, "附录 B　运行记录")
        log = mysql.read_frame(
            "SELECT dt, run_id, config_version, COUNT(*) AS steps, ROUND(SUM(elapsed_sec), 1) AS seconds "
            "FROM etl_log GROUP BY dt, run_id, config_version ORDER BY dt", con)
        if len(log):
            D.table(doc, log.rename(columns={"dt": "日期", "run_id": "运行编号", "config_version": "配置版本",
                                             "steps": "步骤数", "seconds": "耗时（秒）"}))
        else:
            D.para(doc, "没有运行记录。")

    out = config.REPORT_DIR / "数据质量评估报告.docx"
    return D.save(doc, out)
