import json
import math
import re
import time
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional


PROTECTED_TOKENS = {"viên", "vỉ", "hộp", "ống", "gói", "vien", "vi", "goi", "ong", "hop"}
THRESHOLD = 0.75
MARGIN = 0.15


def normalize(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s)
    s = s.lower()
    s = re.sub(r"[^\w%.\-+]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def strip_accents(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


def is_protected(token: str) -> bool:
    token = normalize(token)
    if not token:
        return False
    if re.fullmatch(r"\d+", token):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?%", token):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?ml", token):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?mg", token):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?mcg", token):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?g", token):
        return True
    if token in PROTECTED_TOKENS:
        return True
    return False


class Corrector:
    def __init__(self, keywords_path, nearmiss_path, products_path=None):
        self.keywords_path = Path(keywords_path)
        self.nearmiss_path = Path(nearmiss_path)
        self.products_path = Path(products_path) if products_path else None
        self.keywords = self._load_json(self.keywords_path)
        self.nearmiss = self._load_json(self.nearmiss_path)
        self.products = self._load_products(self.products_path) if self.products_path else []

    def _load_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _load_products(self, path: Path) -> List[dict]:
        if not path.exists():
            return []
        rows = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def correct_token(self, tok: str) -> dict:
        token = normalize(tok)
        if not token:
            return {"status": "unknown", "token": tok, "candidates": []}
        if is_protected(token):
            return {"status": "protected", "token": token, "candidates": []}
        if token in self.keywords:
            return {"status": "exact", "token": token, "candidates": [{"keyword": token, "score": 1.0, "rule": "exact"}]}

        variant_entry = self.nearmiss.get(token)
        if not variant_entry:
            return {"status": "unknown", "token": token, "candidates": []}
        matches = variant_entry.get("c", [])
        is_ambiguous = bool(variant_entry.get("amb"))
        if not matches:
            return {"status": "unknown", "token": token, "candidates": []}

        best_by_keyword = {}
        for item in matches:
            keyword = item.get("keyword")
            if not keyword:
                continue
            if keyword in self.keywords:
                popularity = float(self.keywords[keyword].get("popularity", 1))
                max_pop = max((float(v.get("popularity", 1)) for v in self.keywords.values()), default=1.0)
                weight = float(item.get("weight", 0.5))
                score = weight * (1 + math.log(1 + popularity) / math.log(1 + max_pop))
                candidate = {
                    "keyword": keyword,
                    "score": round(score, 3),
                    "rule": item.get("rule", "unknown"),
                    "sample": self.keywords[keyword].get("sample", ""),
                }
                current = best_by_keyword.get(keyword)
                if current is None or candidate["score"] > current["score"]:
                    best_by_keyword[keyword] = candidate

        scored = list(best_by_keyword.values())
        scored.sort(key=lambda item: item["score"], reverse=True)
        if not scored:
            return {"status": "unknown", "token": token, "candidates": []}

        if is_ambiguous:
            return {"status": "ambiguous", "token": token, "candidates": scored[:3]}

        top = scored[0]
        second = scored[1] if len(scored) > 1 else None
        if top["score"] >= THRESHOLD and (second is None or top["score"] - second["score"] >= MARGIN):
            return {"status": "corrected", "token": token, "candidates": scored[:3], "suggestion": top["keyword"]}
        return {"status": "did_you_mean", "token": token, "candidates": scored[:3]}

    def suggest(self, prefix: str, limit: int = 10) -> list:
        prefix = normalize(prefix)
        if not prefix:
            return []
        matches = []
        for keyword, meta in self.keywords.items():
            if keyword.startswith(prefix):
                matches.append({"keyword": keyword, "popularity": meta.get("popularity", 0)})
        matches.sort(key=lambda item: item["popularity"], reverse=True)
        return matches[:limit]

    def find_products(self, query: str, limit: int = 10) -> list:
        terms = normalize(query).split()
        if not terms:
            return []
        results = []
        for product in self.products:
            name_norm = normalize(product.get("webName", ""))
            if all(term in name_norm for term in terms):
                results.append({"webName": product.get("webName"), "category": product.get("category")})
                if len(results) >= limit:
                    break
        return results

    def correct(self, query: str) -> dict:
        start = time.perf_counter()
        result = self._correct(query)
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)
        return result

    def _correct(self, query: str) -> dict:
        normalized = normalize(query)
        tokens = normalized.split()
        if not tokens:
            return {"decision": "no_results", "query": query, "tokens": []}

        token_results = [self.correct_token(token) for token in tokens]
        statuses = {r["status"] for r in token_results}

        if "ambiguous" in statuses:
            ambiguous_token = next(r for r in token_results if r["status"] == "ambiguous")
            return {
                "decision": "did_you_mean",
                "query": query,
                "candidates": ambiguous_token["candidates"],
                "tokens": token_results,
            }

        if "corrected" in statuses:
            rebuilt = [r.get("suggestion", r["token"]) for r in token_results]
            return {
                "decision": "auto_correct",
                "query": query,
                "suggestion": " ".join(rebuilt),
                "tokens": token_results,
            }

        if "did_you_mean" in statuses:
            dym_token = next(r for r in token_results if r["status"] == "did_you_mean")
            return {
                "decision": "did_you_mean",
                "query": query,
                "candidates": dym_token["candidates"],
                "tokens": token_results,
            }

        if all(r["status"] in ("protected", "exact") for r in token_results):
            return {"decision": "no_change", "query": query, "tokens": token_results}

        return {"decision": "no_results", "query": query, "tokens": token_results}
