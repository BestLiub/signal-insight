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

## 怎么开始

1. 把讲师发的 `signal.db`、`checkpoints.db` 放进 `data/`；
2. 在项目根目录安装：`python -m pip install -e ".[dev]"`（可编辑安装，见《可编辑安装》文档）；
3. 在 `notebooks/` 里按天打开 notebook，从第一格开始运行。

## 怎么跑

```powershell
. .\.env.ps1                                         # 新开的终端先载入 MySQL 账号（.env.ps1 不进 Git）
python -m signal_insight.pipeline --day 2018-10-03   # 一键从 ODS 生成 dwd_signal、维表、dws_stay
python -m pytest                                     # 跑全部测试：写库的测试只用临时库，不动 signal_insight
```

团队工程规范见 `docs/工程规范.md`。
