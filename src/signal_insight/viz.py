"""图表主题：字体、配色、标题区与来源行。

只会因为"图表规范变了"而改（docs/工程规范.md 第 2 条）。规范全文见 docs/图表规范.md。
落在代码里的是这几条：
  1. 标题写结论、数字由代码算；副标题写口径；左下角写来源    → finish()
  2. 灰色打底，一种颜色强调一件事，红色只表示警示            → 下面的颜色常量
  3. 同一个区域、同一类客群，在所有图里颜色相同              → AREA_COLOR、SEG_COLOR
  4. 只用开源字体（课件、报告、简历作品都要对外发）          → apply_theme()

import 本模块不改任何全局设置（docs/工程规范.md 第 7 条）：要生效，调用方显式调用 apply_theme()。
"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.layout_engine import ConstrainedLayoutEngine
from matplotlib.patches import Rectangle

from . import config

__all__ = ["MAIN", "MAIN_LIGHT", "MAIN_DARK", "MAIN_MID", "GRAY", "GRAY_DARK", "RED", "AMBER",
           "INK", "MUTED", "FAINT", "AREA_COLOR", "SEG_COLOR", "apply_theme", "finish"]

# ── 配色：灰色打底，一种颜色强调一件事，红色只表示警示 ──
MAIN, MAIN_LIGHT, MAIN_DARK, MAIN_MID = "#1D6FA5", "#DCEAF5", "#174E73", "#7FB3D9"
GRAY, GRAY_DARK, RED, AMBER = "#C4CAD3", "#8E99A6", "#D64545", "#B7791F"
INK, MUTED, FAINT = "#1F2937", "#6B7280", "#9CA3AF"            # 正文、副标题、来源行
AREA_COLOR = {"西塔": MAIN, "太原街商圈": "#D9822B", "中街商圈": "#3B8C66",
              "沈阳北站": "#7A5EA8", "沈阳世博园": "#B04A6A", "棋盘山风景区": "#6B7F2A"}
SEG_COLOR = {"市内来访": MAIN, "周边居民": MAIN_MID, "外地来客": "#D9822B", "市外来访": "#D9822B",
             "过夜地不明": GRAY}                                # "不明"永远是灰色：不是一类人，是不知道

# ── 字体：只写开源字体的名字（版权原因见 docs/图表规范.md 第 0 节）──
# 思源字体由 Adobe 和 Google 分别发布，名字不同、字形一样；不同机器装的发行版不同，所以别名都列上。
FONTS = ["TeX Gyre Termes",       # Times New Roman 的开源平替（西文衬线）
         "Noto Serif CJK SC",     # 宋体的开源平替：思源宋体
         "Source Han Sans SC"]    # 黑体的开源平替：思源黑体
_ALIASES = ["Source Han Serif SC", "Noto Serif SC", "Noto Sans CJK SC", "Noto Sans SC",
            "Noto Sans CJK JP", "Noto Serif CJK JP"]
_LATIN_ONLY = {"TeX Gyre Termes", "DejaVu Sans"}


def apply_theme() -> list[str]:
    """设置 matplotlib 的字体和坐标轴样式，返回实际生效的字体列表。每个 notebook 第一格调用一次。

    只保留本机真的装了的字体：列了没装的，matplotlib 每画一张图都会刷一屏 findfont 警告。
    font.family 写成一串具体字体，matplotlib 才会逐字回退（中文缺的负号、上下标由 DejaVu Sans 补）。
    """
    installed = {f.name for f in font_manager.fontManager.ttflist}
    fonts = [f for f in FONTS + _ALIASES if f in installed] + ["DejaVu Sans"]
    if not [f for f in fonts if f not in _LATIN_ONLY]:
        print("⚠️ 本机没有课程用的开源中文字体，图里的中文会变成方框。安装方法见 docs/图表规范.md 第 0 节。")
    plt.rcParams.update({
        "font.family": fonts, "axes.unicode_minus": True,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
        "axes.grid": True, "axes.grid.axis": "y", "axes.axisbelow": True, "grid.color": "#E5E7EB",
        "axes.edgecolor": FAINT, "xtick.color": "#4B5563", "ytick.color": "#4B5563",
        "xtick.major.size": 0, "ytick.major.size": 0, "legend.frameon": False,
        "figure.dpi": 100, "savefig.dpi": 200,
    })
    return fonts


def finish(fig, title: str, subtitle: str, source: str, path: str | None = None) -> Path | None:
    """给一张图加统一的标题区和来源行，留好上下的空白；path 给文件名时保存到 image/，返回完整路径。

    标题区的位置按"英寸"算而不是按比例：图高 4 英寸还是 7 英寸，标题区看起来都一样大。
    两种排版引擎都支持：普通的图用 tight_layout 留白；用了 layout="constrained" 的图改它的 rect。
    标题是 fig.texts[0]，"读回断言"靠这一点检查标题里的数字是不是代码算的。

    不做的事：不读数据库，不算任何业务数字（标题里的数由调用方算好传进来）。
    """
    h, w = fig.get_figheight(), fig.get_figwidth()
    n_sub = subtitle.count("\n") + 1 if subtitle else 0
    fig.add_artist(Rectangle((0.02, 1 - 0.115 / h), 0.38 / w, 0.045 / h,
                             transform=fig.transFigure, color=MAIN, lw=0))       # 强调色短条
    fig.text(0.02, 1 - 0.19 / h, title, fontsize=16, fontweight="bold", color=INK, va="top")
    if subtitle:
        fig.text(0.02, 1 - 0.57 / h, subtitle, fontsize=10.5, color=MUTED, va="top", linespacing=1.5)
    fig.text(0.02, 0.1 / h, source, fontsize=8.5, color=FAINT)
    top, bottom = 1 - (0.67 + 0.23 * n_sub) / h, 0.32 / h                      # 上留标题区，下留来源行
    engine = fig.get_layout_engine()
    if isinstance(engine, ConstrainedLayoutEngine):
        engine.set(rect=(0.01, bottom, 0.98, top - bottom))                    # 注意：这里是 (左, 下, 宽, 高)
    else:
        fig.tight_layout(rect=(0.01, bottom, 0.99, top))                       # 这里是 (左, 下, 右, 上)
    if path is None:
        return None
    out = Path(path) if Path(path).is_absolute() else config.IMAGE_DIR / path
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    return out