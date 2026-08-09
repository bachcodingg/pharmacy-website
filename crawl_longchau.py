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


def extract_next_data_product(html):
    """Pull structured product data straight from the page's Next.js
    __NEXT_DATA__ payload - authoritative price/brand/prescription-flag/
    registration-number/specification, not scraped off rendered text. Not
    every page has it (or has price on it - some prescription items show
    no price at all), so every caller must handle a None return."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return None
    product = data.get("props", {}).get("pageProps", {}).get("product")
    if not product:
        return None

    prices = product.get("prices") or []
    default_price = next((p for p in prices if p.get("isSellDefault")), None) or (prices[0] if prices else None)

    primary_image = (product.get("primaryImage") or {}).get("url") or None
    secondary_images = [
        img.get("url") for img in (product.get("secondaryImages") or []) if img.get("url")
    ]

    return {
        "sourceSku": product.get("sku"),
        "brand": product.get("brand") or None,
        "prescription": product.get("prescription"),
        "registNum": product.get("registNum") or None,
        "specification": product.get("specification") or None,
        "price": default_price.get("price") if default_price else None,
        "priceUnit": default_price.get("measureUnitName") if default_price else None,
        "currency": (default_price.get("currencySymbol") if default_price else None) or "đ",
        "image": primary_image,
        "images": secondary_images,
    }


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
    next_data = extract_next_data_product(html) or {}

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
        "spec": next_data.get("specification") or extract_spec(tree),
        "regNo": next_data.get("registNum") or extract_reg_no(tree),
        "sourceSku": next_data.get("sourceSku"),
        "brand": next_data.get("brand"),
        "prescription": next_data.get("prescription"),
        "price": next_data.get("price"),
        "priceUnit": next_data.get("priceUnit"),
        "currency": next_data.get("currency"),
        "image": next_data.get("image"),
        "images": next_data.get("images") or [],
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


def reparse_cache():
    """Re-run parse_product() over every HTML file already sitting in raw/ -
    zero network requests. Use this after changing what parse_product()
    extracts (e.g. adding price) instead of re-crawling: the site was already
    fetched once, the new fields (price, brand, prescription, spec, regNo)
    were in that HTML all along, they just weren't being read yet."""
    files = sorted(f for f in os.listdir(RAW_DIR) if f.endswith(".html"))
    print(f"== Re-parsing {len(files)} cached pages from {RAW_DIR}/ (no network) ==")

    ok = fail = 0
    stats = {"desc": 0, "ing": 0, "spec": 0, "reg": 0, "price": 0, "brand": 0, "image": 0, "mismatch": 0}
    records = []

    for i, filename in enumerate(files, 1):
        path = os.path.join(RAW_DIR, filename)
        with open(path, encoding="utf-8") as f:
            html = f.read()

        url_match = re.search(r'"url":"(https://nhathuoclongchau\.com\.vn/[^"]+)"', html)
        url = url_match.group(1).replace("\\/", "/") if url_match else None
        if not url:
            fail += 1
            continue

        try:
            rec = parse_product(html, url)
        except Exception as e:
            print(f"  [parse loi] {filename}: {e}")
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
        if rec["price"] is not None:
            stats["price"] += 1
        if rec["brand"]:
            stats["brand"] += 1
        if rec["image"]:
            stats["image"] += 1
        if any(l["mismatch"] for l in rec["ingredientLinks"]):
            stats["mismatch"] += 1

        if i % PROGRESS_EVERY == 0 or i == len(files):
            print(f"[progress] {i}/{len(files)} ok={ok} fail={fail}")

    with open(OUT_FILE, "w", encoding="utf-8") as out:
        for rec in records:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\n== Xong: {ok} ok, {fail} loi -> {OUT_FILE} ==")
    if ok:
        for k, label in [("desc", "shortDescription"), ("ing", "ingredients"),
                         ("spec", "spec"), ("reg", "regNo"),
                         ("price", "price (real, from site)"), ("brand", "brand (real, from site)"),
                         ("image", "image (real, from site)")]:
            print(f"   co {label:26s}: {stats[k]:4d}/{ok} ({100 * stats[k] // ok}%)")
        print(f"   link text/slug lech  : {stats['mismatch']} san pham")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=CONCURRENCY,
                    help=f"so request dong thoi (default {CONCURRENCY})")
    ap.add_argument("--min-delay", type=float, default=0.0,
                    help="thoi gian cho truoc toi thieu giua cac request")
    ap.add_argument("--max-delay", type=float, default=0.15,
                    help="thoi gian cho truoc toi da giua cac request")
    ap.add_argument("--reparse-cache", action="store_true",
                    help="re-parse every cached raw/*.html file into products.jsonl, no network requests")
    args = ap.parse_args()

    if args.reparse_cache:
        reparse_cache()
        return

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
