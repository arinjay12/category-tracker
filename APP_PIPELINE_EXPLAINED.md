# India App Whitespace Pipeline — How It Works

> **One-line summary:** This pipeline watches what consumer apps are exploding in the US right now, checks whether India has a credible equivalent, and generates investment memos for categories where the answer is no.

---

## Why this exists

India has a 12–36 month lag behind the US on consumer app adoption. The categories that hit escape velocity in the US between 2023 and 2025 — AI productivity tools, niche mental health apps, personal finance apps for young adults — will find their Indian equivalents between 2025 and 2028. The window to back the India-first builder in those categories is right now, before the category is obvious.

The physical product pipeline (Products tab) looks at what physical D2C goods are rising globally and unserved in India. This pipeline does the same thing for consumer apps and SaaS — but with a completely different signal set, different evaluation criteria, and different output fields, because the economics of apps are nothing like the economics of physical goods.

**No AOV floor. No capital ceiling. No sourcing complexity.** Instead: monetization model, growth loop, India readiness, DAU/WAU/MAU retention thesis.

---

## The 10 Categories

The pipeline tracks these app categories:

| Slug | Label | Scope |
|------|-------|-------|
| `ai_tools` | AI Consumer Tools | AI assistants, AI writing, AI creative, AI productivity for everyday consumers |
| `personal_finance` | Personal Finance | Budgeting, expense tracking, investment apps, savings, wealth management |
| `mental_health` | Mental Health | Therapy apps, meditation, mood tracking, anxiety management, sleep tech |
| `fitness_apps` | Fitness & Health Apps | Workout tracking, nutrition logging, health monitoring, wearable companion apps |
| `creator_tools` | Creator & Freelancer | Content creation tools, portfolio builders, client management, creator monetization |
| `social_community` | Social & Community | Niche social networks, community platforms, interest-based apps |
| `edtech` | Learning & Edtech | Micro-learning, skill building, language apps, certifications |
| `home_local` | Home & Local Services | Home management, on-demand local services, hyperlocal discovery |
| `entertainment` | Entertainment & Media | Audio content, casual games, short-form interactive, IP-based apps |
| `dating_social` | Dating & Relationships | Niche dating, relationship tools, social matching |

You pick one category per run from the Streamlit UI. The pipeline focuses all 4 collectors and the generation prompt on that single category.

---

## The 5-Stage Pipeline

```
Stage 1: Collection         ← 4 collectors, Exa searches only, no Claude
Stage 2: Enrichment         ← Claude Sonnet validates and normalises signals
Stage 3: Idea generation    ← Claude Sonnet writes 5 app opportunity memos
Stage 4: Evaluation         ← Claude Haiku scores each memo on 6 dimensions
Stage 5: Render             ← Python renders scored memos to Markdown
```

Each stage feeds the next. Nothing is fabricated — every claim in the output traces back to a URL the collector found or a tool call the model made.

---

## Stage 1: Collection

**What it does:** Fires 4 separate collectors in parallel, each targeting a different signal type. All searches go through the Exa API (semantic web search). No Claude calls in this stage — pure data gathering.

**Target:** For a single category run, each collector runs 2–6 Exa queries, giving roughly 30–60 raw signals total before filtering.

---

### Collector 1 — Product Hunt

**What it looks for:** Consumer apps trending on Product Hunt right now.

Product Hunt is the strongest leading indicator for "what is getting early US consumer traction today." When an app gets featured and upvoted heavily, it means real users are adopting it — not just analysts writing about it. The lag from Product Hunt breakout to India mainstream is typically 12–24 months.

**Queries:** Two per category. One for recent launches (2025–2026), one for highly-upvoted products in the category.

**Example queries for `mental_health`:**
```
site:producthunt.com mental health meditation therapy app 2025 2026
site:producthunt.com mental health meditation therapy app upvotes featured launched
```

**Signal type it produces:** `rising_brand_gap` — a specific US app product is gaining traction and has no India equivalent.

