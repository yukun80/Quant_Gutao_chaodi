# Gutao_Chaodi 项目架构说明

## 1. 文档目标

本文档用于回答三个问题：

1. 仓库里每个目录和文件的作用是什么。
2. 实盘监控与回测验证两条主链路如何运行。
3. 当你修改某个模块时，应该关注哪些上下游影响。

---

## 2. 仓库目录总览

```text
.
├── doc/                      # 设计文档、日志、项目记忆与规范
├── scripts/                  # 运维与联调脚本入口
├── src/                      # 生产代码（实盘 + 回测）
├── tests/                    # 单元测试与行为回归
├── README.md                 # 快速上手与入口导航
├── requirements.txt          # Python 依赖
└── .env.example              # 配置模板
```

---

## 3. 文件职责索引

### 3.1 `src/` 运行时代码

| 路径 | 作用 |
| --- | --- |
| `src/__init__.py` | 包导出入口，声明顶层可导入模块。 |
| `src/config.py` | 统一配置模型，负责 `.env` 加载与参数校验。 |
| `src/models.py` | 领域模型定义（股票池、快照、告警事件）与数据清洗。 |
| `src/pool_manager.py` | 日内监控股票池构建（Tushare + AkShare）。 |
| `src/fetcher.py` | 东方财富快照异步采集、重试与字段解析。 |
| `src/engine.py` | 策略状态机：基线建立、阈值触发、one-shot 熔断。 |
| `src/notifier.py` | Apprise 通知网关封装。 |
| `src/main.py` | 实盘主入口，串联建池、采集、评估、通知。 |
| `src/backtest/__init__.py` | 回测包导出入口。 |
| `src/backtest/mapper.py` | 回测分钟数据映射到 `StockSnapshot`。 |
| `src/backtest/runner.py` | 单股单日回放执行器，复用 `StrategyEngine`。 |
| `src/backtest/providers/base.py` | 回测数据源抽象接口。 |
| `src/backtest/providers/joinquant_provider.py` | JoinQuant 分钟数据接入与错误分类。 |
| `src/backtest/providers/__init__.py` | 回测 provider 导出入口。 |
| `src/backtest_cli.py` | 回测 CLI 入口（参数解析、预检查、结果输出）。 |

### 3.2 `tests/` 测试代码

| 路径 | 作用 |
| --- | --- |
| `tests/test_models.py` | 模型字段清洗与一字跌停判定测试。 |
| `tests/test_engine.py` | 策略 one-shot 与开板剔除行为测试。 |
| `tests/test_pool_manager.py` | 股票池构建与 ST 标签测试。 |
| `tests/test_backtest_mapper.py` | 回测映射逻辑测试。 |
| `tests/test_backtest_runner.py` | 回放执行分类结果测试。 |
| `tests/test_backtest_joinquant_provider.py` | JoinQuant provider 认证/字段行为测试。 |
| `tests/test_backtest_cli.py` | CLI 参数与返回码契约测试。 |

### 3.3 `scripts/` 脚本入口

| 路径 | 作用 |
| --- | --- |
| `scripts/run_live.sh` | 实盘运行入口脚本。 |
| `scripts/backtest_joinquant_smoke.sh` | JoinQuant 联网 smoke 联调脚本。 |

### 3.4 `doc/` 文档资产

| 路径 | 作用 |
| --- | --- |
| `doc/Development_White_Paper.md` | 项目白皮书与最初架构设计。 |
| `doc/worklog/2026-02-18_implementation_status.md` | 第一阶段实现状态记录。 |
| `doc/worklog/2026-02-19_backtest_implementation_status.md` | 回测实现阶段总结。 |
| `doc/Project_Architecture_Guide.md` | 当前文档：全路径与架构说明。 |
| `doc/Project_Memory.md` | 项目记忆与决策约束沉淀。 |
| `doc/Commenting_Convention.md` | 注释规范与维护原则。 |

---

## 4. 实盘主链路（`src/main.py`）

1. 读取配置并初始化日志。
2. 构建当日股票池（全市场入池，ST 仅作为标签）。
3. 初始化策略引擎并注册股票池。
4. 在监控窗口内循环：
   - 获取可监控代码。
   - 异步拉取实时快照。
   - 逐条交给引擎评估。
   - 命中后通过网关发送通知。
5. 输出轮次、告警次数、引擎状态摘要。

---

## 5. 回测主链路（`src/backtest_cli.py`）

1. 解析参数（日期、代码、阈值、数据源、字段映射）。
2. 输出 precheck（运行上下文确认）。
3. 初始化 provider（当前仅 JoinQuant）。
4. 拉取单股单日分钟数据。
5. 映射为 `StockSnapshot` 后按时间回放。
6. 复用 `StrategyEngine` 判断是否触发。
7. 输出回测报告（触发状态、原因、触发时刻、降幅等）。

---

## 6. 配置说明（核心字段）

### 6.1 实盘相关

- `VOL_DROP_THRESHOLD`: 封单降幅阈值（0~1）。
- `DINGTALK_KEYWORD`: 钉钉机器人关键词安全匹配前缀。
- `MAX_CONCURRENCY`: 并发请求上限。
- `REQUEST_TIMEOUT_SEC`: 请求总超时。
- `RETRY_ATTEMPTS` / `RETRY_WAIT_SEC`: 重试策略。
- `POLL_INTERVAL_SEC`: 轮询间隔。
- `MONITOR_START_TIME` / `MONITOR_END_TIME`: 实盘监控时段。
- `EM_HEADERS_JSON` / `EM_COOKIE`: EastMoney 可选请求头与 Cookie 扩展位。

### 6.2 回测相关

- `BACKTEST_SOURCE`: 回测数据源（当前 `joinquant`）。
- `BACKTEST_MINUTE_ASKV1_FIELD`: 分钟级 `ask_v1` 代理字段名。
- `JQ_USERNAME` / `JQ_PASSWORD`: JoinQuant 账号认证信息。
- `BACKTEST_USE_NOTIFIER`: 预留开关，当前未接入发送逻辑。

---

## 7. 关键设计约束

1. 策略引擎是唯一判定源，实盘与回测必须复用同一引擎。
2. `StockSnapshot` 是策略输入契约，不允许策略层直接消费原始 dict。
3. one-shot 规则固定：单标的单日只允许触发一次。
4. 一旦开板（`high_price > limit_down_price`）立即剔除，不再监控。
5. 当前回测是分钟级近似，不等价于 tick 级卖一挂单回放。

---

## 8. 常见问题定位入口

1. 回测认证失败：优先检查 `JQ_USERNAME` / `JQ_PASSWORD`。
2. 回测字段缺失：检查 `BACKTEST_MINUTE_ASKV1_FIELD` 与 provider 报错中的列名列表。
3. 回测无数据：确认日期是否交易日、代码是否有效、账号是否有权限。
4. 实盘无告警：检查是否满足一字跌停条件与阈值触发条件。
