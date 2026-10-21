"""路径与口径常量；读业务参数文件。整个包的最底层：不 import 项目里的任何模块
（docs/工程规范.md 第 3 条）。
只会因为这几种原因而改（docs/工程规范.md 第 2 条）：
  · 文件放的位置变了   → 改下面的路径常量；
  · 用哪个库变了       → 改库名（MySQL 逻辑库，默认值可被环境变量覆盖）；
  · 口径常量变了       → 改 UTC_OFFSET_HOURS、ANALYSIS_DAY；
  · 参数文件的读法变了 → 改 load_settings。参数本身（500 米、30 分钟......）不在
这里，在 config/settings.yaml。
MySQL 版和原 SQLite 版的区别只有一处：库不再是 data/ 里的 .db 文件，而是 MySQL
服务器上的逻辑库（schema），
所以 DB_PATH / CHECKPOINT_DB / WAREHOUSE_PATH 换成了 DB_SCHEMA /
CHECKPOINT_SCHEMA / WAREHOUSE_SCHEMA（都是字符串）。
账号、密码、主机不写在这里——这个文件要进 Git；它们由 .env.ps1 设成环境变量，
signal_mysql.database 去读。
"""
import hashlib
import json
import os

from pathlib import Path
import yaml
# 路径从"本文件在哪"往上推，而不是用 Path.cwd()。
# cwd 取决于你在哪个文件夹打开 notebook、在哪个目录运行命令，每个人、每次都可能不一样；
# 本文件永远在 src/signal_insight/ 里，往上两级就是项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"              # 讲师发的原始 signal.db、checkpoints.db 放这里（只用于一次性迁移）
IMAGE_DIR = PROJECT_ROOT / "image"            # notebook 出图
REPORT_DIR = PROJECT_ROOT / "reports"         # 生成的报告、备忘录（D09；不进 Git，随时可以重新生成）
LANDING_DIR = DATA_DIR / "landing"            # 上游每天推送的分区文件放这里（D11）
SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"   # 业务参数的唯一来源（D06）
# MySQL 逻辑库名：默认值就是课程约定的名字；环境变量里设了就用环境变量的（换库不用改代码）
DB_SCHEMA = os.environ.get("SIGNAL_INSIGHT_SCHEMA", "").strip() or "signal_insight"
     # 探索库：ODS + D01–D10 的结果表
CHECKPOINT_SCHEMA = os.environ.get("SIGNAL_CHECKPOINT_SCHEMA", "").strip() or "signal_checkpoint"  # 检查点库：跟丢时恢复前一天的表
WAREHOUSE_SCHEMA = os.environ.get("SIGNAL_WAREHOUSE_SCHEMA", "").strip() or "signal_warehouse"
    # 生产库（D11）：多日分区
# 口径常量：写两份、两份不一致的代价比重复大得多，所以第二次出现就收进来（封装触发条件 T3）
UTC_OFFSET_HOURS = 8           # 原始时间戳是 UTC 毫秒；北京时间 = UTC + 8 小时（D01 用作息验证过）
ANALYSIS_DAY = "2018-10-03"    # 只分析 10-03（D01 发现 F1，D02 执行）；D11 多日运行后它会变成运行参数
SOURCE_NOTE = "数据来源：沈阳移动信令样本（脱敏，2018 年国庆）"   # 出图来源行的固定前半句
def load_settings(path=None) -> dict:
    """读 config/settings.yaml，返回嵌套字典，比如 settings["stay"]
["radius_m"]。（D06 起才用到）
    每次调用都重新读文件：notebook 里改了 yaml，不用重启内核。
    文件必须是 UTF-8：用 Windows 记事本"另存为"时选了 ANSI（GBK），这里会给出明
确的报错。
    """
    p = SETTINGS_PATH if path is None else path
    try:
        text = open(p, encoding="utf-8").read()
    except UnicodeDecodeError as e:
        raise UnicodeDecodeError(e.encoding, e.object, e.start, e.end,
                                 f"{p} 不是 UTF-8 编码：用编辑器另存为 UTF-8 再试") from None
    return yaml.safe_load(text)
def config_hash(settings: dict) -> str:
    """这份参数的"指纹"：形如 "2.0.0+f115940a"（声明的版本 + 参数内容的哈希前 8
位）。（D11 起才用到）
    对解析后的参数算哈希，不对文件文本算：加一行注释、调换两个键的顺序，参数没
变，指纹就不该变；
    改了任何一个数，指纹一定变。
    """
    text = json.dumps(settings, sort_keys=True, ensure_ascii=False, default=str)
    return f"{settings['version']}+{hashlib.sha1(text.encode('utf-8')).hexdigest()[:8]}"