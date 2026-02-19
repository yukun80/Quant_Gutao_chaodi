# Gutao_Chaodi 开发日志（策略验证回测阶段性总结）

- 日期：2026-02-19
- 范围：截至当前仓库实现（含本次回测联调增强）
- 对应目标：实现“指定日期 + 指定股票”的策略验证回测，并评估项目整体完成度。

## 1. 当前完成情况总览

### 1.1 回测能力（本次重点）
- 已达到“可执行、可验证、可排障”的阶段：
  - 已支持单股单日回测（CLI 可直接执行）。
  - 已接入 JoinQuant 数据源实现（分钟级）。
  - 已补齐联调排障能力（认证校验、字段诊断、执行前预检查）。
- 已从“仅 mock 验证”升级到“真实账号实测”：
  - 已有真实 JoinQuant 样本运行记录（见第 5 节）。
  - 仍未形成批量样本联调报告（仅完成单样本实测）。

### 1.2 实盘监控主链路
- “股票池 -> 快照采集 -> 策略引擎 -> 通知”主流程可运行。
- 单次触发、防重复提醒、开板剔除均已实现。
- 生产化保障（自动调度/守护/指标看板）仍不完整。

## 2. 已完成项

### 2.1 回测主链路实现完成
- 回测执行器：`src/backtest/runner.py`
  - `BacktestRequest` / `BacktestResult` 已定义并使用。
  - 复用 `StrategyEngine`，未重复实现策略判定逻辑。
- 数据映射：`src/backtest/mapper.py`
  - 分钟数据转 `StockSnapshot`。
  - 保持与实盘一致的数据模型和校验路径。

### 2.2 JoinQuant 接入与联调增强已完成
- Provider 抽象：`src/backtest/providers/base.py`
- JoinQuant Provider：`src/backtest/providers/joinquant_provider.py`
  - 支持账号认证（`JQ_USERNAME` / `JQ_PASSWORD`）。
  - 增加认证失败显式报错（`JoinQuant auth failed`）。
  - 增加权限/额度类错误分级（permission/quota）。
  - 增加返回字段诊断（字段缺失时输出 available columns）。
  - 支持 `low_limit` 缺失时 `pre_close * 0.9` 兜底。

### 2.3 CLI 与联调工具已完成
- CLI：`src/backtest_cli.py`
  - 支持单股单日执行：`python -m src.backtest_cli --date YYYY-MM-DD --code 600000 --source joinquant`
  - 增加 precheck 输出：source/date/code/jq_code/threshold/askv1_field。
  - 返回码语义明确：参数/配置问题 `2`，执行期问题 `3`。
- 联调脚本：`scripts/backtest_joinquant_smoke.sh`
  - 提供一键 smoke 入口，便于真实联网联调。

### 2.4 配置、依赖、文档与测试已更新
- 配置扩展：`src/config.py`、`.env.example`
  - `BACKTEST_SOURCE`、`BACKTEST_MINUTE_ASKV1_FIELD`、`JQ_USERNAME`、`JQ_PASSWORD` 等。
- 依赖更新：`requirements.txt` 新增 `jqdatasdk>=1.9`
- 文档更新：`README.md` 已补充 backtest 与 smoke 用法。
- 测试新增并通过：
  - `tests/test_backtest_mapper.py`
  - `tests/test_backtest_runner.py`
  - `tests/test_backtest_cli.py`
  - `tests/test_backtest_joinquant_provider.py`
- `tests/test_notifier.py`
- `tests/test_fetcher.py`
- 当前测试结果：`pytest -q` => `22 passed`

## 3. 未完成项

### 3.1 真实 JoinQuant 端到端联调记录未完成
- 已完成 1 组真实账号联调样本（见第 5 节）。
- 仍未形成“多样本输入-输出-错误分类”的系统化联调报告。
- 尚未确认不同日期、不同股票下字段稳定性（尤其 `ask_v1` 代理字段）与查询额度行为。

### 3.2 回测结果输出形态仍较轻量
- 目前默认仅控制台输出，未落盘 JSON/CSV。
- 不利于批量样本复盘和参数回溯。

### 3.3 通知联动仍未接入回测链路
- `BACKTEST_USE_NOTIFIER` 仅为配置预留。
- 尚未将回测命中结果接入 `NotificationGateway`（可选开关模式）。

### 3.4 回测精度与范围仍有限
- 粒度：分钟级近似（`ask_v1` 代理字段），非 tick 级卖一挂单原值。
- 范围：仅单股单日；未支持区间批量、参数扫描、统计报表。

### 3.5 项目级未完项（非本次新增）
- 交易日自动调度未实现（当前手动启动）。
- 进程守护/自动拉起未实现。
- 指标看板与统一可观测性（延迟、重试率、告警速率）未完善。
- 外部接口契约级集成测试仍不足。

## 4. 下一步建议（按优先级）

1. 用真实 JoinQuant 账号完成 6 组以上样本联调，并落地联调记录文档（成功/失败分类、字段可用性、配额行为）。
2. 增加回测结果落盘（JSON/CSV），形成可复盘数据资产。
3. 接入 `BACKTEST_USE_NOTIFIER`，实现回测命中后的可选通知分支。
4. 规划并推进 tick 级数据方案，提升“封单异动”验证精度。
5. 补齐项目级生产化能力（调度、守护、监控指标、集成演练）。

## 5. 本次对话增量更新（2026-02-19）

### 5.1 配置与安全治理
- 已新增安全相关配置：
  - `DINGTALK_KEYWORD`（钉钉关键词安全前缀）
  - `EM_HEADERS_JSON`（EastMoney 可选请求头 JSON）
  - `EM_COOKIE`（EastMoney 可选 Cookie）
- 已新增 `.gitignore`，忽略：
  - `.env`、`.venv/`、`__pycache__/`、`.pytest_cache/`、`logs/`、`*.pyc`
- 已将 `.env.example` 恢复为占位模板，不包含真实密钥。
- 已修正钉钉 URL 模板为 Apprise 协议：
  - `dingtalk://your_dingtalk_token/`

### 5.2 钉钉安全策略适配
- `NotificationGateway` 已支持关键词注入，发送正文前自动添加 `DINGTALK_KEYWORD`。
- 解决了 `apprise.add(https://oapi...) == False` 的问题：
  - 根因是 URL 格式不符合 Apprise 钉钉插件要求。
  - 修复后 `app.add(dingtalk://token/) == True`。

### 5.3 EastMoney 鉴权扩展位
- 维持“默认不强制账号密钥”的当前策略。
- 已提供可选鉴权扩展位（Header/Cookie 注入），用于后续接口策略变化时兼容。

### 5.4 真实回测样本结果（用户实测）
- 命令：
  - `bash scripts/backtest_joinquant_smoke.sh 2025-11-05 002122`
- 结果：
  - `triggered: YES`
  - `reason: sell1_drop`
  - `trigger_time: 2025-11-05 09:32:00`
  - `baseline_ask_v1: 8256400`
  - `trigger_ask_v1: 518600`
  - `drop_ratio: 93.72%`
- 说明：
  - 当前回测按全天分钟数据回放，因此可在上午时段触发。
  - 若要严格对齐实盘（13:00-15:00），需新增回测时间窗口过滤。
