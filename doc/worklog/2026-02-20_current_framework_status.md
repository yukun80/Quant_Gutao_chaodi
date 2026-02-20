# Gutao_Chaodi 当前工作状态（2026-02-20）

- 日期：2026-02-20
- 范围：基于当前仓库代码与测试状态（`src/`、`tests/`、`doc/`）
- 目标：沉淀“当前已实现能力”和“尚未实现项”，修正文档与实现不对齐问题

---

## 1. 当前已实现（As-Built）

### 1.1 实盘链路（可运行）
- 主链路已打通：`PoolManager -> EastMoneyFetcher -> StrategyEngine -> NotificationGateway`。
- 监控池：全市场股票入池，ST 仅作为标签，不自动剔除。
- 一字跌停前置过滤与开板剔除已实现。
- one-shot 静默已实现（单标的单日最多一次提醒）。
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
- 当前测试通过：`pytest -q` => `30 passed`。
- 关键覆盖：
  - `tests/test_backtest_runner.py`：全天累计、窗口判定、误触发回归；
  - `tests/test_backtest_cli.py`：新 CLI 契约与返回码；
  - `tests/test_backtest_joinquant_provider.py`：字段/鉴权/额度错误路径；
  - 实盘关键模块测试：`engine`、`fetcher`、`notifier`、`pool_manager`。

---

## 2. 本次已完成的文档对齐

1. 更新 `doc/Project_Architecture_Guide.md`
- 修正回测主链路描述（buy-flow）；
- 修正文件职责、测试索引与配置说明；
- 移除对已删除 `doc/Commenting_Convention.md` 的引用；
- 明确“回测与实盘策略分叉”的当前事实。

2. 更新 `doc/Development_White_Paper.md`
- 增加 As-Built Delta 摘要，标注为“初版设计”并给出当前实现对齐入口。

3. 更新 `doc/Project_Memory.md`
- 补充 15:00 闭区间判定事实；
- 补充历史回测配置参数仍存在但主链路未使用的说明。

---

## 3. 当前未实现 / 遗留项

### 3.1 回测能力未完成项
- 回测结果未落盘（JSON/CSV），仍以控制台输出为主。
- 不支持批量区间回测、参数扫描、统计报表。
- `BACKTEST_USE_NOTIFIER` 仍为预留开关，未接入实际通知路径。

### 3.2 实盘生产化未完成项
- 交易日自动调度未实现（当前手动启动）。
- 进程守护/自动拉起未实现（systemd/supervisor/容器编排未接入）。
- 指标看板未完善（轮询耗时、成功率、重试率、告警速率等未形成统一观测面）。

### 3.3 技术债务
- `src/config.py` 中保留多项历史回测参数（`BACKTEST_PROXY_MODE`、`BACKTEST_SIGNAL_COMBINATION` 等），当前主路径未消费。
- `src/backtest/mapper.py` 仍保留 `ask_v1 -> StockSnapshot` 的历史映射能力，当前回测主路径不依赖该函数。
- `src/main.py` 中 `confirm_minutes` 读取的是 `BACKTEST_CONFIRM_MINUTES`（命名语义与实盘用途不一致），建议拆分为独立实盘参数。

---

## 4. 建议下一步（优先级）

1. 配置收敛：清理或迁移未使用的历史回测配置项，减少“配置存在但无效”的认知负担。
2. 回测资产化：增加回测结果落盘与批量执行入口，形成可复盘数据资产。
3. 实盘参数治理：将 `confirm_minutes` 拆分为实盘独立配置，避免与回测参数耦合。
4. 生产化补齐：增加调度、守护、统一指标与健康检查。

---

## 5. 备注

- 本文档是“当前状态快照”，用于对齐代码事实，不替代白皮书的设计背景价值。
- 历史阶段记录请继续参考：
  - `doc/worklog/2026-02-18_implementation_status.md`
  - `doc/worklog/2026-02-19_backtest_implementation_status.md`
