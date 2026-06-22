"""
IndiaFundingCollector — mines recent India startup funding news per category.

Queries Inc42, YourStory, and Entrackr for recent funding rounds in each picked
category. These signals help the enrichment/idea agents understand who has already
raised in a category — both a validation signal (category attracting capital) and
a competition signal (funded players now exist).

Exa-only — no Claude calls in this collector.
2 queries per picked category, max 6 queries per run (lean on Exa budget).
"""
from __future__ import annotations
import hashlib
import time

from collectors.base_collector import BaseCollector
from utils.db import is_seen, mark_seen
from utils.signal_schema import RawSignal
from utils.tools import web_search
from utils.logger import get_logger

logger = get_logger()

MAX_QUERIES_PER_RUN = 6


def _build_funding_query(category_label: str, source: str) -> str:
    if source == "inc42":
        return (
            f"{category_label} startup India raised funding seed pre-seed 2025 2026 "
            "site:inc42.com"
        )
    # yourstory + entrackr combined
    return (
        f"India {category_label} D2C brand raised funding investment round 2025 2026 "
        "site:yourstory.com OR site:entrackr.com"
    )


class IndiaFundingCollector(BaseCollector):
    source_name = "india_funding"

    def __init__(self, profile: dict | None = None, **kwargs):
        self.profile = profile or {}
        self.config = self.profile.get("collection", {}).get("india_funding", {})

    def fetch(self) -> list[RawSignal]:
        profile_cats = self.profile.get("categories", {})
        picked = [
            c for c, v in profile_cats.items()
            if isinstance(v, dict) and v.get("weight", 0) > 0
        ]
        if not picked:
            logger.info("[india_funding] no picked categories — skipping")
            return []

        # Build 2 tasks per picked category (alternating sources), capped at 6
        tasks: list[tuple[str, str, str]] = []
        for cat in picked:
            label = cat.replace("_", " ").title()
            tasks.append((cat, label, "inc42"))
            tasks.append((cat, label, "yourstory_entrackr"))
            if len(tasks) >= MAX_QUERIES_PER_RUN:
                break

        lookback = self.config.get("lookback_days", 180)
        signals: list[RawSignal] = []

        logger.info(
            f"[india_funding] {len(tasks)} queries across "
            f"{len(set(t[0] for t in tasks))} categories"
        )

        for cat, label, source in tasks:
            query = _build_funding_query(label, source)
            try:
                results = web_search(query=query, num_results=4, days_back=lookback)
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
                            "signal_type": "india_funding",
                            "query_source": source,
                        },
                    ))
                    mark_seen(self.source_name, sig_id)
            except Exception as e:
                logger.warning(f"[india_funding] query failed for '{query[:60]}': {e}")
            time.sleep(0.3)

        return signals
