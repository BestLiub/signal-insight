"""数据质量：稽核记录。只会因为“稽核记录的格式变了”而改（docs/工程规范 nd 第2条）
D01 在 notebook 里写的 dq_record 用的是全局变量 con；搬进来以后连接改成第一个参数——
函数偷偷依赖 notebook 的全局变量，是封装时最常见的坑；在 notebook 里能跑，搬出来就 NameError。

读写稽核表用 singal_mysql.batabase 的 read_frame / write_frame, "怎么进库"
连接由调用方用 mysql.connect(config.DB_SCHEMA) 建好传进来。每记一条就提交一次，关掉 notebook 也不会丢。
"""
import pandas as pd

from signal_mysql import database as mysql

STATUSES = ("通过", "警告", "不通过")
COLUMNS = ["check_id", "dimension", "item", "field", "result", "status", "evidence", "decision"]  # 列名和参数名一一对应

# 重构后的，工程化的数据质量埋点函数，解决了之前notebook版本的重大缺陷，不再偷偷依赖全局数据库连接con，把连接作为第一个入参传入，可以单独抽成py模块
# 脱离notebook也能正常运行
# 核心：写入DQ稽核结果，相同 check_id 自动覆盖旧记录，MySQL写入后手动commit防止事务回滚
# con: 数据库连接对象
# check_id: 稽核任务唯一编号，核心主键标识
# dimension: 质检维度，数据质检大类（完整性、准备性、时效性、一致性、唯一性）
# item: 稽核项名称，当前这条检查是干什么的
# field: 被检查的字段名
# result: 稽核结果文本，放统计数字、结论
# status: 稽核状态，只能三选一
# evidence:证据备注，用来存储辅助信息
# decision: 处置意见，发现问题之后怎么处理
def dq_record(con, check_id: str, dimension: str, item: str, field: str, result: str, status: str, evidence: str = "", decision: str="") -> None:
    """把一条检查结果记进 dq_check_result 表；同一个 check_id 再记一次会覆盖旧记录(重跑不会越记越多)。"""
    if status not in STATUSES:
        raise ValueError(f"状态只能是 {' /'.join(STATUSES)}, 收到: {status!r}")
    row = pd.DataFrame([dict(zip(COLUMNS, [check_id, dimension, item, field, result, status, evidence, decision]))])
    try:
        old = mysql.read_frame("SELECT * FROM dq_check_result", con)
    except Exception:                            # 第一次记录时这张表还不存在
        old = row.iloc[0:0]
    new = pd.concat([old[old["check_id"] != check_id], row], ignore_index=True)
    mysql.write_frame(new, "dq_check_result", con, if_exists="replace", index=False)
    con.commit()                    # MySQL:记完就提交。连接已在事务里时 pandas 不会替我们提交，关连接时没提交的会被回滚
    print(f"[{status}] {check_id} {dimension} | {item}: {result}")

def profile(df: pd.DataFrame) -> pd.DataFrame:
    """数据画像：每个字段一行————类型，缺失数 (空值 + 空白字符串)、缺失率、唯一值个数、示例值。

        “缺失”不只是空值；只有空格的字符串看起来有值，其实没有任何信息，也算缺失。
        纯计算：只接收 DataFrame，不读库。
    """
    rows = []
    for col in df.columns:
        s = df[col]
        n_null = int(s.isna().sum())
        is_text = pd.api.types.is_string_dtype(s) or s.dtype == object
        n_blank = int(s.astype("string").str.strip().eq("").sum()) if is_text else 0

        # rows.append(xxx) = 把当前这一列的画像信息打包成字典，放到rows列表里存起来，攒完全部字段后再同意变成表格
        rows.append({
            "field": col,  # 就是当前循环的列名字字符串,就是字段名
            "dtype": str(s.dtype),  # s.dtype是这一列的pandas类型(int64/string/float64/datetime64)转成字符串存起来
            "n_missing": n_null + n_blank,  # n_null + n_blank 总缺失数量: 原始NaN空值+空白/全空格字符串
            # "missing_rate": (n_null + n_blank) / len(s),  # 缺失率 = 总缺失数 / 当前列总行数
            "missing_rate" : (n_null + n_blank) / len(df) if len(df) > 0 else 0.0, # 缺失率 = 总缺失数 / 当前列总行数
            # nunique()默认不计入NaN，如果想要把NaN也算一个独立的值，要写成nunique(dropna=False)
            # 默认(dropna=True) 外面包int转为普通整数
            "n_unique": int(s.nunique()),  # 统计不重复的值的个数，默认自动忽略NaN
            # s.notna().any() 判断这一列有没有至少一个不是空的值
            # 如果有，s.dropna() 先丢掉所有NaN，再.iloc[0] 取第一个有效值当样例
            # 如果整列全是空：直接赋值 None，防止取数报错
            "example": s.dropna().iloc[0] if s.notna().any() else None,  # 三元判断，用来拿一个非空示例值
        })
    return pd.DataFrame(rows, columns=["field", "dtype", "n_missing", "missing_rate", "n_unique", "example"])

