"""
RedditAppCollector — mines Reddit for consumer app complaint clusters and demand signals.

Two distinct signal types:
1. US complaint clusters (r/apps, r/androidapps, r/iphoneapps) — what app categories
   are generating pain/demand in the US right now. These are the categories India
   will seek solutions for in 1-3 years.
2. India demand signals (r/india, r/IndiaTech, r/bangalore, r/mumbai) — explicit
   "is there an Indian app for X?" posts and discussions about missing app categories.

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

MAX_QUERIES_PER_RUN = 8

# Per-category Reddit query pools — alternates between US complaint mining
# and India demand mining.
CATEGORY_REDDIT_QUERIES: dict[str, list[str]] = {
    "ai_tools": [
        'site:reddit.com/r/artificial OR site:reddit.com/r/ChatGPT AI app alternatives complaints 2025',
        'site:reddit.com/r/india OR site:reddit.com/r/IndiaTech AI app tools recommendations',
    ],
    "personal_finance": [
        'site:reddit.com/r/personalfinance budgeting app complaints "wish there was" alternatives',
        'site:reddit.com/r/india OR site:reddit.com/r/IndiaInvestments finance budgeting app India recommendation',
    ],
    "mental_health": [
        'site:reddit.com/r/mentalhealth OR site:reddit.com/r/therapy app complaints alternatives 2025',
        'site:reddit.com/r/india mental health therapy app India recommendation gap',
    ],
    "fitness_apps": [
        'site:reddit.com/r/fitness OR site:reddit.com/r/loseit fitness app complaints alternative',
        'site:reddit.com/r/india OR site:reddit.com/r/gym fitness workout app India recommendations',
    ],
    "creator_tools": [
        'site:reddit.com/r/freelance OR site:reddit.com/r/YoutubeCreators creator tools complaints "wish there was"',
        'site:reddit.com/r/india creator tools freelancer app India recommendation',
    ],
    "social_community": [
        'site:reddit.com/r/apps OR site:reddit.com/r/socialskills niche social app "I wish" complaints',
        'site:reddit.com/r/india community app social platform India gap',
    ],
    "edtech": [
        'site:reddit.com/r/learnprogramming OR site:reddit.com/r/languagelearning app complaints alternatives',
        'site:reddit.com/r/india learning app edtech recommendation gap',
    ],
    "home_local": [
        'site:reddit.com/r/homeimprovement OR site:reddit.com/r/personalfinance home services app complaints',
        'site:reddit.com/r/india OR site:reddit.com/r/bangalore home services app India recommendation',
    ],
    "entertainment": [
        'site:reddit.com/r/androidapps OR site:reddit.com/r/iphoneapps entertainment audio game app complaints',
        'site:reddit.com/r/india entertainment app India gap recommendation',
    ],
    "dating_social": [
        'site:reddit.com/r/dating OR site:reddit.com/r/OnlineDating dating app complaints niche alternative',
        'site:reddit.com/r/india dating app India niche gap recommendation',
    ],
}


class RedditAppCollector(BaseCollector):
    source_name = "reddit_app"

    def __init__(self, profile: dict | None = None, **kwargs):
        self.profile = profile or {}

    def fetch(self) -> list[RawSignal]:
        profile_cats = self.profile.get("categories", {})
        picked = [
            c for c, v in profile_cats.items()
            if isinstance(v, dict) and v.get("weight", 0) > 0
        ]
        if not picked:
            logger.info("[reddit_app] no picked categories — skipping")
            return []

        tasks: list[tuple[str, str, str]] = []  # (cat, query, signal_type)
        for cat in picked:
            queries = CATEGORY_REDDIT_QUERIES.get(cat, [])
            if not queries:
                term = CATEGORY_SEARCH_TERMS.get(cat, cat.replace("_", " "))
                queries = [
                    f'site:reddit.com {term} app complaints "I wish" alternatives',
                    f'site:reddit.com/r/india {term} app recommendation gap',
                ]
            for i, q in enumerate(queries[:2]):
                signal_type = "complaint_cluster" if i == 0 else "explicit_demand"
                tasks.append((cat, q, signal_type))
            if len(tasks) >= MAX_QUERIES_PER_RUN:
                break

        signals: list[RawSignal] = []
        logger.info(f"[reddit_app] {len(tasks)} queries across {len(set(t[0] for t in tasks))} categories")

        for cat, query, signal_type in tasks:
            try:
                results = web_search(query=query, num_results=6, days_back=365)
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
                            "platform": "reddit",
                        },
                    ))
                    mark_seen(self.source_name, sig_id)
            except Exception as e:
                logger.warning(f"[reddit_app] query failed for '{query[:60]}': {e}")
            time.sleep(0.3)

        return signals
