# signal-insight：沈阳国庆信令客流洞察

用沈阳 2018 年国庆的手机信令样本，回答一个问题：**国庆傍晚来西塔的人，几点来、待多久、从哪来、还去了哪儿**——并把它做成一个每天能跑、坏数据进不来、每个数字查得到出处的系统。

分析只是其中四分之一，另外四分之三是**数据工程、数据治理和交付**：五层数据仓库、质量门禁、多日分区流水线、隐私抑制、自动生成的报告和一个只读聚合表的展示平台。

## 核心结果

| 指标 | 数值 |
|---|---|
| 原始信令 → 清洗后 | 518,443 → 515,931 条（剔除 0.48%，其中 98.8% 是完全重复） |
| 停留 / 样本用户 | 19,015 段 / 5,644 人 |
| 傍晚访客（西塔 500 米，停留结束 ≥17:00） | **3,310 人** |
| 19:00 在场人数 | **2,037 人**（占当小时可定位人数 5,069 的 40%） |
| 停留时长中位 | 约 160 分钟；41% 的傍晚访客到 23:59 仍未离开（删失） |
| 客群构成 | 市内来访 38.7% / 过夜地不明 24.4% / 周边居民 22.6% / 外地来客 14.3% |
| 跨商圈联动 | 太原街 18.2%（604 人）/ 中街 11.7%（386 人） |

## 这个项目做了什么

- **五层数据仓库**：ODS / DWD / DIM / DWS / ADS 共 35 张表（另有 4 张运行支撑表：`etl_log`、`partition_registry`、`dq_gate_result`、`dq_partition_profile`），表名前缀即分层；看到表名就知道处理到哪一步、生成它的代码在哪个文件里。
- **质量门禁**：七条规则与「最近通过分区的中位数」比较，任何一条不通过，该分区登记为 `blocked`，**下游一行都不写**。10-01、10-02 因数据量只有正常日的 2.8% 被拦下。
- **多日流水线**：按 `dt` 分区、同事务先删后写、6 小时回看接住跨午夜停留、按文件指纹去重、重跑与回填、`stale` 状态传播。
- **口径可复现**：业务参数只在 `config/settings.yaml` 写一次，口径表由模板渲染，`etl_log` 记录每次运行的配置指纹。
- **隐私保护**：小样本抑制（少于 5 人置空）+ 互补抑制（同组只藏一格时再藏一格），防止用「总数减去其他格子」反推个人。
- **交付物**：11 张应用层表、两份自动生成的 Word 报告、7 页 Streamlit 平台、Docker 部署。

## 架构

```
上游分区文件 (Parquet / DB)
        │  ingest：指纹去重、登记
        ▼
   ODS 原始层 ── 只读，一个值都不改
        │  dwd：四步清洗
   DWD 明细层 ── 一条信令一行
        │  dws：停留 / 过夜地 / 出行 / 人·小时
   DWS 汇总层 ── 从「信号」变成「人」
        │  ads：按用途聚合 + 生成时抑制
   ADS 应用层 ── 11 张表，只给平台和报告
        │
   ┌────┴─────┐
平台 (7 页)   报告 (Word) + 图表包
   ▲
gate 门禁：七条规则决定这一天能不能进下游
```

代码的依赖方向是单向的：`config ← 通用能力 ← 各层计算 ← 编排 ← 命令行`，下层永远不 import 上层，由 `tools/check_deps.py` 强制检查（11 个模块、27 条依赖边、无环）。

## 技术栈

