"""指标口径：dim_metric 的完整表格，给不看代码的人查。"""
import lib  # noqa: F401
from lib import queries as Q, ui
import streamlit as st

ui.setup("指标口径")
con, dt, area, synthetic = ui.sidebar()
st.dataframe(Q.metrics(con), use_container_width=True)
st.caption("口径由 config/settings.yaml 的 metrics 模板渲染：参数一改，这张表跟着变。")
