"""地图：长宽比校正、区县底图、指北针、比例尺。

和 theme.py 分开，是因为改动原因不同（docs/工程规范.md 第 2 条）：改配色的人不该面对一堆地图代码；
地图要按纬度换算距离，主题不需要。
不读数据库：多边形由调用方用 geo.rings_from_points 还原好传进来（docs/工程规范.md 第 4 条）。
原型在 D03 notebook 的代码格 14（那份不删、不改）；收进来时多了 set_map_aspect，比例尺的纬度改成了参数 lat0。
"""
import numpy as np

from .theme import INK

LAT0 = 41.8                  # 沈阳大约的纬度：经度 1 度的长度只有纬度 1 度的 cos(41.8°) ≈ 0.75 倍


def set_map_aspect(ax, lat0: float = LAT0, bare: bool = True) -> None:
    """地图长宽比校正：经纬度不能直接当平面坐标画，否则东西方向会被拉宽 1/0.75 倍。

    bare=True 时顺便去掉刻度、网格和边框：地图上的经纬度刻度大家用不到，比例尺才有用。
    """
    ax.set_aspect(1 / np.cos(np.radians(lat0)))
    if bare:
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
        for sp in ax.spines.values():
            sp.set_visible(False)


def draw_districts(ax, polys, values=None, cmap=None, norm=None, edge="#9AA3AE", lw=0.6):
    """画区县边界；给了 values（{区县: 数值}）就按数值填色，成为分级设色地图。

    返回所有顶点的范围 (经度最小, 经度最大, 纬度最小, 纬度最大)，调用方用它设视窗。
    """
    for name, rings in polys.items():
        fc = cmap(norm(values[name])) if values is not None and name in values else "none"
        for ring in rings:
            ax.fill(ring[:, 0], ring[:, 1], facecolor=fc, edgecolor=edge, lw=lw)
    allpts = np.vstack([r for rings in polys.values() for r in rings])
    return allpts[:, 0].min(), allpts[:, 0].max(), allpts[:, 1].min(), allpts[:, 1].max()


def north_arrow(ax) -> None:
    """右上角的指北针。"""
    ax.annotate("北", xy=(0.95, 0.93), xytext=(0.95, 0.83), xycoords="axes fraction", ha="center", va="center",
                fontsize=9, color=INK, arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.2))


def scale_bar(ax, km: float, lat0: float = LAT0) -> None:
    """左下角的比例尺：按纬度把公里换成经度差。地图没有刻度轴时，必须给大家一个距离参照。

    先设好 xlim、ylim 再调用：比例尺的位置按当前视窗算。
    """
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    deg = km / (111.32 * np.cos(np.radians(lat0)))
    xs, ys = x0 + 0.04 * (x1 - x0), y0 + 0.05 * (y1 - y0)
    ax.plot([xs, xs + deg], [ys, ys], color=INK, lw=2, solid_capstyle="butt")
    ax.text(xs + deg / 2, ys + 0.015 * (y1 - y0), f"{km:g} 公里", ha="center", va="bottom", fontsize=8.5, color=INK)