| 类别 | 技术 | 在这个项目里干什么 |
|---|---|---|
| 语言 | Python 3.11+ | 全部代码 |
| 数据存储 | MySQL 8.0（InnoDB，按 `dt` 分区） | 五层 35 张表 + 4 张运行支撑表；开发库 / 生产库分离 |
| 数据库访问 | SQLAlchemy 2 + PyMySQL | 连接池、事务、参数绑定、批量写入 |
| 数据处理 | pandas 2.x、NumPy | 清洗、停留识别、按人/小时聚合 |
| 算法 | SciPy、scikit-learn | 点落面、作息聚类 |
| 静态可视化 | Matplotlib 3.8、seaborn | 报告与 notebook 的图（PNG） |
| 交互可视化 | Plotly、Streamlit | 7 页展示平台，只读聚合表 |
| 文档生成 | python-docx、python-pptx | 自动生成 Word 报告 / 答辩 PPT 初稿 |
| 配置 | PyYAML | `settings.yaml` 是业务参数与口径模板的唯一来源 |
| 文件格式 | PyArrow（Parquet） | 上游分区文件 |
| 测试 | pytest（单元 / 契约 / 集成三层） | 集成测试用「迷你世界」，真实数据不进测试 |
| 工程 | argparse CLI、logging、`etl_log` | 一条命令跑一天；每一步的行数、耗时、配置版本可追溯 |
| 部署 | Docker | 镜像只含代码与聚合结果，不含原始数据 |

## 目录

| 位置 | 是什么 | 进 Git 吗 |
|---|---|---|
| `data/` | 原始 `signal.db`、上游分区文件 `landing/`、导出的公开库 | **不进** |
| `docs/` | 工程规范、数据字典、指标口径表、图表规范、发现清单 | 进 |
| `notebooks/` | 课程与实验 notebook（`D001_…` 三位编号、`E01_…` 实验） | 进（运行结果自动清空） |
| `src/signal_insight/` | 代码包：notebook、命令行、测试都从这里 import | 进 |
| `src/signal_mysql/` | 数据库适配层（连接、读写、标识符转义） | 进 |
| `app/` | Streamlit 平台：`Home.py` + 6 个分页 + `lib/` 数据访问层 | 进 |
| `config/settings.yaml` | 业务参数与口径模板的唯一来源（改参数改这里） | 进 |
| `tests/` | `unit/` 单元、`contract/` 契约（不许改）、`integration/` 集成 | 进 |
| `tools/` | 预检、依赖检查、分区生成、导出 | 进 |
| `image/` | notebook 出图（随时可以重新生成） | **不进** |
| `reports/` | 生成的备忘录、报告（随时可以重新生成） | **不进** |

## 怎么开始

```bash
python -m pip install -e ".[dev,app]"     # 可编辑安装，含测试与平台依赖
```

1. 把原始 `signal.db` 放进 `data/`（本仓库不含数据）；
2. 在项目根目录安装上面那一行；
3. 在 `notebooks/` 里按编号打开 notebook，从第一格开始运行。

## 一键运行（Docker，无需本地装 MySQL）

```bash
docker compose up --build
```

打开 <http://localhost:8501> 就能看到 7 页平台，侧栏可切换 6 个日期（10-03 真实、10-04 起为模拟并带水印）。

- **数据从哪来**：`deploy/db/*.sql` 由 MySQL 容器首次初始化时自动导入。只含 `ads_` / `dim_` 的聚合结果，已做小样本抑制，**不含任何个人信息，也不含原始信令**。
- **首次启动**约需 2–4 分钟（拉取 `mysql:8.0` 与构建应用镜像）。
- **重置数据**：`docker compose down -v`，下次启动会重新导入。
- **端口被占用**：改 `docker-compose.yml` 里 `"8501:8501"` 的左边那个数字。

国内网络拉取慢时（Docker Hub / PyPI 连接超时），可以换源：

```bash
docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
docker compose up -d
```

基础镜像也可以在 Docker Desktop 的 **Settings → Docker Engine** 里配置 `registry-mirrors`。

重新生成种子数据（改了应用层之后）：

```bash
python tools/export_seed.py --dates 2018-10-03 2018-10-04 2018-10-05 2018-10-06
```

## 怎么跑

```bash
python -m signal_insight.pipeline --day 2018-10-03    # 开发库：一键从 ODS 生成明细层、维表、全部 dws_ 表
python -m pytest                                       # 跑全部测试
```

## 生产库与命令行

开发库 `signal_insight` 只放分析日（notebook 用）；多日数据走生产库 `signal_warehouse`，由命令行写入：

