"""交付前自查（D15）：11 项检查，一条命令跑完。任何一项不通过，退出码为 1。

    python tools/preflight.py           完整检查（含 pytest）
    python tools/preflight.py --quick   跳过 pytest 和数据库检查
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _sh(cmd):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main(argv=None):
    quick = "--quick" in (argv or sys.argv[1:])
    rows = []

    def add(name, ok, detail=""):
        rows.append((name, "✅" if ok else "❌", detail))

    # 1 关键文件
    need = ["src/signal_insight/config.py", "src/signal_insight/pipeline.py", "app/Home.py",
            "Dockerfile", "config/settings.yaml", "README.md"]
    add("1 关键文件齐全", all((ROOT / f).exists() for f in need),
        "、".join(f for f in need if not (ROOT / f).exists()) or "齐全")

    # 2 依赖方向
    code, out = _sh([sys.executable, "tools/check_deps.py"])
    add("2 依赖检查", code == 0, out.strip().splitlines()[-1] if out.strip() else "")

    # 3 测试
    if quick:
        add("3 测试全绿", True, "已跳过（--quick）")
    else:
        code, out = _sh([sys.executable, "-m", "pytest", "-q"])
        last = out.strip().splitlines()[-1] if out.strip() else ""
        add("3 测试全绿", code == 0, last)

    # 4 README 四节
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    parts = {"目录": "目录", "安装": "pip install -e", "流水线": "signal_insight.pipeline", "测试": "pytest"}
    add("4 README 四节", all(v in readme for v in parts.values()),
        "、".join(k for k, v in parts.items() if v not in readme) or "齐全")

    # 5 图表
    figs = list((ROOT / "image").glob("*.png"))
    add("5 关键图已生成", len(figs) >= 10, f"{len(figs)} 张")

    # 6-7 数据库
    try:
        import os
        from signal_mysql import database as mysql
        from signal_insight import config
        with mysql.connect(config.WAREHOUSE_SCHEMA, readonly=True) as con:
            tables = mysql.table_names(con)
            need_tables = ["dws_stay", "dws_user_area_day", "ads_area_daily", "ads_dq_partition"]
            add("6 生产库关键表", all(t in tables for t in need_tables),
                "、".join(t for t in need_tables if t not in tables) or "齐全")
            n_metric = int(con.execute("SELECT COUNT(*) FROM dim_metric").fetchone()[0])
            n_cfg = len(config.load_settings()["metrics"])
            add("7 口径表行数", n_metric == n_cfg, f"库里 {n_metric} 行，配置 {n_cfg} 条")
    except Exception as e:
        add("6 生产库关键表", quick, "已跳过" if quick else f"{type(e).__name__}: {e}")
        add("7 口径表行数", quick, "已跳过" if quick else "无法连接生产库")

    # 8 平台只读聚合表
    bad = []
    for p in (ROOT / "app").rglob("*.py"):
        s = p.read_text(encoding="utf-8")
        if re.search(r"FROM\s+(dwd_|dws_|ods_)", s):
            bad.append(str(p.relative_to(ROOT)))
    add("8 平台不碰明细", not bad, "、".join(bad) or "只读 ads_/dim_")

    # 9 隐私唯一来源
    hits = [str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.py")
            if re.search(r"def (mask_id|suppress|suppress_grouped|suppress_columns|drop_small)\b", p.read_text(encoding="utf-8"))]
    add("9 隐私只有一处", hits == ["src\\signal_insight\\privacy.py"] or hits == ["src/signal_insight/privacy.py"], "、".join(hits) or "没找到")

    # 10 工作区干净
    code, out = _sh(["git", "status", "--porcelain"])
    add("10 工作区干净", code == 0 and not out.strip(), out.strip()[:120] or "干净")

    # 11 原始数据不进 Git
    code, out = _sh(["git", "ls-files", "data", "image", "reports"])
    add("11 原始数据与产物不进 Git", code == 0 and not out.strip(), out.strip()[:120] or "未跟踪")

    width = max(len(r[0]) for r in rows)
    for name, ok, detail in rows:
        print(f"{name:<{width}}  {ok}  {detail}")
    failed = [r for r in rows if r[1] == "❌"]
    print(f"\n{len(rows) - len(failed)}/{len(rows)} 项通过")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
