# Forecast archive

Every forecast published at https://tokenfly.ai/snow/, written by the `forecast` workflow of the main
branch. `forecasts/YYYY/MM/DD/HHMMZ.jsonl.gz` holds one JSON row per (resort, ski day) for the resorts
refreshed in that run. `obs/YYYY/MM/YYYY-MM-DD.jsonl.gz` holds what the nearby SNOTEL stations measured
on that ski day. The row formats are documented in `pipeline/verify/archive.py` on `main`; read them
back with `pipeline.verify.archive.read_rows` and `read_obs`.
