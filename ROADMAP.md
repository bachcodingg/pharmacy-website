# Roadmap — Pharmacy Search

Rewritten 2026-09-18. Target: **~10,000 lines** of work the project actually
needs, over roughly 6–7 weeks.

This replaces the 20,000-line plan written earlier the same day. That plan was
not wrong, but four of its items have since shipped and the budget has halved,
which changes the sequencing rather than just shortening the list. What was cut
and why is at the bottom — on a smaller budget the cuts are the interesting
part, not the keeps.

Companion document: `NEXT-STEPS.txt` holds the detailed findings
(F-01..F-15, N-01..N-12) and the gotchas. This file is the sequencing plan on
top of it.

---

## Shipped since the 20,000-line plan

Four of that plan's Phase 1 and 2 items are done, which is why this one starts
somewhere else:

| Item | Where |
|---|---|
| Litestream WAL replication + a restore drill rehearsed in CI (F-13) | `c32bcf1` |
| Reviews restricted to verified purchasers (N-08) | `92bf470` |
| Structured JSON logs to stdout | `e5967c7` |
| vi/en locale layer across all eight shopper views (F-15) | `2be02fe` |

Two of those change what the rest of the roadmap should be, not just how long
it is. See "The decision that got easier".

---

## On the 10,000-line target

A line count is a size, not an outcome, and it is the one target that is
trivially gamed — verbose tests, generated boilerplate, a locale file with
4,000 one-word entries. Used as a **scope budget** it is fine: it says how much
to commit to before stopping to reassess. It is not a measure of progress. The
guardrails section is what keeps it honest.

## Baseline (2026-09-18)

| Area | Lines |
|---|---|
| `backend/app/` (18 modules) | 3,469 |
| `backend/tests/` (21 files) | 2,612 |
| `backend/eval/` + `build/` + `learning/` | 1,194 |
| `frontend/src/` (22 files + CSS) | 4,030 |
| Dockerfile, fly.toml, litestream.yml, entrypoint, scripts, CI | 440 |
| **Total (excl. crawler and data files)** | **11,745** |

+10,000 is therefore a little under double the current codebase. At a
sustainable, actually-reviewed pace of ~1,500 lines/week that is 6–7 weeks.

---

## The decision that got easier

The previous plan opened with "decide the data layer before writing 15,000
lines against `sqlite3`", and budgeted 2,000 lines for a repository layer plus
a Postgres-or-LiteFS migration. At 10,000 lines that item does not fit, and it
should not be squeezed in — a half-built abstraction over raw SQL is worse than
the raw SQL.

**Recommendation: commit to SQLite for this budget, and stop listing Postgres
as a goal.** Two things make that defensible now that were not true a week ago:

- The data is replicated. F-13 was the honest objection to a single SQLite
  file, and it is answered: WAL frames ship to object storage every second and
  the restore is rehearsed on every push rather than hoped for.
- Nothing in the 10,000 lines below needs a second writer. Payments, email,
  prescriptions and tracking are all low-write, and the `BEGIN IMMEDIATE` in
  `write_transaction()` already serialises the one path that oversells.

What you give up is zero-downtime deploys and horizontal scale. At one machine
serving one pharmacy's catalogue that is a real cost and not yet a pressing
one. Revisit when a second machine is genuinely needed, and write the ADR then,
with load numbers rather than in advance of them.

The other ordering constraint from the previous plan — i18n before the next 15
view files — is now satisfied. New views get `t()` from their first line.

---

## Phase 1 — Make it a real shop (~3,400 lines, weeks 1–2)

The README currently has to admit that nothing is ever charged and that
password reset is not a working flow. Those are the two admissions in it a
customer would care about most.

| Item | LOC |
|---|---|
| Payments: provider abstraction, VNPay + Momo sandbox, HMAC request signing, IPN webhook with replay protection, refunds | 1,600 |
| Unified order state machine, folding `awaiting_prescription` into it | 600 |
| Transactional email: `outbox` table, retry worker, provider adapter (Resend/Postmark/SES), templates for order confirmation, prescription decision and password reset | 1,200 |

**Build the state machine once, here.** Payments and the prescription hold both
mutate order status, and `admin_orders.py` already carries a hand-written
transition table. Adding a payment status beside it leaves two parallel status
concepts in one schema, which is how orders end up in states nobody wrote down.

