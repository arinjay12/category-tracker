"""
AppIdeaAgent — generates consumer app opportunity memos from signals.

Same architecture as idea_agent.py (Claude Sonnet, streaming, tool use) but
with a completely different prompt focused on:
- US consumer app categories blowing up NOW
- India whitespace: what hasn't landed there yet
- VC lens: monetization, growth loop, retention, India timing

No physical-product constraints (no AOV floor, no sourcing, no capital ceiling).
"""
import json
import os
import uuid
import hashlib
import time
from datetime import datetime
import anthropic
from utils.signal_schema import NormalizedSignal, IdeaDict
from utils.tools import TOOL_DEFINITIONS, dispatch_tool
from utils.logger import get_logger
from utils.models import GENERATION_MODEL
from utils.app_categories import APP_CATEGORIES

logger = get_logger()


def _build_system_prompt(profile: dict) -> str:
    cats_dict = profile.get("categories", {})
    picked = [k for k, v in cats_dict.items() if isinstance(v, dict) and v.get("weight", 0) > 0]

    cat_desc_lines = []
    for slug in picked:
        label, desc = APP_CATEGORIES.get(slug, (slug, ""))
        cat_desc_lines.append(f"  - {slug}: {label} — {desc}")
    cat_str = "\n".join(cat_desc_lines) or "  (none — this is a bug)"

    return f"""You are a consumer tech analyst generating app opportunity memos for an India-focused early-stage fund (TDV Partners). Your mandate: identify consumer app categories that are EXPLODING in the US right now but haven't yet found their Indian equivalent.

CONTEXT:
- India has 700M+ smartphone users, UPI as the payment layer, and a young urban population hungry for consumer apps
- There is typically a 12-36 month lag between US consumer app breakouts and their India equivalents
- "India equivalent" means an app that has achieved meaningful scale (100k+ MAU, Series A+ funding) in the same category
- You are NOT evaluating whether US apps can expand to India — you are looking for WHITESPACE where an India-first builder could win

CATEGORIES — generate ideas ONLY in these:
{cat_str}

HARD RULE — CATEGORY: Every idea MUST have `category` set to one of the slugs above (exactly as spelled). If a signal is in a different category, drop it.

LENS PRIORITY:
- `geo_arbitrage`: US app category with strong DAU/revenue growth, zero or weak India equivalent. Highest priority.
- `complaint_cluster`: Indian Reddit/Quora posts explicitly asking "is there an Indian app for X?" Second priority.
- `rising_brand_gap`: A specific US app brand (Headspace, Calm, YNAB, Notion, Duolingo) dominating a category with no comparable Indian product. Also high priority.
- `format_shift`: A new app format (AI-native, voice-first, video-first) that existing Indian players haven't adopted.
- `unbranded_market`: Category exists in India but only through inferior, unbranded, or clunky alternatives.

SELF-EVALUATION REQUIREMENT:
Before emitting each idea, check:
1. Is the category one of the picked categories? If not, DROP.
2. Is there genuine India whitespace? "India has Zerodha" is not whitespace for personal finance apps — be specific about what sub-category is missing.
3. Is the US signal real and recent (2024-2026)? Not a category that peaked in 2020.
4. Is there a viable monetization model that works for India's price-sensitive market?
5. Is the growth loop believable — what would make users invite other users?
6. Is this category fundable at early stage? (seed/pre-seed, $250K-$2M ticket)

OUTPUT FORMAT:
Return a JSON array. Each idea MUST have ALL these fields:
{{
  "category": "one of the category slugs listed above",
  "title": "Short category/opportunity name (3-5 words)",
  "tagline": "SPECIFIC one-sentence thesis: what is blowing up in the US, what is the India gap, and why now. E.g. '<US app category> is a <size> India opportunity — no credible Indian equivalent exists yet.'",
  "problem": "3-5 sentences on the consumer pain. WHO feels it (specific India persona), HOW they currently cope, WHY existing India options are inadequate. Quote specific signal language where possible.",
  "target_consumer": "Specific India consumer persona — age, city, digital behavior. E.g. '22-28 year olds in Bangalore/Mumbai with ₹8-15L income, heavy Instagram users, English-first'",
  "market_size_estimate": "India TAM for this category — e.g. '~35M young urban Indians with personal finance anxiety, $50-100M annual subscription wallet based on ARPU comps'",
  "why_now": "Why this specific window (2025-2027) and not earlier or later. Name the US app/trend driving urgency. UPI, 5G, smartphone penetration, demographic inflection — be specific.",
  "monetization_model": "Primary model: freemium | subscription | transaction | ads — include ₹ price point. E.g. 'Freemium — free core + ₹299/month premium (vs Headspace at $12.99/month). India ARPU target ₹150-200/month.'",
  "growth_loop": "The specific viral/organic loop that drives user acquisition without paid ads. E.g. 'Share a financial summary on LinkedIn → friends ask what app → referral. Or: complete a challenge → share result card on Instagram Stories.'",
  "repeat_purchase": "Retention signal: DAU/WAU/MAU target + one-line retention thesis. E.g. 'Target: DAU/MAU ~35% (Duolingo-level). Daily habit formation through streaks + push notifications. Retention driven by sunk cost of progress data.'",
  "brand_angle": "Primary positioning: 'honest' | 'premium' | 'playful' | 'scientific' | 'heritage' | 'community' | 'functional'. Pick genuinely.",
  "distribution_channels": "Primary organic acquisition channels: app store SEO, Instagram/YouTube creator integrations, word-of-mouth referral, community Slack/Discord, college campus, employer B2B2C, etc.",
  "word_of_mouth_potential": "1-10 — how naturally do users share this app?",
  "exit_comps": "One global comparable exit proving this category is venture-fundable. E.g. 'Headspace + Calm combined >$3B valuation — validates premium meditation app subscriptions at scale.' One sentence.",
  "india_timing": "'early (3+ yrs behind US) | on-time (1-2 yrs behind) | late (Indian players already exist)' — add one-line evidence for the timing read",
  "idea_rationale": "3-4 sentences: (1) which US signals triggered this, (2) the specific India whitespace, (3) the key risk/assumption a fund would need to validate",
  "competitors_india": "",
  "reference_brands_global": "US/EU/JP apps that prove this category works globally — brand + metric if known",
  "wedge": "1-2 sentences: which Indian apps exist in this space (name them), and the ONE dimension a new entrant can beat them on. If truly no Indian players, say so.",
  "lenses_fired": "comma-separated: geo_arbitrage, rising_brand_gap, complaint_cluster, format_shift, etc.",
  "contributing_signal_ids": ["signal_id_1"],
  "source_signal": "primary collector (e.g. 'product_hunt', 'reddit_app', 'vc_consumer_signals', 'india_app_gap')",
  "source_urls": ["url1", "url2"],
  "comparable_products_global": ["US/EU/JP apps proving the category globally"],
  "opportunity_type": "geo_arbitrage | complaint_cluster | format_shift | unbranded_market | rising_brand_gap | wildcard",
  "investability_read": "Two-part string joined by newline. Line 1: 'India status: <unfilled | weak incumbents | crowded> — <one-line justification>'. Lines 2-3: frank two-line take on whether this is fundable at seed stage for an India consumer tech fund (ticket size, time-to-leadership, category size)."
}}

SOURCE HONESTY: Never fabricate URLs. Never invent metrics. If you're uncertain about India MAU figures, say so. An honest 'insufficient data' is more useful to the fund than a confident lie."""


