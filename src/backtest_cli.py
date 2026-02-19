from __future__ import annotations

"""CLI entrypoint for single-stock single-day strategy replay."""

import argparse
from datetime import date, datetime, time
from typing import Callable, Sequence

from .backtest.mapper import normalize_code_to_jq
from .backtest.providers import IntradayMinuteProvider, JoinQuantMinuteProvider
from .backtest.runner import BacktestRequest, BacktestResult, run_single_day_backtest
from .config import get_settings

ProviderFactory = Callable[[str, str | None, str | None, str, bool], IntradayMinuteProvider]


def _build_parser() -> argparse.ArgumentParser:
    """Define command-line arguments for replay execution."""
    parser = argparse.ArgumentParser(description="Validate strategy trigger by date and stock code")
    parser.add_argument("--date", required=True, help="trade date in YYYY-MM-DD")
    parser.add_argument("--code", required=True, help="stock code, e.g. 600000")
    parser.add_argument("--source", default=None, help="backtest data source, only joinquant currently")
    parser.add_argument("--threshold", type=float, default=None, help="deprecated alias of --ask-drop-threshold")
    parser.add_argument("--ask-drop-threshold", type=float, default=None, help="ask_v1 drop ratio vs previous window")
    parser.add_argument(
        "--volume-spike-threshold",
        type=float,
        default=None,
        help="volume growth ratio vs previous window",
    )
    parser.add_argument("--confirm-minutes", type=int, default=None, help="consecutive minutes required before trigger")
    parser.add_argument("--signal-combination", default=None, choices=["and", "or"], help="combine dual signals")
    parser.add_argument("--min-abs-delta-ask", type=int, default=None, help="minimum absolute ask_v1 delta")
    parser.add_argument("--min-abs-delta-volume", type=int, default=None, help="minimum absolute volume delta")
    parser.add_argument("--username", default=None, help="joinquant username override")
    parser.add_argument("--password", default=None, help="joinquant password override")
    parser.add_argument("--askv1-field", default=None, help="minute field used as ask_v1 proxy")
    parser.add_argument(
        "--proxy-mode",
        default=None,
        choices=["allow_proxy", "strict"],
        help="allow proxy fallback or require strict ask_v1 field",
    )
    parser.add_argument("--window-start", default=None, help="replay window start in HH:MM")
    parser.add_argument("--window-end", default=None, help="replay window end in HH:MM")
    return parser


def _parse_hhmm(value: str) -> time:
    """Parse HH:MM string into a time object."""
    return datetime.strptime(value, "%H:%M").time()


def _default_provider_factory(
    source: str,
    username: str | None,
    password: str | None,
    askv1_field: str,
    allow_proxy_fallback: bool,
) -> IntradayMinuteProvider:
    """Build provider instance from CLI/source parameters."""
    if source != "joinquant":
        raise ValueError(f"unsupported source '{source}', only joinquant is available")
    # Provider fallback behavior is controlled by proxy mode.
    return JoinQuantMinuteProvider(
        username=username,
        password=password,
        ask_v1_field=askv1_field,
        allow_proxy_fallback=allow_proxy_fallback,
    )


def _format_report(
    request: BacktestRequest,
    result: BacktestResult,
    source: str,
    askv1_field_used: str,
) -> str:
    """Format final replay outcome report."""
    lines = [
        "=== Gutao_Chaodi Backtest Report ===",
        f"source: {source}",
        f"trade_date: {request.trade_date:%Y-%m-%d}",
        f"code: {request.code}",
        f"ask_drop_threshold: {request.ask_drop_threshold:.2%}",
        f"volume_spike_threshold: {request.volume_spike_threshold:.2%}",
        f"signal_combination: {request.signal_combination}",
        f"confirm_minutes: {request.confirm_minutes}",
        f"askv1_field_used: {askv1_field_used}",
        f"window: {request.window_start:%H:%M}-{request.window_end:%H:%M}",
        f"samples: {result.samples}",
        f"samples_in_window: {result.samples_in_window}",
        f"triggered: {'YES' if result.triggered else 'NO'}",
        f"reason: {result.reason}",
        f"data_quality: {result.data_quality}",
        f"confidence: {result.confidence}",
    ]
    if result.prev_window_ts is not None:
        lines.append(f"prev_window_ts: {result.prev_window_ts:%Y-%m-%d %H:%M:%S}")
    if result.triggered:
        lines.append(f"trigger_time: {result.trigger_time:%Y-%m-%d %H:%M:%S}")
        lines.append(f"curr_window_ts: {result.curr_window_ts:%Y-%m-%d %H:%M:%S}")
        lines.append(f"prev_ask_v1: {result.prev_ask_v1}")
        lines.append(f"curr_ask_v1: {result.curr_ask_v1}")
        lines.append(f"ask_change_ratio: {result.ask_change_ratio:.2%}")
        lines.append(f"prev_volume: {result.prev_volume}")
        lines.append(f"curr_volume: {result.curr_volume}")
        lines.append(f"volume_change_ratio: {result.volume_change_ratio:.2%}")
        lines.append(f"signal_ask_drop: {result.signal_ask_drop}")
        lines.append(f"signal_volume_spike: {result.signal_volume_spike}")
    return "\n".join(lines)


