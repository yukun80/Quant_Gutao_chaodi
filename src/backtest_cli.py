from __future__ import annotations

"""CLI entrypoint for single-stock single-day buy-flow replay."""

import argparse
from datetime import date, datetime, time
from typing import Callable, Sequence

from .backtest.mapper import normalize_code_to_jq
from .backtest.providers import IntradayMinuteProvider, JoinQuantMinuteProvider
from .backtest.runner import BacktestRequest, BacktestResult, run_single_day_backtest
from .config import get_settings

ProviderFactory = Callable[[str, str | None, str | None], IntradayMinuteProvider]


def _build_parser() -> argparse.ArgumentParser:
    """Define command-line arguments for replay execution."""
    parser = argparse.ArgumentParser(description="Validate strategy trigger by date and stock code")
    parser.add_argument("--date", required=True, help="trade date in YYYY-MM-DD")
    parser.add_argument("--code", required=True, help="stock code, e.g. 600000")
    parser.add_argument("--source", default=None, help="backtest data source, only joinquant currently")
    parser.add_argument("--username", default=None, help="joinquant username override")
    parser.add_argument("--password", default=None, help="joinquant password override")
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
) -> IntradayMinuteProvider:
    """Build provider instance from CLI/source parameters."""
    if source != "joinquant":
        raise ValueError(f"unsupported source '{source}', only joinquant is available")
    return JoinQuantMinuteProvider(username=username, password=password)


def _format_report(
    request: BacktestRequest,
    result: BacktestResult,
    source: str,
) -> str:
    """Format final replay outcome report."""
    lines = [
        "=== Gutao_Chaodi Backtest Report ===",
        f"source: {source}",
        f"trade_date: {request.trade_date:%Y-%m-%d}",
        f"code: {request.code}",
        "strategy: buy_flow_breakout",
        "buy_flow_proxy: one_word_limit_down_volume",
        "trigger_rule: current_buy_volume > cumulative_buy_volume_before",
        "cumulative_scope: full_day",
        f"window: {request.window_start:%H:%M}-{request.window_end:%H:%M}",
        f"samples: {result.samples}",
        f"samples_in_window: {result.samples_in_window}",
        f"samples_one_word_in_window: {result.samples_one_word_in_window}",
        f"triggered: {'YES' if result.triggered else 'NO'}",
        f"reason: {result.reason}",
        f"data_quality: {result.data_quality}",
        f"confidence: {result.confidence}",
    ]
    if result.triggered:
        lines.append(f"trigger_time: {result.trigger_time:%Y-%m-%d %H:%M:%S}")
        lines.append(f"current_buy_volume: {result.current_buy_volume}")
        lines.append(f"cumulative_buy_volume_before: {result.cumulative_buy_volume_before}")
    return "\n".join(lines)


def _format_precheck(
    source: str,
    code: str,
    jq_code: str,
    trade_date: date,
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
            "strategy: buy_flow_breakout",
            "buy_flow_proxy: one_word_limit_down_volume",
            "trigger_rule: current_buy_volume > cumulative_buy_volume_before",
            "cumulative_scope: full_day",
            "one_word_filter: close==high==limit_down_price",
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
    window_start_raw = args.window_start or settings.BACKTEST_WINDOW_START or settings.MONITOR_START_TIME
    window_end_raw = args.window_end or settings.BACKTEST_WINDOW_END or settings.MONITOR_END_TIME
    username = args.username or settings.JQ_USERNAME
    password = args.password or settings.JQ_PASSWORD

    if source not in {"joinquant"}:
        print("source must be 'joinquant'")
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
    print(_format_precheck(source, code, jq_code, trade_date, window_start, window_end))

    try:
        provider = provider_factory(source, username, password)
    except Exception as exc:
        print(f"provider init failed: {exc}")
        return 2

    request = BacktestRequest(
        code=code,
        trade_date=trade_date,
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

    print(_format_report(request=request, result=result, source=source))
    return 0


def main() -> None:
    """Console script entrypoint."""
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
