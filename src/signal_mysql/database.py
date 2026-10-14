"""真正连接 MySQL：连接池、命名绑定、DataFrame、元数据、迁移和事务。

此模块不使用文件数据库。MySQL DDL 会隐式提交；DDL 和业务 DML 必须分阶段。
"""
from __future__ import annotations
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import hashlib, os, re, uuid
import pandas as pd
import sqlparse
from sqlalchemy import create_engine, text, inspect, types
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError, OperationalError, DatabaseError

def ident(name: str) -> str:
    if not isinstance(name,str) or not name or len(name)>64 or any(c in name for c in ('`','\x00',';')):
        raise ValueError('无效数据库对象名')
    return '`'+name+'`'

def settings_url(schema: str | None, readonly: bool=False):
    supplied=os.environ.get('SIGNAL_MYSQL_URL')
    if supplied:
        base=make_url(supplied)
        if base.drivername!='mysql+pymysql': raise ValueError('仅允许 mysql+pymysql 驱动')
        return base.set(database=schema)
    prefix='SIGNAL_MYSQL_RO_' if readonly and os.environ.get('SIGNAL_MYSQL_RO_USER') else 'SIGNAL_MYSQL_'
    return URL.create('mysql+pymysql',username=os.environ.get(prefix+'USER','signal_app'),
    password=os.environ.get(prefix+'PASSWORD',''),host=os.environ.get('SIGNAL_MYSQL_HOST','127.0.0.1'),
    port=int(os.environ.get('SIGNAL_MYSQL_PORT','3306')),database=schema,query={'charset':'utf8mb4'})

@lru_cache(maxsize=32)
def engine(url):
    return create_engine(url,pool_pre_ping=True,pool_recycle=1800,pool_size=5,max_overflow=5,
                         connect_args={'connect_timeout':10,'init_command':"SET SESSION sql_mode='STRICT_TRANS_TABLES,ANSI_QUOTES,NO_ENGINE_SUBSTITUTION'"},hide_parameters=True)

def create_schema(schema: str):
    schema=schema_name(schema)
    ident(schema)
    with engine(settings_url(None)).connect() as con:
        con.execute(text(f'CREATE DATABASE IF NOT EXISTS {ident(schema)} CHARACTER SET utf8mb4 COLLATE utf8mb4_bin'))
        con.commit()

def schema_exists(schema: str) -> bool:
    schema=schema_name(schema)
    with engine(settings_url(None)).connect() as con:
        return con.execute(text('SELECT 1 FROM information_schema.schemata WHERE schema_name=:schema'),{'schema':schema}).first() is not None

def bind(sql: str, params=None):
    """将旧课程的 ? 占位转为命名参数，不对数据做字符串插值。"""
    # quote 仅作用于 SQL token；字符串字面量与命名绑定保持原样。
    sql = re.sub(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`[^`]*`)|(?<![:\w])\b(cursor|rows|option|groups|rank|condition)\b", lambda m: m[1] if m[1] else '`'+m[2]+'`', sql, flags=re.I)
    if params is None: return text(sql), {}
    if isinstance(params,dict): return text(sql),params
    values=list(params); positions=[]; quote=None; escaped=False
    for i,char in enumerate(sql):
        if escaped: escaped=False;continue
        if char=='\\' and quote: escaped=True;continue
        if char in ("'",'"','`'):
            if quote==char:quote=None
            elif quote is None:quote=char
        elif char=='?' and quote is None:positions.append(i)
    if len(positions)!=len(values):raise ValueError('SQL 占位符与参数数目不一致')
    for n,pos in reversed(list(enumerate(positions))):sql=sql[:pos]+f':p{n}'+sql[pos+1:]
    return text(sql),{f'p{i}':value for i,value in enumerate(values)}

class Row:
    def __init__(self,row):self.mapping=dict(row._mapping);self.values=tuple(row)
    def __getitem__(self,key):return self.values[key] if isinstance(key,int) else self.mapping[key]
    def __iter__(self):return iter(self.values)
    def keys(self):return self.mapping.keys()

class Result:
    def __init__(self,result):self.raw=result
    def fetchone(self):
        row=self.raw.fetchone();return None if row is None else Row(row)
    def fetchall(self):return [Row(r) for r in self.raw.fetchall()]
    def __iter__(self):return (Row(r) for r in self.raw)
    @property
    def lastrowid(self):return self.raw.lastrowid
    @property
    def rowcount(self):return self.raw.rowcount
    def scalar(self):return self.raw.scalar()
    @property
    def description(self):return [(name,None,None,None,None,None,None) for name in self.raw.keys()]

