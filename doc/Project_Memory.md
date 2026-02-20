# Gutao_Chaodi 项目记忆（Project Memory）

## 1. 当前策略内核（已更新）

### 1.1 实盘策略
- 保持不变：继续使用 `StrategyEngine` 的盘口异动逻辑。
- 核心信号：`ask_v1` 下降 + `volume` 上升（支持 AND/OR、连续确认、one-shot、开板剔除）。

### 1.2 回测策略
- 已与实盘解耦：回测不再复用 `StrategyEngine`。
- 采用 buy-flow 分钟策略：
  - 仅在“一字跌停分钟”将 `volume` 视为买量代理。
  - 触发条件：`current_buy_volume > cumulative_buy_volume_before`。
  - `cumulative` 为全天累计（09:30 起），触发判定仅在回测窗口内执行。
  - 当前窗口判定为闭区间（默认包含 `15:00` 分钟线）。

---

## 2. 数据语义与置信度

### 2.1 数据质量标签
- `minute_proxy`: 分钟级代理字段（低置信度）。

### 2.2 置信度
- 回测默认输出 `data_quality=minute_proxy` 与 `confidence=low`。
- 含义：当前结果用于方向验证，不等价于 L2/Tick 盘口精度。

---

## 3. 关键代码锚点

### 3.1 回测入口
- 文件：`src/backtest_cli.py`
- 关键点：
  - 仅保留日期、代码、窗口、数据源、账号参数。
  - precheck/report 明确展示 buy-flow 规则与累计范围。

### 3.2 回测执行器
- 文件：`src/backtest/runner.py`
- 关键点：
  - 按时间排序保证状态机可重复。
  - 全天累计买量，窗口内判定触发。
  - 保持 one-shot（命中即返回）。

### 3.3 JoinQuant Provider
- 文件：`src/backtest/providers/joinquant_provider.py`
- 关键点：
  - 固定拉取分钟字段：`close/high/low_limit/pre_close/volume`。
  - `low_limit` 缺失时 `pre_close * 0.9` 兜底。

---

## 4. 不变量（修改前必须检查）

1. one-shot 不变量
- 回测单股单日命中后应立即停止并返回。

2. 触发口径不变量
- 触发条件必须是 `current_buy_volume > cumulative_buy_volume_before`。

3. 统计范围不变量
- `cumulative` 必须按全天累计。
- 触发判定必须限制在回测窗口内。

4. 一字跌停过滤不变量
- 仅在 `close == high == limit_down_price` 分钟参与买量统计。

5. 质量披露不变量
- 回测报告必须输出 `data_quality` 与 `confidence`。

---

## 5. 参数与默认值（当前事实）

- `BACKTEST_SOURCE=joinquant`
- `BACKTEST_WINDOW_START=13:00`
- `BACKTEST_WINDOW_END=15:00`

补充：
- `src/config.py` 中仍保留历史回测参数（`BACKTEST_PROXY_MODE`、`BACKTEST_SIGNAL_COMBINATION` 等），当前主路径未使用。
- 这些参数属于兼容遗留，后续应统一清理或迁移。

---

## 6. 故障词典（更新后）

| 现象 | 含义 | 处理 |
| --- | --- | --- |
| `no_data_in_window` | 窗口内没有分钟样本 | 检查日期、停牌、窗口参数 |
| `no_one_word_limit_down` | 窗口内无一字跌停分钟 | 属于策略前置条件不满足 |
| `threshold_not_met` | 有一字跌停分钟但未突破累计基准 | 观察买量是否持续不足 |
| `JoinQuant permission/quota error` | 权限或额度不足 | 检查账号权限/额度 |

---

## 7. 测试策略记忆（必须维持）

- `tests/test_backtest_runner.py`
  - 覆盖：全天累计、窗口判定、13:02 不误触发、15:00 可触发、缺失数据路径。
- `tests/test_backtest_cli.py`
  - 覆盖：新 precheck/report 契约、参数校验、执行异常路径。
- `tests/test_backtest_joinquant_provider.py`
  - 覆盖：字段拉取、`low_limit` fallback、认证与权限错误。

---

## 8. 后续演进建议（不影响当前运行）

1. 加入批量样本回测与落盘（CSV/JSON）。
2. 增加“收盘竞价分钟是否纳入判定”的可配置开关。
3. 条件允许时接入更高质量数据口径（逐笔/Tick）做交叉验证。