**Email is the unblocker, not a nicety.** Password reset currently records a
token that only an operator reading the database can retrieve. That is the
correct failure mode, and it is still not a reset flow. Everything about
account recovery and order communication sits behind these 1,200 lines.

**Exit gate:** an order can be paid in sandbox and refunded, both transitions
land in `admin_audit_log`, and a password reset completes end to end without
anyone opening the database.

---

## Phase 2 — Close the security and search gaps (~2,300 lines, weeks 3–4)

| Item | LOC |
|---|---|
| httpOnly / Secure / SameSite=Lax cookie sessions + CSRF on state-changing requests (F-04) | 900 |
| FTS5 over `search_text`, replacing the `LIKE '%term%'` scan (F-07b) | 500 |
| Corrector: finish F-08, under the 50 ms budget | 500 |
| Session-linked query logs, so correction precision becomes computable | 400 |

**F-04 is defence in depth, not an open hole.** The frontend escapes
consistently across all 15 view files and there is no known injection path. Say
that in the PR — a security change described as fixing a vulnerability that
does not exist teaches the next reader the wrong thing.

**F-07b is the honest fix for the indexes already added.** `idx_products_*`
cannot serve a leading-wildcard `LIKE`, so today's indexes help every query
except the search one. Note the gotcha: the FTS table needs triggers to stay in
sync, and `SEARCH_TEXT_FOLD_VERSION` has to be bumped if folding changes.

**F-08 is 500 lines now, not 1,000.** `NEXT-STEPS.txt` Task 2 has the profile
and three prototyped changes, and the measured gap is 71 ms against a 50 ms
budget — 1.5x, not the 10x the original 1,349 ms figure implied. The audit's
suggested SymSpell deletion index is explicitly the wrong tool for this metric:
0.5-cost adjacent substitutions mean a weighted cap of 3.0 admits six
operations, so a lossless deletion index needs depth 6.

**Watch for the XPASS.** When the corrector gets under budget,
`tests/test_core.py::test_correction_latency_budget` will pass — and because it
is `strict=True`, an unexpected pass **fails the suite**. That is the design
working. Convert it to a normal assertion at that moment and say so.

**Exit gate:** `eval/held_out.py --full` top-1 still ≥ 0.912; `eval/latency.py`
p95 < 50 ms; suite green with the xfail converted.

---

## Phase 3 — The pharmacy-specific surface (~2,900 lines, weeks 5–6)

This is the part that is a pharmacy rather than a generic storefront, and where
the project's premise pays off.

| Item | LOC |
|---|---|
| Pharmacist prescription review console: queue, approve/reject with reason, document upload to object storage, audit trail | 1,200 |
| Drug interaction checker + ingredient / ATC index, warning at cart and checkout | 1,100 |
| Order tracking: shipment states, carrier reference, customer-facing timeline and notifications | 600 |

**The review console is the highest-value item on this page.** 389 of the 1,894
products are prescription-only and the backend gate already exists — orders are
held in `awaiting_prescription` and only a pharmacist can release them. What
does not exist is a usable screen for the pharmacist doing it. The policy is
enforced; the workflow is a JSON API call.

**The interaction checker is the one item with real clinical risk.** It gives
advice about medicines. Scope it narrowly: warn and require acknowledgement,
never silently block, always name the source of the interaction data, and keep
a pharmacist in the loop for anything it flags. A wrong warning that trains
users to dismiss warnings is worse than no checker. Settle the data licensing
question before writing the code.

---

## Phase 4 — Reach and proof (~1,700 lines, week 7)

| Item | LOC |
|---|---|
| SEO: History-API routing with a server-side SPA fallback, per-product `<title>`/meta/Open Graph, Product JSON-LD, `sitemap.xml` (F-14) | 900 |
| Playwright E2E suite across the shopper flows, in both locales | 800 |

**F-14 has a comment to update.** `main.py` mounts the frontend with a comment
explaining that no path-based fallback is needed *because* the router is
hash-based. That comment becomes wrong the moment this ships.

**Run the E2E suite in both locales.** The i18n layer is new, and the failure
mode it introduces — a key that resolves in one language and falls through in
the other — is invisible to the unit tests and to a single-locale browser pass.

