"""《数据清洗与加工说明》：某一天从 ODS 到应用层的加工过程与客流结论。"""
from contextlib import closing

from signal_mysql import database as mysql

from .. import config
from ..report import figures as F
from . import docx_kit as D
from .facts import FactLog


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

        D.heading(doc, "三、局限")
        D.bullets(doc, [
            "样本是中国移动的用户，且按傍晚到访圈选：结论只对这群人成立，不能代表全市客流。",
            "只有一天，而且是国庆假期：工作日、周末的节律需要补数据对照。",
            "位置是基站级的，城区误差几百米；区域边界附近的人可能被分错区域。",
            "小样本抑制会隐藏少于 5 人的格子；各区域可以重叠，人数不能相加。",
        ])
    D.heading(doc, "四、数字溯源")
    D.table(doc, facts.frame())
    out = config.REPORT_DIR / f"数据清洗与加工说明_{date}.docx"
    return D.save(doc, out)
