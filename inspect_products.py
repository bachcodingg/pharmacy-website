#!/usr/bin/env python3
"""
Crawler nha thuoc Long Chau - lay webName, shortDescription, ingredients.
KHONG lay gia.

v2 - sua cac loi phat hien tu 20 ban ghi dau:
  - ingredients: dung khoi "Thanh phan" lam nguon su that, tach ten + lieu luong.
    Link /thanh-phan/ chi giu neu ten co mat trong raw (loc nhieu tu muc Luu y).
  - clean_text: giai ma &nbsp;, chuan hoa NFC, tach chu bi dinh.
  - spec: doi sang regex tren text tho.
  - parser: tu chon lxml, khong co thi dung html.parser.

Cai dat:
    pip install requests beautifulsoup4 lxml

Chay:
    python crawl_longchau.py --limit 20      # thu truoc
    python crawl_longchau.py --limit 200     # roi scale
"""

import argparse
import html as _html
import json
import os
import random
import re
import time
import unicodedata
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    import lxml
    PARSER = "lxml"
except ImportError:
    PARSER = "html.parser"
    print("[i] Khong co lxml, dung html.parser (cham hon nhung van chay)")

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



def strip_accents(s):
    """Bo dau tieng Viet - dung de so sanh, KHONG dung de luu tru."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("\u0111", "d").replace("\u0110", "D").lower()


def clean_text(s):
    """
    Giai ma HTML entity, chuan hoa Unicode, don khoang trang.

    KHONG tach chu o ranh gioi thuong/HOA: quy tac do se pha hong ten
    thuong hieu viet lien nhu NutriGrow, LactoBiomin. Va khong the dung
    khoang ky tu kieu [a-zà-ỹ] cho tieng Viet - trong Unicode, chu hoa
    va chu thuong tieng Viet nam xen ke nhau trong cung khoang codepoint.
    """
    if not s:
        return None
    s = _html.unescape(s)
    s = unicodedata.normalize("NFC", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"([.,;:])(?=[^\s\d])", r"\1 ", s)
    return re.sub(r"\s+", " ", s).strip()


def polite_get(session, url, tries=3):
    """GET co delay + retry. Ton trong server, dung giam delay."""
    for attempt in range(tries):
        time.sleep(random.uniform(1.2, 2.2))
        try:
            r = session.get(url, headers=HEADERS, timeout=25)
        except requests.RequestException as e:
            print(f"  [loi mang] {e}")
            time.sleep(5 * (attempt + 1))
            continue

        if r.status_code == 200:
            return r
        if r.status_code in (429, 403):
            wait = 20 * (attempt + 1)
            print(f"  [{r.status_code}] bi chan, doi {wait}s")
            time.sleep(wait)
            continue
        print(f"  [{r.status_code}] bo qua {url}")
        return None
    return None


def meta(soup, prop):
    tag = (soup.find("meta", attrs={"property": prop})
           or soup.find("meta", attrs={"name": prop}))
    return tag["content"].strip() if tag and tag.get("content") else None



def collect_product_urls(session, limit):
    urls, seen = [], set()

    r = polite_get(session, f"{BASE}/sitemap.xml")
    if r and "<loc>" in r.text:
        print("[i] Tim thay sitemap")
        for loc in re.findall(r"<loc>(.*?)</loc>", r.text):
            path = loc.replace(BASE, "")
            if PRODUCT_RE.match(path) and loc not in seen:
                seen.add(loc)
                urls.append(loc)
                if len(urls) >= limit:
                    return urls
        if urls:
            print(f"[i] Sitemap cho {len(urls)} URL")
        else:
            print("[i] Sitemap khong co URL san pham (co le la sitemap index)")

    print("[i] Duyet trang danh muc")
    per_cat = max(1, limit // len(CATEGORIES) + 10)

    for cat in CATEGORIES:
        got, page = 0, 1
        while got < per_cat and len(urls) < limit and page <= 15:
            page_url = f"{BASE}/{cat}" + (f"?page={page}" if page > 1 else "")
            r = polite_get(session, page_url)
            if not r:
                break

            soup = BeautifulSoup(r.text, PARSER)
            found = 0
            for a in soup.find_all("a", href=True):
                path = a["href"].replace(BASE, "")
                if not PRODUCT_RE.match(path):
                    continue
                full = urljoin(BASE, a["href"])
                if full in seen:
                    continue
                seen.add(full)
                urls.append(full)
                got += 1
                found += 1
                if len(urls) >= limit:
                    break

            print(f"  {cat} p{page}: +{found} (tong {len(urls)})")
            if found == 0:
                break
            page += 1

    return urls[:limit]



def extract_ingredients(soup):
    """
    Tra ve (parsed, linked, raw).

    raw    : text tho cua khoi "Thanh phan" - NGUON SU THAT.
    parsed : [{"name": ..., "dose": ...}] tach tu raw.
             dose la lieu luong -> KHONG BAO GIO duoc sua chinh ta.
    linked : link /thanh-phan/ NHUNG chi giu neu ten co mat trong raw.
             Loc bo nhieu tu muc "Luu y" (vi du retinoid, resorcinol
             o trang Klenzit khong phai thanh phan that).
    """
    text = soup.get_text("\n", strip=True)

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
    for a in soup.find_all("a", href=True):
        if "/thanh-phan/" not in a["href"]:
            continue
        txt = a.get_text(strip=True)
        slug = a["href"].rstrip("/").split("/")[-1]
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


def extract_spec(soup):
    """Quy cach dong goi (Hop 3 Vi x 10 Vien) - KHONG duoc sua chinh ta."""
    text = soup.get_text("\n", strip=True)
    m = re.search(r"Quy cách\s*\n+(.{3,120}?)\s*\n+(?:Thành phần|Công dụng)",
                  text, re.S)
    return clean_text(m.group(1)) if m else None


def extract_reg_no(soup):
    """So dang ky - dinh danh chinh thuc, huu ich khi dedupe."""
    text = soup.get_text("\n", strip=True)
    m = re.search(r"Số đăng ký\s*\n+([A-Z0-9\-\./]{4,40})", text)
    return m.group(1).strip() if m else None


def parse_product(html, url):
    soup = BeautifulSoup(html, PARSER)

    h1 = soup.find("h1")
    web_name = h1.get_text(strip=True) if h1 else meta(soup, "og:title")
    if not web_name:
        return None

    ing_parsed, ing_linked, ing_raw = extract_ingredients(soup)

    return {
        "source": "longchau",
        "url": url,
        "category": url.replace(BASE + "/", "").split("/")[0],
        "webName": clean_text(web_name),
        "shortDescription": clean_text(meta(soup, "og:description")
                                       or meta(soup, "description")),
        "ingredients": ing_parsed,
        "ingredientLinks": ing_linked,
        "ingredientRaw": ing_raw,
        "spec": extract_spec(soup),
        "regNo": extract_reg_no(soup),
        "crawledAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    os.makedirs(RAW_DIR, exist_ok=True)
    session = requests.Session()

    print(f"== Gom URL (muc tieu {args.limit}) ==")
    urls = collect_product_urls(session, args.limit)
    print(f"== Duoc {len(urls)} URL ==\n")

    ok = fail = 0
    stats = {"desc": 0, "ing": 0, "spec": 0, "reg": 0, "mismatch": 0}

    with open(OUT_FILE, "w", encoding="utf-8") as out:
        for i, url in enumerate(urls, 1):
            slug = url.rstrip("/").split("/")[-1].replace(".html", "")
            raw_path = os.path.join(RAW_DIR, slug + ".html")

            if os.path.exists(raw_path):
                html = open(raw_path, encoding="utf-8").read()
            else:
                r = polite_get(session, url)
                if not r:
                    fail += 1
                    continue
                html = r.text
                with open(raw_path, "w", encoding="utf-8") as f:
                    f.write(html)

            rec = parse_product(html, url)
            if not rec:
                fail += 1
                continue

            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
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

            print(f"[{i}/{len(urls)}] {rec['webName'][:60]}")

    print(f"\n== Xong: {ok} ok, {fail} loi -> {OUT_FILE} ==")
    if ok:
        for k, label in [("desc", "shortDescription"), ("ing", "ingredients"),
                         ("spec", "spec"), ("reg", "regNo")]:
            print(f"   co {label:18s}: {stats[k]:4d}/{ok} "
                  f"({100 * stats[k] // ok}%)")
        print(f"   link text/slug lech  : {stats['mismatch']} san pham")
        print("\n=> Kiem tra bang mat: ingredients co khop ingredientRaw khong?")
        print("   Thuc pham chuc nang / thiet bi thuong khong co muc Thanh phan.")


if __name__ == "__main__":
    main()