```bash
python -m signal_insight init                         # 建生产库（复制 ODS）并生成维表
python -m signal_insight ingest data/landing/x.parquet # 把一个上游分区文件并进生产库
python -m signal_insight run --date 2018-10-03        # 在生产库上跑一天（可给多个日期）
python -m signal_insight run --todo                   # 跑所有待处理、待重跑、出错的日期（定时任务）
python -m signal_insight run --start 2018-10-01 --end 2018-10-06   # 回填一段日期
python -m signal_insight status                       # 每个日期处理到哪一步
python tools/check_deps.py                            # 检查模块依赖方向和循环依赖
```

## 展示平台

```bash
streamlit run app/Home.py      # 7 页平台：总览、节律、客源、联动、空间、质量、口径
python tools/export_ads.py     # 导出对外版生产库（只含 ads_ / dim_）
```

平台只读聚合表；每页的取数和图都在 `app/lib/` 下，7 页文件在 `app/pages/`。

## 报告与交付

```bash
python -m signal_insight report quality                        # 数据质量评估报告.docx（9 章，8 章由代码生成）
python -m signal_insight report cleaning --date 2018-10-03     # 数据清洗与加工说明.docx（含参数敏感性）
python -m signal_insight pack --date 2018-10-03                # 图表包：图 + facts.json + 报告骨架
python tools/preflight.py                                      # 交付前自查 11 项
```

报告用 `python-docx` 生成（`reports/` 不进 Git）；图表包和报告里的数字都登记了来源。

## 数据表

| 层 | 表 | 生成它的代码 |
|---|---|---|
| 原始层 | `ods_signal` 等 10 张（只读） | — |
| 明细层 | `dwd_signal` | `dwd.py` |
| 维表 | `dim_cell`、`dim_hotspot`、`dim_metric`、`dim_area`、`dim_area_polygon`、`dim_district_boundary` | `dims.py` |
| 汇总层 | `dws_stay`、`dws_night`、`dws_trip`、`dws_user_day`、`dws_user_hour` | `dws/` 下同名文件 |
| 汇总层（区域） | `dws_stay_area`、`dws_user_area_day`：区域是 `area` 列的取值 | `dws/area.py` |
| 应用层（只在生产库） | `ads_area_hourly`、`ads_area_segment`、`ads_area_daily`、`ads_area_radius`、`ads_area_origin`、`ads_area_linkage`、`ads_hex_hourly`、`ads_od_district`；数据质量 `ads_dq_partition`、`ads_dq_rule`、`ads_dq_clean_steps`。生成时已做小样本抑制和互补抑制，带 `is_synthetic` | `ads.py` |

加一个分析区域：在 `config/settings.yaml` 的 `areas` 里加一项 → `python -m signal_insight dims` →
`python -m signal_insight run --start 2018-10-03 --end 2018-10-06`。计算模块一行不用改。

指标口径见 `docs/指标口径表.csv`（由 `config/settings.yaml` 渲染）。

## 数据说明与局限

- **仓库不含任何原始数据与个人信息**：`data/`、`image/`、`reports/` 都不进 Git，notebook 运行结果由 nbstripout 在提交时清空。
- **只有 10-03 一天真实数据**：10-01 仅 54 条、10-02 仅 14,331 条（正常日的 2.8%），两天被门禁拦截；10-04 起为模拟分区，仅用于演示多日流水线，带 `is_synthetic` 标记且图表打水印，**不参与任何结论**。
- **样本不是随机抽样**：单一运营商、按傍晚到访西塔圈选，结论只对「国庆当天到过西塔一带的这群人」成立，不能推全市。
- **停留时长是下限**：数据在 23:59 截止，41% 的傍晚访客当时仍未离开，报告统一写「至少」。
- **区域可以重叠**：西塔 500 米圆与商圈边界有交集，各区域人数不能相加。

## 文档

- 团队工程规范（分层、依赖方向、命名、测试、图表）：`docs/工程规范.md`
- 数据字典与字段含义：`docs/数据字典.md`
- 指标口径表：`docs/指标口径表.csv`
- 已知数据问题清单：`config/known_issues.yaml`
