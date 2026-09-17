# Roadmap — Pharmacy Search

Written 2026-09-18. Target: grow the codebase by ~20,000 lines of work that the
project actually needs, over roughly 11–14 weeks.

Companion document: `NEXT-STEPS.txt` holds the detailed findings (F-01..F-15,
N-01..N-12) and the gotchas. This file is the sequencing plan built on top of
it. Where the two disagree about tree state, this file is newer.

> **Note on `NEXT-STEPS.txt`:** it opens with "NOTHING IS COMMITTED", which is
> no longer true — that work landed in `3eb5346` / `d68e821`. Its backlog
> (Task 4) is still accurate and is the basis for everything below.

---

## On the 20,000-line target

A line count is a size, not an outcome, and it is the one target that is
trivially gamed — verbose tests, generated boilerplate, a locale file with
4,000 one-word entries. Used as a **scope budget** it is fine: it says how much
work to commit to before stopping to reassess. It is not a measure of progress.
The guardrails section exists to keep it honest.

---

## Baseline (2026-09-18)

| Area | Lines |
|---|---|
| `backend/app/` (17 modules) | 3,263 |
| `backend/tests/` (19 files) | 2,174 |
| `backend/eval/` + `build/` | 917 |
| `frontend/src/` (21 files + CSS) | 3,413 |
| **Total (excl. crawler + data files)** | **~9,770** |

+20,000 is therefore **3x the current codebase**. At a sustainable,
actually-reviewed pace of ~1,500–2,000 lines/week that is 11–14 weeks.

Backlog items confirmed still outstanding as of this date:

- No FTS5 anywhere; `catalog.py:61` still uses a `LIKE` scan with leading wildcards.
- No httpOnly cookie or CSRF handling in `backend/app/`.
- No i18n layer; the only locale-aware code is two `toLocaleString` calls.
- Payments stubbed at `checkout.py:30` (`available: False`).

---

## The two ordering decisions that make or break this

Everything else is negotiable. These two are not, because getting them wrong
means rewriting thousands of lines you have already written.

### 1. Decide the data layer before writing 15,000 lines against `sqlite3`

Every module today calls `get_connection()` and writes raw SQL. Add 15k lines
of features first and then do F-12b (Postgres / LiteFS), and you touch every
one of those lines a second time. Either commit to SQLite permanently and stop
listing Postgres as a goal, or introduce the repository/query layer in Phase 1
while there are only 17 modules to convert.

### 2. Do i18n before writing the next 15 view files

F-15 means extracting strings from 21 existing frontend files. Build
comparison, tracking, returns and loyalty views first and it becomes 36 files
to extract from — and every new string gets written twice.

---

## Phase 1 — Foundations (~4,700 lines, weeks 1–3)

Nothing user-visible ships in this phase. That is the point: these are the
lines that make the other 15,000 cheap.

| Item | LOC | Why first |
|---|---|---|
| Data-access layer + Postgres-or-LiteFS decision (F-12b) | 2,000 | Blocks everything below |
| i18n scaffolding + vi-VN extraction of the existing 21 views (F-15) | 1,800 | Blocks all new UI |
| FTS5 over `search_text`, replacing the `LIKE` scan (F-07b) | 500 | Blocks search work; also the honest fix for indexes that a leading-wildcard `LIKE` can never use |
| Structured JSON logging + Sentry + Litestream backups (F-13) | 400 | One `fly volumes destroy` from total data loss |

**Exit gate:** full suite green; `eval/held_out.py` top-1 still >= 0.930;
restore-from-backup rehearsed into staging at least once.

---

## Phase 2 — Correctness and trust (~5,600 lines, weeks 4–6)

| Item | LOC |
|---|---|
| httpOnly / Secure / SameSite cookie sessions + CSRF (F-04) | 900 |
| Email verification + transactional email (outbox table, worker, templates) | 1,300 |
| VNPay/Momo sandbox: provider abstraction, HMAC signing, IPN webhook, refunds, order state machine | 2,200 |
| SEO: History-API router, server SPA fallback, per-product meta/OG, Product JSON-LD, `sitemap.xml` (F-14) | 1,200 |

**Dependency worth naming:** the payments state machine and the
prescription-hold flow both mutate order status. Build the state machine once,
here, and fold `awaiting_prescription` into it rather than leaving two parallel
status concepts in the schema.

