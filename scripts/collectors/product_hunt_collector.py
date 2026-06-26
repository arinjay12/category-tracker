"""
ProductHuntCollector — mines trending consumer app launches from Product Hunt.

Product Hunt is the strongest leading indicator for "what consumer apps are getting
traction in the US right now." Daily upvotes, comments, and featured products surface
the categories where consumer attention and early adoption are concentrating — typically
12-24 months before mainstream India adoption.

Exa-only. No Claude calls.
2 queries per picked category, max 6 per run.
"""
from __future__ import annotations
import hashlib
import time

from collectors.base_collector import BaseCollector
from utils.db import is_seen, mark_seen
from utils.signal_schema import RawSignal
from utils.tools import web_search
from utils.logger import get_logger
from utils.app_categories import CATEGORY_SEARCH_TERMS

logger = get_logger()

MAX_QUERIES_PER_RUN = 6


class ProductHuntCollector(BaseCollector):
    source_name = "product_hunt"

    def __init__(self, profile: dict | None = None, **kwargs):
        self.profile = profile or {}

    def fetch(self) -> list[RawSignal]:
        profile_cats = self.profile.get("categories", {})
        picked = [
            c for c, v in profile_cats.items()
            if isinstance(v, dict) and v.get("weight", 0) > 0
        ]
        if not picked:
            logger.info("[product_hunt] no picked categories — skipping")
            return []

        # 2 queries per category: recent launches + top-rated
        tasks: list[tuple[str, str]] = []
        for cat in picked:
            term = CATEGORY_SEARCH_TERMS.get(cat, cat.replace("_", " "))
            tasks.append((cat, f"site:producthunt.com {term} 2025 2026"))
            tasks.append((cat, f"site:producthunt.com {term} upvotes featured launched"))
            if len(tasks) >= MAX_QUERIES_PER_RUN:
                break

        signals: list[RawSignal] = []
        logger.info(f"[product_hunt] {len(tasks)} queries across {len(set(t[0] for t in tasks))} categories")

        for cat, query in tasks:
            try:
                results = web_search(query=query, num_results=6, days_back=180)
                for r in results:
                    if "error" in r or not r.get("url"):
                        continue
                    url = r["url"]
                    sig_id = hashlib.sha256(url.encode()).hexdigest()[:16]
                    if is_seen(self.source_name, sig_id):
                        continue
                    signals.append(RawSignal(
                        id=sig_id,
                        source=self.source_name,
                        title=r.get("title", ""),
                        body=r.get("snippet", "")[:2000],
                        url=url,
                        created_at=r.get("published_date", ""),
                        extra={
                            "category": cat,
                            "signal_type": "rising_brand_gap",
                            "platform": "product_hunt",
                        },
                    ))
                    mark_seen(self.source_name, sig_id)
            except Exception as e:
                logger.warning(f"[product_hunt] query failed for '{query[:60]}': {e}")
            time.sleep(0.3)

        return signals