---

### Collector 2 — VC Consumer Signals

**What it looks for:** Where institutional US money is concentrating in consumer apps.

If TechCrunch is covering a $20M Series A in "AI therapy apps," if a16z has published a thesis on "the future of personal finance apps," if Sequoia has made 3 investments in "creator monetization tools" in the last 18 months — that is a forward indicator of category importance. VC dollars follow conviction, and conviction follows data that's not yet public. By the time VC money concentrates in a category, the category is real.

**Sources:** TechCrunch funding coverage, a16z blog, Sequoia Capital blog, The Generalist.

**Queries:** Two per category. One for TechCrunch funding announcements, one for VC thesis posts.

**Example queries for `personal_finance`:**
```
site:techcrunch.com personal finance budgeting investment app consumer app raised funding 2025 2026
site:a16z.com OR site:sequoiacap.com OR site:thegeneralist.io personal finance budgeting investment app consumer startup investment thesis
```

**Signal type it produces:** `geo_arbitrage` — institutional money has validated this category in the US.

---

### Collector 3 — Reddit App Signals

**What it looks for:** Two distinct signal types from Reddit — US complaint clusters and India explicit demand.

Reddit is where real users vent about apps without PR filters. This collector mines two sub-signals:

**US complaint clusters** — Posts in US subreddits (`r/apps`, `r/androidapps`, `r/personalfinance`, `r/mentalhealth`, etc.) where users complain about a category and ask for alternatives. "I've tried every budgeting app and they all suck because..." is a gold mine. It tells you a category has demand but no dominant solution — which means the category is still open.

**India explicit demand** — Posts in India subreddits (`r/india`, `r/IndiaTech`, `r/bangalore`, `r/IndiaInvestments`, etc.) where users explicitly ask whether there's an Indian equivalent of something. "Is there a Duolingo equivalent for Indian languages?" is literally a user writing your investment thesis for you.

**Queries:** Two per category — one US complaint, one India demand. Different subreddits.

**Example queries for `mental_health`:**
```
site:reddit.com/r/mentalhealth OR site:reddit.com/r/therapy app complaints alternatives 2025
site:reddit.com/r/india mental health therapy app India recommendation gap
```

**Signal types it produces:**
- `complaint_cluster` — the US complaint query
- `explicit_demand` — the India demand query (highest confidence whitespace signal)

Per-category query pools are pre-written in the code (not just generic templates) — each category has Reddit-specific subreddits and keyword combinations chosen for that category's audience.

---

### Collector 4 — India App Gap

**What it looks for:** The highest-confidence signal type — explicit posts where users say "I want an Indian version of X."

This collector targets two very specific signal types:

**Whitespace posts:** Reddit and Quora posts containing phrases like "India version," "Indian alternative," or "India equivalent" in the context of the category. These are users who have already done the cross-country comparison themselves and are stating the gap directly.

**India startup funding:** Inc42, YourStory, and Entrackr coverage of Indian consumer app funding rounds in the same category. This tells you where Indian capital is already moving — which is both a validation signal (smart money sees the category) and a competitive signal (who is already funded).

**Queries:** Two per category:
```
"India version" OR "Indian alternative" OR "India equivalent" mental health meditation therapy app site:reddit.com OR site:quora.com

India mental health consumer app startup raised funding 2025 2026 site:inc42.com OR site:yourstory.com OR site:entrackr.com
```

**Signal types it produces:**
- `white_space` — explicit gap articulation from a real user
- `momentum` — India funding activity in the category

---

## Stage 2: Pre-filter + Enrichment

**What it does:** Claude Sonnet goes through the raw signals, verifies the ones it's uncertain about using web searches, and normalises all of them into a structured format.

**Pre-filter (Python, no LLM):** Before hitting Claude, a simple rule-based filter runs. Signals tagged `white_space`, `rising_brand`, or `geo_arbitrage` pass automatically. For everything else, signals with too-short body text (< 40 chars) and too-short title (< 20 chars) get dropped — they don't have enough content to enrich. This reduces noise before spending Claude tokens.

