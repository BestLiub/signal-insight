"""图表包：把某一天的标准图、关键数字和报告骨架一次生成（D15 的 report pack 命令）。"""
import json
from contextlib import closing
from pathlib import Path

from signal_mysql import database as mysql

from .. import config
from ..report import figures as F


def build_figure_pack(settings, date, out_dir=None):
    """生成 PNG + facts.json + 报告骨架.md，返回目录。"""
    out = Path(out_dir or config.REPORT_DIR / f"pack_{date}")
    out.mkdir(parents=True, exist_ok=True)
    facts = {}
    with closing(mysql.connect(config.WAREHOUSE_SCHEMA)) as con:
        for fn in [F.fig_partition_overview, F.fig_gate_heatmap, F.fig_clean_funnel,
                   F.fig_pipeline_timing, F.fig_area_hourly, F.fig_segment, F.fig_radius,
                   F.fig_linkage, F.fig_hex_map, F.fig_origin]:
            try:
                fig, f = fn(con, settings, date) if fn not in (F.fig_partition_overview, F.fig_gate_heatmap) else fn(con, settings)
            except Exception as e:
                print(f"跳过 {fn.__name__}：{type(e).__name__}: {e}")
                continue
            if fig is not None:
                facts.update(f)
    for p in config.IMAGE_DIR.glob("report_*.png"):
        (out / p.name).write_bytes(p.read_bytes())
    (out / "facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "报告骨架.md").write_text(
        f"# {date} 分析报告骨架\n\n## 结论\n- （用 facts.json 里的数字填）\n\n"
        "## 证据\n- 图：report_area_hourly / report_segment / report_radius / report_linkage / report_hex_map\n\n"
        "## 口径与局限\n- 见《数据清洗与加工说明》\n", encoding="utf-8")
    return out
