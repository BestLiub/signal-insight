"""汇总层（dws_）：一张表一个文件（D08 起；D06–D07 时是一个文件 dws.py）。

docs/工程规范.md 第 5 条：这一层的表超过 3 张、或文件超过约 300 行，就把模块变成同名文件夹。
下面的重新导出保证原来的写法一行不改：dws.build_stay(...)、from signal_insight.dws import build_trip 照样能用。
"""
from .stay import STAY_COLS, build_stay, find_segments
from .night import NIGHT_COLS, build_night
from .trip import TRIP_COLS, build_trip
