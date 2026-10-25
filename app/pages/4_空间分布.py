"""空间分布：六边形热力（少于 5 人的格子不显示）。"""
import lib  # noqa: F401
from lib import charts as C, queries as Q, ui
import streamlit as st

ui.setup("空间分布")
con, dt, area, synthetic = ui.sidebar()
if dt is None:
    st.stop()
hx = Q.hex_hourly(con, dt)
if hx.empty:
    st.info("这一天没有可展示的六边形格子。")
    st.stop()
hours = sorted(hx["hour"].unique())
hour = st.selectbox("小时", hours, index=len(hours) - 1)
st.plotly_chart(C.hex_scatter(hx, hour), use_container_width=True)
st.caption("六边形边长 550 米；少于 5 人的格子直接不输出（地图上就是空白）。")
