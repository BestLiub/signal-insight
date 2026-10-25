"""图表规范的自动检查（D11）：把能用代码查的那部分规范写成代码。

和 theme.py 分开：改的原因不同（加一条检查规则 vs 改配色字体），用的人也不同（评审 vs 画图）。
能自动查的只是规范的一部分：结论对不对、口径写清没有、颜色会不会误导，还得靠人看。
"""
import matplotlib.patches

TITLE_SIZE = 16          # viz.finish 写标题用的字号：靠它认出“标题”这一行


def lint_figure(fig) -> list[str]:
    """按图表规范检查一张图，返回问题列表；空列表 = 通过。

    检查：有没有用 viz.finish 加标题区和来源行；标题里有没有数字（结论式标题要给关键数字）；标题是否过长；
    双轴图；3D、极坐标；超过 5 块的饼图；超过 7 项的图例；小于 8 磅的刻度字。
    """
    issues = []
    texts = [t for t in fig.texts if t.get_text().strip()]
    title = next((t.get_text() for t in texts if t.get_fontsize() == TITLE_SIZE), None)
    source = next((t.get_text() for t in texts if t.get_text().startswith("数据来源")), None)
    if title is None or source is None:
        issues.append("没有用 viz.finish 加标题区和来源行")
    else:
        if not any(ch.isdigit() for ch in title):
            issues.append("标题里没有数字：结论式标题应当给出关键数字")
        if len(title) > 40:
            issues.append(f"标题 {len(title)} 字，超过 40 字，读者一眼看不完")
    positions = {}
    for ax in fig.get_axes():
        key = tuple(round(v, 3) for v in ax.get_position().bounds)
        positions.setdefault(key, []).append(ax)
    if any(len(v) > 1 for v in positions.values()):
        issues.append("有两个坐标轴叠在同一位置（双轴图）：改成上下两个面板")
    for ax in fig.get_axes():
        if ax.name == "3d":
            issues.append("用了 3D 坐标轴")
        if ax.name == "polar":
            issues.append("用了极坐标（雷达图 / 玫瑰图），换成条形图更好比较")
        wedges = [p for p in ax.patches if isinstance(p, matplotlib.patches.Wedge)]
        if len(wedges) > 5:
            issues.append(f"饼图有 {len(wedges)} 块，超过 5 块应改成条形图")
        leg = ax.get_legend()
        if leg is not None and len(leg.get_texts()) > 7:
            issues.append(f"图例有 {len(leg.get_texts())} 项，超过 7 项：考虑直接在线尾标注或拆图")
        if any(lab.get_text() and lab.get_fontsize() < 8 for lab in ax.get_xticklabels() + ax.get_yticklabels()):
            issues.append("刻度字号小于 8 磅")
    return issues
