"""页面框架：标题、侧边栏、连接。每页只写自己的内容。"""
import pandas as pd
import streamlit as st

from signal_insight import config

from . import queries as Q


def setup(title):
    st.set_page_config(page_title=f"信令客流洞察 · {title}", layout="wide")
    st.title(title)


def sidebar():
    con = Q.connect()
    ds = Q.dates(con)
    dt = st.sidebar.selectbox("日期", ds, index=len(ds) - 1) if ds else None
    ar = Q.areas(con)
    area = st.sidebar.selectbox("区域", ar) if ar else None
    part = Q.dq_partition(con)
    synthetic = bool(part.loc[part["dt"] == dt, "is_synthetic"].any()) if dt is not None else False
    if synthetic:
        st.sidebar.warning("这一天含模拟分区：仅用于流水线演示")
    st.sidebar.caption(f"配置版本 {config.config_hash(config.load_settings())}")
    return con, dt, area, synthetic


def stop_if_suppressed(value, area):
    if value is None or (isinstance(value, float) and value != value):
        st.info(f"{area} 当天傍晚访客少于 5 人，按小样本抑制规则不展示指标。换一个区域试试。")
        st.stop()


def kpi(label, value):
    st.metric(label, "—" if value is None else value)