**Enrichment (Claude Sonnet with web search):** The remaining signals are batched (20 at a time) and sent to Claude Sonnet. The model has access to `web_search` and `fetch_page` tools. It uses these to:

- Verify whether a complaint is widespread (not a one-off) by searching for corroborating Reddit threads, review counts, etc.
- Check India-specific availability — does India already have a well-executed equivalent?
- Estimate evidence strength: **high** (100+ mentions across sources), **medium** (20–100), **low** (<20)

**What the enrichment agent is told to produce for each signal:**
```
signal_type:         complaint_cluster | explicit_demand | format_shift | momentum |
                     white_space | unbranded_market | geo_arbitrage | rising_brand_gap
summary:             one-line, specific — not "AI apps are popular" but "Indian users
                     on r/india asking for an Indian Headspace equivalent (15+ posts, 2024-2025)"
category_tags:       which of the 10 app categories this maps to
consumer_tags:       specific persona — ["urban_professionals_22_30", "fitness_enthusiasts"]
evidence_strength:   high / medium / low
key_entities:        brand names, specific apps, people mentioned
pain_acuity:         1–5 severity score for complaint signals (null for trend signals)
gap_dimensions:      what specifically is missing in India
geo_markets:         which global markets have this (US, EU, Japan, Korea)
enrichment_notes:    the actual analysis — what's the pain, who feels it, what's the gap
```

**Tool use limit:** Max 4 web searches per batch. The model is instructed to search only for signals it's genuinely uncertain about — not every signal. Signals from the India Gap collector (explicit "India version of X" posts) have high self-evident value and don't need verification.

**Output:** 8–15 high-quality `NormalizedSignal` objects per batch of 20 raw signals. Some raw signals get dropped (too weak, no India angle, already well-served). The survivors carry forward all the structured metadata the idea agent will use.

---

## Stage 3: App Idea Generation

**What it does:** Claude Sonnet takes the enriched signals and generates 5 investment memos — one per idea — in structured JSON.

**Model:** Claude Sonnet 4.6 (the same model handling this conversation). Used with streaming (required for long outputs) and tool access (can do additional web searches if uncertain about India market size or competition).

**Tool use limit:** Max 3 additional searches. The model is specifically instructed to output JSON immediately after tool use, not to search exhaustively.

---

### What the model is told

The system prompt establishes the lens:

> "Your mandate: identify consumer app categories that are EXPLODING in the US right now but haven't yet found their Indian equivalent. India has 700M+ smartphone users, UPI as the payment layer, and a young urban population hungry for consumer apps. There is typically a 12–36 month lag between US consumer app breakouts and their India equivalents."

**Lens priority (highest to lowest):**
1. `geo_arbitrage` — US app category with strong DAU/revenue growth, zero or weak India equivalent
2. `complaint_cluster` — Indian Reddit/Quora posts explicitly asking "is there an Indian app for X?"
3. `rising_brand_gap` — A specific US app brand dominating a category with no comparable Indian product
4. `format_shift` — A new app format (AI-native, voice-first) that Indian players haven't adopted
5. `unbranded_market` — Category exists in India but only through inferior/unbranded alternatives

**Self-evaluation before emitting each idea:**
The model is instructed to check before including any idea:
1. Is there genuine India whitespace? ("India has Zerodha" is not whitespace for personal finance apps — be specific about what sub-category is missing)
2. Is the US signal real and from 2024–2026? Not a category that peaked in 2020
3. Is there a viable monetization model for India's price-sensitive market?
4. Is the growth loop believable — what would make users invite other users?
5. Is this fundable at seed stage ($250K–$2M)?

**Diversity enforcement:** Across the 5 ideas, the model must use at least 3 different `opportunity_type` values, at least 3 different categories, and at least 3 different `brand_angle` values. This prevents 5 variations of the same template.

