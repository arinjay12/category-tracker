"""
IndiaAppGapCollector — directly surfaces India app whitespace signals.

Three signal types:
1. "India version of X" — explicit gap posts on Reddit/Quora where users name
   a US app they want in India. The highest-confidence whitespace signal.
2. India startup funding — Inc42/YourStory/Entrackr coverage of Indian consumer
   app funding rounds. Shows where Indian capital is moving and what's funded.
3. Indie Hackers / HN — solo builders launching in these spaces, often the
   earliest signal of an emerging category.

Exa-only. No Claude calls.
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


class IndiaAppGapCollector(BaseCollector):
    source_name = "india_app_gap"

    def __init__(self, profile: dict | None = None, **kwargs):
        self.profile = profile or {}

    def fetch(self) -> list[RawSignal]:
        profile_cats = self.profile.get("categories", {})
        picked = [
            c for c, v in profile_cats.items()
            if isinstance(v, dict) and v.get("weight", 0) > 0
        ]
        if not picked:
            logger.info("[india_app_gap] no picked categories — skipping")
            return []

        tasks: list[tuple[str, str, str]] = []  # (cat, query, signal_type)
        for cat in picked:
            term = CATEGORY_SEARCH_TERMS.get(cat, cat.replace("_", " "))
            label = cat.replace("_", " ")

            # Signal 1: explicit "India version of" gap posts
            tasks.append((
                cat,
                f'"India version" OR "Indian alternative" OR "India equivalent" {term} app site:reddit.com OR site:quora.com',
                "white_space",
            ))
            # Signal 2: India startup funding in this space
            tasks.append((
                cat,
                f'India {label} consumer app startup raised funding 2025 2026 site:inc42.com OR site:yourstory.com OR site:entrackr.com',
                "momentum",
            ))
            if len(tasks) >= MAX_QUERIES_PER_RUN:
                break

        signals: list[RawSignal] = []
        logger.info(f"[india_app_gap] {len(tasks)} queries")

        for cat, query, signal_type in tasks:
            try:
                results = web_search(query=query, num_results=5, days_back=365)
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
                        body=r.get("snippet", "")[:2500],
                        url=url,
                        created_at=r.get("published_date", ""),
                        extra={
                            "category": cat,
                            "signal_type": signal_type,
                            "platform": "india_gap",
                        },
                    ))
                    mark_seen(self.source_name, sig_id)
            except Exception as e:
                logger.warning(f"[india_app_gap] query failed for '{query[:60]}': {e}")
            time.sleep(0.3)

        return signals
