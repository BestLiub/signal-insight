"""检查 src/signal_insight 的依赖方向和循环依赖（D11）。

    python tools/check_deps.py        有违规时退出码为 1，可以放进提交前的检查

规则（docs/工程规范.md 第 3 条）：上层可以 import 下层，下层不能 import 上层；同一层之间不互相依赖；
同一个包（viz/、dws/）里的文件可以互相引用；不允许循环依赖。

为什么写成脚本：依赖方向靠人眼看，十几个模块之后就看不过来了；写成脚本，每次提交前跑一遍，违规当场发现。
这是 D10 中期代码评审第 1 条的自动版。tools/ 在项目根目录、不进包：它是维护项目用的，不被任何代码 import。
"""
import ast
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "src" / "signal_insight"

# 从下到上：数字越大越靠上。新模块要在这里登记，否则检查会报“没登记的模块”。
LAYERS = {
    "config": 0,
    "db": 1, "geo": 1, "quality": 1, "privacy": 1, "viz": 1,
    "dwd": 2, "dims": 2, "dws": 2,
    "ads": 3, "gate": 3, "ingest": 3, "report": 3,
    "pipeline": 4,
    "__main__": 5,
}


def module_of(path: Path) -> str:
    """src/signal_insight/dws/stay.py → dws；src/signal_insight/pipeline.py → pipeline。"""
    rel = path.relative_to(PKG)
    return rel.parts[0] if len(rel.parts) > 1 else rel.stem


def imports_of(path: Path) -> set[str]:
    """一个文件 import 了包里的哪些模块（只看相对导入：from . import x、from .x import y、from .. import x）。"""
    me = module_of(path)
    in_subpkg = len(path.relative_to(PKG).parts) > 1
    out = set()
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.ImportFrom) and n.level >= 1:
            top_level = n.level == 2 or (n.level == 1 and not in_subpkg)   # 指向包的顶层，而不是子包内部
            if not top_level:
                continue
            names = [n.module.split(".")[0]] if n.module else [a.name for a in n.names]
            out.update(x for x in names if x != me)
    return out


def check():
    files = [p for p in PKG.rglob("*.py") if p.name != "__init__.py" or p.parent != PKG]
    graph, problems = {}, []
    for p in files:
        m = module_of(p)
        if m not in LAYERS:
            problems.append(f"没登记的模块：{m}（在 tools/check_deps.py 的 LAYERS 里给它定一层）")
            continue
        for dep in imports_of(p):
            graph.setdefault(m, set()).add(dep)
            if dep not in LAYERS:
                problems.append(f"{p.relative_to(PKG)} import 了没登记的模块 {dep}")
            elif LAYERS[dep] >= LAYERS[m]:
                problems.append(f"{p.relative_to(PKG)}（第 {LAYERS[m]} 层）import 了 {dep}（第 {LAYERS[dep]} 层）：只能 import 更低的层")
    # 找环：深度优先，走回正在访问的节点就是环
    state, cycles = {}, []

    def visit(node, path):
        state[node] = "visiting"
        for nxt in graph.get(node, ()):
            if state.get(nxt) == "visiting":
                cycles.append(" → ".join(path[path.index(nxt):] + [nxt]))
            elif nxt not in state:
                visit(nxt, path + [nxt])
        state[node] = "done"

    for node in sorted(graph):
        if node not in state:
            visit(node, [node])
    problems += [f"循环依赖：{c}" for c in cycles]
    return graph, problems


def main() -> int:
    graph, problems = check()
    n_edges = sum(len(v) for v in graph.values())
    if problems:
        print(f"依赖检查：{len(problems)} 处违规")
        for p in problems:
            print("  ✗ ", p)
        return 1
    print(f"依赖检查通过：{len(graph)} 个模块、{n_edges} 条依赖，全部从上往下，没有环")
    return 0


if __name__ == "__main__":
    sys.exit(main())
