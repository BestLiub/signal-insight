"""空间计算：球面距离、从顶点表还原多边形、点落面、多边形面积。

纯计算（docs/工程规范.md 第 4 条）：只接收数字、数组、DataFrame，不连数据库，不 import viz。
所以测试时塞几个手写的点就能测，平台、报告、notebook 都能直接复用。

四个函数的原型在 D03 的 notebook 里（代码格 12、18、24），那几份不删、不改：D03 是写出 dim_cell 的那天的记录。
D03 写的时候就把读库留在了调用方（rings_from_points 接收读好的顶点表），所以搬过来只补了类型标注和说明。
"""
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
