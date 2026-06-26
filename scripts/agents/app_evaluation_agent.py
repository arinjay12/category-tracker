"""
AppEvaluationAgent — scores consumer app ideas on 6 app-specific dimensions.

Same architecture as evaluation_agent.py (Claude Haiku, single-pass JSON) but
with a completely different scoring rubric tuned for consumer app fundability
in India.

Score field mapping (reusing IdeaDict fields with new semantics):
  score_demand        → signal loudness (same as product pipeline)
  score_launchability → india_readiness (behavioral/infra readiness in India)
  score_capital_fit   → monetization_fit (can this model work in India's market?)
  score_arbitrage     → india_gap (how unfilled is this category in India?)
  score_competition   → competition (inverted: higher = less competition)
  score_distribution  → growth_loop_strength (organic acquisition potential)
"""
import json
import os
import time
import anthropic
from utils.signal_schema import IdeaDict
from utils.logger import get_logger
from utils.models import EVALUATION_MODEL
from utils.app_categories import APP_CATEGORIES

logger = get_logger()

# Scoring weights — tuned for consumer app fundability
APP_SCORING_WEIGHTS = {
    "demand_strength":   0.25,
    "india_readiness":   0.20,
    "monetization_fit":  0.20,
    "india_gap":         0.15,
    "competition":       0.10,
    "growth_loop":       0.10,
}

APP_FILTERS = {
    "min_composite_score":   5.5,
    "min_india_readiness":   4,    # below this = India market not ready
    "min_india_gap":         3,    # below this = India already has good options
}

SYSTEM_PROMPT = """You are a consumer app evaluator for an India-focused early-stage fund.
Score each app opportunity on 6 dimensions. Return structured JSON only.

CONTEXT:
- India market: 700M+ smartphone users, UPI payment layer, 5G rollout, young urban demographic
- Target: tier-1 + tier-2 Indian cities (both), not just metros
- Monetization reality: Indian users resist paid apps. Freemium with ₹99-499/month premium is the sweet spot. Ads-based works for high-DAU apps. Enterprise B2B2C is increasingly viable.
- Growth reality: viral loops and social proof matter more than paid UA in early India consumer apps

SCORING RUBRIC:

score_demand (1-10): Signal loudness — how much evidence of this pain/demand?
  10 = multiple Reddit/Quora India threads explicitly asking for this, Product Hunt breakouts, VC theses naming this space
  7-9 = clear global breakout + India demand signals from 2+ sources
  5-6 = strong global signal but India demand inferred (not explicitly stated)
  3-4 = scattered signals, mostly from one source
  1-2 = single signal or analyst speculation

score_launchability (1-10): INDIA READINESS — is India behaviorally/technically ready for this category?
  10 = India-native behavior already exists (UPI transactions, short-video consumption, group chats) — category slots directly into existing behavior
  7-9 = India is clearly moving in this direction; 1-2 year lag from US but infrastructure and habit formation are there
  5-6 = India adoption plausible but requires behavior change or infra that's not fully there (e.g. credit-card subscriptions, ambient computing)
  3-4 = significant behavior change needed, or depends on infra India lacks (e.g. open banking APIs, health records portability)
  1-2 = category requires behaviors India won't have for 3+ years, or regulatory blocker exists

score_capital_fit (1-10): MONETIZATION FIT — can this business model work in India's price-sensitive market?
  10 = proven India freemium/subscription comp (Zerodha, Zoho, Unacademy) at similar ARPU; or ads model with proven DAU in India
  7-9 = India users demonstrably pay for this category (OTT subscriptions, gaming, tools) at viable ARPU
  5-6 = monetization uncertain — Indian users pay abroad but India-specific ARPU data is unclear
  3-4 = strong resistance to monetization in India (e.g. content/media in categories where piracy dominates)
  1-2 = category is structurally hard to monetize in India (very low ARPU, high CAC, no ads inventory)

score_arbitrage (0-10): INDIA GAP — how unfilled is this specific category in India?
  10 = zero credible Indian equivalent; no Series A+ funded Indian app in this space
  7-9 = weak Indian equivalents exist but all are poorly executed / underfunded / no brand
  4-6 = some Indian players but they serve a narrow slice; clear sub-category whitespace
  1-3 = strong Indian players already exist (Groww for investing, PhonePe for payments, etc.); gap is narrow
  0 = not a geo-arbitrage idea (category is already crowded in India)

score_competition (1-10): INVERTED — higher score means LESS competition (better for entry)
  10 = true whitespace; no credible app in India for this use case
  7-9 = 1-2 small or unfunded Indian players; no well-funded incumbent
  5-6 = established players but fragmented; room for differentiated entry
  3-4 = multiple funded incumbents; needs exceptional wedge
  1-2 = dominated by well-funded players (Zerodha, ShareChat, BYJU's-tier) or Google/Meta default

score_distribution (1-10): GROWTH LOOP STRENGTH — how naturally does the app acquire users?
  10 = extremely viral by nature: user creates artifact others want to see/use (Wordle, Canva, Notion docs), or strong referral incentive baked into core product
  7-9 = good organic channels: app store SEO, creator integrations, social sharing, community-led growth
  5-6 = moderate organic loop; some virality but primarily needs paid UA or partnerships
  3-4 = primarily needs expensive paid UA, influencer partnerships, or enterprise BD
  1-2 = no natural organic loop; purely dependent on paid acquisition

Also assess:
- eval_flags: array of strings — specific issues like "India subscription resistance for this category",
  "well-funded Indian incumbent exists (name it)", "behavior change required", "low ARPU ceiling",
  "no viral loop", "regulatory risk (RBI, SEBI, TRAI)", "Google/Apple default competes directly"

Return ONLY a JSON array:
[{
  "idea_id": "<id>",
  "score_demand": <1-10>,
  "score_launchability": <1-10>,
  "score_capital_fit": <1-10>,
  "score_arbitrage": <0-10>,
  "score_competition": <1-10>,
  "score_distribution": <1-10>,
  "eval_flags": ["flag1", "flag2"]
}]"""


