"""数据质量：分区健康、门禁规则结果。"""
import lib  # noqa: F401
from lib import charts as C, queries as Q, ui
import streamlit as st

ui.setup("数据质量")
con, dt, area, synthetic = ui.sidebar()
part = Q.dq_partition(con)
st.dataframe(part, use_container_width=True)
if dt is not None:
    st.plotly_chart(C.heatmap_rules(Q.dq_rule(con, dt)), use_container_width=True)
st.caption("红 = 不通过，黄 = 警告；任何一条不通过，整个分区不通过、下游一行都不写。")
