# Gutao_Chaodi 当前工作状态（2026-02-20，2026-02-21补记）

- 日期：2026-02-21
- 范围：基于当前仓库代码与测试状态（`src/`、`tests/`、`doc/`）
- 目标：沉淀最新 As-Built 能力与未完成项

## 1. 当前已实现（As-Built）

### 1.1 调度与通知链路

- `src/app.py` 已实现日内自动调度：
  - 北京时间 `09:26`：交易日判断 + 一字跌停统计推送；
  - `13:00-15:00`：触发午盘实盘会话。
- 钉钉机器人模式已统一为 **Webhook 出站**；
  - 入站命令回调链路已移除（不再支持 `/help`、`/test`、`/current`）。
- `09:26` 统计消息支持分片发送，0 只时也发送摘要消息。

### 1.2 实盘策略链路

- 主链路：`PoolManager -> EastMoneyFetcher -> StrategyEngine -> NotificationGateway`。
- 09:26 先筛选一字跌停名单，午盘仅监控该名单（不回退全市场）。
- 实盘策略为双规则 OR：
  - `buy_flow_breakout`
  - `sell1_drop`
- 一字门禁与开板剔除已实现，`flush_pending()` 尾分钟补判已实现。

### 1.3 回测链路

- 回测已与实盘引擎解耦，使用 buy-flow runner。
- 回测触发条件：`current_buy_volume > cumulative_buy_volume_before`。
- JoinQuant provider 支持认证、权限错误分类、`low_limit` fallback。

### 1.4 测试状态

- 当前测试通过：`pytest -q` => `47 passed`。
- 新增测试覆盖：
  - `tests/test_app_scheduler.py`
  - `tests/test_trading_calendar.py`
  - `tests/test_runtime_status.py`

## 2. 2026-02-21 增量变更

1. 删除入站命令功能
- 删除 `src/command_server.py`、`src/command_router.py`、`src/command_session.py`、`src/message_formatter.py`。
- 删除对应命令测试用例。

2. 新增交易日能力
- 新增 `src/trading_calendar.py`，基于 AkShare 交易日历判定开市日。

3. 新增 09:26 盘前统计
- `src/app.py` 新增一字跌停统计与摘要推送逻辑（含消息分片）。

4. 午盘监控改为名单驱动
- `src/main.py` 的 `run_live` 新增 `preset_codes` 入参，仅监控 09:26 筛选名单。

5. 配置更新
- 新增：`PREOPEN_SCAN_TIME`、`TRADING_TIMEZONE`、`PREOPEN_MESSAGE_MAX_ROWS_PER_CHUNK`。
- 删除：命令回调相关配置项。

## 3. 当前未完成 / 遗留项

### 3.1 回测能力未完成项

- 回测结果未落盘（JSON/CSV），仍以控制台输出为主。
- 不支持批量区间回测、参数扫描、统计报表。
- `BACKTEST_USE_NOTIFIER` 仍为预留开关，未接入实际通知路径。

### 3.2 生产化未完成项

- 进程守护/自动拉起未实现（systemd/supervisor/容器编排未接入）。
- 统一指标看板未完善（轮询耗时、重试率、告警速率等）。

### 3.3 技术债务

- `src/config.py` 中仍保留部分历史回测兼容参数，主路径未消费。
- `src/backtest/mapper.py` 保留历史映射能力，当前主回测路径不依赖。

## 4. 建议下一步（优先级）

1. 回测资产化：增加 JSON/CSV 落盘与批量回放入口。
2. 运行保障：接入 systemd/supervisor 与健康巡检。
3. 可观测性：补充规则级命中统计和调度级成功率指标。