class Connection:
    def __init__(self,schema: str,readonly: bool=False):
        if isinstance(schema,Path):
            label=schema;schema=schema_name(label)
            if not readonly:create_schema(schema)
        ident(schema);self.schema=schema;self.readonly=readonly
        self.sa=engine(settings_url(schema,readonly)).connect()
        # 双引号为标识符；严格模式拒绝截断及坏值，连接时重置只读状态。
        self.sa.exec_driver_sql("SET SESSION sql_mode='STRICT_TRANS_TABLES,ANSI_QUOTES,NO_ENGINE_SUBSTITUTION'")
        self.sa.exec_driver_sql("SET SESSION time_zone='+00:00'")
        self.sa.exec_driver_sql('SET SESSION transaction_read_only='+('ON' if readonly else 'OFF'))
        self.sa.commit()
    def execute(self,sql,params=None):
        statement,values=bind(sql,params)
        return Result(self.sa.execute(statement,values))
    def executemany(self,sql,rows):
        rows=list(rows)
        if not rows:return None
        statement,_=bind(sql,rows[0]);values=[bind(sql,row)[1] for row in rows]
        return Result(self.sa.execute(statement,values))
    def commit(self):self.sa.commit()
    def rollback(self):self.sa.rollback()
    def close(self):self.sa.close()
    def __enter__(self):return self
    def __exit__(self,exc_type,exc,tb):self.rollback() if exc_type else self.commit()

def connect(schema: str | None=None, readonly: bool=False) -> Connection:
    return Connection(schema or os.environ.get('SIGNAL_INSIGHT_SCHEMA','signal_insight'),readonly)

def read_frame(sql,con,params=None,**kwargs):
    statement,values=bind(sql,params)
    return pd.read_sql(statement,con.sa,params=values,**kwargs)

def frame_types(df):
    result={}
    for col in df.columns:
        s=df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            from sqlalchemy.dialects.mysql import DATETIME
            result[col]=DATETIME(fsp=3)
        elif pd.api.types.is_integer_dtype(s) or pd.api.types.is_bool_dtype(s):result[col]=types.BigInteger()
        elif pd.api.types.is_float_dtype(s):result[col]=types.Float(precision=53)
        else:
            longest=int(s.dropna().astype(str).str.len().max()) if len(s.dropna()) else 0
            result[col]=types.String(191) if col in {'dt','day','imsi','lac_cell','area','site_id','adcode'} else types.Text()
    return result

def write_frame(df,name,con,if_exists='fail',index=True,**kwargs):
    """DataFrame 使用真实 SQLAlchemy MySQL 连接；replace 属于 DDL 阶段。"""
    ident(name)
    if if_exists == 'replace':
        con.commit()
        con.execute(f"DROP TABLE IF EXISTS {ident(name)}")
        con.commit()
        if_exists == 'append'
    kwargs.setdefault('dtype',frame_types(df))
    kwargs.setdefault('chunksize',1000)
    # Connection 已在事务中时 pandas 不另行提交，分区 DML 可整体回滚。
    return df.to_sql(name,con.sa,if_exists=if_exists,index=index,**kwargs)

def table_exists(con,table):
    return con.execute('SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=?',(table,)).fetchone() is not None
def columns(con,table):
    return con.execute('SELECT ordinal_position-1 AS cid,column_name AS name,column_type AS type, '
        "IF(is_nullable='NO',1,0) AS not_null,column_default AS dflt_value,IF(column_key='PRI',1,0) AS pk "
        'FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=? ORDER BY ordinal_position',(table,)).fetchall()
def table_names(con,prefix=''):
    return [r[0] for r in con.execute('SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name LIKE ? ORDER BY table_name',(prefix+'%',))]

def column_result(con,table):
    return con.execute('SELECT ordinal_position-1 AS cid,column_name AS name,column_type AS type, '
        "IF(is_nullable='NO',1,0) AS not_null,column_default AS dflt_value,IF(column_key='PRI',1,0) AS pk "
        'FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=? ORDER BY ordinal_position',(table,))

def columns_frame(con,table):
    return pd.DataFrame([dict(row) for row in columns(con,table)])

def index_result(con,table):
    return con.execute('SELECT 0 AS seq,index_name AS name,MAX(non_unique)=0 AS is_unique FROM information_schema.statistics '
                       'WHERE table_schema=DATABASE() AND table_name=? GROUP BY index_name',(table,))

