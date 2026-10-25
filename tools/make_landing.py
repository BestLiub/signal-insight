
"""本地生成明确标注的模拟分区；生产数仓仍是 MySQL。"""
from pathlib import Path
import json,argparse
import pandas as pd
from signal_mysql import database as mysql
from signal_insight import config
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--day',required=True);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    con=mysql.connect(config.DB_SCHEMA,readonly=True)
    try:
        raw=mysql.read_frame('SELECT * FROM ods_signal LIMIT 1000',con)
    finally:con.close()
    source=(pd.to_datetime(raw['timestamp'],unit='ms')+pd.Timedelta(hours=8)).dt.normalize().min()
    shift=int((pd.Timestamp(args.day)-source).total_seconds()*1000)
    for col in ['timestamp','timestamp1']:raw[col]=raw[col]+shift
    args.out.parent.mkdir(parents=True,exist_ok=True);raw.to_parquet(args.out,index=False)
    args.out.with_suffix('.meta.json').write_text(json.dumps({'is_synthetic':True,'dates':[args.day]},ensure_ascii=False),encoding='utf-8')
    print('模拟分区已生成',len(raw))
if __name__=='__main__':main()
