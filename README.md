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
- `--username xxx --password yyy` override JoinQuant credentials
- `--window-start 13:00 --window-end 15:00` replay monitor window

## Notes on Backtest Logic

- Backtest uses minute-level `volume` proxy under one-word limit-down bars to estimate buy-flow.
- Trigger rule: `current_buy_volume > cumulative_buy_volume_before`.
- Cumulative scope is full day (from 09:30); trigger evaluation is only inside configured window.
- Report includes `data_quality=minute_proxy` and `confidence=low` to indicate proxy-based inference.

## Security Notes

- DingTalk robots can enforce keyword safety. Set `DINGTALK_KEYWORD` in `.env`.
- Optional EastMoney headers/cookie can be configured by `EM_HEADERS_JSON` and `EM_COOKIE`.
- Keep secrets only in `.env`; `.env.example` is a template.

## Documentation

- Architecture guide: `doc/Project_Architecture_Guide.md`
- Project memory: `doc/Project_Memory.md`
- Design white paper: `doc/Development_White_Paper.md`
- Worklog: `doc/worklog/`
