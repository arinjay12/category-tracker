#!/usr/bin/env python3
"""
find_apps.py — run the Consumer App Whitespace pipeline for one category.

Pipeline:
  4 collectors (Product Hunt, VC signals, Reddit, India gap)
  → pre-filter → enrichment → app idea generation
  → app evaluation → markdown output

Output: user_data/latest_apps.md

Usage:
    ./venv/bin/python scripts/find_apps.py --category ai_tools
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS_DIR.parent
USER_DATA = SKILL_ROOT / "user_data"
sys.path.insert(0, str(SCRIPTS_DIR))

import yaml
from dotenv import load_dotenv

load_dotenv(USER_DATA / ".env", override=False)

from utils.app_categories import APP_CATEGORIES

TOTAL_STAGES = 5
_current_stage = 0


def progress(message: str, *, done: bool = False) -> None:
    global _current_stage
    if done:
        prefix = "✓"
    else:
        _current_stage += 1
        prefix = f"[{_current_stage}/{TOTAL_STAGES}]"
    line = f"{prefix} {message}"
    print(line, flush=True)
    _write_status(line)


def substep(message: str) -> None:
    indented = f"    {message}"
    print(indented, flush=True)
    _write_status(indented)


def _write_status(message: str) -> None:
    try:
        (USER_DATA / "progress.txt").write_text(
            f"{datetime.now(timezone.utc).strftime('%H:%M:%S')}  {message}\n"
        )
    except Exception:
        pass


def check_env() -> None:
    missing = [k for k in ("EXA_API_KEY", "ANTHROPIC_API_KEY") if not os.getenv(k)]
    if missing:
        print(
            "ERROR: missing API key(s): " + ", ".join(missing),
            file=sys.stderr,
        )
        sys.exit(1)


def prefilter_signals(signals: list) -> list:
    keep = []
    for s in signals:
        signal_type = s.extra.get("signal_type", "")
        if signal_type in ("white_space", "rising_brand", "geo_arbitrage"):
            keep.append(s)
            continue
        if s.extra.get("has_comments"):
            keep.append(s)
            continue
        if len(s.body) < 40 and len(s.title) < 20:
            continue
        keep.append(s)
    return keep


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Consumer App Whitespace pipeline.")
    parser.add_argument(
        "--category", required=True,
        choices=list(APP_CATEGORIES.keys()),
        help="App category slug to track (e.g. ai_tools, personal_finance)",
    )
    args = parser.parse_args()

    category_slug = args.category
    cat_label, cat_desc = APP_CATEGORIES[category_slug]

    print(f"App Whitespace Tracker — category: {cat_label}\n", flush=True)
    start = time.time()

    try:
        (USER_DATA / "progress.txt").write_text("Starting app pipeline...\n")
    except Exception:
        pass

    check_env()

    # Synthetic profile — just the picked category, no physical product settings
    profile = {
        "categories": {
            cat: {"weight": 1.0 if cat == category_slug else 0.0}
            for cat in APP_CATEGORIES
        }
    }

    from utils.db import init_db, is_duplicate_idea, mark_idea_seen, record_run, record_idea
    init_db()

    # ----- Stage 1: Collection -----
    progress(f"Collecting signals: Product Hunt, VC publications, Reddit, India gap ({cat_label})")

    from collectors.product_hunt_collector import ProductHuntCollector
    from collectors.vc_consumer_signals_collector import VCConsumerSignalsCollector
    from collectors.reddit_app_collector import RedditAppCollector
    from collectors.india_app_gap_collector import IndiaAppGapCollector

    raw_signals: list = []
    collection_errors: list[str] = []

    for label, ctor in (
        ("Product Hunt",         ProductHuntCollector),
        ("VC consumer signals",  VCConsumerSignalsCollector),
        ("Reddit app signals",   RedditAppCollector),
        ("India app gap",        IndiaAppGapCollector),
    ):
        try:
            collector = ctor(profile=profile)
            sigs = collector.fetch_safe() if hasattr(collector, "fetch_safe") else collector.fetch()
            raw_signals.extend(sigs)
            substep(f"{label}: {len(sigs)} signals")
        except Exception as e:
            substep(f"{label}: failed ({e})")
            collection_errors.append(label)

    if not raw_signals:
        print("\nNo signals collected. Check your Exa API key and network.", file=sys.stderr)
        return 1

    # ----- Stage 2: Pre-filter + enrichment -----
    filtered = prefilter_signals(raw_signals)
    progress(f"Enriching {len(filtered)} signals with Claude Sonnet...")

    try:
        from agents import signal_enrichment_agent
        normalized = signal_enrichment_agent.enrich_signals(filtered, profile)
    except Exception as e:
        substep(f"enrichment failed: {e} — falling back to raw signals")
        from utils.signal_schema import NormalizedSignal
        normalized = [
            NormalizedSignal(
                id=s.id,
                signal_type=s.extra.get("signal_type", "unknown"),
                summary=s.title,
                category_tags=[s.extra.get("category", "")],
                consumer_tags=[],
                evidence_strength="low",
                recency=s.created_at,
                key_entities=[],
                raw_source=s.source,
                raw_url=s.url,
                enrichment_notes=s.body[:300] if s.body else "",
            )
            for s in filtered
        ]

    if not normalized:
        print("\nNo enriched signals. Pipeline cannot continue.", file=sys.stderr)
        return 1

    # ----- Stage 3: App idea generation -----
    progress(f"Generating app opportunity memos from {len(normalized)} signals...")

    try:
        from agents import app_idea_agent
        raw_ideas = app_idea_agent.generate_app_ideas(
            signals=normalized,
            profile=profile,
        )
    except Exception as e:
        print(f"\nApp idea generation failed: {e}", file=sys.stderr)
        return 1

    if not raw_ideas:
        print("\nNo ideas generated.", file=sys.stderr)
        return 1

    new_ideas = [i for i in raw_ideas if not is_duplicate_idea(i.idea_hash)]
    substep(f"{len(new_ideas)} new / {len(raw_ideas)} generated (after dedup)")

    if not new_ideas:
        print("\nAll generated ideas were duplicates. Try again or wait for new signals.", file=sys.stderr)
        return 0

    # ----- Stage 4: Evaluation + scoring -----
    progress("Scoring and filtering app ideas...")
    try:
        from agents import app_evaluation_agent
        scored = app_evaluation_agent.evaluate_app_ideas(ideas=new_ideas, profile=profile)
    except Exception as e:
        print(f"\nEvaluation failed: {e}", file=sys.stderr)
        return 1

    def _sort_key(i):
        passed = i.eval_status == "passed"
        rank_bucket = 0 if passed else 1
        wildcard_penalty = 1 if (passed and i.opportunity_type == "wildcard") else 0
        return (rank_bucket + wildcard_penalty, -i.score_composite)

    scored.sort(key=_sort_key)

    # ----- Stage 5: Render markdown -----
    progress("Writing ideas to user_data/latest_apps.md...")
    from render_apps_markdown import render_app_ideas
    rendered_md = render_app_ideas(scored, run_started=start, profile=profile)
    out_path = USER_DATA / "latest_apps.md"
    out_path.write_text(rendered_md, encoding="utf-8")

    snapshot = [
        {
            "index": i,
            "idea_id": getattr(idea, "idea_id", None),
            "title": idea.title,
            "category": idea.category,
            "tagline": idea.tagline,
            "score_composite": idea.score_composite,
            "opportunity_type": idea.opportunity_type,
        }
        for i, idea in enumerate(scored, 1)
    ]
    snapshot_json = json.dumps(
        {"run_at": datetime.now(timezone.utc).isoformat(), "ideas": snapshot},
        indent=2,
    )
    (USER_DATA / "latest_apps.json").write_text(snapshot_json, encoding="utf-8")

    runs_dir = USER_DATA / "runs"
    runs_dir.mkdir(exist_ok=True)
    run_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    (runs_dir / f"{run_stamp}_apps_{category_slug}.md").write_text(rendered_md, encoding="utf-8")
    (runs_dir / f"{run_stamp}_apps_{category_slug}.json").write_text(snapshot_json, encoding="utf-8")

    for idea in scored:
        mark_idea_seen(idea.idea_hash, idea.title)
        record_idea(
            idea_id=idea.idea_id,
            run_at=idea.run_date,
            title=idea.title,
            score_composite=idea.score_composite,
            source=idea.source_signal,
            category_tags=idea.category,
            opportunity_type=idea.opportunity_type,
            hero_product="",
        )

    record_run({
        "run_at": datetime.now(timezone.utc).isoformat(),
        "signals_collected": len(raw_signals),
        "ideas_generated": len(raw_ideas),
        "ideas_written": len(scored),
        "collectors_run": "app_pipeline",
        "pipelines_run": "apps",
        "duration_seconds": round(time.time() - start, 1),
        "errors": len(collection_errors),
        "notes": f"category={category_slug}",
    })

    duration = round(time.time() - start, 1)
    done_msg = (
        f"Done in {duration}s. {len(raw_signals)} signals → {len(raw_ideas)} ideas "
        f"→ {len(scored)} evaluated."
    )
    print(f"\n{done_msg}", flush=True)
    print(f"Read: {out_path}", flush=True)
    _write_status(f"DONE: {done_msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
