"""契约测试共用的小工具（讲师提供）。

MySQL 版的约定：测试只读 signal_insight，从不在里面建表、写表。
要写库的测试都在 sandbox() 建的临时库 test_course_xxx 里跑：进来时是空库，出去时连库删掉。
D01-2 已经给 signal_app 授过 test_course_ 开头的库的权限；D01、D02 演示建库用的也是这个机制。
"""
import ast
from contextlib import contextmanager
from pathlib import Path

import pytest
from signal_mysql import database as mysql

from signal_insight import config

PKG = Path(config.__file__).resolve().parent
SANDBOX_PREFIX = "test_course_"


def ods_available() -> bool:
    """连得上 MySQL，并且 signal_insight 里有 ods_signal。只读连接，查完就关。"""
    try:
        con = mysql.connect(config.DB_SCHEMA, readonly=True)
    except Exception:                    # 终端没载入 .env.ps1、MySQL 没启动、库还没迁移……
        return False
    try:
        return mysql.table_exists(con, "ods_signal")
    finally:
        con.close()


needs_data = pytest.mark.skipif(not ods_available(),
                                reason=f"需要 MySQL 库 {config.DB_SCHEMA} 里的 ods_signal："
                                       f"先在终端载入 .env.ps1，并确认 D01 第 6 步已经迁移")


@contextmanager
def sandbox(label: Path):
    """临时 MySQL 库：with sandbox(tmp_path) as con: …

    label 一般传 pytest 的 tmp_path，只当标签用：mysql.connect(Path) 把它映射成唯一的 test_course_ + 哈希，
    自动建库，不读写任何文件。离开 with 时先回滚，再连库带表删掉，最后关连接——
    database.Connection 自己的 with 只提交、不关连接，所以这里不用它。
    """
    con = mysql.connect(Path(label))
    if not con.schema.startswith(SANDBOX_PREFIX):          # 保险：无论怎么调用，都删不到 signal_insight
        con.close()
        raise ValueError(f"临时库必须以 {SANDBOX_PREFIX} 开头，收到：{con.schema}")
    try:
        yield con
    finally:
        try:
            con.rollback()
            con.execute(f"DROP DATABASE IF EXISTS {mysql.ident(con.schema)}")
        finally:
            con.close()


@contextmanager
def ods_copy(label: Path):
    """临时库里放一份 signal_insight 的全部 ods_ 表：测试只读 ODS，不依赖、也不改动学生自己建的表。

    表结构用 CREATE TABLE … LIKE 照抄（列类型、索引都一样），数据用 INSERT … SELECT 复制，
    53 万行在 MySQL 服务器里直接搬，不经过 Python。复制完先提交，再交给测试。
    """
    src = mysql.connect(config.DB_SCHEMA, readonly=True)
    try:
        names = mysql.table_names(src, "ods_")
    finally:
        src.close()
    schema = mysql.ident(config.DB_SCHEMA)
    with sandbox(label) as con:
        for name in names:
            con.execute(f"CREATE TABLE {mysql.ident(name)} LIKE {schema}.{mysql.ident(name)}")
            con.execute(f"INSERT INTO {mysql.ident(name)} SELECT * FROM {schema}.{mysql.ident(name)}")
            con.commit()
        yield con


def count_elsewhere(schema: str, table: str) -> int:
    """另开一个连接数行数。只有提交了的数据，别的连接才看得见：用来检查“写完有没有提交”。"""
    other = mysql.connect(schema)
    try:
        return other.execute(f"SELECT COUNT(*) FROM {mysql.ident(table)}").fetchone()[0]
    finally:
        other.close()


def imported_names(module_file: Path) -> set[str]:
    """一个 .py 文件 import 了哪些模块（含相对导入，形如 .config、..geo）。"""
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            names.add(base)
            sep = "" if base.endswith(".") else "."
            names.update(f"{base}{sep}{a.name}" for a in node.names)
    return names


def called_names(module_file: Path) -> set[str]:
    """一个 .py 文件里调用过的函数名和方法名（只看代码，不看注释和文档字符串）。"""
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            out.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
    return out


DB_MODULES = {"signal_mysql", "sqlalchemy", "pymysql", "sqlite3", "db"}      # db：项目里的 signal_insight.db
DB_CALLS = {"connect", "execute", "executemany", "read_frame", "write_frame", "write_partition", "read_partition",
            "replace_table", "append_table", "read_sql", "read_sql_query", "read_sql_table", "to_sql"}


def touches_database(module_file: Path) -> bool:
    """规则 4 的自动检查：import 了连库的模块（signal_mysql、sqlalchemy、pymysql、sqlite3、项目里的 db），
    或调用了读写库的函数（read_frame、write_frame、write_partition、read_sql、to_sql、connect、execute……）。"""
    parts = {p for n in imported_names(module_file) for p in n.split(".") if p}
    return bool(parts & DB_MODULES) or bool(called_names(module_file) & DB_CALLS)


def dws_files() -> list[Path]:
    """汇总层的代码文件：D06–D07 是一个 dws.py，D08 起是 dws/ 文件夹。"""
    return [PKG / "dws.py"] if (PKG / "dws.py").exists() else sorted((PKG / "dws").glob("*.py"))


def numeric_constants(module_file: Path) -> set:
    """一个 .py 文件里出现的数字常量（只看代码）。用来检查有没有把业务参数写死。"""
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
    return {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and type(n.value) in (int, float)}
