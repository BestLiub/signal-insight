"""Plotly 图：和报告同源（颜色、标题规则一致）。"""
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
    d = df[df["hour"] == hour]
    # plotly 6 起 scatter_mapbox 换成 MapLibre 的 scatter_map（mapbox_style → map_style）
    # center 必须显式给：不给时 MapLibre 停在西经 0°、北纬 0°，zoom 11 下点全在屏幕外
    center = ({"lon": float(d["center_lng"].mean()), "lat": float(d["center_lat"].mean())}
              if len(d) else {"lon": 123.41, "lat": 41.81})
    fig = px.scatter_map(d, lat="center_lat", lon="center_lng", size="users", color="users",
                         color_continuous_scale="Blues", zoom=10, height=520, center=center,
                         map_style="carto-positron")
    fig.update_traces(marker=dict(sizemin=4, opacity=0.85),
                      hovertemplate="%{text}<br>在场 %{marker.color} 人<extra></extra>",
                      text=[f"格子 ({q},{r})" for q, r in zip(d["q"], d["r"])])
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
