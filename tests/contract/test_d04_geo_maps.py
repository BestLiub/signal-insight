"""D04 契约：geo（纯计算）与 viz 变成包之后的 maps、重新导出。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from signal_insight import geo, viz
from _helpers import PKG, imported_names, touches_database

SQUARE = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=float)
HOLE = np.array([[4, 4], [6, 4], [6, 6], [4, 6]], dtype=float)


def test_haversine_one_degree_of_latitude_is_about_111_km():
    assert abs(geo.haversine(41.0, 123.0, 42.0, 123.0) - 111_195) < 1


def test_haversine_is_vectorized_symmetric_and_zero_on_same_point():
    d = geo.haversine(np.array([41.8, 41.9]), np.array([123.4, 123.5]), 41.8, 123.4)
    assert d.shape == (2,) and d[0] == 0
    assert np.isclose(geo.haversine(41.8, 123.4, 41.9, 123.5), geo.haversine(41.9, 123.5, 41.8, 123.4))


def test_rings_from_points_sorts_by_seq_and_splits_rings():
    pts = pd.DataFrame({"name": ["A"] * 6, "ring": [0, 0, 0, 1, 1, 1], "seq": [2, 0, 1, 0, 1, 2],
                        "lng": [3, 1, 2, 7, 8, 9], "lat": [0, 0, 0, 5, 5, 5]})
    polys = geo.rings_from_points(pts, "name")
    assert list(polys) == ["A"] and len(polys["A"]) == 2
    assert polys["A"][0][:, 0].tolist() == [1, 2, 3]


def test_rings_from_points_without_ring_column():
    pts = pd.DataFrame({"name": ["A", "A", "A", "B", "B", "B"], "seq": [0, 1, 2, 0, 1, 2],
                        "lng": [0, 1, 1, 5, 6, 6], "lat": [0, 0, 1, 5, 5, 6]})
    polys = geo.rings_from_points(pts, "name")
    assert list(polys) == ["A", "B"] and all(len(r) == 1 for r in polys.values())


def test_point_in_polygons_respects_holes_and_returns_none_outside():
    res = geo.point_in_polygons([1, 5, 20], [1, 5, 20], {"环形": [SQUARE, HOLE]})
    assert list(res) == ["环形", None, None]


def test_ring_area_km2_of_a_small_square():
    ring = np.array([[123.0, 41.8], [123.01, 41.8], [123.01, 41.81], [123.0, 41.81]])
    expected = 0.01 * 111.32 * np.cos(np.radians(41.805)) * 0.01 * 110.57
    assert np.isclose(geo.ring_area_km2(ring), expected, rtol=1e-3)


def test_geo_is_pure_computation():
    """docs/工程规范.md 第 4 条：geo 不碰数据库、不 import viz。"""
    assert not touches_database(PKG / "geo.py")
    assert not any("viz" in n for n in imported_names(PKG / "geo.py"))


def test_viz_is_a_package_and_old_imports_still_work():
    assert (PKG / "viz" / "__init__.py").exists() and not (PKG / "viz.py").exists()
    from signal_insight.viz import MAIN, finish, apply_theme  # noqa: F401  原来的写法照样能用
    assert callable(viz.finish) and callable(viz.maps.draw_districts)


def test_maps_functions_draw_without_reading_the_database():
    fig, ax = plt.subplots()
    bounds = viz.maps.draw_districts(ax, {"甲": [SQUARE], "乙": [SQUARE + 20]})
    assert bounds == (0, 30, 0, 30)
    ax.set_xlim(-1, 31); ax.set_ylim(-1, 31)
    viz.maps.set_map_aspect(ax)
    viz.maps.north_arrow(ax)
    viz.maps.scale_bar(ax, 5)
    assert not ax.get_xticks().size
    plt.close(fig)
    assert not touches_database(PKG / "viz" / "maps.py")
