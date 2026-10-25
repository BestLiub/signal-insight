"""空间计算：球面距离、从顶点表还原多边形、点落面、多边形面积。

纯计算（docs/工程规范.md 第 4 条）：只接收数字、数组、DataFrame，不连数据库，不 import viz。
所以测试时塞几个手写的点就能测，平台、报告、notebook 都能直接复用。

四个函数的原型在 D03 的 notebook 里（代码格 12、18、24），那几份不删、不改：D03 是写出 dim_cell 的那天的记录。
D03 写的时候就把读库留在了调用方（rings_from_points 接收读好的顶点表），所以搬过来只补了类型标注和说明。
"""
import math
import numpy as np
import pandas as pd
from matplotlib.path import Path as MplPath

EARTH_R = 6_371_000          # 地球平均半径（米）


def haversine(lat1, lng1, lat2, lng2):
    """两点间的球面距离（米）。参数可以是数字，也可以是等长的数组 / Series。

    注意参数顺序：先纬度、后经度（和"经纬度"的说法相反，讲师卡易错点）。
    """
    lat1, lng1, lat2, lng2 = (np.radians(np.asarray(v, dtype=float)) for v in (lat1, lng1, lat2, lng2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_R * np.arcsin(np.sqrt(a))


def dist_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """两点间的球面距离（米），标量版（D06）：在 Python 循环里一次只算一对点时用它。

    为什么要两个版本：numpy 的优势是"一次算一百万对"；单独算一对点时，构造数组的开销比计算本身还大，
    比这个 math 版慢几十倍。停留识别的内层循环一次只比一对点，所以用这个。
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def rings_from_points(points: pd.DataFrame, key: str) -> dict[str, list[np.ndarray]]:
    """从"一行一个顶点"的表还原多边形：{名称: [环1, 环2, ...]}，每个环是 N×2 的 (lng, lat) 数组。

    points 至少要有 key、seq、lng、lat 四列；有 ring 列时按 ring 分环（区县边界有飞地和洞），
    没有就当只有一个环（商圈边界）。名称按第一次出现的顺序排列。
    """
    pts = points if "ring" in points.columns else points.assign(ring=0)
    return {name: [r.sort_values("seq")[["lng", "lat"]].to_numpy(dtype=float) for _, r in g.groupby("ring")]
            for name, g in pts.groupby(key, sort=False)}


def point_in_polygons(lng, lat, polys: dict[str, list[np.ndarray]]) -> np.ndarray:
    """点落面：返回每个点所在多边形的名称，不在任何多边形里的返回 None。

    一个名称可以有好几个环：用奇偶规则，落在奇数个环里算"在里面"，
    这样飞地（多个外环）和洞（内环）都能正确处理，不用分情况写。
    多边形有重叠时，先出现的名称优先。
    """
    xy = np.column_stack([np.asarray(lng, dtype=float), np.asarray(lat, dtype=float)])
    out = np.full(len(xy), None, dtype=object)
    for name, rings in polys.items():
        inside = np.zeros(len(xy), dtype=bool)
        for ring in rings:
            inside ^= MplPath(ring).contains_points(xy)        # ^= 异或：奇数个环 = 在里面
        out[inside & pd.isna(out)] = name
    return out


def ring_area_km2(ring: np.ndarray) -> float:
    """多边形面积（平方公里）：鞋带公式，按所在纬度把经纬度换算成公里。城市尺度下误差可以忽略。"""
    x, y = ring[:, 0], ring[:, 1]
    kx, ky = 111.32 * np.cos(np.radians(y.mean())), 110.57    # 每度经度、每度纬度约多少公里
    return float(abs(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)) / 2 * kx * ky)


# ── D13：分析区域与六边形网格 ─────────────────────────────────────────

def polygon_centroid(ring: np.ndarray) -> tuple[float, float]:
    """多边形的面积质心 (lng, lat)，鞋带公式。商圈的“中心”用它，不用顶点平均值。

    顶点是人画的：哪边拐弯多哪边顶点就密，顶点平均值会被拽向那一侧。这个中心要参与距离计算
    （客群的“周边居民”就是量到它），所以不能马虎。
    """
    x, y = ring[:, 0], ring[:, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    cross = x * y1 - x1 * y
    area = cross.sum() / 2
    if abs(area) < 1e-15:
        return float(x.mean()), float(y.mean())
    return float(((x + x1) * cross).sum() / (6 * area)), float(((y + y1) * cross).sum() / (6 * area))


def area_membership(lng, lat, dim_area: pd.DataFrame, area_polys: dict) -> pd.DataFrame:
    """点 × 区域的归属（长表）：一个点可以同时属于好几个区域。

    返回列 idx（输入点的位置）、area、dist_center_m（点到区域中心，米，取整）。
    圆形区域看到中心的距离 ≤ 半径；多边形区域看点是否落在边界里（area_polys[区域名]）。
    区域可以重叠，所以不能用 point_in_polygons 那种“先到先得”。
    """
    lng, lat = np.asarray(lng, dtype=float), np.asarray(lat, dtype=float)
    parts = []
    for a in dim_area.itertuples(index=False):
        d = haversine(lat, lng, a.center_lat, a.center_lng)
        if a.kind == "circle":
            inside = d <= a.radius_m
        else:
            inside = point_in_polygons(lng, lat, {a.area: area_polys[a.area]}) == a.area
        idx = np.flatnonzero(inside)
        parts.append(pd.DataFrame({"idx": idx, "area": a.area, "dist_center_m": d[idx].round()}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["idx", "area", "dist_center_m"])


def _kxy(lat0: float) -> tuple[float, float]:
    """在纬度 lat0 附近，每度经度、每度纬度约多少米：六边形网格用的局部平面换算。"""
    return 111_320 * math.cos(math.radians(lat0)), 110_574


def hex_bin(lng, lat, lng0, lat0, size_m):
    """点 → 所在六边形的轴坐标 (q, r)。网格原点在 (lng0, lat0)，size_m 是六边形边长（米）。

    为什么用六边形：每个格子到 6 个邻居的距离相等，热力图不会像方格那样出现横竖条纹。
    """
    kx, ky = _kxy(lat0)
    x = (np.asarray(lng, dtype=float) - lng0) * kx
    y = (np.asarray(lat, dtype=float) - lat0) * ky
    qf = (math.sqrt(3) / 3 * x - y / 3) / size_m
    rf = (2 / 3 * y) / size_m
    sf = -qf - rf
    q, r, s = np.round(qf), np.round(rf), np.round(sf)      # 立方坐标取整，再修正误差最大的那一维
    dq, dr, ds = np.abs(q - qf), np.abs(r - rf), np.abs(s - sf)
    fix_q = (dq > dr) & (dq > ds)
    fix_r = ~fix_q & (dr > ds)
    q = np.where(fix_q, -r - s, q)
    r = np.where(fix_r, -q - s, r)
    return q.astype(int), r.astype(int)


def hex_center(q, r, lng0, lat0, size_m):
    """六边形 (q, r) 的中心经纬度。"""
    kx, ky = _kxy(lat0)
    q, r = np.asarray(q, dtype=float), np.asarray(r, dtype=float)
    x = size_m * math.sqrt(3) * (q + r / 2)
    y = size_m * 1.5 * r
    return lng0 + x / kx, lat0 + y / ky


def hex_polygon(q, r, lng0, lat0, size_m) -> np.ndarray:
    """一个六边形的 6 个顶点 (lng, lat)，画图用。"""
    kx, ky = _kxy(lat0)
    cx, cy = hex_center(q, r, lng0, lat0, size_m)
    ang = np.radians(np.arange(6) * 60 + 30)
    return np.column_stack([cx + size_m * np.cos(ang) / kx, cy + size_m * np.sin(ang) / ky])
