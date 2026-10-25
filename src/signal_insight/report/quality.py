"""《数据质量评估报告》：门禁、分区、清洗、运行耗时，一次生成 Word。"""
from contextlib import closing

from signal_mysql import database as mysql

from .. import config
from ..report import figures as F
from . import docx_kit as D
from .facts import FactLog


def build_quality_report(settings, start=None, end=None):
    facts = FactLog()
    with closing(mysql.connect(config.WAREHOUSE_SCHEMA)) as con:
        part = mysql.read_frame("SELECT * FROM ads_dq_partition ORDER BY dt", con)
        if start:
            part = part[part["dt"] >= start]
        if end:
            part = part[part["dt"] <= end]
        dts = part["dt"].tolist()
        doc = D.new_doc("数据质量评估报告")
        D.para(doc, F.source(settings))
        D.heading(doc, "一、分区与门禁")
        D.para(doc, f"本次覆盖 {len(dts)} 个分区（{dts[0] if dts else '—'} 至 {dts[-1] if dts else '—'}）。"
                    f"处理完成 {int((part['pipeline_status'] == 'done').sum())} 个，"
                    f"被门禁拦下 {int((part['pipeline_status'] == 'blocked').sum())} 个。")
        D.table(doc, part[["dt", "rows", "users", "volume_ratio", "valid_hours", "gate_status", "pipeline_status", "is_synthetic"]])
        fig, f1 = F.fig_partition_overview(con, settings)
        if fig is not None:
            D.picture(doc, config.IMAGE_DIR / "report_partition_overview.png")
            facts.add("分区总记录数", f1["partition_rows"], "ads_dq_partition.rows")
        fig, f2 = F.fig_gate_heatmap(con, settings)
        if fig is not None:
            D.picture(doc, config.IMAGE_DIR / "report_gate_heatmap.png")
            facts.add("被门禁拦下的分区数", f2["gate_blocked"], "ads_dq_rule.result")
        D.heading(doc, "二、清洗与加工")
        if dts:
            fig, f3 = F.fig_clean_funnel(con, settings, dts[-1])
            if fig is not None:
                D.picture(doc, config.IMAGE_DIR / "report_clean_funnel.png")
                facts.add("最后一天清洗剔除行数", f3["clean_removed"], "ads_dq_clean_steps.rows_removed")
            fig, f4 = F.fig_pipeline_timing(con, settings, dts[-1])
            if fig is not None:
                D.picture(doc, config.IMAGE_DIR / "report_pipeline_timing.png")
                facts.add("一个分区处理耗时（秒）", f4["pipeline_seconds"], "etl_log")
    D.heading(doc, "三、数字溯源")
    D.table(doc, facts.frame())
    out = config.REPORT_DIR / "数据质量评估报告.docx"
    return D.save(doc, out)
