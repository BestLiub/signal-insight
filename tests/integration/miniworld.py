"""测试用的“迷你世界”（D13）：4 个基站、1 个区县、1 个商圈、20 个用户、几天的信令，答案事先知道。

真数据太大、答案未知：跑一遍要几分钟，错了也看不出来。迷你世界几秒钟跑完整条流水线，每个数都能手算。
一个人的一天：0–9 点在 A、B 两个基站之间乒乓（人没动，基站在跳），10–16 点在 C（测试商圈里），18 点以后回到 A。
"""
import copy

import pandas as pd

from signal_mysql import database as mysql

from signal_insight import config, ingest, pipeline

CELLS = {                                    # lac_cell: (lng, lat)
    "1-1": (123.400, 41.800),                # A：测试热点中心
    "1-2": (123.402, 41.800),                # B：离 A 约 166 米（模拟乒乓切换）
    "1-3": (123.450, 41.800),                # C：离 A 约 4.2 公里，在“测试商圈”里
    "1-4": (122.000, 41.000),                # D：市外
}
D1, D2, D3 = "2018-10-10", "2018-10-11", "2018-10-12"


def make_settings(**over) -> dict:
    """真实的 settings.yaml 打底，把热点、区域、门禁基准换成迷你世界的。"""
    s = copy.deepcopy(config.load_settings())
    s["hotspot"] = {**s["hotspot"], "name": "测试热点", "lng": 123.400, "lat": 41.800, "radius_m": 500}
    s["areas"] = [{"name": "测试热点", "kind": "hotspot"}, {"name": "测试商圈", "kind": "polygon"}]
    s["gate"] = {**s["gate"], "bootstrap": {"rows": 2000, "rows_per_user": 100.0}}
    s["ads"] = {**s["ads"], "focus_area": "测试热点", "hex": {**s["ads"]["hex"], "origin_area": "测试热点"}}
    s.update(over)
    return s


def _ms(local):
    return int((pd.Timestamp(local) - pd.Timedelta(hours=config.UTC_OFFSET_HOURS) - pd.Timestamp("1970-01-01"))
               / pd.Timedelta(milliseconds=1))


def user_day_records(imsi, day, keep_hours=range(24)):
    """一个人一天的信令，每 12 分钟一条；17 点没有信令（模拟一个空档）。"""
    rows = []
    for i, t in enumerate(pd.date_range(f"{day} 00:00", f"{day} 23:59", freq="12min")):
        if t.hour not in keep_hours or t.hour == 17:
            continue
        cell = ("1-1" if i % 2 else "1-2") if t.hour < 10 else "1-3" if t.hour < 17 else "1-1"
        lac, ci = cell.split("-")
        ts = _ms(t)
        rows.append((ts, imsi, float(lac), float(ci), "86130000000000", ts - 5, None, "", 20, "#*#0000"))
    return rows


def build_source_db(path, days, n_users=20, sparse_days=()):
    """生成和 signal.db 同样结构的 ODS 库。sparse_days 里的日期只有 1 个用户、3 个小时（门禁应拦下）。"""
    rows = []
    for d in days:
        users = [f"4600000950000000{u:02d}" for u in range(n_users)]
        if d in sparse_days:
            rows += user_day_records(users[0], d, keep_hours=[10, 11, 12])
        else:
            for u in users:
                rows += user_day_records(u, d)
    rows.append(rows[0])                      # 一条完全重复
    rows.append((rows[1][0], None, 1.0, 1.0, "", 0, None, "", 2, ""))   # 一条缺 IMSI
    cols = ["timestamp", "imsi", "lac_id", "cell_id", "phone", "timestamp1", "tmp0", "tmp1", "nid", "npid"]
    with mysql.connect(path) as con:
        mysql.write_frame(pd.DataFrame(rows, columns=cols), "ods_signal", con, index=False)
        mysql.write_frame(pd.DataFrame([(lng, lat, k) for k, (lng, lat) in CELLS.items()],
                                       columns=["lng", "lat", "lac_cell"]), "ods_cell", con, index=False)
        square = [(123.3, 41.7), (123.6, 41.7), (123.6, 41.9), (123.3, 41.9)]
        mysql.write_frame(pd.DataFrame([("000000", "测试区", 0, i, x, y) for i, (x, y) in enumerate(square)],
                                       columns=["adcode", "district", "ring", "seq", "lng", "lat"]),
                          "ods_district_boundary", con, index=False)
        mall = [(123.445, 41.795), (123.455, 41.795), (123.455, 41.805), (123.445, 41.805)]
        mysql.write_frame(pd.DataFrame([("测试商圈", i, x, y) for i, (x, y) in enumerate(mall)],
                                       columns=["name", "seq", "lng", "lat"]), "ods_aoi_v2", con, index=False)
        empty = {"ods_poi_purpose": ["lng", "lat", "type", "name"],
                 "ods_poi_transport": ["lng", "lat", "type", "name", "line"],
                 "ods_aoi_v1": ["name", "seq", "lng", "lat"], "ods_aoi_json": ["name", "seq", "x", "y"],
                 "ods_nid_mapping": ["nid", "推测含义", "所属网元(4GEPC)", "大类"]}
        for t, cols_ in empty.items():        # 用不到，但生产库要求 9 张 ods_ 表齐全
            mysql.write_frame(pd.DataFrame(columns=cols_), t, con, index=False)
    return path


def build_warehouse(tmp_path, days=(D1, D2), sparse=(), settings=None):
    """建好迷你世界的生产库并生成维表，返回 (库名, settings)。连接由调用方用 with 打开、关闭。"""
    settings = settings or make_settings()
    src = build_source_db(tmp_path / "src", days, sparse_days=sparse)
    wh = ingest.init_warehouse(src, tmp_path / "wh")
    with mysql.connect(wh) as con:
        pipeline.refresh_dims(con, settings)
    return wh, settings


def fingerprint(con, dt, tables):
    """几张表在某一天的“指纹”：行数 + 内容哈希。重跑前后比指纹，就知道有没有一行变了。"""
    out = {}
    for t in tables:
        df = mysql.read_frame(f"SELECT * FROM {t} WHERE dt = ?", con, params=(dt,))
        df = df.sort_values(list(df.columns)).reset_index(drop=True)
        out[t] = (len(df), int(pd.util.hash_pandas_object(df, index=False).sum()) if len(df) else 0)
    return out