---

### What each idea contains

Every idea card has these fields:

| Field | What it contains |
|-------|-----------------|
| `title` | 3–5 word opportunity name (e.g. "Indian AI Journaling App") |
| `tagline` | One-sentence thesis: what's blowing up in the US, what's the India gap, why now |
| `problem` | 3–5 sentences: WHO feels it, how they cope today, WHY Indian options fall short |
| `target_consumer` | Specific persona: age, city, digital behaviour, income band |
| `market_size_estimate` | India TAM with methodology (not made up — tied to comps or population data) |
| `why_now` | Why this specific 2025–2027 window and not earlier or later |
| `monetization_model` | Freemium / subscription / transaction / ads + ₹ price point + India ARPU target |
| `growth_loop` | The specific viral/organic loop: what makes a user invite another user |
| `repeat_purchase` | DAU/WAU/MAU retention thesis: what brings users back daily/weekly |
| `brand_angle` | Primary positioning: honest / premium / playful / scientific / community / functional |
| `distribution_channels` | Primary organic acquisition: app store SEO, Instagram, word-of-mouth, community, etc. |
| `exit_comps` | One global exit proving this category is venture-fundable |
| `india_timing` | Early (3+ yrs behind US) / On-time (1–2 yrs) / Late (already seeded in India) |
| `idea_rationale` | 3–4 sentences: signals that triggered this, the specific India whitespace, key risk/assumption |
| `competitors_india` | Named Indian apps in this space (left blank here, filled in as a separate enrichment pass) |
| `reference_brands_global` | US/EU/JP apps that prove the category — brand + metric if known |
| `wedge` | Which Indian apps exist, and the ONE dimension a new entrant can beat them on |
| `investability_read` | Two-part frank take: India status (unfilled / weak incumbents / crowded) + fundability at seed |
| `opportunity_type` | geo_arbitrage / complaint_cluster / format_shift / unbranded_market / rising_brand_gap / wildcard |
| `source_urls` | All URLs from signals that contributed to this idea (never fabricated) |

---

## Stage 4: Evaluation & Scoring

**What it does:** Claude Haiku scores each idea on 6 dimensions using a single-pass structured JSON call. No tool use — the model scores based on what it already knows and what the idea card says.

**Model:** Claude Haiku (fastest, cheapest, single-pass). Haiku is specifically good at following structured rubrics. Using Sonnet here would be over-powered and much more expensive.

---

### The 6 Scoring Dimensions

These reuse the same IdeaDict score fields as the physical product pipeline, but with completely different rubrics.

---

**Score 1: Demand Signal (1–10)**

Signal loudness — how much evidence of this pain/demand exists?

- **10** = Multiple Reddit/Quora India threads explicitly asking for this, Product Hunt breakouts, VC theses naming this space
- **7–9** = Clear global breakout + India demand signals from 2+ sources
- **5–6** = Strong global signal but India demand inferred (not explicitly stated)
- **3–4** = Scattered signals, mostly from one source
- **1–2** = Single signal or analyst speculation

Weight in composite: **25%** (highest — signal quality is the foundation of everything)

---

**Score 2: India Readiness (1–10)**

Maps to `score_launchability` in the data schema. Is India behaviourally and technically ready for this app category?

This is the most India-specific score. Many categories work in the US but require infrastructure or behavioural habits that India doesn't have yet — open banking APIs, ambient computing, advanced credit scoring, etc.

- **10** = India-native behaviour already exists and slots directly in: UPI transactions, short-video, group chats — category plugs into existing behaviour
- **7–9** = India is clearly moving in this direction; 1–2 year lag from US but infrastructure and habits are there
- **5–6** = India adoption plausible but requires behaviour change or infrastructure not fully there (e.g. credit-card subscriptions, ambient computing)
- **3–4** = Significant behaviour change needed, or depends on infrastructure India lacks (open banking APIs, health records portability)
- **1–2** = Category requires behaviours India won't have for 3+ years, or has a regulatory blocker