def _make_idea_hash(category: str, title: str) -> str:
    import re
    stop_words = {"a", "an", "the", "for", "of", "in", "on", "at", "to", "with", "and", "or", "is", "it", "app"}
    text = f"{category} {title}".lower()
    words = re.sub(r"[^a-z0-9 ]", "", text).split()
    words = sorted(w for w in words if w not in stop_words)
    return hashlib.sha256(" ".join(words).encode()).hexdigest()[:16]


def generate_app_ideas(
    signals: list[NormalizedSignal],
    profile: dict,
    recent_titles: list[str] = None,
    max_tool_rounds: int = 4,
) -> list[IdeaDict]:
    if not signals:
        return []

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = GENERATION_MODEL

    system_prompt = _build_system_prompt(profile)
    _emit_progress(f"app idea generation: synthesising from {len(signals)} signals (Sonnet + tool use, ~5-9 min)")

    signals_text = json.dumps([
        {
            "signal": f"{s.summary[:100]} [{s.raw_source}]",
            "type": s.signal_type,
            "category_tags": s.category_tags,
            "consumer_tags": s.consumer_tags,
            "evidence_strength": s.evidence_strength,
            "key_entities": s.key_entities,
            "pain_acuity": s.pain_acuity,
            "gap_dimensions": s.gap_dimensions,
            "geo_markets": s.geo_markets,
            "enrichment_notes": s.enrichment_notes,
            "raw_url": s.raw_url,
        }
        for s in signals
    ], indent=2)

    existing_str = ""
    if recent_titles:
        existing_str = (
            "\n\nALREADY EXPLORED — do NOT repeat these concepts:\n"
            + "\n".join(f"- {t}" for t in recent_titles[:60])
        )

    MAX_IDEAS = 5

    user_prompt = f"""Here are {len(signals)} consumer app signals from Product Hunt, Reddit, VC publications, and India gap analysis. Generate {MAX_IDEAS} consumer app opportunity memos for an India-focused early-stage fund.

Target: {MAX_IDEAS} ideas total, at most 1 wildcard. Bias strongly toward geo_arbitrage and rising_brand_gap — these are the fund's primary signal.
{existing_str}

DIVERSITY:
- Use at least 3 DIFFERENT values for `opportunity_type` across the {MAX_IDEAS} ideas
- Use at least 3 DIFFERENT category slugs across the {MAX_IDEAS} ideas (don't cluster in one category)
- Use at least 3 DIFFERENT `brand_angle` values

TOOL USE LIMIT: At most 3 searches, only for India market sizing or competitor checks you're genuinely uncertain about.
Output JSON immediately after.

Signals:
{signals_text}

Return ONLY a JSON array starting with ```json"""

    messages = [{"role": "user", "content": user_prompt}]
    text = ""

    for _ in range(max_tool_rounds):
        for attempt in range(3):
            try:
                with client.messages.stream(
                    model=model,
                    max_tokens=24000,
                    system=system_prompt,
                    tools=TOOL_DEFINITIONS,
                    messages=messages,
                ) as stream:
                    response = stream.get_final_message()
                break
            except Exception as e:
                if "overloaded" in str(e).lower() and attempt < 2:
                    wait = 30 * (attempt + 1)
                    logger.warning(f"[app_idea_agent] API overloaded — retrying in {wait}s")
                    time.sleep(wait)
                else:
                    raise

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if tool_uses:
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for tu in tool_uses:
                logger.info(f"[app_idea_agent] tool: {tu.name}")
                result = dispatch_tool(tu.name, tu.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result[:3000],
                })
            messages.append({"role": "user", "content": tool_results})
            continue

        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        break
    else:
        logger.warning("[app_idea_agent] max tool rounds — forcing final output")
        messages.append({"role": "user", "content": (
            "You have reached the tool use limit. "
            "Output your final JSON array of consumer app opportunity memos now. "
            "Start with ```json."
        )})
        with client.messages.stream(
            model=model,
            max_tokens=24000,
            system=system_prompt,
            messages=messages,
        ) as stream:
            final = stream.get_final_message()
        text = "".join(b.text for b in final.content if hasattr(b, "text"))

    return _parse_ideas(text)


