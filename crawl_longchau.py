#!/usr/bin/env python3

import argparse
import asyncio
import html as _html
import json
import os
import random
import re
import time
import unicodedata
from collections import Counter
from typing import Optional
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

try:
    import httpx
    HAS_HTTPX = True
    HAS_REQUESTS = True
except ImportError:
    HAS_HTTPX = False
    try:
        import requests as _requests
        HAS_REQUESTS = True
        print("[i] httpx khong co, dung requests + ThreadPool (van nhanh hon serial)")
    except ImportError:
        HAS_REQUESTS = False
        import urllib.request as _urllib
        import ssl as _ssl
        _CTX = _ssl.create_default_context()
        print("[i] httpx + requests khong co, dung urllib stdlib (slowest, no deps)")

try:
    from selectolax.parser import HTMLParser as _SelectolaxParser
    PARSER_BACKEND = "selectolax"
except ImportError:
    try:
        from bs4 import BeautifulSoup
        try:
            import lxml
            BS_PARSER = "lxml"
        except ImportError:
            BS_PARSER = "html.parser"
            print(f"[i] Khong co selectolax, dung BeautifulSoup + {BS_PARSER}")
        PARSER_BACKEND = "bs4"
    except ImportError:
        PARSER_BACKEND = "stdlib"
        from html.parser import HTMLParser as _StdHTMLParser
        print("[i] Khong co selectolax/bs4, dung html.parser stdlib (slow, no deps)")

        class _StdNode:
            __slots__ = ("tag", "attrs", "children", "_text_parts")
            def __init__(self, tag, attrs):
                self.tag = tag.lower() if tag else tag
                self.attrs = {k.lower(): (v if v is not None else "")
                              for k, v in (attrs or [])}
                self.children = []
                self._text_parts = []

            def _all_text(self, parts):
                parts.extend(self._text_parts)
                for c in self.children:
                    if isinstance(c, _StdNode):
                        c._all_text(parts)
                    else:
                        parts.append(c)

            def text(self, strip=False, separator="", deep=True):
                parts = []
                self._all_text(parts)
                s = separator.join(parts) if separator else "".join(parts)
                if strip:
                    s = s.strip()
                return s

            @property
            def attributes(self):
                return self.attrs

            @property
            def body(self):
                return self

            def css(self, selector):
                return list(self._iter_find(selector))

            def css_first(self, selector):
                for n in self._iter_find(selector):
                    return n
                return None

            def _iter_find(self, selector):
                sel = selector.strip()
                has_eq = re.fullmatch(r"([a-z0-9]+)\[([a-z0-9_-]+)=\"([^\"]+)\"\]", sel, re.I)
                has_attr = re.fullmatch(r"([a-z0-9]+)\[([a-z0-9_-]+)\]", sel, re.I)
                just_tag = re.fullmatch(r"[a-z0-9]+", sel, re.I)

                def match(node):
                    if node.tag is None:
                        return False
                    if has_eq:
                        tg, at, val = has_eq.groups()
                        return (node.tag == tg.lower()
                                and node.attrs.get(at.lower()) == val)
                    if has_attr:
                        tg, at = has_attr.groups()
                        return (node.tag == tg.lower()
                                and at.lower() in node.attrs
                                and node.attrs[at.lower()] != "")
                    if just_tag:
                        return node.tag == sel.lower()
                    return False

                stack = list(self.children)
                while stack:
                    n = stack.pop(0)
                    if isinstance(n, _StdNode):
                        if match(n):
                            yield n
                        stack[0:0] = n.children

        class _StdDOMBuilder(_StdHTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.root = _StdNode(None, [])
                self.stack = [self.root]

            def handle_starttag(self, tag, attrs):
                node = _StdNode(tag, attrs)
                self.stack[-1].children.append(node)
                if tag.lower() not in ("meta", "link", "img", "br", "hr",
                                       "input", "source"):
                    self.stack.append(node)

            def handle_endtag(self, tag):
                tagl = tag.lower()
                for i in range(len(self.stack) - 1, 0, -1):
                    if self.stack[i].tag == tagl:
                        self.stack = self.stack[:i]
                        break

            def handle_startendtag(self, tag, attrs):
                self.stack[-1].children.append(_StdNode(tag, attrs))

            def handle_data(self, data):
                if self.stack:
                    self.stack[-1]._text_parts.append(data)

        def _parse_stdlib(html: str):
            b = _StdDOMBuilder()
            b.feed(html)
            b.close()
            return b.root

_HTTP_EXECUTOR: ThreadPoolExecutor = None
_LOOP: asyncio.AbstractEventLoop = None


class _BSNode:
    """Adapter BeautifulSoup tag -> giao dien giong selectolax node."""
    def __init__(self, tag):
        self._tag = tag

    def css(self, selector):
        return [_BSNode(t) for t in self._tag.select(selector)]

    def css_first(self, selector):
        r = self._tag.select_one(selector)
        return _BSNode(r) if r else None

    def text(self, strip=False, separator="", deep=True):
        if separator:
            s = self._tag.get_text(separator=separator, strip=strip)
        else:
            s = self._tag.get_text(strip=strip)
        return s

    @property
    def attributes(self):
        return self._tag.attrs if self._tag is not None else {}

    @property
    def body(self):
        return self


def _make_parser(html: str):
    if PARSER_BACKEND == "selectolax":
        return _SelectolaxParser(html)
    soup = BeautifulSoup(html, BS_PARSER)
    return _BSNode(soup)


def _run_in_executor(func, *args):
    """Chay sync func trong thread pool de async-friendly."""
    global _HTTP_EXECUTOR, _LOOP
    if _HTTP_EXECUTOR is None:
        _HTTP_EXECUTOR = ThreadPoolExecutor(max_workers=CONCURRENCY + 2)
    _LOOP = asyncio.get_running_loop()
    return _LOOP.run_in_executor(_HTTP_EXECUTOR, lambda: func(*args))


class _RequestsResponse:
    def __init__(self, r):
        self._r = r

    @property
    def status_code(self):
        return self._r.status_code

    @property
    def text(self):
        return self._r.text


class _RequestsClient:
    """Giong httpx.AsyncClient nhung su dung requests trong thread pool."""
    def __init__(self, concurrency):
        self._session = _requests.Session()
        self._concurrency = concurrency

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._session.close()
        return False

    async def get(self, url, headers=None, timeout=None):
        def _do():
            return _RequestsResponse(
                self._session.get(url, headers=headers, timeout=timeout)
            )
        return await _run_in_executor(_do)


def _make_client(concurrency):
    if HAS_HTTPX:
        limits = httpx.Limits(max_connections=concurrency + 2,
                              max_keepalive_connections=concurrency)
        return httpx.AsyncClient(limits=limits, follow_redirects=True)
    if HAS_REQUESTS:
        return _RequestsClient(concurrency)
    return _UrllibClient(concurrency)


class _UrllibClient:
    """Backend cuoi cung - urllib stdlib (khong can cai gi)."""
    def __init__(self, concurrency):
        self._concurrency = concurrency

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None, timeout=None):
        def _do():
            req = _urllib.Request(url, headers=headers or {})
            try:
                with _urllib.urlopen(req, timeout=timeout, context=_CTX) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    return _UrllibResponse(resp.status, body)
            except _urllib.HTTPError as e:
                try:
                    body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    body = ""
                return _UrllibResponse(e.code, body)
        return await _run_in_executor(_do)