---

## Phase 3 — Product surface (~8,400 lines, weeks 7–11)

Most of the line count lives here, and this is the part most specific to a
pharmacy rather than a generic storefront.

| Item | LOC |
|---|---|
| Pharmacist prescription review console (queue, approve/reject, upload, audit) | 1,200 |
| Drug interaction checker + ingredient / ATC index | 1,100 |
| Admin: suppliers, purchase orders, reorder forecasting, CSV import/export | 1,800 |
| Order tracking, shipment states, customer notifications | 900 |
| Returns and refunds | 800 |
| Loyalty points + rules-based promotions (beyond flat coupons) | 900 |
| Comparison, recently-viewed, "bought together" recommendations | 1,000 |
| Store locator / click-and-collect | 700 |

---

## Phase 4 — Search quality and hardening (~3,200 lines, weeks 12–14)

| Item | LOC |
|---|---|
| SymSpell deletion index + LRU cache (NEXT-STEPS Task 2), closing the 50 ms budget | 1,000 |
| Session-linked query logs so correction precision becomes computable; expanded harness | 500 |
| Playwright E2E suite + CI matrix | 900 |
| Image pipeline: mirror off the Long Chau CDN, WebP/AVIF, srcset, tighten CSP (F-11) | 800 |

When the corrector finally gets fast enough,
`tests/test_core.py::test_correction_latency_budget` will XPASS — and because
it is `strict=True`, that **fails the suite**. This is the design working, not
a break. Convert it to a normal passing assertion at that moment and say so in
the commit message.

---

## Budget reconciliation

| Phase | LOC |
|---|---|
| 1 — Foundations | 4,700 |
| 2 — Correctness and trust | 5,600 |
| 3 — Product surface | 8,400 |
| 4 — Search quality and hardening | 3,200 |
| **Total** | **~21,900** |

That is deliberately ~2,000 over target. Phase 3 is the release valve: cut
store locator and comparison first if the count lands at 20,000 early.

Least certain estimate on this page: the 2,000 for the data layer. It could
double depending on how much raw SQL resists abstraction. Convert `catalog.py`
first and re-estimate from the measured cost.

---

## Guardrails

These matter more than the schedule. Without them, 20,000 lines is a liability.

- **~30% of every budget above is tests.** A workstream that ships 1,200 lines
  with 80 lines of tests is not done. The backend ratio today is 2,174/3,263 —
  do not let it fall.
- **PR size cap: 400 lines.** `NEXT-STEPS.txt` Task 3 already got this right —
  nine independent commits, not one squash. That discipline is the only thing
  that keeps 20,000 lines reviewable.
- **No new file over ~400 lines.** `corrector.py` at 825 is the current outlier
  and it has earned it; do not grow a second one by accident.
- **The accuracy floor is permanent:** `top1_accuracy >= 0.930` and
  `no_candidates_rate <= 0.040`, checked on every corrector change. The session
  that wrote `NEXT-STEPS.txt` lost 0.930 -> 0.926 to a "cleaner" bound that was
  simply wrong. This gate is what catches that.
- **One ADR per workstream** (~100 lines each; docs, counted separately from
  the code budget). The Postgres-vs-LiteFS decision especially.
- **Fill `eval/human_typed.tsv`.** It is still a header row. Until it has real
  rows, 92.6% is a lower-bound proxy and not user-facing accuracy — and no
  amount of new code changes that.

---

## Week 1, concretely

1. Correct or retire the stale parts of `NEXT-STEPS.txt`. A handoff document
   that is wrong about tree state is worse than no document.
2. Write the data-layer ADR. Postgres or LiteFS — decide, do not defer.
3. Build the repository layer against the existing schema; convert `catalog.py`
   and `db.py` only; keep the suite green. That one conversion gives you the
   real per-module cost for the other 15.

---

## Out of scope

Deliberately not on this roadmap:

- **N-07 user enumeration** via the 409 on register. A genuine tradeoff against
  registration UX, mitigated by rate limiting. Revisit only alongside email
  verification in Phase 2.
- **Real payment-processor onboarding.** Phase 2 covers sandbox integration
  only. Live VNPay/Momo merchant approval is paperwork time, not code time, and
  does not belong in a line budget.
