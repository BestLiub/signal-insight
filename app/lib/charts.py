"""Plotly 图：和报告同源（颜色、标题规则一致）。"""
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

MAIN, MAIN_LIGHT, RED, AMBER, GRAY = "#1D6FA5", "#DCEAF5", "#D64545", "#B7791F", "#C4CAD3"


def _layout(fig, title):
    fig.update_layout(title=title, template="plotly_white", margin=dict(l=10, r=10, t=50, b=10),
                      font=dict(family="Noto Sans SC, Microsoft YaHei, sans-serif", size=13))
    return fig


def line_hourly(df, area=None):
    d = df if area is None else df[df["area"] == area]
    fig = px.line(d, x="hour", y="users", color="area", markers=True)
    return _layout(fig, "每小时在场人数")


def bar_segment(df):
    fig = px.bar(df, x="area", y="users", color="segment", barmode="group")
    return _layout(fig, "客群构成（少于 5 人的格子已隐藏）")


def line_radius(df):
    fig = px.line(df, x="band_order", y="cum_share", color="area", markers=True)
    fig.update_yaxes(tickformat=".0%")
    return _layout(fig, "辐射圈层累计占比")


def bar_linkage(df):
    d = df.melt(id_vars=["area", "other_area"], value_vars=["share_before", "share_after"],
                var_name="时机", value_name="share")
    d["时机"] = d["时机"].map({"share_before": "先去", "share_after": "后去"})
    fig = px.bar(d, x="other_area", y="share", color="时机", facet_row="area", barmode="group")
    fig.update_yaxes(tickformat=".0%")
    return _layout(fig, "商圈联动：先去 / 后去")


def hex_scatter(df, hour):
    d = df[df["hour"] == hour].copy()
    # plotly 6 起 scatter_mapbox 换成 MapLibre 的 scatter_map（mapbox_style → map_style）
    # center 必须显式给：不给时 MapLibre 停在西经 0°、北纬 0°，zoom 11 下点全在屏幕外
    center = ({"lon": float(d["center_lng"].mean()), "lat": float(d["center_lat"].mean())}
              if len(d) else {"lon": 123.41, "lat": 41.81})
    # 人数从 5 到 2,000 跨 400 倍：面积用平方根（面积 ∝ 人数），颜色用对数，
    # 否则人少的格子会被压成看不清的小白点，而西塔那一格独占整条色阶。
    d["色阶"] = np.log10(d["users"])
    fig = px.scatter_map(d, lat="center_lat", lon="center_lng", size="users", color="色阶",
                         color_continuous_scale=[[0, "#8FBCDA"], [0.5, "#3E86B5"], [1, "#0B3C5D"]],
                         range_color=(np.log10(5), np.log10(2000)), size_max=40,
                         zoom=10, height=520, center=center,
                         map_style="carto-positron", custom_data=["users", "q", "r"])
    fig.update_traces(marker=dict(sizemin=7, opacity=0.9),
                      hovertemplate="格子 (%{customdata[1]}, %{customdata[2]})<br>"
                                    "在场 %{customdata[0]:,} 人<extra></extra>")
    fig.update_layout(coloraxis_colorbar=dict(
        title="在场人数", thickness=12,
        tickvals=[np.log10(v) for v in (5, 10, 30, 100, 300, 1000, 2000)],
        ticktext=["5", "10", "30", "100", "300", "1,000", "2,000"]))
    return _layout(fig, f"{hour} 点六边形热力（少于 5 人不显示）")


def bar_origin(df, area):
    d = df[df["area"] == area].head(10)
    fig = px.bar(d, x="users", y="origin", orientation="h")
    return _layout(fig, f"{area} 客源区县前 10 位")


def heatmap_rules(df):
    pivot = df.pivot(index="dt", columns="rule_id", values="value")
    fig = go.Figure(go.Heatmap(z=pivot.values, x=pivot.columns, y=pivot.index,
                               colorscale=[[0, MAIN_LIGHT], [0.5, AMBER], [1, RED]]))
    return _layout(fig, "门禁规则结果")
