# Gutao_Chaodi 当前工作状态（2026-02-20）

- 日期：2026-02-20
- 范围：基于当前仓库代码与测试状态（`src/`、`tests/`、`doc/`）
- 目标：沉淀“当前已实现能力”和“尚未实现项”，修正文档与实现不对齐问题

---

## 1. 当前已实现（As-Built）

### 1.1 实盘链路（可运行，已完成策略改造）
- 主链路已打通：`PoolManager -> EastMoneyFetcher -> StrategyEngine -> NotificationGateway`。
- 监控池：全市场股票入池，ST 仅作为标签，不自动剔除。
- 一字跌停前置门禁与开板剔除已实现。
- 实盘策略已升级为“双规则 OR”：
  - 规则 A：`buy_flow_breakout`（一字跌停条件下，当前分钟成交量代理 `> 当日前序累计成交量`）；
  - 规则 B：`sell1_drop`（一字跌停条件下，相邻分钟卖一挂单量显著下降）。
- 两规则均强制在“一字跌停”前提下判定，不再存在“仅规则A有一字前置”的不一致。
- 告警静默语义已调整为“每规则各触发一次”：
  - 单票单日最多两次告警（A一次 + B一次）；
  - 若同一分钟双规则同时命中，合并为一条告警并同时标记两规则已触发。
- 已新增 `flush_pending()` 收口逻辑，主循环结束后会补判最后分钟，避免尾分钟信号丢失。
- 运行窗口控制已实现（默认 `13:00-15:00`）。

### 1.2 回测链路（已重构）
- 回测已与实盘策略引擎解耦，不再复用 `StrategyEngine`。
- 当前回测规则：
  - 仅在一字跌停分钟将 `volume` 作为买量代理；
  - 全天累计买量（09:30 起）；
  - 仅在回测窗口内判定触发；
  - 触发条件为 `current_buy_volume > cumulative_buy_volume_before`。
- 回测 CLI 已切换为新口径输出：
  - precheck/report 显示 `buy_flow_breakout`、`current_buy_volume`、`cumulative_buy_volume_before`。

### 1.3 JoinQuant 接入能力
- 已支持账号认证与错误分类：认证失败、权限/额度错误。
- 已支持 `low_limit` 缺失时 `pre_close * 0.9` 兜底。
- 当前回测字段依赖：`close/high/low_limit/pre_close/volume`。

### 1.4 测试状态
- 当前测试通过：`pytest -q` => `35 passed`。
- 新增/强化覆盖：
  - `tests/test_engine.py`：
    - 双规则 OR；
    - 一字前置门禁（A/B 都受约束）；
    - 开板剔除；
    - 每规则各一次；
    - `flush_pending()` 尾分钟补判；
    - 规则合并触发路径。
  - `tests/test_models.py`：新增告警消息中规则字段与 buy-flow 字段输出校验。

---

## 2. 本次对话完成的修改（增量记录）

1. 重构 `src/engine.py`
- 由旧的“相邻窗口 ask/volume 组合判定”改为“1分钟桶 + 双规则 OR”。
- 新增规则常量与规则级触发跟踪（`buy_flow_breakout`、`sell1_drop`）。
- 新增全局一字门禁，统一约束 A/B 两规则。
- 新增 `flush_pending()`，收口补判最后分钟。

2. 更新 `src/main.py`
- 实盘引擎参数改为读取 `LIVE_CONFIRM_MINUTES`（不再耦合 `BACKTEST_CONFIRM_MINUTES`）。
- 主循环结束后增加 `flush_pending()` 结果发送。
- 日志中增加 `rule` 字段，便于区分触发来源。

3. 扩展 `src/models.py`
- `AlertEvent` 新增字段：`signal_buy_flow`、`trigger_rule`、`current_buy_volume`、`cumulative_buy_volume_before`。
- `format_message()` 增加规则名与 buy-flow 关键值展示。

4. 更新配置模板与校验
- `src/config.py` 新增 `LIVE_CONFIRM_MINUTES` 并纳入校验。
- `.env.example` 新增 `LIVE_CONFIRM_MINUTES=1`。

5. 测试改造
- 重写 `tests/test_engine.py` 以匹配新实盘策略语义。
- 更新 `tests/test_models.py` 覆盖新告警消息内容。

---

## 3. 当前未实现 / 遗留项

### 3.1 回测能力未完成项
- 回测结果未落盘（JSON/CSV），仍以控制台输出为主。
- 不支持批量区间回测、参数扫描、统计报表。
- `BACKTEST_USE_NOTIFIER` 仍为预留开关，未接入实际通知路径。

### 3.2 实盘能力待完善项
- “严格全天累计”当前依赖实时快照中的当日累计成交量字段；尚未增加字段异常/回退策略的专项监控与告警分级。
- 实盘告警模板已扩展，但未形成规则级聚合统计（如 A/B 触发率、尾分钟触发占比）。
- 未补充实盘运行手册中的新参数说明与调参建议（`LIVE_CONFIRM_MINUTES`、A/B 规则阈值口径）。

### 3.3 生产化未完成项
- 交易日自动调度未实现（当前手动启动）。
- 进程守护/自动拉起未实现（systemd/supervisor/容器编排未接入）。
- 指标看板未完善（轮询耗时、成功率、重试率、告警速率等未形成统一观测面）。

### 3.4 技术债务
- `src/config.py` 中仍保留多项历史回测参数（`BACKTEST_PROXY_MODE`、`BACKTEST_SIGNAL_COMBINATION` 等），当前主路径未消费。
- `src/backtest/mapper.py` 仍保留 `ask_v1 -> StockSnapshot` 的历史映射能力，当前回测主路径不依赖该函数。
- `src/engine.py` 中保留了部分兼容字段（如 `volume_spike_threshold`、`signal_combination`）仅用于向后兼容，建议后续清理。

---

## 4. 建议下一步（优先级）

1. 文档同步
- 更新 `doc/Project_Memory.md`、`doc/Project_Architecture_Guide.md`，将实盘策略描述同步为“双规则 OR + 一字统一门禁 + 每规则一次”。

2. 配置收敛
- 清理或迁移未使用的历史回测/实盘兼容参数，减少“配置存在但无效”的认知负担。

3. 实盘观测增强
- 增加规则级运行指标（A/B 命中次数、合并命中次数、尾分钟 flush 命中次数）。

4. 回测资产化
- 增加结果落盘与批量执行入口，形成可复盘数据资产。

---

## 5. 备注

- 本文档是“当前状态快照”，用于对齐代码事实，不替代白皮书的设计背景价值。
- 历史阶段记录请继续参考：
  - `doc/worklog/2026-02-18_implementation_status.md`
  - `doc/worklog/2026-02-19_backtest_implementation_status.md`
