"""商圈联动：A 的傍晚访客里，先去 / 后去 B 的比例。"""
import lib  # noqa: F401
from lib import charts as C, queries as Q, ui
import streamlit as st

ui.setup("商圈联动")
con, dt, area, synthetic = ui.sidebar()
if dt is None:
    st.stop()
lk = Q.area_linkage(con, dt)
st.plotly_chart(C.bar_linkage(lk), use_container_width=True)
st.caption("一人可属多类，比例不能相加；数据只能说明先后顺序，不能说明因果。")
st.dataframe(lk, use_container_width=True)
