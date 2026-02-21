# Gutao_Chaodi 项目架构说明（As-Built）

- 更新时间：2026-02-21
- 目标：对齐当前仓库真实实现（Webhook 出站、交易日自动调度、09:26 统计+午盘名单监控）

## 1. 仓库目录总览

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

## 2. 文件职责索引

### 2.1 `src/` 运行时代码

| 路径 | 作用 |
| --- | --- |
| `src/app.py` | 统一调度入口：交易日判断、09:26 统计推送、13:00-15:00 实盘会话触发。 |
| `src/main.py` | 实盘执行器：建池、拉取快照、策略评估、命中通知。 |
| `src/trading_calendar.py` | AkShare 交易日历封装（`is_trading_day`）。 |
| `src/runtime_status.py` | 运行态心跳与轮询/告警计数。 |
| `src/config.py` | 统一配置模型与参数校验。 |
| `src/models.py` | 领域模型定义（股票池、快照、告警事件）与数据清洗。 |
| `src/pool_manager.py` | 日内监控股票池构建（AkShare + 本地缓存回退）。 |
| `src/fetcher.py` | 东方财富快照异步采集、重试与字段解析。 |
| `src/engine.py` | 策略状态机：一字跌停门禁、双规则 OR、one-shot。 |
| `src/notifier.py` | Apprise 通知网关封装（Webhook 出站发送）。 |
| `src/backtest_cli.py` | 回测 CLI 入口（参数解析、预检查、结果输出）。 |
| `src/backtest/runner.py` | 单股单日 buy-flow 回放执行器（全天累计 + 窗口内触发）。 |
| `src/backtest/providers/joinquant_provider.py` | JoinQuant 分钟数据接入与错误分类。 |

说明：入站命令模块（`/help`、`/test`、`/current`）已移除，不再维护命令回调服务。

### 2.2 `tests/` 测试代码

| 路径 | 作用 |
| --- | --- |
| `tests/test_app_scheduler.py` | 09:26 统计消息、分片、名单过滤与调度行为测试。 |
| `tests/test_trading_calendar.py` | 交易日判断测试。 |
| `tests/test_runtime_status.py` | 运行态计数与心跳测试。 |
| `tests/test_models.py` | 模型字段清洗与一字跌停判定测试。 |
| `tests/test_engine.py` | 策略 one-shot 与开板剔除行为测试。 |
| `tests/test_pool_manager.py` | 股票池构建与 ST 标签测试。 |
| `tests/test_fetcher.py` | EastMoney 可选 Header/Cookie 配置与解析测试。 |
| `tests/test_notifier.py` | 通知网关关键词注入与发送体测试。 |
| `tests/test_backtest_mapper.py` | 回测映射逻辑测试。 |
| `tests/test_backtest_runner.py` | 回放执行分类结果测试。 |
| `tests/test_backtest_joinquant_provider.py` | JoinQuant provider 认证/字段行为测试。 |
| `tests/test_backtest_cli.py` | CLI 参数与返回码契约测试。 |

## 3. 实盘主链路（Scheduler + Live）

### 3.1 日调度链路（`src/app.py`）

1. 读取配置并初始化日志。
2. 按 `TRADING_TIMEZONE` 获取当前北京时间。
3. 到达 `PREOPEN_SCAN_TIME`（默认 09:26）后执行：
   - 调用 `is_trading_day()` 判断是否交易日。
   - 非交易日：当天直接跳过统计与实盘会话。
   - 交易日：建全市场池并拉一次快照，筛选“一字跌停”标的。
   - 发送群消息（含序号、代码、名称、卖1单数）；若为 0 只仍发送摘要。
4. 进入监控窗口（默认 13:00-15:00）后，调用 `run_live(..., preset_codes=09:26名单)`。

### 3.2 实盘会话链路（`src/main.py`）

1. 建池并按 `preset_codes` 过滤监控范围。
2. 初始化 `StrategyEngine`，只对名单内标的轮询。
3. 命中策略信号后通过 `NotificationGateway.send_alert()` 自动推送钉钉。
4. 窗口结束时执行 `flush_pending()` 补判尾分钟。

## 4. 回测主链路（`src/backtest_cli.py`）

1. 解析参数（日期、代码、数据源、账号、窗口）。
2. 初始化 JoinQuant provider。
3. 拉取单股单日分钟数据并按时间排序。
4. 执行 buy-flow 回放：
   - 仅在一字跌停分钟统计买量代理（`volume`）。
   - 触发条件：`current_buy_volume > cumulative_buy_volume_before`。
5. 输出报告（触发状态、原因、触发时刻、关键值）。

## 5. 配置说明（核心字段）

### 5.1 实盘相关

- `DINGTALK_URL` / `DINGTALK_KEYWORD`
- `PREOPEN_SCAN_TIME` / `TRADING_TIMEZONE`
- `PREOPEN_MESSAGE_MAX_ROWS_PER_CHUNK`
- `MONITOR_START_TIME` / `MONITOR_END_TIME`
- `VOL_DROP_THRESHOLD` / `ASK_DROP_THRESHOLD` / `LIVE_CONFIRM_MINUTES`
- `MAX_CONCURRENCY` / `REQUEST_TIMEOUT_SEC` / `RETRY_ATTEMPTS` / `RETRY_WAIT_SEC`
- `POOL_PROVIDER` / `POOL_FAILOVER_MODE` / `POOL_CACHE_*`
- `EM_HEADERS_JSON` / `EM_COOKIE`

### 5.2 回测相关

- `BACKTEST_SOURCE`（当前 `joinquant`）
- `BACKTEST_WINDOW_START` / `BACKTEST_WINDOW_END`
- `JQ_USERNAME` / `JQ_PASSWORD`

## 6. 关键设计约束

1. 钉钉仅使用 Webhook 出站发送，不接收入站命令。
2. 09:26 统计即使 0 只也必须发送摘要，保证运行可观测。
3. 午盘实盘仅监控 09:26 筛选名单，不回退全市场。
4. 实盘与回测策略分叉：实盘 `StrategyEngine`，回测 buy-flow runner。
5. 一旦开板（`high_price > limit_down_price`）立即剔除，不再监控。

## 7. 常见问题定位入口

1. 09:26 无群消息：检查 `DINGTALK_URL`、`DINGTALK_KEYWORD`、网络与日志异常。
2. 非交易日仍触发统计：检查交易日历接口可用性与时区配置。
3. 午盘无告警：检查 09:26 名单是否为空，及策略触发条件是否命中。
4. 回测认证失败：优先检查 `JQ_USERNAME` / `JQ_PASSWORD`。
5. 回测字段缺失：检查 provider 报错中的列名（重点 `volume`、`low_limit`）。
