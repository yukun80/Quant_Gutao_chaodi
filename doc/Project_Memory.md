# Gutao_Chaodi 项目记忆（Project Memory）

## 1. 当前策略内核（已更新）

### 1.1 核心范式
- 已从“固定基线比值”升级为“相邻窗口差分”。
- 每一条信号都比较 `上一窗口` 与 `当前窗口`，不再引用日内某个固定时点。
- 双子信号：
  - `signal_ask_drop`: 卖一挂单（`ask_v1`）下降。
  - `signal_volume_spike`: 成交量（`volume`）上升。

### 1.2 组合关系
- 由 `SIGNAL_COMBINATION` / `BACKTEST_SIGNAL_COMBINATION` 控制：`and` 或 `or`。
- `and` 语义：两个子信号同窗同时满足才计为命中。
- `or` 语义：任意子信号满足即可计为命中。

### 1.3 连续确认
- `confirm_minutes` 表示“连续命中窗口数”。
- 默认已改为 `1`（包含回测默认）。

---

## 2. 数据语义与置信度

### 2.1 数据质量标签
- `tick_a1v`: 真实盘口卖一量（高置信度）。
- `minute_proxy`: 分钟代理字段（低置信度）。

### 2.2 代理模式
- `BACKTEST_PROXY_MODE=allow_proxy`：允许 `ask_v1` 缺失时回退到 `volume`。
- `BACKTEST_PROXY_MODE=strict`：不允许回退，缺失即报错。

### 2.3 防呆规则（关键）
- 当 `askv1_field=volume` 且 `signal_combination=and` 时，CLI 会直接拒绝运行。
- 原因：两个子信号基于同一序列时方向相反，数学上几乎不可能同窗同时满足。

---

## 3. 关键代码锚点（按注释重建）

### 3.1 决策引擎
- 文件：`src/engine.py`
- 关键注释已覆盖：
  - 兼容旧参数入口（`vol_drop_threshold`）
  - 相邻窗口差分计算
  - AND/OR 组合判定
  - 连续确认计数
  - one-shot 静默
- 关键状态：
  - `prev_window_map`: 上一窗口特征
  - `confirm_count_map`: 连续命中计数
  - `processed_set`: 已触发静默集
  - `removed_pool`: 开板剔除集

### 3.2 回测入口
- 文件：`src/backtest_cli.py`
- 关键注释已覆盖：
  - 参数优先级与兼容别名
  - proxy_mode 到 provider fallback 的映射
  - `askv1_field=volume + and` 冲突防呆

### 3.3 回测执行器
- 文件：`src/backtest/runner.py`
- 关键注释已覆盖：
  - 按时间排序保证状态机可重复
  - 仅评估窗口内数据
  - 使用与实盘一致的 `StrategyEngine`
  - 结果输出包含窗口级指标与数据质量

### 3.4 JoinQuant 映射层
- 文件：`src/backtest/providers/joinquant_provider.py`
- 关键注释已覆盖：
  - `data_quality` 标记传播
  - fallback 为代理时的低置信度语义
  - `low_limit` 缺失时 `pre_close * 0.9` 兜底

---

## 4. 不变量（修改前必须检查）

1. one-shot 不变量
- 触发后必须加入 `processed_set`，当日不可重复触发。

2. 开板剔除不变量
- `high_price > limit_down_price` 时必须剔除并清理状态。

3. 输入契约不变量
- 策略层只接受 `StockSnapshot`，禁止直接透传 provider 原始结构。

4. 差分不变量
- 策略判定必须基于相邻窗口，不得回退为“固定基线全程比较”。

5. 质量披露不变量
- 回测报告必须输出 `data_quality` 与 `confidence`。

---

## 5. 参数与默认值（当前事实）

- `BACKTEST_CONFIRM_MINUTES=1`
- `BACKTEST_PROXY_MODE=allow_proxy`
- `BACKTEST_SIGNAL_COMBINATION=or`（回测默认更适配代理口径）
- `SIGNAL_COMBINATION=and`（实盘默认）
- `BACKTEST_MINUTE_ASKV1_FIELD=volume`（代理口径）

---

## 6. 故障词典（更新后）

| 现象 | 含义 | 处理 |
| --- | --- | --- |
| `invalid config: askv1_field=volume cannot be combined with signal_combination=and` | 配置组合自相矛盾 | 改 `--signal-combination or`，或改用真实 `askv1_field` |
| `data_quality: minute_proxy` | 当前信号来自代理字段 | 降低置信度解读，优先使用 tick 口径复核 |
| `threshold_not_met` | 窗口内未形成有效连续命中 | 调整阈值、组合关系或确认窗口数 |
| `JoinQuant permission/quota error` | 权限或额度不足 | 检查账号权限/额度 |

---

## 7. 测试策略记忆（必须维持）

- `tests/test_engine.py`
  - 覆盖 AND/OR、连续确认、开板剔除、one-shot。
- `tests/test_backtest_runner.py`
  - 覆盖窗口回放、数据缺失、窗口过滤。
  - 覆盖“午后早段不误触发、尾盘才触发”的回归样本。
- `tests/test_backtest_cli.py`
  - 覆盖参数校验、冲突防呆、执行异常路径。
- `tests/test_backtest_joinquant_provider.py`
  - 覆盖字段映射、fallback、认证与权限错误。

---

## 8. 后续演进建议（不影响当前运行）

1. 增加 `strict` 回测流水线（默认不 fallback）作为研究基准。
2. 对 `minute_proxy` 结果单独落盘，避免与 `tick_a1v` 混用统计。
3. 增加多窗口聚合（3m/5m）A/B 测试，评估噪声与滞后权衡。
