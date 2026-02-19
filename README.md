# Gutao_Chaodi

A-share afternoon limit-down anomaly monitor for all listed A-share symbols.

## Quick start

1. Create environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure env:

```bash
cp .env.example .env
# fill tokens/passwords in .env (do not write real secrets into .env.example)
```

3. Run:

```bash
bash scripts/run_live.sh
```

## Test

```bash
pytest -q
```

## Backtest (single date + single stock)

Run strategy validation for one stock on one date:

```bash
python -m src.backtest_cli --date 2025-01-10 --code 600000 --source joinquant
```

Smoke command (reads `.env` credentials):

```bash
bash scripts/backtest_joinquant_smoke.sh 2025-01-10 600000
```

Options:
- `--ask-drop-threshold 0.3` ask_v1 drop threshold vs previous window
- `--volume-spike-threshold 0.8` volume growth threshold vs previous window
- `--signal-combination and` require both signals (`and`) or either (`or`)
- `--confirm-minutes 1` require consecutive window hits before alert
- `--proxy-mode allow_proxy` allow fallback to volume proxy when ask_v1 field is unavailable
- `--min-abs-delta-ask 5000` absolute ask_v1 delta floor
- `--min-abs-delta-volume 2000` absolute volume delta floor
- `--username xxx --password yyy` override JoinQuant credentials
- `--askv1-field volume` choose minute field used as ask_v1 proxy
- `--window-start 13:00 --window-end 15:00` replay only monitor window

## Notes on Backtest Precision

- Strategy evaluates rolling window deltas, not a fixed intraday baseline.
- Preferred signal is tick-level `a1_v`; fallback to minute proxy is allowed when unavailable.
- Backtest report exposes `data_quality` and `confidence` to flag proxy-based results.
- Backtest default uses `signal_combination=or` with proxy data; switch to `and` only when ask_v1 is independent from volume.
- Safety guard: `askv1_field=volume` cannot be used with `signal_combination=and`.

## Security Notes

- DingTalk robots can enforce keyword safety. Set `DINGTALK_KEYWORD` in `.env`.
- Optional EastMoney headers/cookie can be configured by `EM_HEADERS_JSON` and `EM_COOKIE`.
- Keep secrets only in `.env`; `.env.example` is a template.

## Documentation

- Architecture guide: `doc/Project_Architecture_Guide.md`
- Project memory: `doc/Project_Memory.md`
- Commenting convention: `doc/Commenting_Convention.md`
- Design white paper: `doc/Development_White_Paper.md`
- Worklog: `doc/worklog/`
