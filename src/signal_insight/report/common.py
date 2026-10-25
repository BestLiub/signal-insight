"""报告包的公共件：来源行、数值格式、区域颜色、模拟数据标记。"""
from .. import config


def source_line(settings, extra=""):
    """每张图、每份报告的来源行：数据来源 + 配置版本（数字可追溯到哪一版参数）。"""
    return f"数据来源：沈阳移动信令样本（脱敏，2018 年国庆）；加工：signal_insight 配置 {config.config_hash(settings)}" + (f"；{extra}" if extra else "")


def is_synth(df, col="is_synthetic"):
    """这张表里有没有模拟分区：有就在图/报告上打水印。"""
    return bool(col in df.columns and df[col].astype(int).any())


def fmt_int(v):
    return "—" if v is None or (isinstance(v, float) and v != v) else f"{int(v):,}"


def fmt_pct(v, digits=1):
    return "—" if v is None or (isinstance(v, float) and v != v) else f"{v:.{digits}%}"


def md(text, **kw):
    """把模板里的 {key} 换成 kw 里的值；找不到就原样留着（报告不该因为一句措辞生成失败）。"""
    try:
        return text.format(**kw)
    except (KeyError, IndexError):
        return text