def _parse_ideas(text: str) -> list[IdeaDict]:
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        data = json.loads(text.strip())
    except Exception as e:
        logger.warning(f"[app_idea_agent] failed to parse JSON: {e} — attempting recovery")
        raw = text.strip()
        last_complete = raw.rfind("\n  },")
        if last_complete == -1:
            last_complete = raw.rfind("},")
        if last_complete > 0:
            truncated_fixed = raw[:last_complete + 4] + "\n]"
            if not truncated_fixed.lstrip().startswith("["):
                truncated_fixed = "[" + truncated_fixed.lstrip()
            try:
                data = json.loads(truncated_fixed)
                logger.info(f"[app_idea_agent] recovery: {len(data)} ideas")
            except Exception:
                return []
        else:
            return []

    results = []
    run_date = datetime.utcnow().strftime("%Y-%m-%d")

    def _s(item, key, default=""):
        value = item.get(key, default)
        if value is None:
            return default
        if isinstance(value, list):
            return ", ".join(str(v).strip() for v in value if v)
        return str(value) if not isinstance(value, str) else value

    for item in data:
        if not isinstance(item, dict) or not item.get("title"):
            continue

        title = item["title"]
        category = item.get("category", "")
        idea_hash = _make_idea_hash(category, title)

        ir_raw = item.get("investability_read", "")
        if isinstance(ir_raw, dict):
            ir_str = "\n".join(filter(None, [ir_raw.get("india_status", ""), ir_raw.get("fundability_take", "")]))
        else:
            ir_str = str(ir_raw) if ir_raw else ""

        idea = IdeaDict(
            idea_id=str(uuid.uuid4()),
            run_date=run_date,
            category=category,
            title=title,
            tagline=item.get("tagline", ""),
            problem=item.get("problem", ""),
            target_consumer=_s(item, "target_consumer"),
            market_size_estimate=_s(item, "market_size_estimate"),
            why_now=_s(item, "why_now"),
            # Physical product fields — blank for apps
            hero_product="",
            hero_product_detail="",
            aov_estimate="",
            margin_estimate="",
            capital_required_estimate="",
            first_year_revenue_estimate="",
            sourcing_approach="",
            gtm_tactics="",
            ai_angle="none",
            # App-relevant fields
            brand_angle=_s(item, "brand_angle"),
            distribution_channels=_s(item, "distribution_channels"),
            word_of_mouth_potential=_s(item, "word_of_mouth_potential"),
            idea_rationale=_s(item, "idea_rationale"),
            competitors_india="",
            reference_brands_global=_s(item, "reference_brands_global"),
            wedge=_s(item, "wedge"),
            lenses_fired=_s(item, "lenses_fired"),
            contributing_signals=", ".join(item.get("contributing_signal_ids", [])),
            source_signal=item.get("source_signal", ""),
            source_url="\n".join(item.get("source_urls", [])[:6]),
            opportunity_type=item.get("opportunity_type", "geo_arbitrage"),
            comparable_product_images="",
            time_sensitive=False,
            idea_hash=idea_hash,
            investability_read=ir_str,
            exit_comps=_s(item, "exit_comps"),
            repeat_purchase=_s(item, "repeat_purchase"),
            india_timing=_s(item, "india_timing"),
            # App-specific
            monetization_model=_s(item, "monetization_model"),
            growth_loop=_s(item, "growth_loop"),
        )
        results.append(idea)

    logger.info(f"[app_idea_agent] generated {len(results)} app ideas")
    _emit_progress(f"app idea generation: produced {len(results)} candidate ideas")
    return results


def _emit_progress(message: str) -> None:
    from pathlib import Path as _Path
    indented = f"    {message}"
    print(indented, flush=True)
    try:
        progress_path = _Path(__file__).resolve().parent.parent.parent / "user_data" / "progress.txt"
        progress_path.write_text(indented + "\n")
    except Exception:
        pass
