"""
TDV Consumer Whitespace Tracker — Streamlit UI

Wraps the india-d2c pipeline with a simple web interface.
Users supply their own API keys (Anthropic + Exa) per session — never stored.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import yaml
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent
USER_DATA = ROOT / "user_data"
SCRIPTS_DIR = ROOT / "scripts"
LOCK_FILE = USER_DATA / ".running"

# Must stay in sync with scripts/setup.py CATEGORIES
CATEGORIES: dict[str, tuple[str, str]] = {
    "beauty":             ("Beauty",             "makeup, skincare, haircare, fragrance"),
    "personal_care":      ("Personal Care",       "bath/body, oral, hygiene, shaving, deodorant"),
    "food_cpg":           ("Food & CPG",          "snacks, beverages, condiments (non-functional)"),
    "home":               ("Home",               "cleaning, laundry, kitchen tools, decor, candles, home fragrance"),
    "pet":                ("Pet",                "food, accessories, grooming, supplements"),
    "wellness":           ("Wellness",           "adaptogens, topicals, ingestible wellness, functional gummies"),
    "sexual_wellness":    ("Sexual Wellness",    "intimacy products, hormonal, performance (premium)"),
    "fashion_apparel":    ("Fashion & Apparel",  "women's, men's, premium/functional apparel"),
    "jewellery_watches":  ("Jewellery & Watches","fashion jewellery, fine, lab-grown, smartwatches"),
    "fitness_nutrition":  ("Fitness & Nutrition","gear, supplements, protein, functional foods, pre/post-workout"),
    "cognitive_wellness": ("Cognitive Wellness", "nootropics, focus supplements, brain health, lion's mane, bacopa"),
    "spiritual_lifestyle":("Spiritual Lifestyle","premium incense, meditation tools, yoga props, puja accessories"),
    "sleep_recovery":     ("Sleep & Recovery",   "sleep supplements, magnesium, glycine, recovery tools"),
}

DISTRIBUTION_CHANNELS = [
    "affiliate_coupon", "direct_email_whatsapp_sms", "influencer",
    "marketplace_ppc", "organic_social", "paid_digital_ads",
    "pr_press", "quick_commerce", "referral_virality", "seo_content",
]


def _write_profile(category_slug: str) -> None:
    """Write a fresh profile.yaml for this run with the selected category active."""
    USER_DATA.mkdir(exist_ok=True)
    profile = {
        "market": {"capital_ceiling_lakhs": 20},
        "categories": {
            cat: {
                "weight": 1.0 if cat == category_slug else 0.0,
                "includes": desc,
            }
            for cat, (label, desc) in CATEGORIES.items()
        },
        "distribution": {ch: 2 for ch in DISTRIBUTION_CHANNELS},
        "hard_excludes": {"preset": [], "custom": []},
    }
    with open(USER_DATA / "profile.yaml", "w", encoding="utf-8") as f:
        yaml.dump(profile, f, default_flow_style=False, allow_unicode=True)


# ── Page setup ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="TDV Category Tracker",
    page_icon="🔍",
    layout="wide",
)

st.title("TDV Consumer Whitespace Tracker")
st.caption("Spot rising global categories before they land in India.")

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("API Keys")
    st.caption("Used for this run only — never stored on disk.")

    anthropic_key = st.text_input(
        "Anthropic API Key",
        type="password",
        placeholder="sk-ant-api03-...",
    )
    exa_key = st.text_input(
        "Exa API Key",
        type="password",
        placeholder="xxxxxxxx-xxxx-...",
    )

    st.divider()

    if LOCK_FILE.exists():
        st.warning("A run is currently in progress.")
        if st.button("Clear stuck run", help="Use if a previous run crashed and left the lock file behind."):
            LOCK_FILE.unlink(missing_ok=True)
            st.success("Cleared. You can run again.")
            st.rerun()

    st.divider()
    st.caption(
        "**How it works:** Searches Indian marketplaces, Reddit, US D2C publications, "
        "and India funding news for your chosen category — then Claude Sonnet synthesises "
        "5 VC-lens investment memos.\n\n"
        "**Typical runtime:** 10–15 minutes.\n\n"
        "**Cost per run:** ~$0.50–1.50 in API credits (your keys, your bill)."
    )

# ── Main area ─────────────────────────────────────────────────────────────────

category_slug = st.selectbox(
    "Category to track",
    options=list(CATEGORIES.keys()),
    format_func=lambda slug: CATEGORIES[slug][0],
)

cat_label, cat_scope = CATEGORIES[category_slug]
st.caption(f"_{cat_scope}_")

keys_ready = bool(anthropic_key and exa_key)
locked = LOCK_FILE.exists()

run_btn = st.button(
    f"Run tracker — {cat_label}",
    type="primary",
    disabled=not keys_ready or locked,
)

if not keys_ready:
    st.info("Enter your Anthropic and Exa API keys in the sidebar to run.")
elif locked:
    st.warning("A run is already in progress. See the sidebar to clear it if it's stuck.")

# ── Execution ─────────────────────────────────────────────────────────────────

if run_btn and keys_ready and not locked:
    LOCK_FILE.write_text("running")
    _write_profile(category_slug)

    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = anthropic_key
    env["EXA_API_KEY"] = exa_key

    st.subheader(f"Running: {cat_label}")
    log_box = st.empty()
    log_lines: list[str] = []

    try:
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPTS_DIR / "find_ideas.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(ROOT),
        )

        assert proc.stdout is not None
        for line in proc.stdout:
            stripped = line.rstrip()
            if stripped:
                log_lines.append(stripped)
                log_box.code("\n".join(log_lines[-15:]), language=None)

        proc.wait()

    except Exception as e:
        st.error(f"Unexpected error launching pipeline: {e}")
        LOCK_FILE.unlink(missing_ok=True)
        st.stop()

    finally:
        LOCK_FILE.unlink(missing_ok=True)

    if proc.returncode == 0:
        output_path = USER_DATA / "latest_ideas.md"
        if output_path.exists():
            content = output_path.read_text(encoding="utf-8")
            log_box.empty()
            st.success(f"Done — {cat_label} tracker complete.")
            st.divider()
            st.markdown(content)
            st.download_button(
                label="Download output (.md)",
                data=content,
                file_name=f"TDV_{category_slug}_{time.strftime('%Y%m%d')}.md",
                mime="text/markdown",
            )
        else:
            st.error("Pipeline finished but output file is missing. Check the log above.")
    else:
        st.error(
            f"Pipeline failed (exit code {proc.returncode}). "
            "Check the log above — the most common causes are an invalid API key "
            "or an Exa rate limit."
        )
