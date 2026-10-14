"""数据质量：稽核记录。只会因为“稽核记录的格式变了”而改（docs/工程规范 nd 第2条）
D01 在 notebook 里写的 dq_record 用的是全局变量 con；搬进来以后连接改成第一个参数——
函数偷偷依赖 notebook 的全局变量，是封装时最常见的坑；在 notebook 里能跑，搬出来就 NameError。

读写稽核表用 singal_mysql.batabase 的 read_frame / write_frame，"怎么进库"
连接由调用方用 mysql.connect(config.DB_SCHEMA) 建好传进来。每记一条就提交一次，关掉 notebook 也不会丢。
"""
import pandas as pd

from signal_mysql import database as mysql

STATUSES = ("通过", "警告", "不通过")
COLUMNS = ["check_id", "dimension", "item", "field", "result", "status", "evidence", "decision"]  # 列名和参数名一一对应

# 重构后的，工程化的数据质量埋点函数，解决了之前notebook版本的重大缺陷，不再偷偷依赖全局数据库连接con，把连接作为第一个入参传入，可以单独抽成py模块
# 脱离notebook也能正常运行
# 核心：写入DQ稽核结果，相同 check_id 自动覆盖旧记录，MySQL 写入后手动commit防止事务回滚
# con: 数据库连接对象
# check_id: 稽核任务唯一编号，核心主键标识
# dimension: 质检维度，数据质检大类（完整性、准备性、时效性、一致性、唯一性）
# item: 稽核项名称，当前这条检查是干什么的
# field: 被检查的字段名
# result: 稽核结果文本，放统计数字、结论
# status: 稽核状态，只能三选一
# evidence: 证据备注，用来存储辅助信息
# decision: 处置意见，发现问题之后怎么处理
def dq_record(con, check_id: str, dimension: str, item: str, field: str, result: str, status: str, evidence: str = "", decision: str="") -> None:
    """把一条检查结果记进 dq_check_result 表：同一个 check_id 再记一次会覆盖旧记录(重跑不会越记越多)。"""
    if status not in STATUSES:
        raise ValueError(f"状态只能是 {' / '.join(STATUSES)}，收到：{status!r}")
    row = pd.DataFrame([dict(zip(COLUMNS, [check_id, dimension, item, field, result, status, evidence, decision]))])
    try:
        old = mysql.read_frame("SELECT * FROM dq_check_result", con)
    except Exception:
        old = row.iloc[0:0]  # 第一次记录时这张表还不存在
    new = pd.concat( [old[old["check_id"] != check_id], row], ignore_index=True)
    mysql.write_frame(new, "dq_check_result", con, if_exists="replace", index=False)
    con.commit() # MySQL:记完就提交。连接已在事务里时 pandas 不会替我们提交，关连接时没提交的会被回滚
    print(f"[{status}] {check_id} {dimension} | {item}: {result}")