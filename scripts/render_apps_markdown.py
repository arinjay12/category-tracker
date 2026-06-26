"""
render_apps_markdown.py — render scored app ideas as readable markdown.

Parallel to render_markdown.py (physical products) but tuned for consumer apps:
- Shows monetization_model + growth_loop instead of AOV/margin
- Sub-score labels: India Readiness, Monetization Fit, India Gap, Growth Loop
- No capital ceiling diagnostic (apps have different cost structure)
"""
from __future__ import annotations

import time
from datetime import datetime, timezone


def _format_score_bar(score: float, max_score: int = 10) -> str:
    filled = round(score)
    return "■" * filled + "□" * (max_score - filled) + f" {score}/{max_score}"


def _badge(opportunity_type: str) -> str:
    badges = {
        "geo_arbitrage":    "🌍 Geo-arbitrage",
        "rising_brand_gap": "🚀 Rising brand gap",
        "complaint_cluster":"📣 Complaint cluster",
        "format_shift":     "🔄 Format shift",
        "unbranded_market": "🏷️ Unbranded market",
        "wildcard":         "🎲 Wildcard",
    }
    b = badges.get(opportunity_type, "")
    return b


def _safe(value, default: str = "—") -> str:
    if value is None or value == "":
        return default
    return str(value)


def render_app_ideas(ideas: list, run_started: float | None = None, profile: dict | None = None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    duration = f" · ran in {round(time.time() - run_started, 1)}s" if run_started else ""

    passed = [i for i in ideas if getattr(i, "eval_status", "passed") == "passed"]
    rejected = [i for i in ideas if getattr(i, "eval_status", "passed") == "rejected"]

    summary = f"{len(passed)} passed · {len(rejected)} flagged" if rejected else f"{len(passed)} ideas"

    from utils.app_categories import APP_CATEGORIES

    def _cat_label(slug: str) -> str:
        label, _ = APP_CATEGORIES.get(slug, (slug, ""))
        return label

    out: list[str] = [
        f"# India App Whitespace Tracker — TDV (auto-generated) · {now}{duration}\n",
        f"_{summary}. Passed ideas first (sorted by score), flagged ideas below with reasons._\n",
        "---\n",
    ]

    for i, idea in enumerate(ideas, 1):
        is_rejected = getattr(idea, "eval_status", "passed") == "rejected"
        status_badge = "⚠️ Flagged" if is_rejected else "✓ Passed"
        badge = _badge(idea.opportunity_type)
        header = f"## {i}. {idea.title}  ·  [{idea.score_composite:.1f}/10]  ·  {status_badge}"
        if badge:
            header += f"  ·  {badge}"
        out.append(header)
        out.append(f"_{idea.tagline}_  ·  **Category:** {_cat_label(idea.category)}\n")

        if is_rejected:
            raw_reasons = _safe(getattr(idea, "eval_reasons", ""), "")
            out.append(f"> **Why flagged:** {raw_reasons}\n")

        out.append(f"**Global signal (Why now)**\n{_safe(idea.why_now)}\n")
        out.append(f"**Problem**\n{_safe(idea.problem)}\n")
        out.append(f"**Target consumer**\n{_safe(idea.target_consumer)}\n")

        investability_text = _safe(getattr(idea, "investability_read", ""), "")
        if investability_text and investability_text != "—":
            lines = investability_text.split("\n")
            india_status_line = lines[0].strip() if lines else ""
            fundability_lines = "\n".join(l for l in lines[1:] if l.strip())
        else:
            india_status_line = ""
            fundability_lines = ""

        if india_status_line:
            out.append(f"**India status**\n{india_status_line}\n")
        else:
            out.append("**India status**\n—\n")

        out.append(f"**Who's already here (India)**\n{_safe(idea.competitors_india)}\n")
        if _safe(getattr(idea, "reference_brands_global", ""), "") not in ("", "—"):
            out.append(f"**Reference apps (global)**\n{idea.reference_brands_global}\n")

        if fundability_lines or investability_text:
            out.append(f"**Investability read**\n{fundability_lines if fundability_lines else investability_text}\n")
        else:
            out.append("**Investability read**\n—\n")

        exit_comps_text = _safe(getattr(idea, "exit_comps", ""), "")
        repeat_purchase_text = _safe(getattr(idea, "repeat_purchase", ""), "")
        india_timing_text = _safe(getattr(idea, "india_timing", ""), "")
        if exit_comps_text not in ("", "—"):
            out.append(f"**Exit comps**\n{exit_comps_text}\n")
        if repeat_purchase_text not in ("", "—"):
            out.append(f"**Retention (DAU/WAU/MAU)**\n{repeat_purchase_text}\n")
        if india_timing_text not in ("", "—"):
            out.append(f"**India timing**\n{india_timing_text}\n")

        # App-specific fields
        monetization_text = _safe(getattr(idea, "monetization_model", ""), "")
        growth_loop_text = _safe(getattr(idea, "growth_loop", ""), "")
        if monetization_text not in ("", "—"):
            out.append(f"**Monetization model**\n{monetization_text}\n")
        if growth_loop_text not in ("", "—"):
            out.append(f"**Growth loop**\n{growth_loop_text}\n")

        # Sub-scores with app-specific labels
        out.append("**Sub-scores**")
        out.append(f"- Demand signal:      `{_format_score_bar(idea.score_demand)}`")
        out.append(f"- India readiness:    `{_format_score_bar(idea.score_launchability)}`")
        out.append(f"- Monetization fit:   `{_format_score_bar(idea.score_capital_fit)}`")
        competition_headroom = 10 - idea.score_competition
        out.append(f"- Competition room:   `{_format_score_bar(competition_headroom)}`")
        out.append(f"- Growth loop:        `{_format_score_bar(idea.score_distribution)}`")
        arb = getattr(idea, "score_arbitrage", None)
        if arb is not None and arb > 0:
            out.append(f"- India gap:          `{_format_score_bar(arb)}`")
        out.append("")

        urls = getattr(idea, "source_urls", None) or []
        if isinstance(urls, str):
            urls = [u.strip() for u in urls.split(",") if u.strip()]
        if not urls:
            # Fall back to source_url (newline-separated)
            src = getattr(idea, "source_url", "")
            if src:
                urls = [u.strip() for u in src.split("\n") if u.strip()]
        if urls:
            out.append("**Source signals**")
            for url in urls[:5]:
                out.append(f"- {url}")
            out.append("")

        out.append("---\n")

    out.append(_build_overview_table(ideas, _cat_label))
    out.append(
        "---\n\n"
        "_Run saved. Ask me to **show past runs**, change tracked categories, "
        "or **run the app tracker again**. Full output: `user_data/latest_apps.md`_\n"
    )

    return "\n".join(out)


def _build_overview_table(ideas: list, cat_label_fn) -> str:
    if not ideas:
        return ""

    lines = [
        "## Overview",
        "",
        "| # | App Idea | Score | Status | Category |",
        "|---|----------|-------|--------|----------|",
    ]
    for i, idea in enumerate(ideas, 1):
        is_rejected = getattr(idea, "eval_status", "passed") == "rejected"
        status = "⚠️ Flagged" if is_rejected else "✓ Passed"
        title = (idea.title or "").replace("|", "\\|")
        tagline = (_safe(idea.tagline, "") or "").replace("|", "\\|").replace("\n", " ").strip()
        cat = cat_label_fn(idea.category) if idea.category else "—"
        lines.append(f"| {i} | **{title}** | {idea.score_composite:.1f}/10 | {status} | {tagline[:80]}<br>_{cat}_ |")

    lines.append("")
    return "\n".join(lines)
