"""客流节律：每个分析区域一天的在场曲线。"""
import lib  # noqa: F401
from lib import charts as C, queries as Q, ui
import streamlit as st

ui.setup("客流节律")
con, dt, area, synthetic = ui.sidebar()
if dt is None:
    st.stop()
h = Q.area_hourly(con, dt)
st.plotly_chart(C.line_hourly(h, area), use_container_width=True)
st.caption("每人每小时一个位置；区域可以重叠，各区域人数不能相加；口径：ads_area_hourly。")
st.dataframe(h, use_container_width=True)
