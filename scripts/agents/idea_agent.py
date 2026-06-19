"""
IdeaAgent — generates D2C product idea cards from normalized signals.
Uses Claude Sonnet with tool use. Self-evaluates each idea before emitting.
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

logger = get_logger()


def _build_system_prompt(profile: dict) -> str:
    # --- Read user profile (use ACTUAL profile.yaml schema) ---
    cats_dict = profile.get("categories", {})
    picked_categories = [
        k for k, v in cats_dict.items()
        if isinstance(v, dict) and v.get("weight", 0) > 0
    ]

    dist_channels = profile.get("distribution", {})  # correct key is "distribution"

    market = profile.get("market", {})
    capital_lakhs = market.get("capital_ceiling_lakhs", 20)

    # Hard AOV floor — internal config (utils/config.py), not in profile.yaml.
    # This is a D2C unit-economics floor, not a per-user setting.
    from utils.config import MIN_AOV_RUPEES
    min_aov = MIN_AOV_RUPEES

    # User-specific hard excludes. These come from onboarding (Q3) — the user
    # picked which categorical risks they want ruled out. We DO NOT impose any
    # additional always-on excludes (cold chain, complex formulation, etc.)
    # beyond what the user explicitly said. If the user can handle cold chain,
    # they shouldn't be blocked from cold-chain ideas because the system
    # assumed they couldn't.
    EXCLUDE_DESCRIPTIONS = {
        "cold_chain": "Cold chain or perishable logistics (anything that needs refrigerated transport/storage)",
        "complex_formulation": "Complex or scientific formulation (novel actives, R&D-heavy, requires specialist chemistry)",
        "tight_regulation": "Tight regulation (FSSAI nutraceutical cat 8, AYUSH, baby formula, medical devices)",
        "over_10kg": "Heavy items over 10kg — shipping costs become meaningful (5-10% of AOV), returns get expensive, damage rates rise, COD risk goes up. Couriers can still handle these but unit economics get tight.",
        "ingestible": "Anything ingestible (food, supplements, drinks — anything consumed)",
    }
    excludes = profile.get("hard_excludes", {})
    preset_excludes = excludes.get("preset", []) if isinstance(excludes, dict) else []
    custom_excludes = excludes.get("custom", []) if isinstance(excludes, dict) else []

    # Expand preset keys to descriptions; pass custom strings through as-is.
    user_exclude_lines = []
    for e in preset_excludes:
        user_exclude_lines.append(EXCLUDE_DESCRIPTIONS.get(e, e))
    for e in custom_excludes:
        user_exclude_lines.append(e)

    # --- Format strings for the prompt ---
    cat_str = "\n".join(f"  - {c}" for c in picked_categories) or "  (none — this is a bug)"
    dist_str = "\n".join(f"  {ch}: {score}" for ch, score in sorted(dist_channels.items())) or "  (none specified)"
    user_excludes_str = (
        "\n".join(f"- {line}" for line in user_exclude_lines)
        if user_exclude_lines else "(none — the user did not pick any categorical excludes in onboarding)"
    )

    return f"""You are a consumer category analyst generating opportunity memos for an India-focused consumer/D2C fund. Your job is to identify rising global categories that are under-served in India and assess whether each represents a fundable early-stage bet. You are NOT writing for a founder — you are writing for an investor evaluating category whitespace.

ANALYSIS PARAMETERS:
- India focus: tier-1 urban consumers (metro cities — Mumbai, Delhi, Bangalore, Hyderabad, Pune, Chennai)
- AOV HARD FLOOR: ≥₹{min_aov}. D2C unit economics break below this (CAC + shipping + returns + payment fees). Any category whose AOV is structurally below ₹{min_aov} should be flagged as uneconomic for D2C. If a bundle/kit format could cross ₹{min_aov}, note it — but don't force it.
- Gross margin floor for investable D2C: ≥60%
- Capital ceiling for reference: ₹{capital_lakhs}L (seed-stage capital context — use to assess whether this is pre-seed / seed fundable)

CATEGORIES — these are the ONLY categories you may generate ideas in:
{cat_str}

**HARD RULE — CATEGORY:** Every idea you emit MUST have `category` set to one of the values above (exactly as spelled). Do not generate ideas in any other category, even if a signal looks interesting. If a signal is in an unpicked category, drop it — do not stretch it to fit a picked category, and do not emit it as an "interesting wildcard." The user explicitly said these are their categories; respect that.

