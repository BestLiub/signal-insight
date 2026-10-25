"""信令客流洞察平台 · 总览。运行：在项目根目录执行 streamlit run app/Home.py"""
import lib  # noqa: F401  （把 src/ 加进搜索路径）
from lib import charts as C, queries as Q, ui
import pandas as pd
import streamlit as st

ui.setup("总览")
con, dt, area, synthetic = ui.sidebar()
if dt is None:
    st.info("生产库还没有数据：先运行 python -m signal_insight init 和 run --date …")
    st.stop()
d = Q.area_daily(con, dt).set_index("area")
if area not in d.index or pd.isna(d.loc[area, "evening_visitors"]):
    ui.stop_if_suppressed(None, area)
r = d.loc[area]
h = Q.area_hourly(con, dt)
hh = h[(h["area"] == area)].dropna(subset=["users"])
pk = hh.loc[hh["users"].idxmax()] if len(hh) else None
c1, c2, c3, c4 = st.columns(4)
with c1:
    ui.kpi("傍晚访客", f"{int(r['evening_visitors']):,} 人")
with c2:
    ui.kpi("停留时长中位", "—" if pd.isna(r["stay_min_p50"]) else f"{r['stay_min_p50']:.0f} 分钟")
with c3:
    ui.kpi("客源距离中位", "—" if pd.isna(r["night_dist_km_p50"]) else f"{r['night_dist_km_p50']:.1f} 公里")
with c4:
    ui.kpi("23 点后仍在", "—" if pd.isna(r["censored_share"]) else f"{r['censored_share']:.0%}")
if pk is not None:
    st.caption(f"{area} 的高峰在 {int(pk['hour'])} 点，在场 {int(pk['users']):,} 人。")
st.plotly_chart(C.line_hourly(h, area), use_container_width=True)
st.dataframe(Q.area_daily(con, dt), use_container_width=True)
if synthetic:
    st.warning("本页含模拟分区，仅用于演示。")
