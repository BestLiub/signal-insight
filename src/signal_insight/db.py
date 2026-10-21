
"""MySQL 存储层：显式 DDL 阶段、InnoDB 分区 DML 和元数据。"""
import pandas as pd
from signal_mysql import database as mysql
from . import config
TS_FORMAT='%Y-%m-%d %H:%M:%S.%f'

def connect(path=None):
    return mysql.connect(config.DB_SCHEMA if path is None else path)

def table_exists(con,table):
    return mysql.table_exists(con,table)

def _for_storage(df):
    return df.copy()  # MySQL 存 DATETIME(3)，不把时间强制转换为文本。

def write_partition(con,df,table,dt,dt_col='dt'):
    return mysql.write_partition(con,df,table,dt,dt_col)

def read_partition(con,table,dt,columns='*',parse_dates=None):
    return mysql.read_frame(f'SELECT {columns} FROM {mysql.ident(table)} WHERE dt=?',con,params=(dt,),parse_dates=parse_dates)

def replace_table(con,df,table):
    mysql.write_frame(df,table,con,if_exists='replace',index=False);con.commit();return len(df)

def append_table(con,df,table):
    if table_exists(con,table):
        have={r[1] for r in mysql.columns(con,table)}
        for name,kind in mysql.frame_types(df).items():
            if name not in have:con.execute(f'ALTER TABLE {mysql.ident(table)} ADD COLUMN {mysql.ident(name)} '+kind.compile(dialect=con.sa.dialect))
        con.commit()
    mysql.write_frame(df,table,con,if_exists='append',index=False);con.commit();return len(df)

def ensure_indexes(con):
    if table_exists(con,'ods_signal'):
        mysql.ensure_index(con,'idx_ods_signal_ts','ods_signal',['timestamp'])
    if table_exists(con,'dim_cell'):
        mysql.ensure_index(con,'idx_dim_cell_pk','dim_cell',['lac_cell'],unique=True)
    for table in mysql.table_names(con):
        if 'dt' in {r[1] for r in mysql.columns(con,table)}:mysql.ensure_index(con,'idx_'+table+'_dt',table,['dt'])
    return mysql.index_names(con)