class _UrllibResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


class HTTPErrorWrapper(Exception):
    pass


def _http_err_cls():
    if HAS_HTTPX:
        return httpx.HTTPError
    if HAS_REQUESTS:
        return _requests.RequestException
    return Exception


def _make_parser(html: str):
    if PARSER_BACKEND == "selectolax":
        return _SelectolaxParser(html)
    if PARSER_BACKEND == "bs4":
        soup = BeautifulSoup(html, BS_PARSER)
        return _BSNode(soup)
    return _parse_stdlib(html)


def HTMLParser(*args, **kwargs):
    return _make_parser(*args, **kwargs)

BASE = "https://nhathuoclongchau.com.vn"
RAW_DIR = "raw"
OUT_FILE = "products.jsonl"
LEARNED_PAIRS_FILE = "learned_pairs.json"

CATEGORIES = [
    "thuoc",
    "thuc-pham-chuc-nang",
    "duoc-my-pham",
    "cham-soc-ca-nhan",
    "trang-thiet-bi-y-te",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9",
}

PRODUCT_RE = re.compile(r"^/(?:" + "|".join(CATEGORIES) + r")/[a-z0-9\-]+\.html$")
SUBCAT_RE = re.compile(r"^/(?:" + "|".join(CATEGORIES) + r")/[a-z0-9\-]+(?:/[a-z0-9\-]+)?$")