def _format_precheck(
    source: str,
    code: str,
    jq_code: str,
    trade_date: date,
    threshold: float,
    ask_drop_threshold: float,
    volume_spike_threshold: float,
    signal_combination: str,
    proxy_mode: str,
    confirm_minutes: int,
    min_abs_delta_ask: int,
    min_abs_delta_volume: int,
    askv1_field: str,
    window_start: time,
    window_end: time,
) -> str:
    """Format pre-execution context so user can verify run parameters quickly."""
    return "\n".join(
        [
            "=== Gutao_Chaodi Backtest Precheck ===",
            f"source: {source}",
            f"trade_date: {trade_date:%Y-%m-%d}",
            f"code: {code}",
            f"jq_code: {jq_code}",
            f"threshold: {threshold:.2%}",
            f"ask_drop_threshold: {ask_drop_threshold:.2%}",
            f"volume_spike_threshold: {volume_spike_threshold:.2%}",
            f"signal_combination: {signal_combination}",
            f"proxy_mode: {proxy_mode}",
            f"confirm_minutes: {confirm_minutes}",
            f"min_abs_delta_ask: {min_abs_delta_ask}",
            f"min_abs_delta_volume: {min_abs_delta_volume}",
            f"askv1_field: {askv1_field}",
            f"window: {window_start:%H:%M}-{window_end:%H:%M}",
        ]
    )


