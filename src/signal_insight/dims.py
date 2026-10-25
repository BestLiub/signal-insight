"""维度表：dim_cell（扇区 → 站点 → 区县 → 商圈）、dim_hotspot（热点）、dim_metric（指标口径，D08）。

纯计算（docs/工程规范.md 第 4 条）：多边形由调用方用 geo.rings_from_points 还原好传进来，这里不读库。
"""
import re
import numpy as np
import pandas as pd

from . import geo

DIM_CELL_COLS = ["lac_cell", "site_id", "lng", "lat", "district", "aoi"]

def build_dim_cell(ods_cell: pd.DataFrame, districts: dict, aois: dict) -> pd.DataFrame:
    """按 D03 的做法生成 dim_cell: 一个扇区一行，主键 lac_cell 唯一。

    站点 = 坐标相同的扇区，编号按坐标第一次出现的顺序给 S00001、S00002······
    落不进任何区县的标“市外”(不丢)；商圈用 D03 甄别后选定的 v2 边界，落不进商圈的为空。
    """
    cell = ods_cell.dropna(subset=["lng", "lat"])
    sites = cell[["lng", "lat"]].drop_duplicates().reset_index(drop=True)
    sites["site_id"] = "S" + (sites.index + 1).astype(str).str.zfill(5)
    sites["district"] = pd.Series(geo.point_in_polygons(sites["lng"], sites["lat"], districts)).fillna("市外")
    sites["aoi"] = geo.point_in_polygons(sites["lng"], sites["lat"], aois)
    dim = cell.merge(sites, on=["lng", "lat"], how="left")[DIM_CELL_COLS].reset_index(drop=True)
    if not dim["lac_cell"].is_unique:
        raise ValueError("dim_cell 的主键 lac_cell 不唯一: 每 join 一次信令行数就会被放大")
    return dim

def build_dim_hotspot(dwd: pd.DataFrame, dim_cell: pd.DataFrame, top_n: int,
                      name: str, radius_m: int) -> pd.DataFrame:
    """按D04的做法定热点中心: 连接用户数前 top_n 的站点，按用户数加权平均。

    为什么不用第一名站点的坐标：一座基站覆盖几百米，第一名只是那座铁塔的位置，不是人群的重心。
    top_n、name、radius_m 由调用方从 settings.yaml 的 hotspot 段传进来（D06 起去掉了默认值，docs/工程规范.md 第 8 条）。
    """
    sig = dwd[["imsi", "lac_cell"]].merge(dim_cell[["lac_cell", "site_id", "lng", "lat"]], on="lac_cell")
    users = (sig.groupby(["site_id", "lng", "lat"])["imsi"].nunique()
             .sort_values(ascending=False).reset_index(name="n_users"))
    top = users.head(top_n)
    return pd.DataFrame([{
        "name": name,
        "lng": float(np.average(top["lng"], weights=top["n_users"])),
        "lat": float(np.average(top["lat"], weights=top["n_users"])),
        "radius_m": radius_m,
        "note": f"连接用户前 {top_n} 的站点按用户数加权的中心",
    }])


def dim_hotspot_from_settings(settings: dict) -> pd.DataFrame:
    """D11 起热点中心写在 settings.yaml 里：dim_hotspot 直接由配置生成，不再每天按当天数据重算。

    build_dim_hotspot 还留着：它是“中心怎么算出来的”的依据（D04 的方法），只在定中心时用一次。
    """
    h = settings["hotspot"]
    return pd.DataFrame([{
        "name": h["name"],
        "lng": float(h["lng"]),
        "lat": float(h["lat"]),
        "radius_m": h["radius_m"],
        "note": f"settings.yaml（按 D04 的方法用 10-03 的数据算出，连接用户数前 {h['top_n']} 的站点加权）",
    }])