def evaluate_app_ideas(ideas: list[IdeaDict], profile: dict) -> list[IdeaDict]:
    if not ideas:
        return []

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = EVALUATION_MODEL

    min_composite = APP_FILTERS["min_composite_score"]
    min_india_readiness = APP_FILTERS["min_india_readiness"]
    min_india_gap = APP_FILTERS["min_india_gap"]

    # Resolve picked category slugs from profile
    cats = profile.get("categories", {})
    picked_cats_set = {k for k, v in cats.items() if isinstance(v, dict) and v.get("weight", 0) > 0}
    # Fallback: if no profile filtering, accept all APP_CATEGORIES
    if not picked_cats_set:
        picked_cats_set = set(APP_CATEGORIES.keys())

    ideas_text = json.dumps([
        {
            "idea_id": idea.idea_id,
            "title": idea.title,
            "tagline": idea.tagline,
            "category": idea.category,
            "problem": idea.problem,
            "target_consumer": idea.target_consumer,
            "monetization_model": idea.monetization_model,
            "growth_loop": idea.growth_loop,
            "repeat_purchase": idea.repeat_purchase,
            "distribution_channels": idea.distribution_channels,
            "word_of_mouth_potential": idea.word_of_mouth_potential,
            "wedge": idea.wedge,
            "competitors_india": idea.competitors_india,
            "opportunity_type": idea.opportunity_type,
            "india_timing": idea.india_timing,
        }
        for idea in ideas
    ], indent=2)

    user_prompt = f"""Score these {len(ideas)} consumer app opportunity memos for India market entry potential.

App ideas to score:
{ideas_text}"""

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=6000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            break
        except Exception as e:
            if "rate_limit" in str(e).lower() and attempt < 2:
                logger.warning(f"[app_evaluation] rate limited — retrying in 60s (attempt {attempt + 1}/3)")
                time.sleep(60)
            else:
                raise

    text = "".join(b.text for b in response.content if hasattr(b, "text"))
    scores = _parse_scores(text)
    scored_map = {s["idea_id"]: s for s in scores}
    results = []

    weights = APP_SCORING_WEIGHTS

    for idea in ideas:
        if idea.category not in picked_cats_set:
            idea.eval_status = "rejected"
            idea.eval_reasons = f"Category '{idea.category}' not in picked categories"
            idea.score_demand = idea.score_launchability = idea.score_capital_fit = 0
            idea.score_arbitrage = idea.score_competition = idea.score_distribution = 0
            idea.score_composite = 0.0
            results.append(idea)
            continue

        s = scored_map.get(idea.idea_id, {})
        if not s:
            continue

        idea.score_demand = s.get("score_demand", 0)
        idea.score_launchability = s.get("score_launchability", 0)
        idea.score_capital_fit = s.get("score_capital_fit", 0)
        idea.score_arbitrage = s.get("score_arbitrage", 0)
        idea.score_competition = s.get("score_competition", 0)
        idea.score_distribution = s.get("score_distribution", 0)
        idea.eval_flags = ", ".join(s.get("eval_flags", []))

        raw_composite = (
            idea.score_demand        * weights["demand_strength"] +
            idea.score_launchability * weights["india_readiness"] +
            idea.score_capital_fit   * weights["monetization_fit"] +
            idea.score_competition   * weights["competition"] +
            idea.score_distribution  * weights["growth_loop"] +
            idea.score_arbitrage     * weights["india_gap"]
        )

        wom = idea.word_of_mouth_potential
        try:
            wom_score = int(wom) if wom else 0
        except (ValueError, TypeError):
            wom_score = 0
        if wom_score >= 8:
            raw_composite *= 1.08

        idea.score_composite = round(raw_composite, 2)

        reasons: list[str] = []
        if idea.score_launchability < min_india_readiness:
            reasons.append(
                f"India readiness concerns — behavior change or infrastructure gap "
                f"(readiness score {idea.score_launchability}/10)"
            )
        if idea.score_arbitrage < min_india_gap and idea.opportunity_type != "unbranded_market":
            reasons.append(
                f"India gap too small — credible Indian players already exist "
                f"(gap score {idea.score_arbitrage}/10)"
            )
        if idea.score_composite < min_composite:
            reasons.append(
                f"Overall score below minimum (composite {idea.score_composite:.1f}/10)"
            )

        if reasons:
            idea.eval_status = "rejected"
            idea.eval_reasons = "; ".join(reasons)
            logger.info(f"[app_evaluation] REJECT '{idea.title}' — {idea.eval_reasons}")
        else:
            idea.eval_status = "passed"
            idea.eval_reasons = ""

        results.append(idea)

    passed = sum(1 for i in results if i.eval_status == "passed")
    logger.info(f"[app_evaluation] {passed}/{len(results)} passed")
    return results


def _parse_scores(text: str) -> list[dict]:
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    try:
        return json.loads(text.strip())
    except Exception as e:
        logger.warning(f"[app_evaluation] failed to parse scores: {e}")
        return []
