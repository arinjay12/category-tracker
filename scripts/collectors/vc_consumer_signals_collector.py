"""
VCConsumerSignalsCollector — mines US VC investment signals for consumer apps.

Queries TechCrunch funding coverage, a16z consumer thesis posts, and Sequoia
consumer investment announcements. This surfaces categories where institutional
money is concentrating — the strongest leading indicator of "what will be big
in 2-3 years" and the best proxy for what India will see next.

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

# VC sources that publish consumer investment thesis or deal coverage
VC_SOURCES = [
    "site:techcrunch.com",
    "site:a16z.com OR site:sequoiacap.com OR site:thegeneralist.io",
]


class VCConsumerSignalsCollector(BaseCollector):
    source_name = "vc_consumer_signals"

    def __init__(self, profile: dict | None = None, **kwargs):
        self.profile = profile or {}

    def fetch(self) -> list[RawSignal]:
        profile_cats = self.profile.get("categories", {})
        picked = [
            c for c, v in profile_cats.items()
            if isinstance(v, dict) and v.get("weight", 0) > 0
        ]
        if not picked:
            logger.info("[vc_consumer_signals] no picked categories — skipping")
            return []

        tasks: list[tuple[str, str]] = []
        for cat in picked:
            term = CATEGORY_SEARCH_TERMS.get(cat, cat.replace("_", " "))
            tasks.append((cat, f"{VC_SOURCES[0]} {term} consumer app raised funding 2025 2026"))
            tasks.append((cat, f"{VC_SOURCES[1]} {term} consumer startup investment thesis"))
            if len(tasks) >= MAX_QUERIES_PER_RUN:
                break

        signals: list[RawSignal] = []
        logger.info(f"[vc_consumer_signals] {len(tasks)} queries")

        for cat, query in tasks:
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
                        body=r.get("snippet", "")[:2000],
                        url=url,
                        created_at=r.get("published_date", ""),
                        extra={
                            "category": cat,
                            "signal_type": "geo_arbitrage",
                            "platform": "vc_signal",
                        },
                    ))
                    mark_seen(self.source_name, sig_id)
            except Exception as e:
                logger.warning(f"[vc_consumer_signals] query failed for '{query[:60]}': {e}")
            time.sleep(0.3)

        return signals