def schema_result(con):
    return con.execute('SELECT 0 AS seq,DATABASE() AS name,DATABASE() AS file')

def create_sql(con,table):
    return con.execute('SHOW CREATE TABLE '+ident(table)).fetchone()[1]

class MetadataResult:
    def __init__(self,rows):self.rows=rows
    def fetchall(self):return self.rows
    def fetchone(self):return self.rows[0] if self.rows else None
    def __iter__(self):return iter(self.rows)

def ddl_result(con,table):
    return MetadataResult([(create_sql(con,table),)])

def table_definitions(con,prefix=''):
    return MetadataResult([(name,create_sql(con,name)) for name in table_names(con,prefix)])

def sandbox_schema(label):
    """测试显式创建独立的真实 MySQL 库，没有内存数据库替代。"""
    name='test_course_'+hashlib.sha256(str(label).encode()).hexdigest()[:16]
    create_schema(name)
    return name

def schema_name(value):
    """pytest 的 tmp_path 仅作为唯一标签，不创建或读取数据库文件。"""
    if isinstance(value,Path):return 'test_course_'+hashlib.sha256(str(value).encode()).hexdigest()[:16]
    return value
def index_names(con):
    return [r[0] for r in con.execute('SELECT DISTINCT index_name FROM information_schema.statistics WHERE table_schema=DATABASE() ORDER BY index_name')]
def ensure_index(con,name,table,cols,unique=False):
    if con.execute('SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name=? AND index_name=?',(table,name)).fetchone():return
    con.execute('CREATE '+('UNIQUE ' if unique else '')+f'INDEX {ident(name)} ON {ident(table)}('+','.join(ident(c) for c in cols)+')')
    con.commit() # DDL 边界要显式结束，不能插在 DELETE/INSERT 中间。

def write_partition(con,df,table,dt,dt_col='dt'):
    """先完成结构演进，再在同一 InnoDB 事务内删除和追加日期分区。"""
    out=df.copy()
    if dt_col in out:out[dt_col]=dt
    else:out.insert(0,dt_col,dt)
    if not table_exists(con,table):write_frame(out.head(0),table,con,index=False)
    else:
        existing={r[1] for r in columns(con,table)}
        if dt_col not in existing:raise ValueError(f'{table} 缺少分区列 {dt_col}')
        for name,kind in frame_types(out).items():
            if name not in existing:
                con.execute(f'ALTER TABLE {ident(table)} ADD COLUMN {ident(name)} '+kind.compile(dialect=con.sa.dialect))
    con.commit()
    ensure_index(con,'idx_'+table+'_'+dt_col,table,[dt_col])
    try:
        con.execute(f'DELETE FROM {ident(table)} WHERE {ident(dt_col)}=?',(dt,))
        if len(out):write_frame(out,table,con,if_exists='append',index=False)
        con.commit()
    except Exception:con.rollback();raise
    return len(out)

def migrate(con,directory: Path):
    """MySQL DDL 不整体回滚：使用幂等 DDL、校验和与命名锁。"""
    lock='migration:'+con.schema
    if con.execute('SELECT GET_LOCK(?,30)',(lock,)).fetchone()[0]!=1:raise RuntimeError('迁移锁等待超时')
    applied=[]
    try:
        con.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version VARCHAR(191) PRIMARY KEY, '
                    'checksum CHAR(64) NOT NULL,applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB')
        con.commit()
        done={r[0]:r[1] for r in con.execute('SELECT version,checksum FROM schema_migrations')}
        for f in sorted(directory.glob('[0-9][0-9][0-9][0-9]_*.sql')):
            digest=hashlib.sha256(f.read_bytes()).hexdigest()
            if f.stem in done:
                if done[f.stem]!=digest:raise RuntimeError('已应用迁移文件被修改：'+f.stem)
                continue
            for stmt in sqlparse.split(f.read_text(encoding='utf-8')):
                clean=sqlparse.format(stmt,strip_comments=True).strip().rstrip(';')
                if not clean:continue
                match=re.match(r'CREATE (UNIQUE )?INDEX (\w+) ON (\w+)\(([^)]+)\)',clean,re.I)
                if match:ensure_index(con,match[2],match[3],[c.strip() for c in match[4].split(',')],bool(match[1]))
                else:con.execute(clean)
                con.commit()
            con.execute('INSERT INTO schema_migrations(version,checksum) VALUES(?,?)',(f.stem,digest));con.commit()
            applied.append(f.stem)
    finally:
        con.rollback();con.execute('SELECT RELEASE_LOCK(?)',(lock,));con.commit()
    return applied