DISTRIBUTION CHANNEL SCORES (0=can't, 2=comfortable, 3=superpower):
{dist_str}

HARD EXCLUDES — reject any idea requiring:
- Hero SKU priced below ₹{min_aov} (bundle up or drop — no exceptions)
- Capital >₹{capital_lakhs}L to launch first batch (this is the user's hard ceiling)

USER'S CATEGORICAL EXCLUDES (from onboarding):
{user_excludes_str}

Reject any idea that triggers any of the above. Do NOT impose additional excludes that the user didn't pick — if the user is comfortable with (say) cold chain or regulation-heavy categories, you should be too.

LENS PRIORITY — the fund's primary mandate is "rising globally, unfilled in India":
- Strongly prefer `geo_arbitrage` and `rising_brand_gap` signals. These are the lenses the fund cares most about.
- `geo_arbitrage`: a category with a proven, growing global brand that has no credible Indian equivalent yet.
- `rising_brand_gap`: a brand archetype (ingredient, format, ritual) gaining global momentum but absent from India.
- Other lenses (complaint_cluster, format_shift, unbranded_market, wildcard) are valid but secondary.

SELF-EVALUATION REQUIREMENT:
Before emitting each idea, internally ask:
1. Is the category one of the picked categories listed above? If not, DROP.
2. Is the AOV ≥₹{min_aov}? If not, note bundle path or flag as uneconomic.
3. Is gross margin achievable at ≥60%?
4. Is there a clear, named gap vs existing India players?
5. Is the global signal real — is there a rising brand or category wave that has not yet reached India at scale?
6. Is this category fundable at early stage, or is it too small / commoditized / capital-intensive?
If an idea fails these checks — improve it or drop it. Only emit ideas you'd confidently recommend to a fund IC.

WILDCARD IDEAS (within picked categories): You may tag up to 1 idea with `opportunity_type: "wildcard"` if it takes an unexpected angle within one of the picked categories — different consumer moment, surprising format, contrarian positioning. Wildcards still MUST be in a picked category.

OUTPUT FORMAT:
Return a JSON array. Each idea MUST have ALL these fields:
{{
  "category": "one of the 16 categories listed above",
  "title": "Short category/opportunity name (3-5 words)",
  "tagline": "SPECIFIC one-sentence investment thesis: what is rising globally, what is the India gap, and why now. Include indicative AOV ≥₹{min_aov}. E.g. '<global trend> is a ₹<size>Cr+ India opportunity — <gap statement>.'",
  "problem": "3-5 sentences on the consumer pain driving demand. WHO feels it, HOW OFTEN, WHAT they do today, WHY existing India options fall short. Ground in the signals — quote specific complaint language where possible.",
  "target_consumer": "Detailed consumer persona (age, city tier, lifestyle) — e.g. '<age range> in <tier-1 city> with <specific situation>'",
  "market_size_estimate": "e.g. '₹<X>Cr Indian <category> market, <subsegment> <Y>% penetration'",
  "why_now": "Timing: global brand/category rising, format shift, India arbitrage window, regulation change. Name the specific global signal (brand, trend, platform) that is moving.",
  "hero_product": "Representative SKU that anchors the category (format, key ingredients/materials, price). Price ≥₹{min_aov} or note bundle path.",
  "hero_product_detail": "Brief product description for context: physical form, use ritual, key ingredients, and explicit India contrast vs 2-3 existing brands (brand + SKU + price + what they fail at). 3-4 sentences.",
  "aov_estimate": "e.g. '₹<price>'",
  "margin_estimate": "e.g. '<X>-<Y>%'",
  "capital_required_estimate": "Rough seed-stage capital context — e.g. '₹<X>-<Y>L to establish category presence'",
  "first_year_revenue_estimate": "Rough Y1 market-sizing reference — e.g. '₹<X>-<Y>L if 0.1% of addressable market captured'",
  "sourcing_approach": "Brief: contract mfg / white-label / import + repack. MOQ context.",
  "gtm_tactics": "Ideal category-building playbook — what distribution and marketing would a well-funded D2C brand use to win this category in India? 2-3 tactics.",
  "brand_angle": "Primary positioning: 'honest' | 'premium' | 'playful' | 'scientific' | 'heritage' | 'indulgent' | 'community' | 'functional'. Pick genuinely.",
  "distribution_channels": "Natural fit channels for this category in India",
  "ai_angle": "'AI-formulated / AI-personalized' or 'none'",
  "word_of_mouth_potential": "1-10 how viral/shareable this category is in India",
  "idea_rationale": "3-4 sentences: (1) global signals triggering this, (2) the India whitespace, (3) key risk/assumption to validate for fund diligence",
  "competitors_india": "",
  "reference_brands_global": "US/Japan/EU brands that prove this category works globally",
  "wedge": "1-2 sentences: which 2-3 India incumbents exist (brand + SKU + price) and the ONE dimension a new entrant can beat them on.",
  "lenses_fired": "comma-separated: geo_arbitrage, rising_brand_gap, complaint_cluster, format_shift, etc.",
  "contributing_signal_ids": ["signal_id_1", "signal_id_2"],
  "source_signal": "primary collector (e.g. 'amazon_us', 'reddit_us', 'rising_brands')",
  "source_urls": ["url1", "url2", "url3"],
  "comparable_products_global": ["Brand/product from US/EU/Japan/Korea proving the category globally"],
  "opportunity_type": "geo_arbitrage | complaint_cluster | format_shift | unbranded_market | rising_brand_gap | wildcard",
  "investability_read": "Two-part string joined by a newline. Line 1: 'India status: <unfilled | weak incumbents | crowded> — <one-line justification of the competitive landscape>'. Lines 2-3: a frank two-line take on whether this is a fundable early-stage consumer/D2C bet for an India fund (mention ticket size fit, time-to-leadership, category size), or why it is too small / commoditized / capital-intensive."
}}

IMPORTANT — source honesty rules:
1. source_urls: Include ALL URLs from the signals that contributed to this idea. Never fabricate URLs.
2. comparable_products_global: Include brand/product names from US/EU/Japan/Korea that prove this category works globally. These are the reference point for what "good" looks like. Only include if genuinely relevant.
3. idea_rationale: If a category angle came from the profile rather than the signals, say so explicitly.
4. investability_read: Be honest about crowding and capital intensity — do not default to "unfilled" if incumbents exist. The fund needs accurate category assessments, not optimistic framing."""


def _make_idea_hash(category: str, hero_product: str) -> str:
    """Hash category + hero concept for dedup."""
    import re
    stop_words = {"a", "an", "the", "for", "of", "in", "on", "at", "to", "with", "and", "or", "is", "it"}
    text = f"{category} {hero_product}".lower()
    words = re.sub(r"[^a-z0-9 ]", "", text).split()
    words = sorted(w for w in words if w not in stop_words)
    return hashlib.sha256(" ".join(words).encode()).hexdigest()[:16]


def generate_ideas(
    signals: list[NormalizedSignal],
    profile: dict,
    recent_titles: list[str] = None,
    max_tool_rounds: int = 4,
) -> list[IdeaDict]:
    """Generate D2C product ideas from normalized signals."""
    if not signals:
        return []

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = GENERATION_MODEL

    system_prompt = _build_system_prompt(profile)
    _emit_progress(f"idea generation: synthesizing from {len(signals)} signals (the slowest single step, typically 5-9 min — Sonnet does multiple web_search tool calls + one large JSON output)")

    # Format signals for the prompt
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
            "\n\nALREADY EXPLORED — do NOT generate ideas that are the same concept as these, "
            "even if you rename the brand or rephrase the product. For example, if 'protein chickpea chips' "
            "is listed, do NOT generate 'masala roasted chickpea snacks' — same core product.\n"
            + "\n".join(f"- {t}" for t in recent_titles[:80])
        )

    from utils.config import MAX_IDEAS_PER_RUN
    max_ideas = MAX_IDEAS_PER_RUN

    user_prompt = f"""Here are {len(signals)} validated D2C consumer signals. Generate {max_ideas} category opportunity memos for an India-focused consumer/D2C fund.

Target: {max_ideas} ideas total, at most 1 wildcard.
0-2 ideas from power consumer categories (kombucha, apparel, shoes, protein, sauces/condiments, fitness).
{existing_str}

DIVERSITY ACROSS THE 5 IDEAS — to avoid 5 ideas reading like variations of the same template:
- LENS PRIORITY: Bias toward `geo_arbitrage` and `rising_brand_gap` — these are the fund's primary mandate ("rising globally, unfilled in India"). `geo_arbitrage` may appear up to 3 times across the 5 ideas. All other opportunity_types should not repeat more than 2 times. Use at least 3 DIFFERENT values for `opportunity_type` across the 5 ideas.
- Use at least 3 DIFFERENT values for `brand_angle` across the 5 ideas. Do not repeat any brand_angle more than 2 times. 'honest' is overused — only use it when transparency is the actual differentiator.

Remember your self-evaluation step: only emit ideas you'd confidently recommend to a fund IC.
TOOL USE LIMIT: Use at most 3 searches total, only for market sizing or competitor checks you are genuinely uncertain about.
Output JSON immediately after.

Signals:
{signals_text}

Return ONLY a JSON array starting with ```json"""

    messages = [{"role": "user", "content": user_prompt}]
    text = ""

    for _ in range(max_tool_rounds):
        for attempt in range(3):
            try:
                # Streaming is required by the Anthropic API for requests whose
                # predicted output exceeds 10 minutes (max_tokens=24000 triggers this).
                # get_final_message() returns a Message with the same shape that
                # messages.create() would have returned, so downstream code is unchanged.
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
                    logger.warning(f"[idea_agent] API overloaded — retrying in {wait}s (attempt {attempt + 1}/3)")
                    time.sleep(wait)
                else:
                    raise

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if tool_uses:
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for tu in tool_uses:
                logger.info(f"[idea_agent] tool: {tu.name}")
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
        logger.warning("[idea_agent] max tool rounds reached — forcing final output")
        messages.append({"role": "user", "content": (
            "You have reached the tool use limit. "
            "Output your final JSON array of D2C product ideas now, based on what you have. "
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
    """Parse JSON output into IdeaDict objects."""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        data = json.loads(text.strip())
    except Exception as e:
        logger.warning(f"[idea_agent] failed to parse JSON: {e} — attempting truncation recovery")
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
                logger.info(f"[idea_agent] truncation recovery succeeded — {len(data)} ideas recovered")
            except Exception:
                logger.warning("[idea_agent] truncation recovery failed — returning empty")
                return []
        else:
            return []

    results = []
    run_date = datetime.utcnow().strftime("%Y-%m-%d")

    def _str_field(item: dict, key: str, default: str = "") -> str:
        """Coerce a JSON field to a string. Sonnet sometimes returns string
        fields as lists or numbers — this normalises them so downstream code
        can trust the type. Lists get joined with ", ".
        """
        value = item.get(key, default)
        if value is None:
            return default
        if isinstance(value, list):
            return ", ".join(str(v).strip() for v in value if v)
        if not isinstance(value, str):
            return str(value)
        return value

    for item in data:
        if not isinstance(item, dict) or not item.get("title"):
            continue

        title = item["title"]
        category = item.get("category", "")
        hero_product = item.get("hero_product", "")
        idea_hash = _make_idea_hash(category, hero_product or title)

        # Parse investability_read — LLM may return a dict or a string.
        ir_raw = item.get("investability_read", "")
        if isinstance(ir_raw, dict):
            india_status = ir_raw.get("india_status", "")
            fundability = ir_raw.get("fundability_take", "")
            ir_str = "\n".join(filter(None, [india_status, fundability]))
        else:
            ir_str = str(ir_raw) if ir_raw else ""

        idea = IdeaDict(
            idea_id=str(uuid.uuid4()),
            run_date=run_date,
            category=category,
            title=title,
            tagline=item.get("tagline", ""),
            problem=item.get("problem", ""),
            target_consumer=_str_field(item, "target_consumer"),
            market_size_estimate=_str_field(item, "market_size_estimate"),
            why_now=_str_field(item, "why_now"),
            hero_product=hero_product,
            hero_product_detail=_str_field(item, "hero_product_detail"),
            aov_estimate=_str_field(item, "aov_estimate"),
            margin_estimate=_str_field(item, "margin_estimate"),
            capital_required_estimate=_str_field(item, "capital_required_estimate"),
            first_year_revenue_estimate=_str_field(item, "first_year_revenue_estimate"),
            sourcing_approach=_str_field(item, "sourcing_approach"),
            gtm_tactics=_str_field(item, "gtm_tactics"),
            brand_angle=_str_field(item, "brand_angle"),
            distribution_channels=_str_field(item, "distribution_channels"),
            ai_angle=_str_field(item, "ai_angle", default="none"),
            word_of_mouth_potential=_str_field(item, "word_of_mouth_potential"),
            idea_rationale=_str_field(item, "idea_rationale"),
            competitors_india="",  # filled by competitor enrichment later
            reference_brands_global=_str_field(item, "reference_brands_global"),
            wedge=_str_field(item, "wedge"),
            lenses_fired=_str_field(item, "lenses_fired"),
            contributing_signals=", ".join(item.get("contributing_signal_ids", [])),
            source_signal=item.get("source_signal", ""),
            source_url="\n".join(item.get("source_urls", [])[:6]),
            opportunity_type=item.get("opportunity_type", "complaint_cluster"),
            comparable_product_images="",  # filled by competitor enrichment
            time_sensitive=False,
            idea_hash=idea_hash,
            investability_read=ir_str,
        )
        results.append(idea)

    logger.info(f"[idea_agent] generated {len(results)} ideas")
    _emit_progress(f"idea generation: produced {len(results)} candidate ideas")
    return results


def _emit_progress(message: str) -> None:
    """Print a 4-space-indented progress line to stdout AND append to
    user_data/progress.txt so the chat's Monitor can relay it."""
    from pathlib import Path as _Path
    indented = f"    {message}"
    print(indented, flush=True)
    try:
        progress_path = _Path(__file__).resolve().parent.parent.parent / "user_data" / "progress.txt"
        progress_path.write_text(indented + "\n")
    except Exception:
        pass