Weight: **20%**

---

**Score 3: Monetization Fit (1–10)**

Maps to `score_capital_fit`. Can this business model actually work in India's price-sensitive market?

Indian users are more price-resistant than US users. Headspace at $12.99/month works in the US; the India equivalent needs to work at ₹99–299/month or go freemium. This score penalises categories where India-appropriate ARPU makes the unit economics unworkable.

- **10** = Proven India freemium/subscription comp at similar ARPU (Zerodha at ₹20/order, Zoho, Unacademy)
- **7–9** = India users demonstrably pay for this category at viable ARPU (OTT, gaming, tools)
- **5–6** = Monetization uncertain — Indian users pay abroad but India-specific ARPU data is unclear
- **3–4** = Strong resistance in India (content/media where piracy dominates, low income ceiling)
- **1–2** = Structurally hard to monetize in India (very low ARPU, high CAC, no ads inventory)

Weight: **20%**

---

**Score 4: India Gap (1–10)**

Maps to `score_arbitrage`. How unfilled is this specific category in India right now?

This is the core whitespace score. A score of 0 means the category is already crowded in India (e.g. UPI payments). A score of 10 means there is genuinely no funded Indian app in this space.

- **10** = Zero credible Indian equivalent; no Series A+ funded Indian app in this space
- **7–9** = Weak Indian equivalents exist but all poorly executed / underfunded / no brand
- **4–6** = Some Indian players but they serve a narrow slice; clear sub-category whitespace
- **1–3** = Strong Indian players already exist (Groww for investing, PhonePe for payments); gap is narrow
- **0** = Not a geo-arbitrage idea — category already crowded in India

Weight: **15%**

---

**Score 5: Competition Headroom (1–10, inverted)**

Maps to `score_competition`. In the output, this score is displayed as "Competition Headroom" — higher means less competition, which is better for a new entrant.

