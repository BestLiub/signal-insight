"""客源与圈层：客群构成、辐射圈层、客源区县。"""
import lib  # noqa: F401
from lib import charts as C, queries as Q, ui
import streamlit as st

ui.setup("客源与圈层")
con, dt, area, synthetic = ui.sidebar()
if dt is None:
    st.stop()
seg = Q.area_segment(con, dt)
rad = Q.area_radius(con, dt)
ori = Q.area_origin(con, dt)
st.plotly_chart(C.bar_segment(seg), use_container_width=True)
st.plotly_chart(C.line_radius(rad), use_container_width=True)
st.plotly_chart(C.bar_origin(ori, area), use_container_width=True)
st.caption("互补抑制：同一组只藏一格时再藏最小的一格；圈层只在能识别过夜地的人里累计。")
