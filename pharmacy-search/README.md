# Pharmacy Search

A Vietnamese typo-tolerant pharmacy catalogue: 1,894 crawled products, a
15,306-word lexicon, and a Telex/VNI-aware correction engine, wrapped in a
working shop (auth, cart, checkout, orders, prescriptions, admin).

Live: <https://pharmacy-search-giabach.fly.dev>

---

## What is actually interesting here

The shop is conventional. The **corrector** is not.

Vietnamese search breaks every assumption an English spell-checker makes. A
user looking for *bàn chải đánh răng* may type it accented, unaccented
(`ban chai danh rang`), in full Telex (`banf chair ddanhs rawng`), in VNI
(`ban2 chai3`), or — most often — half-finished, with tone keys dropped
wherever they got bored. Meanwhile half the catalogue is Latin drug names
where those same letters are real: `aspirin` must not lose its `s` to a
tone-key stripper.

`app/corrector.py` parses candidate tokens against a real Vietnamese syllable
grammar — onset, nucleus, coda drawn from three closed sets — so it can prove
`tranhs` is `tranh` plus a tone key while leaving `aspirin` untouched. Four
deliberate decisions sit around that:

- **Keyboard-adjacency edit distance.** A `c → v` substitution costs 0.5, not
  1.0, because they are neighbouring keys.
- **Precision over recall, enforced in code.** A fuzzy guess may only
  auto-apply at ≤ 1 edit (`FUZZY_AUTO_MAX_DIST`). Two edits is offered, never
  assumed — `panadol → panactol` is a different drug.
- **Phrase-first resolution.** Two thirds of the lexicon is multi-word, so a
  greedy longest-match runs before per-token correction. That is what
  separates *chống nắng* from *chóng nắng*.
- **A human-in-the-loop learning gate.** Query and click logs are mined for
  (failed query → clicked query) pairs, but nothing enters the live index
  without a pharmacist approving it.

Measured, not claimed: **92.6% top-1 / 93.6% top-3** on a held-out evaluation
where the index is built with two rule groups removed and then tested only on
variants those removed rules generate — so the score cannot be tautological.

---

## Running it

Requires Python 3.12+ and Node 20+.

```bash
git clone <this repo> && cd pharmacy-search

# --- backend ---
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# Build the search index. index/ is a derived artifact and is gitignored, so
# this has to run once before the app can serve corrections.
python build/build_lexicon.py
python build/build_nearmiss.py

# First start migrates the 1,894-product catalogue into SQLite automatically.
uvicorn app.main:app --reload --port 8000
```

```bash
# --- frontend (separate terminal) ---
cd frontend
npm ci
npm run dev        # Vite dev server, proxies /api to :8000
```

Then open the Vite URL. To run everything as one process the way production
does, `npm run build` and start uvicorn — `app/main.py` mounts
`frontend/dist` at `/` when it exists, so there is no CORS layer and no
separate static host.

Configuration is documented in [`.env.example`](.env.example); every path the
app writes to is overridable, and nothing but the defaults is required to run
locally.

```bash
# --- grant yourself admin ---
python build/promote_admin.py you@example.com
```

## Tests and evaluation

```bash
cd backend
python -m pytest tests -q          # 137 tests
python eval/evaluate.py            # held-out correction accuracy
python eval/latency.py             # latency percentiles
python eval/query_log.py           # zero-result rate from real traffic
```

The latency budget test is a `xfail(strict=True)` with a written reason: the
fuzzy fallback still scans the vocabulary per unknown token, so p95 is over
its 50 ms budget. It is carried as a failing test rather than a deleted one,
and the suite will flag the moment it is fixed.

## Architecture

```
backend/
  app/
    config.py       env-driven paths and limits — everything mutable is overridable
    corrector.py    the syllable grammar, Telex encoder, and correction engine
    db.py           schema, numbered migrations, indexes, write_transaction()
    ratelimit.py    in-process sliding-window limiter
    auth.py         PBKDF2 sessions, password reset, addresses
    catalog.py      product listing, facets, reviews, search_catalog()
    cart.py  checkout.py  wishlist.py  inventory.py
    admin_*.py      orders (incl. prescription review), users, coupons,
                    corrections, reports
  build/            lexicon + near-miss index builders, catalogue migration
  eval/             held-out evaluation, latency, query-log analysis
  learning/         log mining and the pharmacist approval gate
  tests/            137 tests
frontend/src/       vanilla JS, hash-router SPA, one view per file
```

**Storage.** SQLite on a single Fly volume at `/data`, holding the database,
the query/click logs and the pharmacist's approved correction pairs. One
machine; no horizontal scaling until this becomes Postgres or LiteFS.

**Prescriptions.** 389 of the 1,894 products are prescription-only. Those are
not blocked from the cart; they hold the *order*. Checkout requires a
prescription reference, the order is created in `awaiting_prescription`, and
only a pharmacist's approval (`PUT /api/admin/orders/{id}/prescription`) can
release it. Every decision is written to `admin_audit_log`.

**Honest labels.** `price_is_estimated`, `brand_is_estimated` and
`stock_is_estimated` mark values the crawl could not source. Stock has no real
source at all — the site's product JSON carries no quantity field.

## Known gaps

Deliberately listed rather than hidden:

- **Payments are not real.** Only cash-on-delivery completes an order. VNPay
  and Momo appear in the UI marked *not connected*; nothing is charged.
- **No transactional email.** Password resets record a token that only an
  operator reading the database can retrieve. That is the correct failure
  mode until a provider is wired up — it is not a working reset flow.
- **Search p95 is over budget** (F-08, above).
- **Sessions are bearer tokens in `localStorage`**, not httpOnly cookies. The
  frontend escapes consistently, so there is no known injection path, but the
  storage choice is still weaker than a cookie.
- **Hash-router SPA**, so product pages are not indexable and cannot be
  previewed when shared.
- **The UI is in English** while the catalogue and the entire premise are
  Vietnamese. It needs a `vi-VN` locale and proper `145.000 ₫` formatting.
- **No backups.** The volume is not replicated; Litestream is the next step.
- **Product images hotlink Long Châu's CDN** and would need mirroring and a
  licence before any commercial use.

## Licence

MIT — see [LICENSE](../LICENSE). The crawled catalogue and its images are
**not** covered by it.