- **10** = True whitespace; no credible app in India for this use case
- **7–9** = 1–2 small or unfunded Indian players; no well-funded incumbent
- **5–6** = Established players but fragmented; room for differentiated entry
- **3–4** = Multiple funded incumbents; needs exceptional wedge
- **1–2** = Dominated by well-funded players (Zerodha-tier, ShareChat, BYJU's) or Google/Meta defaults

Weight: **10%**

---

**Score 6: Growth Loop Strength (1–10)**

Maps to `score_distribution`. How naturally does the app acquire users without paid ads?

Consumer apps with weak organic loops become dependent on paid UA, which is expensive and creates a growth ceiling. Apps with strong viral loops (Canva, Wordle, Notion) scale efficiently. This score rewards apps where the product itself drives acquisition.

- **10** = Extremely viral by nature: user creates an artefact others want to see/use, or referral incentive baked into core product
- **7–9** = Good organic channels: app store SEO, creator integrations, social sharing, community-led growth
- **5–6** = Moderate organic loop; some virality but primarily needs paid UA or partnerships
- **3–4** = Primarily needs expensive paid UA, influencer partnerships, or enterprise BD
- **1–2** = No natural organic loop; purely dependent on paid acquisition

Weight: **10%**

---

### Composite Score

```
Composite = (Demand × 0.25) + (India Readiness × 0.20) + (Monetization Fit × 0.20)
          + (Competition Headroom × 0.10) + (Growth Loop × 0.10) + (India Gap × 0.15)
```

Bonus: if word-of-mouth potential ≥ 8/10, composite is multiplied by 1.08. This rewards categories where social sharing is inherent (e.g. "here's my AI-generated financial summary") — a proxy for organic CAC efficiency.

---

### Hard Filters

Ideas are flagged (not dropped) if they fall below:
- **India Readiness < 4** — India market not ready for this
- **India Gap < 3** — credible Indian players already exist
- **Composite score < 5.5**

Flagged ideas still appear in the output, with the reason clearly stated. The fund may disagree with the evaluation or have additional context.

---

### Eval Flags

In addition to scores, Haiku adds plain-language flags:
- "India subscription resistance for this category"
- "Well-funded Indian incumbent exists: [name]"
- "Behaviour change required for India adoption"
- "Low ARPU ceiling in India market"
- "No viral loop — dependent on paid UA"
- "Google/Apple default competes directly"
- "Regulatory risk: RBI / SEBI / TRAI"

These are displayed alongside the scores in the output.

---

## Stage 5: Render Markdown

**What it does:** Pure Python renders the scored ideas into the `user_data/latest_apps.md` output file. No LLM calls.

**Output structure for each idea card:**
1. Header with score, pass/fail badge, and opportunity type badge
2. Global signal (Why now)
3. Problem + Target consumer
4. India status (first line of investability read)
5. Indian competitors + global reference apps
6. Full investability read (fund-facing fundability take)
7. Exit comps + Retention thesis (DAU/WAU/MAU) + India timing
8. Monetization model + Growth loop (app-specific fields)
9. Sub-scores with visual bars, app-specific labels
10. Source URLs

**Score bar display:**
```
- Demand signal:      ■■■■■■■□□□ 7/10
- India readiness:    ■■■■■■■■□□ 8/10
- Monetization fit:   ■■■■■■□□□□ 6/10
- Competition room:   ■■■■■■■■□□ 8/10
- Growth loop:        ■■■■■■■□□□ 7/10
- India gap:          ■■■■■■■■■□ 9/10
```

**Archive:** Every run writes two permanent files to `user_data/runs/` — a timestamped `.md` (the full report) and a `.json` snapshot (structured data for programmatic use). The filenames include the category slug, e.g. `2026-06-26_143022_apps_mental_health.md`.

---

## How This Is VC-Relevant

The pipeline is designed around a specific investment thesis: **geographic arbitrage in consumer tech**. The entire framing — the signal collection, the enrichment, the idea prompt, the evaluation rubric — is built to answer one question:

> "What is a US app category that has already proven consumer demand and venture fundability, where the India version hasn't been built yet?"

This maps directly to TDV's mandate as a consumer-focused micro-VC.

---

### What each field is for in a fund context

**`investability_read`** — The most important field. Two-part structure:
- Part 1: "India status: unfilled / weak incumbents / crowded" — one sentence on the competitive landscape
- Part 2: A frank 2-line take on whether this is fundable at seed stage, including: ticket size fit, time-to-leadership in the category, category size ceiling

This is written for IC discussion, not for a founder pitch.

**`exit_comps`** — Names one global exit that proves the category is venture-fundable. "Headspace raised $215M and sold to Noom in 2023 — validates premium meditation subscription at scale." This is the proof that the category produces returns, not just users.

**`india_timing`** — Early / On-time / Late, with one-line evidence. A category where India is "early" (3+ years behind the US) is higher-risk but higher-reward. "On-time" (1–2 years behind) is the sweet spot for backing a first mover. "Late" means Indian players are already funded.

**`india_gap` score** — The whitespace score. If a category scores 9/10 on India gap but 4/10 on India readiness, that suggests the opportunity exists but the market isn't ready yet — which changes the investment timing thesis.

**`monetization_model`** — Includes India-specific ₹ price points and ARPU targets. The key question for India consumer apps is: can you build a business at ₹150–300/month ARPU, or does your model only work at US-level pricing?

**`growth_loop`** — The specific viral mechanism. For a seed investment in India, paid UA budgets are limited and CAC is rising. A category where the product itself drives acquisition (referral mechanics, shareable outputs, social proof) is fundamentally better positioned than one that needs to buy every user.

**`repeat_purchase` (DAU/WAU/MAU target + retention thesis)** — In the product pipeline, this field tracks repurchase intervals. In the app pipeline, it tracks engagement depth. An app with daily active usage and high session depth is building a moat; an app used once a month is a utility that will be displaced by a free alternative.

---

### What the pipeline doesn't do

- It doesn't find specific companies to invest in. It finds **categories** with whitespace and generates an investment thesis for each.
- It doesn't replace founder diligence. The output is a starting point for a conversation, not a final recommendation.
- It doesn't have real-time data. The Exa searches return recent pages but not live metrics. For DAU/MAU data on specific India apps, you'd cross-check with App Annie / data.ai.
- It doesn't evaluate founding teams. That's not in scope.

---

## Cost and Time

**Per run (one category):**
- **Runtime:** ~10–15 minutes
- **API cost:** ~$0.50–1.50 in Claude API credits + a small amount of Exa API quota (~50–80 searches out of your 1000/month free tier)
- **Claude calls:** 2–4 Sonnet calls (enrichment batches) + 1 Sonnet streaming call (idea generation) + 1 Haiku call (evaluation)
- **Exa calls:** ~20–30 queries (4 collectors × 2–6 queries each, plus tool-use searches from enrichment)

**Where time is spent:** Almost all of it in Stage 3 (idea generation). Sonnet does multiple web searches, synthesises across 20–30 signals, and outputs 5 detailed memos. This is the slow step by design — the output quality comes from depth, not speed.

---

## Running It

**Via Streamlit (recommended for non-technical users):**
1. Go to the Streamlit app URL
2. Enter your Anthropic API key and Exa API key in the sidebar
3. Click the **📱 Apps** tab
4. Pick a category
5. Click Run

**Via CLI (if you're running locally):**
```bash
./venv/bin/python scripts/find_apps.py --category mental_health
```

Output lands in `user_data/latest_apps.md` and is archived in `user_data/runs/`.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│  USER INPUT: one app category (e.g. "mental_health")    │
└───────────────────┬─────────────────────────────────────┘
                    │
        ┌───────────▼───────────┐
        │   STAGE 1: COLLECT    │  Exa API only. No Claude.
        │                       │
        │  ┌─────────────────┐  │
        │  │  Product Hunt   │  │  trending consumer app launches
        │  │  VC Signals     │  │  TechCrunch, a16z, Sequoia
        │  │  Reddit App     │  │  US complaints + India demand
        │  │  India App Gap  │  │  "India version of X" posts
        │  └────────┬────────┘  │
        │           │ ~40-60 raw signals
        └───────────▼───────────┘
                    │
        ┌───────────▼───────────┐
        │  STAGE 2: ENRICH      │  Claude Sonnet + web_search tool
        │                       │
        │  Pre-filter (Python)  │  drop noise, keep substance
        │  Sonnet enriches      │  validate, classify, normalise
        │  in batches of 20     │  max 4 searches per batch
        │           │ 15-25 NormalizedSignals
        └───────────▼───────────┘
                    │
        ┌───────────▼───────────┐
        │  STAGE 3: GENERATE    │  Claude Sonnet streaming
        │                       │
        │  Geo-arbitrage lens   │  "US blowing up, India gap?"
        │  App-specific prompt  │  monetization, growth loop,
        │  5 structured memos   │  retention, India readiness
        │  max 3 tool searches  │
        └───────────▼───────────┘
                    │
        ┌───────────▼───────────┐
        │  STAGE 4: EVALUATE    │  Claude Haiku (single pass)
        │                       │
        │  6 scores × 5 ideas   │  demand / india readiness /
        │  App-specific rubric  │  monetization fit / india gap /
        │  Composite + filter   │  competition / growth loop
        └───────────▼───────────┘
                    │
        ┌───────────▼───────────┐
        │  STAGE 5: RENDER      │  Pure Python. No Claude.
        │                       │
        │  Markdown cards       │  latest_apps.md
        │  Overview table       │  latest_apps.json
        │  Archived in /runs/   │  timestamped archive
        └───────────────────────┘
```
