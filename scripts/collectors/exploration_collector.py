"""
ExplorationCollector — runs templated exploration queries against Exa.

Per run, this collector:
  1. Reads the user's picked categories from profile.yaml.
  2. Builds an exploration query list: 3 universal queries + 2 per picked category.
  3. Runs each query through Exa with a recent-content filter.

This replaces the old static `search_directives.json` flow. Queries are built fresh
from the current profile on every run — so changes via `update_profile.py` take
effect immediately, no re-onboarding required.

No LLM call. No theme rotation. Just templated queries derived from profile state.
If you want fancier exploration (e.g. per-run themes, adaptive query generation),
add it as a separate flag/feature.
"""
from __future__ import annotations
import hashlib
import time
from datetime import datetime, timedelta

from collectors.base_collector import BaseCollector
from utils.db import is_seen, mark_seen
from utils.signal_schema import RawSignal
from utils.tools import web_search
from utils.logger import get_logger

logger = get_logger()


# Per-category seed queries — tuned to each category's actual online behavior.
# Different categories live on different platforms:
#   - Beauty/skincare → Reddit subs (IndianSkincareAddicts, AsianBeauty)
#   - Electronics → YouTube reviews, r/IndianTech, MySmartPrice
#   - Food → r/IndianFood, quick commerce app reviews, Twitter
#   - Pet → r/IndianPets (newer, smaller), parenting blogs
#   - Fashion → Instagram (weak via Exa), Reddit Indian fashion
# Each pool has ~5-6 queries mixing complaint mining + demand discovery +
# format/format-shift discovery. Avoid baking in specific themes (e.g.
# "hard water", "postpartum") — those should emerge from the data, not
# from assumptions in the seed list.
CATEGORY_SEED_QUERIES: dict[str, list[str]] = {
    "beauty": [
        "site:reddit.com/r/IndianSkincareAddicts product gaps complaints",
        "site:reddit.com/r/AsianBeauty India K-beauty J-beauty gap",
        "site:reddit.com India ingredient skincare brand complaints",
        "Indian premium skincare D2C brand gap opportunity 2026",
        "Korean Japanese skincare format India unbranded segment",
        "site:youtube.com India skincare brand review honest",
    ],
    "personal_care": [
        "site:reddit.com India deodorant shampoo body wash complaints",
        "site:reddit.com/r/IndianSkincareAddicts body care underarm gap",
        "natural personal care brand India unbranded segment opportunity",
        "Indian oral care D2C brand gap mouth fresh",
        "site:reddit.com India shaving razor brand recommendations gap",
        "Indian deo body wash format shift D2C 2026",
    ],
    "food_cpg": [
        "site:reddit.com/r/IndianFood snack beverage D2C brand recommendations",
        "site:reddit.com India healthy snacking brand complaints quality",
        "Indian condiment sauce D2C brand gap mass market",
        "Indian beverage trend new format launch 2026",
        "site:reddit.com India protein snack bar healthy alternative",
        "Indian breakfast cereal D2C brand gap unbranded",
    ],
    "home": [
        "site:reddit.com/r/india home cleaning product recommendations",
        "Indian home decor candle brand D2C gap aspirational",
        "site:reddit.com India kitchen tools brand quality complaints",
        "Indian eco cleaning brand format shift sustainable",
        "site:reddit.com India laundry detergent brand complaints natural",
        "Indian D2C home brand premium mass-market gap 2026",
    ],
    "pet": [
        "site:reddit.com/r/IndianPets dog cat food brand recommendations",
        "site:reddit.com India pet food brand complaints quality grain free",
        "Indian premium pet care D2C brand gap apartment dogs",
        "Indian pet grooming product brand India unbranded opportunity",
        "site:reddit.com India dog treat training supplement brand",
        "Indian cat litter pet accessory format shift D2C 2026",
    ],
    "wellness": [
        "site:reddit.com India sleep gummies magnesium brand recommendations",
        "site:reddit.com India ashwagandha adaptogen supplement complaints",
        "Indian wellness brand gap functional unbranded mass-market",
        "Indian recovery supplement topical brand D2C 2026",
        "site:reddit.com India stress anxiety supplement brand reviews",
        "Indian premium wellness D2C brand gap subscription opportunity",
    ],
    "sexual_wellness": [
        "site:reddit.com India sexual wellness intimacy brand recommendations",
        "site:reddit.com India lubricant condom brand complaints quality",
        "Indian premium sexual wellness D2C brand gap discreet packaging",
        "Indian intimacy product format shift D2C 2026",
        "site:reddit.com India hormonal performance supplement brand",
        "Indian sexual wellness brand mass market unbranded segment",
    ],
    "fashion_apparel": [
        "site:reddit.com India fashion brand recommendations quality complaints",
        "site:reddit.com/r/IndianFashionAddicts brand gap opportunity",
        "Indian D2C fashion brand premium mass market segment gap",
        "Indian ethnic modest fashion D2C brand 2026 launch",
        "site:reddit.com India clothing fit size brand complaints",
        "Indian fashion brand format shift sustainable seasonal opportunity",
    ],
    "jewellery_watches": [
        "site:reddit.com India fashion jewellery brand quality complaints tarnish",
        "site:reddit.com India smartwatch brand recommendations battery",
        "Indian fine jewelry D2C brand gap lab grown diamond opportunity",
        "Indian premium watch D2C brand gap quartz mechanical 2026",
        "site:reddit.com India jewelry brand wedding gifting recommendations",
        "Indian D2C jewelry format shift everyday wearable opportunity",
    ],
    "fitness_nutrition": [
        "site:reddit.com India whey protein brand quality taste complaints",
        "site:reddit.com/r/IndianGuysFitness supplement brand recommendations",
        "site:youtube.com India protein supplement review honest brand",
        "Indian functional food gummies vitamin D2C brand gap 2026",
        "Indian fitness gear resistance band yoga mat brand quality",
        "Indian D2C nutrition brand format shift sachet portion opportunity",
    ],
    "cognitive_wellness": [
        "site:reddit.com India nootropics brain supplement recommendations",
        "site:reddit.com India focus memory supplement brand complaints quality",
        "Indian cognitive wellness D2C brand gap nootropic lion's mane",
        "Indian brain health supplement format shift D2C 2026",
        "site:reddit.com India study focus supplement student professional",
        "Indian nootropic stack brand opportunity unbranded segment",
    ],
    "spiritual_lifestyle": [
        "site:reddit.com India premium incense meditation brand recommendations",
        "site:reddit.com India yoga props meditation cushion brand quality complaints",
        "Indian spiritual lifestyle D2C brand gap premium mindfulness",
        "Indian puja accessories upgraded premium brand opportunity 2026",
        "site:reddit.com India ayurvedic self-care ritual brand recommendations",
        "Indian meditation wellness lifestyle brand format shift D2C",
    ],
    "sleep_recovery": [
        "site:reddit.com India sleep supplement magnesium brand recommendations",
        "site:reddit.com India melatonin sleep aid brand complaints quality",
        "Indian sleep recovery D2C brand gap premium sleep hygiene",
        "Indian magnesium glycine sleep supplement brand opportunity 2026",
        "site:reddit.com India insomnia sleep quality supplement discussion",
        "Indian sleep stack brand format shift sachet bedtime ritual",
    ],
}