METRIC_COLS = ["metric", "meaning", "definition", "params", "source_table"]
METRIC_LABELS = {"metric": "指标", "meaning": "业务含义", "definition": "计算口径", "params": "参数",
                 "source_table": "来源表", "version": "版本"}           # 给人看的表头：报告、平台、导出的口径表
_PLACEHOLDER = re.compile(r"\{([a-z_]+(?:\.[a-z_]+)+)\}")


def render(template: str, settings: dict) -> str:
    """把模板里的 {stay.min_minutes} 这类占位符换成 settings 里对应的值；找不到的参数直接报错。"""
    def lookup(m):
        node = settings
        for key in m.group(1).split("."):
            if not isinstance(node, dict) or key not in node:
                raise KeyError(f"口径模板引用了不存在的参数：{m.group(1)}")
            node = node[key]
        return f"{node:g}" if isinstance(node, float) else str(node)
    return _PLACEHOLDER.sub(lookup, str(template))


def build_dim_metric(settings: dict) -> pd.DataFrame:
    """指标口径表：文字由 settings.yaml 的 metrics 模板渲染，口径和代码用的是同一份参数（docs/工程规范.md 第 9 条）。

    D08 以前这张表是手写的：改了参数忘了改口径表，两边就对不上。现在参数一改，口径表跟着变。
    版本列取 settings 的 version。
    """
    rows = [{k: render(m[k], settings) for k in METRIC_COLS} for m in settings["metrics"]]
    out = pd.DataFrame(rows, columns=METRIC_COLS)
    out["version"] = f"v{settings['version']}"
    return out


AREA_COLS = ["area", "kind", "center_lng", "center_lat", "radius_m", "source", "note"]


def build_dim_area(settings: dict, aois: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """分析区域维表（D13）：按 settings["areas"] 生成，返回 (dim_area, dim_area_polygon)。

    加一个区域 = 在配置里加一项，下游的表、报告、平台自动出现，代码一行不改。三种写法：
      · kind: hotspot —— 圆形，圆心和半径取 settings["hotspot"]：西塔的坐标只写一处；
      · kind: circle  —— 圆形，配置里给 lng、lat、radius_m；
      · kind: polygon —— 边界取自 aois（D03 选定的 ods_aoi_v2，由调用方还原好传进来），中心用面积质心。
    """
    rows, verts = [], []
    for a in settings["areas"]:
        name, kind = a["name"], a["kind"]
        if kind == "hotspot":
            h = settings["hotspot"]
            rows.append({"area": name, "kind": "circle", "center_lng": float(h["lng"]), "center_lat": float(h["lat"]),
                         "radius_m": h["radius_m"], "source": "settings.hotspot", "note": a.get("note", "")})
        elif kind == "circle":
            rows.append({"area": name, "kind": "circle", "center_lng": float(a["lng"]), "center_lat": float(a["lat"]),
                         "radius_m": a["radius_m"], "source": "settings.areas", "note": a.get("note", "")})
        elif kind == "polygon":
            if name not in aois:
                raise ValueError(f"配置里的区域“{name}”在商圈边界（ods_aoi_v2）里找不到")
            rings = aois[name]
            c_lng, c_lat = geo.polygon_centroid(max(rings, key=len))   # 有多个环时用顶点最多的外环定中心
            rows.append({"area": name, "kind": "polygon", "center_lng": c_lng, "center_lat": c_lat,
                         "radius_m": None, "source": "ods_aoi_v2", "note": a.get("note", "")})
            for r, ring in enumerate(rings):
                verts.append(pd.DataFrame({"area": name, "ring": r, "seq": range(len(ring)),
                                           "lng": ring[:, 0], "lat": ring[:, 1]}))
        else:
            raise ValueError(f"区域类型只能是 hotspot、circle、polygon：{a}")
    poly = pd.concat(verts, ignore_index=True) if verts else pd.DataFrame(columns=["area", "ring", "seq", "lng", "lat"])
    return pd.DataFrame(rows, columns=AREA_COLS), poly