---

## Budget reconciliation

| Phase | LOC |
|---|---|
| 1 — Make it a real shop | 3,400 |
| 2 — Security and search gaps | 2,300 |
| 3 — Pharmacy-specific surface | 2,900 |
| 4 — Reach and proof | 1,700 |
| **Total** | **~10,300** |

Deliberately ~300 over. Phase 3's order tracking is the release valve.

Least certain estimate on this page: the 1,600 for payments. VNPay and Momo
sandbox work is mostly signing, callback verification and error-path handling,
and the error paths are where the estimate moves. Build one provider end to end
and re-estimate the second from the measured cost.

---

## Guardrails

These matter more than the schedule.

- **~30% of every budget above is tests.** A workstream shipping 1,200 lines
  with 80 lines of tests is not done. The backend ratio today is 2,612/3,469 —
  do not let it fall.
- **PR size cap: 400 lines.** One finding per commit, with the measurement in
  the message. It is the only thing that keeps 10,000 lines reviewable.
- **No new file over ~400 lines.** `corrector.py` at 886 is the current outlier
  and has earned it; do not grow a second one by accident.
- **The accuracy floor is permanent**, and it is now stated correctly:
  `eval/held_out.py --full` top-1 **≥ 0.912**, checked on every corrector
  change. The old floor of 0.930 came from a 500-case sample with a ±0.022
  interval — wide enough that two runs of identical code straddled it. Never
  compare a sampled run against a full one.
- **One ADR per workstream** (~100 lines each, counted separately from the code
  budget). Payments and the interaction-data source especially.
- **Fill `eval/human_typed.tsv`.** It is still a header row. Until it has real
  rows, 92.6% is a lower-bound proxy and not user-facing accuracy — and no
  amount of new code changes that. Ten people, 100 product names each, typed
  quickly. It is the cheapest item on this page and the only one that turns the
  headline number into a measurement of actual users.
- **Run `scripts/restore-drill.sh remote` once against the real bucket.** The
  CI drill uses a `file://` replica, which proves the mechanism and not the
  credentials. Until someone runs the remote form, backups are tested, not
  proven.

---

## Week 1, concretely

1. Write the payments ADR: the provider abstraction's shape, and what the order
   state machine's states are. Decide before the second provider, not after.
2. Build the state machine and convert `admin_orders.py` to it, keeping the
   suite green. No payment code yet — that conversion gives you the real cost.
3. Stand up the `outbox` table and the retry worker with a logging-only
   adapter. Wiring a real provider is then a config change, and password reset
   stops being a lie in the README a week earlier.

---

## Deliberately cut from the 20,000-line plan

Halving the budget means these do not happen. Worth being explicit rather than
quietly dropping them:

| Cut | LOC | Why this one |
|---|---|---|
| Data-access layer + Postgres/LiteFS migration | 2,000 | See "The decision that got easier". Backups answered the real objection. |
| Admin suppliers, purchase orders, reorder forecasting | 1,800 | Inventory management for a shop with no real stock source — `stock_is_estimated` is true for every row. Build the data source before the forecasting. |
| Loyalty points + rules-based promotions | 900 | Flat coupons already work. Retention mechanics before a working payment flow optimises a funnel nobody can complete. |
| Comparison, recently-viewed, recommendations | 1,000 | Needs traffic to be worth anything, and the click log that feeds it is thin. |
| Customer-facing returns and refunds | 800 | Refunds land in Phase 1 as an admin action. Self-service needs payments settled first. |
| Store locator / click-and-collect | 700 | One pharmacy. |
| Image pipeline off the Long Châu CDN (F-11) | 800 | Real, and a licensing question as much as an engineering one. The CSP already scopes the hotlink. |

Also still out of scope, deliberately:

- **N-07 user enumeration** via the 409 on register. A genuine tradeoff against
  registration UX, mitigated by rate limiting. Revisit alongside email
  verification in Phase 1, where the fix is nearly free.
- **Live payment-processor onboarding.** Phase 1 covers sandbox only. VNPay and
  Momo merchant approval is paperwork time, not code time, and does not belong
  in a line budget.
- **Translating the admin console.** A staff tool for one pharmacy; a
  half-translated screen is worse than a consistent one.