CONCURRENCY = 16
DEFAULT_DELAY_RANGE = (0.0, 0.15)
PROGRESS_EVERY = 25



def strip_accents(s):

    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("\u0111", "d").replace("\u0110", "D").lower()


def accent_fold(s):
    """Variant without diacritics for comparison/lookups."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.replace("\u0111", "d").replace("\u0110", "D").lower()


def normalize(s):
    """Normalize text for catalog indexing and query matching."""
    if not s:
        return ""
    s = _html.unescape(s)
    s = unicodedata.normalize("NFC", s)
    s = s.lower()
    s = re.sub(r"[^\w\s%.\-+]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def clean_text(s):
    """
    Giai ma HTML entity, chuan hoa Unicode, don khoang trang.
    """
    if not s:
        return None
    s = _html.unescape(s)
    s = unicodedata.normalize("NFC", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"([.,;:])(?=[^\s\d])", r"\1 ", s)
    return re.sub(r"\s+", " ", s).strip()


STOPWORDS = {
    "a", "an", "and", "bao", "cua", "cung", "cho", "co", "cac", "cac", "cua", "dung",
    "de", "duoc", "giup", "ho", "hon", "in", "la", "lien", "mot", "nao", "nhu", "nhung",
    "of", "phu", "sao", "thanh", "thay", "the", "thi", "to", "va", "voi", "xung", "cho"
}


def _tokenize(text):
    return [t for t in re.findall(r"[\w]+", text.lower()) if t]


def _extract_candidate_phrases(product):
    candidates = []

    if product.get("normalizedWebName"):
        tokens = _tokenize(product["normalizedWebName"])
        for n in range(1, 5):
            for i in range(len(tokens) - n + 1):
                phrase = " ".join(tokens[i:i+n])
                if len(phrase) < 2:
                    continue
                if any(w in STOPWORDS for w in phrase.split()):
                    continue
                candidates.append((phrase, "brand"))

    if product.get("normalizedShortDescription"):
        tokens = _tokenize(product["normalizedShortDescription"])
        for n in range(1, 5):
            for i in range(len(tokens) - n + 1):
                phrase = " ".join(tokens[i:i+n])
                if len(phrase) < 2:
                    continue
                if any(w in STOPWORDS for w in phrase.split()):
                    continue
                candidates.append((phrase, "symptom"))

    if product.get("normalizedIngredients"):
        tokens = _tokenize(product["normalizedIngredients"])
        for n in range(1, 5):
            for i in range(len(tokens) - n + 1):
                phrase = " ".join(tokens[i:i+n])
                if len(phrase) < 2:
                    continue
                if any(w in STOPWORDS for w in phrase.split()):
                    continue
                candidates.append((phrase, "ingredient"))

    for ing in product.get("ingredients", []):
        name = (ing or {}).get("name")
        if name:
            norm_name = normalize(name)
            if norm_name:
                candidates.append((norm_name, "ingredient"))

    return candidates


def extract_keywords(products, max_keywords=200):
    """Extract keyword phrases from products using a deterministic n-gram baseline."""
    counter = Counter()
    keyword_types = {}

    for product in products:
        for phrase, phrase_type in _extract_candidate_phrases(product):
            counter[phrase] += 1
            if phrase not in keyword_types or phrase_type == "ingredient":
                keyword_types[phrase] = phrase_type

    rows = []
    for phrase, count in counter.most_common(max_keywords):
        rows.append({
            "keyword": phrase,
            "type": keyword_types.get(phrase, "category"),
            "doc_freq": count,
            "popularity": count,
        })

    return rows


def _generate_basic_variants(keyword):
    variants = []
    if len(keyword) > 2:
        variants.append(keyword[1:])
        variants.append(keyword[:-1])
    for i in range(len(keyword)):
        if i + 1 < len(keyword):
            variants.append(keyword[:i] + keyword[i+1] + keyword[i+2:])
    return variants


def _generate_transposition_variants(keyword):
    variants = []
    for i in range(len(keyword) - 1):
        chars = list(keyword)
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
        variants.append("".join(chars))
    return variants


def _generate_phonetic_variants(keyword):
    variants = []
    replacements = [
        ("ph", "f"), ("th", "t"), ("ae", "e"), ("oe", "o"),
        ("oo", "u"), ("ou", "u"), ("qu", "q"), ("kh", "k"),
        ("gh", "g"), ("ng", "n"), ("nh", "n"), ("y", "i"),
    ]
    for src, dst in replacements:
        if src in keyword:
            variants.append(keyword.replace(src, dst))
    return variants


def _generate_typo_variants(keyword):
    variants = []
    for fn in (_generate_basic_variants, _generate_transposition_variants, _generate_phonetic_variants):
        for variant in fn(keyword):
            if variant and len(variant) >= 2 and variant not in variants:
                variants.append(variant)
    return variants


def generate_near_misses(keywords, max_variants=50):
    """Generate typo-like variants and mark ambiguous collisions."""
    mapping = {}
    for entry in keywords:
        keyword = entry["keyword"]
        for variant in _generate_typo_variants(keyword):
            mapping.setdefault(variant, []).append(keyword)

    rows = []
    for variant, hits in mapping.items():
        if not variant:
            continue
        is_ambiguous = len(hits) > 1
        rule = "basic_edit"
        if variant in _generate_transposition_variants(variant):
            rule = "transposition"
        elif variant in _generate_phonetic_variants(variant):
            rule = "phonetic"
        rows.append({
            "variant": variant,
            "keyword": hits[0],
            "rule": rule,
            "weight": 0.8 if len(variant) >= 4 else 0.6,
            "is_ambiguous": is_ambiguous,
        })

    return rows[:max_variants]


def build_lookup_table(rows):
    """Build an in-memory lookup table keyed by variant."""
    table = {}
    for row in rows:
        variant = row.get("variant")
        if not variant:
            continue
        table.setdefault(variant, []).append(row)
    return table


def lookup_variant(table, variant):
    """Return all candidates for a given variant, if any."""
    return table.get(variant, [])


def resolve_query(query, table, min_confidence=0.5):
    """Resolve a query against the lookup table using confidence-aware decision tiers."""
    normalized_query = normalize(query)
    if not normalized_query:
        return {"decision": "noop", "query": query}

    candidates = []
    seen_candidates = set()
    for variant in [normalized_query, accent_fold(normalized_query)] + _generate_typo_variants(normalized_query):
        if not variant:
            continue
        for row in lookup_variant(table, variant):
            key = (row.get("variant"), row.get("keyword"), row.get("rule"))
            if key in seen_candidates:
                continue
            seen_candidates.add(key)
            candidates.append(row)

    if not candidates:
        return {"decision": "noop", "query": normalized_query}

    scored_candidates = []
    for candidate in candidates:
        confidence = float(candidate.get("weight", 0.5))
        if candidate.get("variant") == normalized_query:
            confidence += 0.1
        if candidate.get("variant") == accent_fold(normalized_query):
            confidence += 0.05
        scored_candidates.append((confidence, candidate))

    scored_candidates.sort(key=lambda item: item[0], reverse=True)
    best_confidence, best = scored_candidates[0]
    top_candidates = [candidate for _, candidate in scored_candidates[:3]]

    if best.get("is_ambiguous"):
        return {
            "decision": "disambiguate",
            "query": normalized_query,
            "candidates": top_candidates,
            "confidence": round(best_confidence, 2),
        }

    if best_confidence < min_confidence:
        return {
            "decision": "review",
            "query": normalized_query,
            "suggestion": best.get("keyword"),
            "rule": best.get("rule"),
            "confidence": round(best_confidence, 2),
            "candidates": top_candidates,
        }

    return {
        "decision": "autocorrect",
        "query": normalized_query,
        "suggestion": best.get("keyword"),
        "rule": best.get("rule"),
        "weight": best.get("weight"),
        "confidence": round(best_confidence, 2),
    }


def save_learned_pairs(pairs, path=None):
    """Persist learned typo pairs to disk so they survive across runs."""
    target_path = path or LEARNED_PAIRS_FILE
    directory = os.path.dirname(target_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as handle:
        json.dump(pairs, handle, ensure_ascii=False, indent=2)
    return target_path


def load_learned_pairs(path=None):
    """Load persisted learned typo pairs, if available."""
    target_path = path or LEARNED_PAIRS_FILE
    if not os.path.exists(target_path):
        return []
    with open(target_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def learn_from_logs(logs, store_path=None):
    """Extract promising typo candidates from session logs for pharmacist review."""
    session_map = {}
    for entry in logs:
        session_map.setdefault(entry.get("session_id"), []).append(entry)

    pairs = []
    existing_pairs = load_learned_pairs(store_path)
    seen_pairs = {}
    for entry in existing_pairs:
        key = (entry.get("from_query"), entry.get("to_query"))
        seen_pairs[key] = entry

    for session_id, events in session_map.items():
        for i, first in enumerate(events[:-1]):
            for second in events[i+1:]:
                if first.get("query") == second.get("query"):
                    continue
                if not first.get("query") or not second.get("query"):
                    continue
                if (first.get("result_count", 0) == 0 or first.get("clicked") is False) and (
                    second.get("result_count", 0) > 0 or second.get("clicked") or second.get("added_to_cart")):
                    pair = {
                        "session_id": session_id,
                        "from_query": first.get("query"),
                        "to_query": second.get("query"),
                        "confidence": 1.0,
                    }
                    key = (pair["from_query"], pair["to_query"])
                    if key in seen_pairs:
                        existing = seen_pairs[key]
                        existing["confidence"] = max(existing.get("confidence", 0.0), pair["confidence"])
                        seen_pairs[key] = existing
                    else:
                        seen_pairs[key] = pair
                    break

    pairs = list(seen_pairs.values())
    save_learned_pairs(pairs, store_path)
    return pairs


def evaluate_corrections(gold, predictions):
    """Evaluate correction predictions against gold labels using precision and recall."""
    true_positive = 0
    for item in gold:
        query = item.get("query")
        target = item.get("target")
        match = next((p for p in predictions if p.get("query") == query), None)
        if match and match.get("prediction") == target:
            true_positive += 1

    precision = true_positive / max(len(predictions), 1)
    recall = true_positive / max(len(gold), 1)
    return {"precision": precision, "recall": recall, "true_positive": true_positive}


def meta(tree, prop):
    tag = tree.css_first(f'meta[property="{prop}"]') or tree.css_first(f'meta[name="{prop}"]')
    if not tag:
        return None
    content = tag.attributes.get("content")
    return content.strip() if content else None



_sem: asyncio.Semaphore = None
_DELAY_RANGE = DEFAULT_DELAY_RANGE


def set_sem(n):
    global _sem
    _sem = asyncio.Semaphore(n)


def set_delay(min_delay, max_delay):
    global _DELAY_RANGE
    if max_delay <= 0:
        _DELAY_RANGE = None
    else:
        _DELAY_RANGE = (min_delay, max_delay)


async def polite_get(client, url, tries=3):
    """async GET co delay + retry + semaphore. Ton trong server."""
    async with _sem:
        for attempt in range(tries):
            if _DELAY_RANGE is not None:
                await asyncio.sleep(random.uniform(*_DELAY_RANGE))
            try:
                r = await client.get(url, headers=HEADERS, timeout=25.0)
            except _http_err_cls() as e:
                print(f"  [loi mang] {e}")
                await asyncio.sleep(min(10.0, 2.0 * (attempt + 1)))
                continue

            if r.status_code == 200:
                return r
            if r.status_code in (429, 403):
                wait = min(10.0, 2.0 * (attempt + 1))
                print(f"  [{r.status_code}] bi chan, doi {wait:.1f}s")
                await asyncio.sleep(wait)
                continue
            print(f"  [{r.status_code}] bo qua {url}")
            return None
    return None



def _extract_links_from_html(html, seen, urls, limit):
    """
    Tach product URL + subcat URL tu HTML.
    Tra ve (so_sp_moi, [subcat_urls]).
    """
    tree = HTMLParser(html)
    found, subs = 0, []
    for a in tree.css("a[href]"):
        href = a.attributes.get("href", "")
        if not href:
            continue
        path = href.split("?")[0].replace(BASE, "")

        if PRODUCT_RE.match(path):
            full = urljoin(BASE, href)
            if full not in seen:
                seen.add(full)
                urls.append(full)
                found += 1
                if len(urls) >= limit:
                    break
        elif SUBCAT_RE.match(path) and not path.endswith(".html"):
            subs.append(urljoin(BASE, path))
    return found, subs


async def harvest(client, page_url, seen, urls, limit):
    r = await polite_get(client, page_url)
    if not r:
        return 0, []
    return _extract_links_from_html(r.text, seen, urls, limit)


async def collect_product_urls(client, limit):
    """
    Duyet sitemap truoc, sau do danh muc con XOAY VONG.
    Gi logic v2 nhung fetch concurrent.
    """
    urls, seen = [], set()

    r = await polite_get(client, f"{BASE}/sitemap.xml")
    if r and "<loc>" in r.text:
        for loc in re.findall(r"<loc>(.*?)</loc>", r.text):
            if PRODUCT_RE.match(loc.replace(BASE, "")) and loc not in seen:
                seen.add(loc)
                urls.append(loc)
                if len(urls) >= limit:
                    return urls
        print(f"[i] Sitemap cho {len(urls)} URL")

    print("[i] Duyet danh muc goc")
    queues: dict[str, list[str]] = {c: [] for c in CATEGORIES}
    visited_pages = set()

    tasks = []
    for cat in CATEGORIES:
        page = f"{BASE}/{cat}"
        visited_pages.add(page)
        tasks.append(harvest(client, page, seen, urls, limit))
    results = await asyncio.gather(*tasks)
    for cat, (n, subs) in zip(CATEGORIES, results):
        print(f"  {cat}: +{n} san pham, {len(subs)} danh muc con (tong {len(urls)})")
        queues[cat].extend(s for s in subs if s.startswith(f"{BASE}/{cat}/"))

    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        queues["thuoc"].append(f"{BASE}/thuoc/tra-cuu-thuoc-a-z?alphabet={ch}")

    total_q = sum(len(q) for q in queues.values())
    print(f"[i] Duyet {total_q} trang con (xoay vong + concurrent)")

    seen_q = set()
    while len(urls) < limit and any(queues.values()):
        batch_pages = []
        batch_cats = []
        for cat in CATEGORIES:
            if len(urls) >= limit:
                break
            while queues[cat]:
                page = queues[cat].pop(0)
                if page in visited_pages or page in seen_q:
                    continue
                batch_pages.append(page)
                batch_cats.append(cat)
                seen_q.add(page)
                break
        if not batch_pages:
            break

        tasks = [harvest(client, p, seen, urls, limit) for p in batch_pages]
        results = await asyncio.gather(*tasks)
        for cat, page, (n, subs) in zip(batch_cats, batch_pages, results):
            if n:
                label = page.replace(BASE, "")
                print(f"  [{cat[:9]:9s}] {label[:44]:44s} +{n:3d} (tong {len(urls)})")
            for sub in subs:
                if not sub.startswith(f"{BASE}/{cat}/"):
                    continue
                if sub not in visited_pages and sub not in seen_q:
                    queues[cat].append(sub)

    dist = Counter(u.replace(BASE + "/", "").split("/")[0] for u in urls[:limit])
    print("[i] Phan bo mau:", dict(dist))

    return urls[:limit]



def extract_ingredients(tree):
    text = tree.body.text(separator="\n", deep=True, strip=True)

    m = re.search(
        r"Thành phần\s*\n+((?:.|\n){10,1500}?)"
        r"\s*\n+(?:Xem tất cả|Công dụng|Chỉ định|Cách dùng)",
        text)
    raw = re.sub(r"\s+", " ", m.group(1)).strip() if m else None

    parsed = []
    if raw:
        body = re.sub(r"^.*?chứa\s*:\s*", "", raw)
        for part in body.split(","):
            part = part.strip()
            if not part:
                continue
            dm = re.search(r"\(([^)]*)\)", part)
            name = re.sub(r"\([^)]*\)", "", part).strip(" .;:")
            if name:
                parsed.append({
                    "name": clean_text(name),
                    "dose": dm.group(1).strip() if dm else None,
                })

    raw_lower = (raw or "").lower()
    linked, seen_slug = [], set()
    for a in tree.css("a[href]"):
        href = a.attributes.get("href", "")
        if "/thanh-phan/" not in href:
            continue
        txt = a.text(strip=True)
        slug = href.rstrip("/").split("/")[-1]
        if not txt or slug in seen_slug:
            continue
        if txt.lower() not in raw_lower:
            continue
        seen_slug.add(slug)
        linked.append({
            "text": txt,
            "slug": slug,
            "mismatch": (strip_accents(slug).replace("-", "")
                         != strip_accents(txt).replace(" ", "")),
        })

    return parsed, linked, raw


def extract_spec(tree):
    text = tree.body.text(separator="\n", deep=True, strip=True)
    m = re.search(r"Quy cách\s*\n+(.{3,120}?)\s*\n+(?:Thành phần|Công dụng)",
                  text, re.S)
    return clean_text(m.group(1)) if m else None


def extract_reg_no(tree):
    text = tree.body.text(separator="\n", deep=True, strip=True)
    m = re.search(r"Số đăng ký\s*\n+([A-Z0-9\-\./]{4,40})", text)
    return m.group(1).strip() if m else None


def parse_product(html, url):
    tree = HTMLParser(html)

    h1 = tree.css_first("h1")
    web_name = h1.text(strip=True) if h1 else meta(tree, "og:title")
    if not web_name:
        return None

    ing_parsed, ing_linked, ing_raw = extract_ingredients(tree)

    short_description = clean_text(meta(tree, "og:description")
                                   or meta(tree, "description"))
    ingredient_text = " ".join(i["name"] for i in ing_parsed if i.get("name"))

    return {
        "source": "longchau",
        "url": url,
        "category": url.replace(BASE + "/", "").split("/")[0],
        "webName": clean_text(web_name),
        "shortDescription": short_description,
        "ingredients": ing_parsed,
        "ingredientLinks": ing_linked,
        "ingredientRaw": ing_raw,
        "spec": extract_spec(tree),
        "regNo": extract_reg_no(tree),
        "normalizedWebName": normalize(clean_text(web_name) or ""),
        "normalizedShortDescription": normalize(short_description or ""),
        "normalizedIngredients": normalize(ingredient_text),
        "accentFoldedWebName": accent_fold(clean_text(web_name) or ""),
        "crawledAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }



async def fetch_product(client, url):
    """Tra ve (url, html_text hoac None). Cache tren dia."""
    slug = url.rstrip("/").split("/")[-1].replace(".html", "")
    raw_path = os.path.join(RAW_DIR, slug + ".html")

    if os.path.exists(raw_path):
        with open(raw_path, encoding="utf-8") as f:
            return url, f.read()

    r = await polite_get(client, url)
    if not r:
        return url, None
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(r.text)
    return url, r.text


def load_cached_products(limit=None):
    """Doc san pham tu products.jsonl neu da co; dung cho replay nhanh."""
    if not os.path.exists(OUT_FILE):
        return []
    rows = []
    with open(OUT_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
            if limit and len(rows) >= limit:
                break
    return rows


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=CONCURRENCY,
                    help=f"so request dong thoi (default {CONCURRENCY})")
    ap.add_argument("--min-delay", type=float, default=0.0,
                    help="thoi gian cho truoc toi thieu giua cac request")
    ap.add_argument("--max-delay", type=float, default=0.15,
                    help="thoi gian cho truoc toi da giua cac request")
    args = ap.parse_args()

    os.makedirs(RAW_DIR, exist_ok=True)
    set_delay(args.min_delay, args.max_delay)
    set_sem(args.concurrency)

    async with _make_client(args.concurrency) as client:
        print(f"== Gom URL (muc tieu {args.limit}, concurrency={args.concurrency}) ==")
        t0 = time.time()
        urls = await collect_product_urls(client, args.limit)
        print(f"== Duoc {len(urls)} URL  ({time.time() - t0:.1f}s) ==\n")

        print(f"== Fetch + parse {len(urls)} san pham ==")
        t1 = time.time()
        tasks = [fetch_product(client, u) for u in urls]
        html_results = await asyncio.gather(*tasks)

        ok = fail = 0
        stats = {"desc": 0, "ing": 0, "spec": 0, "reg": 0, "mismatch": 0}
        records = []

        for i, (url, html) in enumerate(html_results, 1):
            if not html:
                fail += 1
                continue
            try:
                rec = parse_product(html, url)
            except Exception as e:
                print(f"  [parse loi] {url}: {e}")
                fail += 1
                continue
            if not rec:
                fail += 1
                continue

            records.append(rec)
            ok += 1
            if rec["shortDescription"]:
                stats["desc"] += 1
            if rec["ingredients"]:
                stats["ing"] += 1
            if rec["spec"]:
                stats["spec"] += 1
            if rec["regNo"]:
                stats["reg"] += 1
            if any(l["mismatch"] for l in rec["ingredientLinks"]):
                stats["mismatch"] += 1

            if i % PROGRESS_EVERY == 0 or i == len(urls):
                print(f"[progress] {i}/{len(urls)} ok={ok} fail={fail}")

        with open(OUT_FILE, "w", encoding="utf-8") as out:
            for rec in records:
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    dt = time.time() - t1
    print(f"\n== Xong: {ok} ok, {fail} loi -> {OUT_FILE}  ({dt:.1f}s, "
          f"{ok / max(dt, 0.001):.1f} rec/s) ==")
    if ok:
        for k, label in [("desc", "shortDescription"), ("ing", "ingredients"),
                         ("spec", "spec"), ("reg", "regNo")]:
            print(f"   co {label:18s}: {stats[k]:4d}/{ok} "
                  f"({100 * stats[k] // ok}%)")
        print(f"   link text/slug lech  : {stats['mismatch']} san pham")


if __name__ == "__main__":
    asyncio.run(main())
