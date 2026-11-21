# World Finals official-site correction

All 17 `ICPC > World Finals` rows in `raw/contests.csv` had an empty
`link.official` cell. The published catalog had the same gap. Each selected
page now has a matching ICPC edition year and is published by ICPC:

| Edition years | Selected site | Why selected |
| --- | --- | --- |
| 2025 | `https://worldfinals.icpc.global/2025/` | Baku event site |
| 2024 | `https://worldfinals.icpc.global/2024/` | Astana event site |
| 2023–2009 | `https://news.icpc.global/wf<year>/` | Year-specific ICPC News page with results and problem links |

The 2022 and 2023 World Finals were both held in Luxor in April 2024. Their
pages explicitly identify the distinct 46th and 47th editions, so the URLs
follow the edition year, not the date of the shared event.

The corrected CSV, source provenance, saved fetch requests, receipts, and
manifest retain the original frozen batch ID. All seven World Finals contests
currently in the live catalog were updated in place, preserving contest and
problem IDs. The other ten official links will be used when their rows can be
published after separate fetch/review issues are resolved. In particular,
the 2023 contest existed in the live catalog despite a blocked batch receipt;
its official link was updated by catalog category and year.

`python scripts/apply_world_finals_official.py --apply` reconciles the frozen
batch; `--publish` reconciles already live contests. Both steps are idempotent.