# Cap total queries per run to keep Exa cost predictable. With 2 queries per
# picked category, this caps a 6-category user at 12 queries.
MAX_QUERIES_PER_RUN = 12


def _build_queries(profile: dict) -> list[str]:
    """Build today's exploration query list from current profile state.

    Only category-specific queries — no broad "universal" queries. If the user
    didn't pick a category, we don't search for it. Honors the user's stated
    scope strictly.
    """
    cats = profile.get("categories", {})
    picked = [
        k for k, v in cats.items()
        if isinstance(v, dict) and v.get("weight", 0) > 0
    ]

    queries: list[str] = []
    for cat in picked:
        queries.extend(CATEGORY_SEED_QUERIES.get(cat, []))
    return queries[:MAX_QUERIES_PER_RUN]


class ExplorationCollector(BaseCollector):
    source_name = "exploration"

    def __init__(self, profile: dict | None = None, lookback_hours: int = 72, **kwargs):
        self.profile = profile or {}
        self.config = self.profile.get("collection", {}).get("exploration", {})
        self.lookback_hours = self.config.get("lookback_hours", lookback_hours)

    def fetch(self) -> list[RawSignal]:
        queries = _build_queries(self.profile)
        if not queries:
            logger.info("[exploration] no picked categories — skipping")
            return []

        days_back = max(1, self.lookback_hours // 24)
        since = datetime.utcnow() - timedelta(hours=self.lookback_hours)
        results: list[RawSignal] = []
        seen_urls: set[str] = set()

        logger.info(f"[exploration] running {len(queries)} queries")

        for query in queries:
            try:
                raw = web_search(query=query, num_results=8, days_back=days_back)
                for r in raw:
                    signal = self._to_signal(r, query, since, seen_urls)
                    if signal:
                        results.append(signal)
            except Exception as e:
                logger.warning(f"[exploration] query failed for '{query[:60]}': {e}")

            time.sleep(0.3)  # Exa rate limit

        return results

    def _to_signal(
        self,
        r: dict,
        query: str,
        since: datetime,
        seen_urls: set[str],
    ) -> RawSignal | None:
        if "error" in r or not r.get("url"):
            return None
        url = r["url"]
        if url in seen_urls:
            return None
        seen_urls.add(url)

        sig_id = hashlib.sha256(url.encode()).hexdigest()[:16]
        if is_seen(self.source_name, sig_id):
            return None
        mark_seen(self.source_name, sig_id)

        return RawSignal(
            id=sig_id,
            source=self.source_name,
            title=r.get("title", ""),
            body=r.get("snippet", "")[:3000],
            url=url,
            created_at=r.get("published_date", ""),
            extra={
                "exploration_query": query,
                "signal_type": "exploration",
            },
        )
