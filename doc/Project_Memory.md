# Gutao_Chaodi 项目记忆（Project Memory）

- 更新时间：2026-02-21
- 用途：记录当前实现下的稳定决策与不可破坏约束。

## 1. 当前策略与调度内核

### 1.1 实盘调度

- 系统仅支持钉钉 Webhook 出站发送，不接收入站命令。
- 每个自然日（北京时间）执行两段流程：
  1. `09:26`：交易日判断 + 一字跌停统计并推送群消息。
  2. `13:00-15:00`：仅监控 `09:26` 统计出的代码列表。
- 非交易日不执行统计与午盘实盘会话。

### 1.2 实盘策略

- `StrategyEngine` 为实盘唯一策略引擎。
- 规则为双规则 OR：
  - `buy_flow_breakout`
  - `sell1_drop`
- 一字跌停为统一前置门禁，开板即剔除。
- 单票单日每规则最多触发一次；两规则都触发后进入静默。

### 1.3 回测策略

- 回测与实盘解耦，不复用 `StrategyEngine`。
- buy-flow 判定：
  - 一字跌停分钟才参与统计；
  - `current_buy_volume > cumulative_buy_volume_before` 触发；
  - `cumulative` 为全天累计，触发判定限于回测窗口。

## 2. 关键代码锚点

- `src/app.py`：交易日调度、09:26 统计消息、午盘会话触发。
- `src/trading_calendar.py`：`is_trading_day()`。
- `src/main.py`：`run_live(..., preset_codes=...)` 名单监控执行器。
- `src/engine.py`：一字门禁 + 双规则 OR + one-shot。
- `src/notifier.py`：Webhook 文本与告警发送。
- `src/backtest/runner.py`：buy-flow 回放。

## 3. 不变量（修改前必须检查）

1. 渠道不变量
- 仅允许 Webhook 出站；不得再引入入站命令回调链路。

2. 调度不变量
- 09:26 摘要消息必须发送；即使 0 只也发“0只”摘要。
- 午盘监控范围必须是 09:26 名单，不回退全市场。

3. 实盘策略不变量
- 两规则都必须在一字跌停前提下判定。
- 开板（`high_price > limit_down_price`）后必须立即剔除。

4. 回测判定不变量
- 触发条件必须是 `current_buy_volume > cumulative_buy_volume_before`。
- 累计范围必须是全天累计，窗口仅用于触发判定。

## 4. 关键参数默认值（当前事实）

- `PREOPEN_SCAN_TIME=09:26`
- `TRADING_TIMEZONE=Asia/Shanghai`
- `MONITOR_START_TIME=13:00`
- `MONITOR_END_TIME=15:00`
- `PREOPEN_MESSAGE_MAX_ROWS_PER_CHUNK=80`
- `POOL_PROVIDER=akshare`
- `POOL_FAILOVER_MODE=cache`
- `BACKTEST_SOURCE=joinquant`

## 5. 故障词典

| 现象 | 含义 | 处理 |
| --- | --- | --- |
| 09:26 无消息 | 通知失败或调度未触发 | 查 `DINGTALK_URL`、网络与日志 |
| 非交易日仍运行 | 交易日历判断异常 | 查 `trading_calendar` 与时区配置 |
| 午盘无告警 | 09:26 名单为空或信号未命中 | 核对统计消息与策略阈值 |
| `no_one_word_limit_down` | 回测窗口无一字跌停分钟 | 属于前置条件不满足 |
| `JoinQuant permission/quota error` | 回测权限或额度不足 | 检查账号权限/额度 |

## 6. 测试基线记忆

- 运行基线：`pytest -q` 全通过（当前 47 条）。
- 调度相关：
  - `tests/test_app_scheduler.py`
  - `tests/test_trading_calendar.py`
  - `tests/test_runtime_status.py`
- 策略与数据：
  - `tests/test_engine.py`
  - `tests/test_models.py`
  - `tests/test_fetcher.py`
  - `tests/test_pool_manager.py`
- 回测：
  - `tests/test_backtest_runner.py`
  - `tests/test_backtest_cli.py`
  - `tests/test_backtest_joinquant_provider.py`
