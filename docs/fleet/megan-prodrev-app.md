# megan-prodrev-app: (DRAFT) NA Product Revenue (Megan) as its own Streamlit app

Approval: Maya, Cowork chat 2026-11-10 ("can you make Meghan's a new streamlit app").
Why: Dan Chen wants the drill for his biweekly with Glenn, Wed 2026-11-18 (Slack C0C5ECTA76J 2026-11-09 13:37). Scope NASE only (Dan, 2026-11-05).
Base: coco/cfd-rename-sga-sub @ dbe4767 (live Consolidated Financials code). Product Revenue code taken from coco/cfd-prodrev-na @ 95028c2.

## What is in the app
- `product_revenue_app.py`: page config "(DRAFT) NA Product Revenue" (wide), one DRAFT header line, then `product_revenue.render()`. Nothing else.
- `product_revenue.py`: copied unchanged from coco/cfd-prodrev-na (SQL unchanged; FY27 caption at :152 unchanged: "FY27 is $157M below Megan's file; under review with Megan.").
- `docs/fleet/cfd-prodrev-na.md`: copied unchanged (tie-out record).

## Entity (snowflake.yml, added at the end of `entities:`)
`product_revenue_dash` -> ORACLE_DATA_PROD.SANDBOX.PRODUCT_REVENUE_DASH, title "(DRAFT) NA Product Revenue (Megan)", main_file product_revenue_app.py. Stage/runtime/compute pool/EAI/warehouse copied from `collectibles_financial_dash`.
Artifacts: product_revenue_app.py, product_revenue.py, data.py, queries.py, pyproject.toml, .streamlit/config.toml.

## Claims
| Claim | Status | Evidence |
| --- | --- | --- |
| product_revenue.py imports only pandas, streamlit, data; calls only `data._q` | CONFIRMED | grep: :18-21, :95 |
| `data._q` exists on this branch | CONFIRMED | data.py:123 |
| data.py imports only os, datetime, pandas, streamlit, queries; queries.py imports only os | CONFIRMED | grep |
| No missing function had to be copied | CONFIRMED | above |
| snowflake.yml has 3 entities; the 2 existing are unchanged | CONFIRMED | `grep -c "type: streamlit"` = 3; `git diff dbe4767 -- snowflake.yml` is additions only |
| Every artifact exists | CONFIRMED | `ls`; `python3 tools/preflight_artifacts.py`: "checked 35 artifact path(s) ... OK -- every artifact exists and every top-level module ships" (covers all 3 entities) |
| financial_app.py, streamlit_app.py, sga.py, data.py, queries.py unchanged vs dbe4767 | CONFIRMED | `git diff --stat dbe4767` lists only snowflake.yml |
| py_compile OK for product_revenue_app.py, product_revenue.py | CONFIRMED | python3 -m py_compile |
| FY26 NASE total = $4,086.9M (4,086,943,019.71) | CONFIRMED | read-only SUM over the FY26 part of PRODUCT_REVENUE_SQL (GMPLN_PRODUCT_RELEASE_BY_COA_MONTHLY_V, SEP26RF, FY26 unpivot) = 4,086,943,019.7081, query id 01c853b7-081a-79d9-69de-0701a6493c1f (self-check re-run: same value, 01c853b8-081a-6d2e-69de-0701a6499057); same as cfd-prodrev-na.md tie-out |
| The app renders correctly in Snowflake | I DON'T KNOW | AppTest not run (HARD RULE); not deployed (Maya ships) |
| Container runtime installs deps for this smaller app the same way | LIKELY | same pyproject.toml and runtime as collectibles_financial_dash |

## Open items
- FY27: Megan's placeholder "General" COAs drive most of the -$157.4M gap; PENDING - Megan Coleman: FY27 values for "General" COAs. Caption stays on screen.
- Charts: come in task cfd-prodrev-na-viz.
- Deploy: not done here; Maya publishes with the Ship buttons.
