# signal-insight：沈阳国庆信令客流洞察

用沈阳 2018 年国庆的手机信令样本，回答“国庆傍晚来西塔的人几点来、待多久、从哪来、还去了哪”。

## 目录

| 位置 | 是什么 | 进 Git 吗 |
|---|---|---|
| `data/` | 讲师发的 `signal.db`（ODS 库）、`checkpoints.db` | **不进** |
| `docs/` | 发现清单、数据字典、图表规范 | 进 |
| `notebooks/` | 每天的分析（`D01_…` 两位编号） | 进（运行结果自动清空） |
| `src/signal_insight/` | 我们的代码包：notebook、命令行、测试都从这里 import | 进 |
| `pyproject.toml` | 包的身份证：名字、依赖、怎么安装 | 进 |
| `config/settings.yaml` | 业务参数与口径模板的唯一来源（改参数改这里） | 进 |
| `tests/` | `contract/` 讲师给的契约测试（不许改），`unit/` 自己写的单元测试 | 进 |
| `image/` | notebook 出图（随时可以重新生成） | **不进** |
| `reports/` | notebook 生成的备忘录、报告（D09 起；随时可以重新生成） | **不进** |

## 怎么开始

1. 把讲师发的 `signal.db`、`checkpoints.db` 放进 `data/`；
2. 在项目根目录安装：`python -m pip install -e ".[dev]"`（可编辑安装，见《可编辑安装》文档）；
3. 在 `notebooks/` 里按天打开 notebook，从第一格开始运行。

## 怎么跑

```bash
python -m signal_insight.pipeline --day 2018-10-03    # 一键从 ODS 生成明细层、维表、全部 dws_ 表和 dim_metric
python -m pytest                                     # 跑全部测试
```

## 生产库与命令行

开发库 `signal_insight` 只放分析日（notebook 用）；多日数据走生产库 `signal_warehouse`，由命令行写入：

```bash
python -m signal_insight init                         # 建生产库（复制 ODS）并生成维表
python -m signal_insight ingest data/landing/x.db     # 把一个上游分区文件并进生产库
python -m signal_insight run --date 2018-10-03        # 在生产库上跑一天（可给多个日期）
python -m signal_insight run --todo                  # 跑所有待处理、待重跑、出错的日期（定时任务）
python -m signal_insight run --start 2018-10-01 --end 2018-10-06   # 回填一段日期
python -m signal_insight status                       # 每个日期处理到哪一步
python tools/check_deps.py                            # 检查模块依赖方向和循环依赖
```

## 数据表

| 层 | 表 | 生成它的代码 |
|---|---|---|
| 原始层 | `ods_signal` 等 9 张（讲师发的库，只读） | — |
| 明细层 | `dwd_signal` | `dwd.py` |
| 维表 | `dim_cell`、`dim_hotspot`、`dim_metric` | `dims.py` |
| 汇总层 | `dws_stay`、`dws_night`、`dws_trip`、`dws_user_day`、`dws_user_hour` | `dws/` 下同名文件 |

指标口径见 `docs/指标口径表.csv`（由 `config/settings.yaml` 渲染）。

团队工程规范见 `docs/工程规范.md`。