def run_cli(argv: Sequence[str] | None = None, provider_factory: ProviderFactory | None = None) -> int:
    """Run backtest CLI and return process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    settings = get_settings()
    provider_factory = provider_factory or _default_provider_factory
    source = (args.source or settings.BACKTEST_SOURCE).strip().lower()

    try:
        trade_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        print(f"invalid --date '{args.date}', expected YYYY-MM-DD")
        return 2

    code = args.code.strip().split(".")[0]
    # Keep historical --threshold behavior as compatibility alias.
    threshold = args.threshold if args.threshold is not None else settings.VOL_DROP_THRESHOLD
    # ask_drop_threshold is the effective sell1-drop ratio used by engine.
    ask_drop_threshold = (
        args.ask_drop_threshold
        if args.ask_drop_threshold is not None
        else settings.ASK_DROP_THRESHOLD if settings.ASK_DROP_THRESHOLD is not None else threshold
    )
    # volume_spike_threshold controls adjacent-window volume surge signal.
    volume_spike_threshold = (
        args.volume_spike_threshold
        if args.volume_spike_threshold is not None
        else settings.BACKTEST_VOLUME_SPIKE_THRESHOLD
        if settings.BACKTEST_VOLUME_SPIKE_THRESHOLD is not None
        else settings.VOLUME_SPIKE_THRESHOLD
    )
    # signal_combination applies to the two sub-signals: ask_drop and volume_spike.
    signal_combination = (
        (args.signal_combination or settings.BACKTEST_SIGNAL_COMBINATION or settings.SIGNAL_COMBINATION).strip().lower()
    )
    proxy_mode = (args.proxy_mode or settings.BACKTEST_PROXY_MODE).strip().lower()
    # strict mode disables ask_v1 proxy fallback in provider mapping.
    allow_proxy_fallback = proxy_mode == "allow_proxy"
    confirm_minutes = args.confirm_minutes if args.confirm_minutes is not None else settings.BACKTEST_CONFIRM_MINUTES
    min_abs_delta_ask = (
        args.min_abs_delta_ask
        if args.min_abs_delta_ask is not None
        else settings.BACKTEST_MIN_ABS_DELTA_ASK
        if settings.BACKTEST_MIN_ABS_DELTA_ASK is not None
        else settings.MIN_ABS_DELTA_ASK
    )
    min_abs_delta_volume = (
        args.min_abs_delta_volume
        if args.min_abs_delta_volume is not None
        else settings.BACKTEST_MIN_ABS_DELTA_VOLUME
        if settings.BACKTEST_MIN_ABS_DELTA_VOLUME is not None
        else settings.MIN_ABS_DELTA_VOLUME
    )
    askv1_field = (args.askv1_field or settings.BACKTEST_MINUTE_ASKV1_FIELD).strip()
    # Window defaults to monitor session when backtest-specific values are missing.
    window_start_raw = args.window_start or settings.BACKTEST_WINDOW_START or settings.MONITOR_START_TIME
    window_end_raw = args.window_end or settings.BACKTEST_WINDOW_END or settings.MONITOR_END_TIME
    username = args.username or settings.JQ_USERNAME
    password = args.password or settings.JQ_PASSWORD

    if not 0 < threshold < 1 or not 0 < ask_drop_threshold < 1:
        print("threshold/ask_drop_threshold must be in (0, 1)")
        return 2
    if volume_spike_threshold < 0:
        print("volume_spike_threshold must be >= 0")
        return 2
    if confirm_minutes <= 0:
        print("confirm_minutes must be a positive integer")
        return 2
    if signal_combination not in {"and", "or"}:
        print("signal_combination must be 'and' or 'or'")
        return 2
    if proxy_mode not in {"allow_proxy", "strict"}:
        print("proxy_mode must be 'allow_proxy' or 'strict'")
        return 2
    if min_abs_delta_ask < 0 or min_abs_delta_volume < 0:
        print("min_abs_delta_ask/min_abs_delta_volume must be >= 0")
        return 2
    # If ask_v1 comes from the same volume column, AND mode is mathematically contradictory.
    if askv1_field.lower() == "volume" and signal_combination == "and":
        print("invalid config: askv1_field=volume cannot be combined with signal_combination=and")
        print("reason: ask_drop and volume_spike are opposite directions on the same series")
        return 2
    if not code.isdigit() or len(code) != 6:
        print(f"invalid --code '{args.code}', expected 6-digit stock code")
        return 2
    try:
        window_start = _parse_hhmm(window_start_raw)
        window_end = _parse_hhmm(window_end_raw)
    except ValueError:
        print("invalid window, expected --window-start/--window-end in HH:MM format")
        return 2
    if window_start > window_end:
        print("invalid window, --window-start must be earlier than or equal to --window-end")
        return 2

    jq_code = normalize_code_to_jq(code)
    print(
        _format_precheck(
            source,
            code,
            jq_code,
            trade_date,
            threshold,
            ask_drop_threshold,
            volume_spike_threshold,
            signal_combination,
            proxy_mode,
            confirm_minutes,
            min_abs_delta_ask,
            min_abs_delta_volume,
            askv1_field,
            window_start,
            window_end,
        )
    )

    try:
        provider = provider_factory(source, username, password, askv1_field, allow_proxy_fallback)
    except Exception as exc:
        print(f"provider init failed: {exc}")
        return 2

    request = BacktestRequest(
        code=code,
        trade_date=trade_date,
        ask_drop_threshold=ask_drop_threshold,
        volume_spike_threshold=volume_spike_threshold,
        confirm_minutes=confirm_minutes,
        signal_combination=signal_combination,
        min_abs_delta_ask=min_abs_delta_ask,
        min_abs_delta_volume=min_abs_delta_volume,
        window_start=window_start,
        window_end=window_end,
    )

    try:
        result = run_single_day_backtest(
            request,
            provider=provider,
        )
    except Exception as exc:
        print(f"backtest execution failed: {exc}")
        return 3

    print(
        _format_report(
            request=request,
            result=result,
            source=source,
            askv1_field_used=askv1_field,
        )
    )
    return 0


def main() -> None:
    """Console script entrypoint."""
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
