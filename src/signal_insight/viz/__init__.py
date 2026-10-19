"""图表：theme 管主题（字体、配色、标题区），maps 管地图。

D02 时这里还是一个文件 viz.py；D04 加地图函数时拆成了包（docs/工程规范.md 第 5 条：一个文件出现第二种改动原因就拆）：
viz.py 用 git mv 改名成 theme.py（内容、提交历史都在），地图函数放进 maps.py。
下面这行"重新导出"保证原来的写法一行都不用改（D01–D03 的 notebook 一个字没动）：
    from signal_insight import viz;  viz.finish(...)          照样能用
    from signal_insight.viz import MAIN, GRAY                  照样能用
"""
from .theme import *          # noqa: F401,F403  （theme.py 里的 __all__ 决定导出哪些名字）
from . import maps            # noqa: F401  地图函数用 viz.maps.xxx 调用
