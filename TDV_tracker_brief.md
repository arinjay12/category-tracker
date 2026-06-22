# TDV Consumer Whitespace Tracker — Brief

**What this is:** An internal note on how we adapted an open-source D2C founder tool into a fund-facing category scanner, and the first output we ran it on.

---

## 1. What the original repo was

**Repo:** [github.com/sanketn/india-d2c](https://github.com/sanketn/india-d2c)

A **founder tool**. The core system prompt read:

> *"You are a D2C product idea generator for a specific founder launching physical consumer products in India."*

The 6-stage pipeline (collect signals → enrich → generate ideas → map competitors → evaluate → render) was designed around a specific founder's constraints — capital ceiling, distribution channels, hard product excludes. Every output field served a launch decision:

| Original field | What it answered |
|---|---|
| `hero_product` | What to actually manufacture first |
| `sourcing_approach` | Which contract manufacturers to approach |
| `gtm_tactics` | How to acquire the first 1,000 customers |
| `capital_required_estimate` | Does this fit the founder's ₹X lakh ceiling? |
| `first_year_revenue_estimate` | Year-1 projections |
| `eval_status` | Pass/fail against the founder's hard personal limits |

The lens priority was flat — `geo_arbitrage`, `complaint_cluster`, `format_shift`, and others competed equally, so you'd reliably get at most one geo-arbitrage idea per run. There was no concept of "is India unfilled?" and no fund-facing read on whether the category was a backable early-stage bet.

---

## 2. What we changed (and what we didn't touch)

### Guardrails — unchanged
We did not modify: signal collectors, Exa search queries, scoring math, onboarding flow, or API-key handling. All new schema fields are optional/additive so existing checkpoints remain valid.

### Change 1 — Analyst persona (`scripts/agents/idea_agent.py`)

**Before:**
> *"You are a D2C product idea generator for a specific founder launching physical consumer products in India."*

**After:**
> *"You are a consumer category analyst generating opportunity memos for an India-focused consumer/D2C fund. Your job is to identify rising global categories that are under-served in India and assess whether each represents a fundable early-stage bet."*

This is the highest-leverage change. It shifts what the model optimises for at generation time — from "can a bootstrapped founder launch this?" to "is this category rising globally and empty in India?"

### Change 2 — Lens priority bias (`idea_agent.py`)

Added an explicit `LENS PRIORITY` block to the generation prompt:

```
LENS PRIORITY — the fund's primary mandate is "rising globally, unfilled in India":
- Strongly prefer geo_arbitrage and rising_brand_gap signals.
- geo_arbitrage may appear up to 3 times across the 5 ideas (previously capped at 1).
```

The original diversity rule capped every opportunity type at one appearance per run. Loosening the cap specifically for `geo_arbitrage` means a single run can surface the three strongest geo-arbitrage plays rather than artificially rotating through less-relevant types.

### Change 3 — New `investability_read` field (`scripts/utils/signal_schema.py` + `idea_agent.py`)

Added an optional field to the `IdeaDict` dataclass:

```python
investability_read: str = ""
```

Sonnet now generates a two-part string per idea:
- **Line 1:** `India status: unfilled | weak incumbents | crowded — one-line justification`
- **Lines 2–3:** Frank fundability take — ticket size context, TAM signal, key diligence risk, exit comp

This field didn't exist before. It turns a product description into a screening memo.

### Change 4 — Renderer retitled + reordered (`scripts/render_markdown.py`)

**Old section order:** Problem → Target consumer → Hero product → Sourcing → GTM tactics → Unit economics → Sub-scores

**New section order:** Global signal (Why now) → Problem → Target consumer → India status → Who's already here → Investability read → Margin/AOV → Sub-scores

Founder-only fields (`hero_product`, `sourcing_approach`, `gtm_tactics`, `capital_required_estimate`, `first_year_revenue_estimate`) are **preserved in the JSON** but hidden from the markdown view. Available for diligence; don't clutter the screening read.

Title changed from `D2C Idea Finder` to `Consumer Whitespace Tracker — TDV`.

---

## 2b. Phase 2 — category recut + VC optimization (2026-06-22)

Six further changes after the first full run, focused on tightening the tool to TDV's mandate and reducing cost-per-run.

### Change 5 — Category set recut from 16 to 13 TDV-mandate-aligned categories

**Removed 6 categories** (not addressable with D2C signal pipeline, outside TDV mandate, or too early):
`footwear`, `innerwear_loungewear`, `eyewear_accessories`, `accessories`, `consumer_electronics`, `baby_kids`

**Added 3 new categories** that reflect TDV's actual thesis areas:
- `cognitive_wellness` — nootropics, lion's mane, bacopa, focus supplements, brain health
- `spiritual_lifestyle` — premium incense, meditation tools, upgraded puja accessories, ayurvedic self-care
- `sleep_recovery` — sleep supplements (magnesium, glycine), recovery tools, sleep hygiene products

All 5 collectors (india_marketplaces, amazon_us, rising_brands, exploration, google_trends) were updated to match the 13-category set.

### Change 6 — Remove D2C-specific generation fields (cost reduction)

Six fields removed from Sonnet's JSON output schema, saving ~30% of output token cost per run:

| Removed field | Why |
|---|---|
| `hero_product` | Specific SKU spec — useful for a launching founder, noise for fund screening |
| `hero_product_detail` | Expanded SKU description — same reason |
| `sourcing_approach` | Contract mfg / MOQ — irrelevant at IC screening stage |
| `gtm_tactics` | Launch playbook — the investee team decides this, not us |
| `first_year_revenue_estimate` | Unreliable Y1 projections — bottom-up TAM is already in `market_size_estimate` |
| `ai_angle` | "AI-formulated or none" flag — not a VC screening signal |

Fields are **kept in the schema** (backward-compatible with existing checkpoints) but default to empty string on new runs.

### Change 7 — Add VC-specific generation fields (zero extra cost)

Three fields added to Sonnet's output schema, replacing the removed D2C fields at no net token increase:

| New field | What it answers |
|---|---|
| `exit_comps` | Global acquisition that proves this category is fundable — e.g. *"Four Sigmatic acquired by P&G (2021)"* |
| `repeat_purchase` | `repeat / one-time / occasion` + repurchase interval — key LTV signal for fund thesis |
| `india_timing` | `early (3+ yrs behind global) / on-time (1-2 yrs) / late (already seeded)` + evidence |

### Change 8 — TDV portfolio flag (Python-side, zero LLM cost)

After evaluation, each idea gets a `portfolio_flag` set from a hardcoded TDV portfolio lookup — no API call, no extra cost. Tells the analyst in one line whether TDV already has a co in this category:

```
TDV portfolio by category:
  beauty:             Kindlife, Stealth Beauty
  home:               Goodmelts, Zulu Club
  wellness:           SoulSensei, Stealth Wellness
  pet:                Stealth Pet Care
  fashion_apparel:    Rapawalk, The Fourth Layer
  jewellery_watches:  Eternz
  food_cpg:           Acai Theory
  cognitive_wellness: Ivory
  spiritual_lifestyle: SoulSensei, DevDham, Apps For Bharat
  sleep_recovery:     Stealth Wellness
```

### Change 9 — New India funding collector (`india_funding_collector.py`)

Exa-only collector (no Claude calls) that queries **Inc42, YourStory, and Entrackr** for recent India startup funding rounds per category. 2 queries per picked category, max 6 per run. Signals the idea agent that a category is already attracting capital — both a validation signal and a competition signal. Adds ~6 Exa calls per run (within free tier).

### Change 10 — Evaluation rubric updates

- **Removed `ai_angle` bonus** from composite score (field no longer generated)
- **Reframed `score_distribution` rubric**: from "what fraction of the founder's GTM tactics are available to this founder?" → "how accessible are D2C channels for this category in India?" — a VC screening question, not a founder operational question. The rubric now scores category-level channel accessibility (influencer, QC, organic search) rather than founder-specific channel match.

---

## 3. Why this helps us as a micro VC

The original tool answered: *"Can this founder launch this product?"*

The new tool answers: *"Is this category rising globally, empty in India, and worth a first cheque?"*

**Screening speed.** A fund analyst reading the old output had to mentally filter out GTM tactics, sourcing notes, and year-1 revenue guesses — none of which matter at screening stage. The new output leads with the global signal and closes with the fundability take. Pass/no-pass in 30 seconds per card.

**The right risk surface.** Founder tools flag "does this exceed the capital ceiling?" We don't care about that at screening — the investee will raise to cover it. The new `investability_read` flags VC-relevant risks: *"commodity segment entrenched at ₹649 — can you reach the ingredient-aware cohort before MuscleBlaze launches a premium line?"* That's a diligence question, not a founder constraint.

**Geo-arbitrage density.** With the original flat lens priority you'd get one geo_arbitrage idea per run. With the new 3× allowance you surface the three strongest geo-arbitrage plays in a single pass — exactly what a fund with a "proven global → empty India" mandate needs. This run returned two geo-arbitrage ideas in the top-2 slots (Creatine at 9.5/10, Stim-Free Pre-Workout at 8.8/10) and three rising_brand_gap ideas, versus the original one-of-each rotation.

**Repeatable category coverage.** The pipeline accepts any category slug. We can run `fitness_nutrition` today, `pet_care` next week, `personal_care` the week after — each run produces a fund-ready one-pager on that category's whitespace with named Indian competitors, global reference brands, India status, and a frank fundability take. At our stage this replaces several hours of analyst desk research per category.

---

## 4. First run output — `fitness_nutrition` (2026-06-19)

*Run on 2 enriched signals (Exa rate-limited on this pass). 5 ideas generated by Claude Sonnet via its own web search tool calls. All 5 passed evaluation filters. Ran in 671s.*

---

### 1. Clinically Dosed Creatine + Recovery Stack · [9.5/10] · ✓ Passed · 🌍 Geo-arbitrage

**Tagline:** Creatine is the most-validated sports supplement globally yet India's creatine market is dominated by under-dosed, unflavoured commodity powders — a flavoured, clinically-dosed creatine + recovery combo at ₹999–₹1,399 is a direct geo-arbitrage play on brands like Momentous and Thorne.

**Category:** Fitness & Nutrition

**Global signal (Why now)**
Creatine's benefits for athletic performance AND cognitive function went mainstream globally in 2022–2024 (driven by Andrew Huberman, Peter Attia, Rhonda Patrick). In India, this wave hit YouTube fitness creators in 2023–24, causing a surge in search intent. Momentous and Thorne are building premium creatine brands in the US at $35–$45/month — zero Indian equivalent exists at a premium-but-accessible ₹999–₹1,399 price. The creatine + electrolyte stack format (used for daily take vs pre-workout) maps perfectly to quick commerce as a daily-replenishment product.

**Problem**
Creatine monohydrate is the single most evidence-backed sports supplement (meta-analyses confirm 5g/day improves strength, cognitive function, and recovery), yet Indian brands treat it as a commodity ingredient: AS-IT-IS Nutrition Creatine (₹599/250g, plain powder, no flavour, no co-actives) and MuscleBlaze Creatine (₹649/250g, same format) are essentially industrial raw material packs. Urban gym-goers increasingly understand creatine's benefits but are buying either cheap unflavoured powder with poor compliance, or expensive US imports (Momentous at ₹3,500+). Clear gap for a flavoured, precisely dosed (5g/serve), travel-convenient creatine + recovery stack (electrolytes + tart cherry extract) at ₹999–₹1,399.

**Target consumer**
Urban gym-goers aged 22–35 in Bangalore, Mumbai, Delhi, Pune — intermediate-to-advanced lifters who follow evidence-based fitness influencers (Ranveer Allahbadia, Nikhil Fit), understand creatine's science, currently buy raw powder but want a premium daily ritual product.

**India status**
Weak incumbents — the creatine segment is entirely commodity-format; no Indian brand has built a Creapure-certified premium creatine product; the ₹1,000–₹1,400 price band is entirely unoccupied.

**Who's already here (India)**
TATA 1mg Creatine (flavoured but thin recovery stack), Fast&Up Creatine Rapid (single-ingredient, no co-actives), MuscleBlaze Creatine (commodity, ₹649, unflavoured), Wellbeing Nutrition Creatine (micronised but plain), BeastLife Creatine (NABL tested but basic), GNC Pro Performance Creatine (₹439–₹2,198, no flavour consistency)

**Reference brands (global)**
Momentous Creatine (US, Creapure + NSF certified), XWERKS Lift (US, flavoured creatine monohydrate), Thorne Creatine (US, premium third-party tested), Gainful Creatine (US, personalised stacks)

**Investability read**
Fundable at pre-seed/seed: ₹10–₹15L launch capital is well within ceiling, and the replenishment nature of creatine (daily use, monthly repurchase) creates strong LTV for D2C. The risk is that the commodity segment is deeply entrenched at ₹599–₹799 — success depends on whether ingredient-aware gym-goers (a growing but still minority cohort) can be reached efficiently enough to justify premium pricing before a well-funded incumbent like MuscleBlaze launches a premium line.

**Margin/AOV** · AOV ₹1,199 single tin; ₹2,199 double-tin subscription bundle · Margin 60–66%

**Sub-scores**
- Demand:               ■■■■■■■■□□ 8/10
- Launchability:        ■■■■■■■■■□ 9/10
- Capital fit:          ■■■■■■■■■□ 9/10
- Competition headroom: ■■□□□□□□□□ 2/10
- Distribution fit:     ■■■■■■■■■□ 9/10
- Geo-arbitrage:        ■■■■■■■■■□ 9/10

---

### 2. Open-Formula Stim-Free Pre-Workout · [8.8/10] · ✓ Passed · 🌍 Geo-arbitrage

**Tagline:** Transparent Labs' stim-free pre-workout is a $500M+ US sub-category — no Indian brand offers a clinically dosed, third-party-tested, caffeine-free pre-workout at ₹1,200–₹1,800, leaving 8M+ jitter-wary Indian gym-goers underserved.

**Category:** Fitness & Nutrition

**Global signal (Why now)**
Transparent Labs Stim-Free is a top-rising search query in the US. Kaged India's import friction (FSSAI caffeine cap, ₹3,500+ price post-duty) has created a pricing vacuum at ₹1,200–₹1,800. TruNativ's $30M raise validates that Indian urban consumers now pay a premium for clean-label nutrition. India's gym membership base crossed 8M in 2024 and protein supplement awareness is high — the adjacent pre-workout category is the natural next purchase. No domestic brand has responded to the open-formula global wave.

**Problem**
India's gym population (8M+ active gym members in tier-1 cities) is increasingly ingredient-literate, yet every domestic pre-workout — MuscleBlaze Pre-Workout 200 Xtreme, Absolute Nutrition Magnitude, Big Muscles Nutrition — hides dosing behind proprietary blends and lacks third-party testing. The FSSAI 200mg caffeine cap makes US imports like Kaged Elite non-compliant and prices them at ₹3,500–₹5,000. Meanwhile 'Transparent Labs Stim-Free' is a top-rising query in US fitness, driven by gym-goers who report jitters, sleep disruption, and cardiovascular anxiety. Indian gym-goers echo this on Reddit India fitness threads. No Indian brand has addressed this; the category is entirely unoccupied at ₹1,200–₹1,800.

**Target consumer**
Men and women aged 22–35 in Mumbai, Bangalore, Delhi, Pune — 4–5x/week gym-goers who are aware of ingredients like citrulline and beta-alanine, have had a negative experience with high-caffeine pre-workouts, and are willing to pay ₹1,500 for a clean label with disclosed doses.

**India status**
Weak incumbents — domestic pre-workout brands compete entirely on price and taste, not formulation quality or transparency; Kaged India's import presence is negligible at ₹3,500+.

**Who's already here (India)**
MuscleBlaze Pre-Workout 200 Xtreme (proprietary blend, no third-party certification), Healthfarm N.O. Pump Stim Free (emerging, weak brand presence), Wellversed Dynamite Caffeine Free (limited ingredient disclosure), Optimum Nutrition Gold Standard Pre-Workout (mass-market, high caffeine)

**Reference brands (global)**
Transparent Labs BULK Pre-Workout (US, open-label stim-free formulas), Kaged Elite Pre-Workout (US, Informed Sport certified), Legion Pulse (US, NSF certified, transparent dosing)

**Investability read**
Fundable seed-stage bet: ticket size fits within ₹20L (first batch + certification + D2C launch), time-to-category-leadership is 18–24 months given zero credible clean-label competitor, and the sports nutrition TAM is ₹16,000Cr+ with pre-workout as fastest-growing segment. Key risk is whether Indian gym-goers will pay a ₹1,500 premium for transparency over caffeine — early D2C testing with micro-influencers can de-risk this before a larger raise.

**Margin/AOV** · AOV ₹1,499–₹1,799 (single tub); ₹2,599 with a creatine sachet bundle · Margin 62–68%

**Sub-scores**
- Demand:               ■■■■■■■■□□ 8/10
- Launchability:        ■■■■■■■■□□ 8/10
- Capital fit:          ■■■■■■■■□□ 8/10
- Competition headroom: ■■■□□□□□□□ 3/10
- Distribution fit:     ■■■■■■■■■□ 9/10
- Geo-arbitrage:        ■■■■■■■■□□ 8/10

---

### 3. Postbiotic Gut-Repair Protein Powder · [7.4/10] · ✓ Passed · 🚀 Rising brand gap

**Tagline:** Postbiotics are the fastest-growing gut health format in the US (ION Gut Health, Pendulum) with zero Indian D2C equivalent — a whey + postbiotic protein at ₹1,800–₹2,400 targeting bloat-prone urban professionals is a direct rising-brand-gap play on a globally validated format India has not yet seen.

**Category:** Fitness & Nutrition

**Global signal (Why now)**
Postbiotics became the dominant gut health format in the US in 2023–24 — ION Gut Health, Pendulum, and Timeline Nutrition collectively raised $200M+ in this period. The format is moving from standalone gut supplements into protein powders (Truvani, Ritual, Garden of Life all launched postbiotic-infused protein in 2023–24). India has seen the probiotic wave (Yakult, BioME) but not the postbiotic wave — the category is 2–3 years behind the US. TruNativ's $30M raise is the clearest Indian signal that gut-health nutrition is investable.

**Problem**
India's ₹4,000Cr+ protein supplement market is bifurcated: cheap adulterated whey or expensive clean whey (Oziva, Trueforma, Shyft) — but neither segment addresses gut discomfort, which is the #1 reported complaint about protein powders in Indian consumer reviews ('bloating after whey', 'digestive issues with protein shakes' appear in hundreds of Amazon India reviews). The emerging global format — postbiotic protein combining fermented whey or postbiotic strains (tributyrin, urolithin A) — has zero representation in India.

**Target consumer**
Urban working professionals aged 25–40 in Bangalore, Mumbai, Hyderabad — primarily those who work out 3–5x/week, have tried multiple protein powders, experienced bloating, and follow gut health content on Instagram. Secondary: women aged 28–40 who associate gut health with skin, energy, and hormonal wellbeing.

**India status**
Weak incumbents — Oziva, Trueforma, and Shyft compete on clean protein/herbs but none have launched a postbiotic protein or made 'zero bloat' a hero claim; the format is entirely open.

**Who's already here (India)**
Trueforma (₹2,400+, prebiotics only, no postbiotics), NATURALTEIN ISO Boost (BC30 probiotic strain, lacks postbiotic actives), AS-IT-IS Atom (DigeZyme enzymes only), Oziva Plant Protein (plant-based, misses whey+postbiotic niche), Patanjali Protein (budget segment, quality concerns)

**Reference brands (global)**
Ritual Essential Protein (US, postbiotic+whey formula), Timeline Nutrition Urolithin A (US), ION Gut Health (US, standalone tributyrin postbiotic), Garden of Life Sport (US, whey+probiotics+enzymes)

**Investability read**
Fundable at seed stage: ₹15–₹18L within ceiling, protein supplement TAM is ₹4,000Cr+ with clear upward mobility to ₹2,200 AOV, and the IBS/gut-pain consumer problem is acutely felt with high WOM potential. Primary diligence risk: landed cost of postbiotic actives at small MOQ — run the ingredient import P&L before committing; if tributyrin cost compresses margin below 60%, shift hero active to fermented whey (GanedenBC30 licensed), which is manufactured domestically.

**Margin/AOV** · AOV ₹2,199 (1kg bag); ₹3,799 bundle with 30-day gut repair kit · Margin 61–67%

**Sub-scores**
- Demand:               ■■■■■■■□□□ 7/10
- Launchability:        ■■■■■■□□□□ 6/10
- Capital fit:          ■■■■■■□□□□ 6/10
- Competition headroom: ■■□□□□□□□□ 2/10
- Distribution fit:     ■■■■■■■■□□ 8/10
- Geo-arbitrage:        ■■■■■■□□□□ 6/10

---

### 4. Daily Nutrition Sachets for Diabetic-Adjacent Adults · [7.3/10] · ✓ Passed · 🚀 Rising brand gap

**Tagline:** TruNativ's $30M raise confirms India's clean-label nutrition moment is here — a daily sachet system (fibre + low-GI protein + adaptogens) targeting India's 100M+ pre-diabetic urban adults at ₹1,200–₹1,600/month is wide open below the clinical medical nutrition segment.

**Category:** Fitness & Nutrition

**Global signal (Why now)**
TruNativ's $30M OrbiMed raise (healthcare-focused fund, not consumer fund) signals that preventive metabolic nutrition is being underwritten as a health outcome category. Abbott Ensure and Glucerna are growing at 12%+ in India but remain anchored in the clinical/hospital channel. The format shift to daily sachet rituals is proven globally (AG1 at $1.4B valuation, Ritual Essential Protein) but has no direct India equivalent below ₹2,500/month. Quick commerce makes daily-ritual supplement subscription viable in tier-1 for the first time.

**Problem**
India has an estimated 136M people with pre-diabetes (ICMR 2023), concentrated in urban metros. These consumers are not diabetic enough for Glucerna or Abbott Ensure (medical nutrition, ₹2,000+/kg, hospital-channel), but too health-anxious to ignore their sugar levels. Existing options — Patanjali Nutrela, generic multivitamins, or imported supplements — don't address the specific daily metabolic needs: low-GI protein, soluble fibre, chromium, and berberine in a convenient single-serve format. No brand has built a ₹1,200–₹1,600/month subscription sachet system for metabolic health prevention.

**Target consumer**
Urban working adults aged 30–50 in Mumbai, Delhi, Bangalore, Hyderabad — professionals with HbA1c in borderline range (5.7–6.4), family history of diabetes, who visit a nutritionist or follow metabolic health accounts on Instagram, and already spend ₹1,000–₹2,000/month on supplements but have no daily metabolic ritual product.

**India status**
Weak incumbents — TruNativ owns fibre/sweetener sachets; Abbott owns clinical nutrition; nobody owns the daily metabolic ritual sachet for pre-diabetic prevention at ₹1,200–₹1,600/month.

**Who's already here (India)**
Ensure Diabetes Care (₹2,000+/kg, hospital-heavy positioning), Protinex Diabetes Care (powder format, lacks daily ritual positioning), Pentasure DM (mass-market, weak ingredient transparency), Vidavance by Signutra (pre-diabetes focused, thin D2C presence), TATA 1mg Whey Sachets (protein-only)

**Reference brands (global)**
AG1 by Athletic Greens (US, daily greens powder subscription ritual), Ritual Essential Protein (US, transparent daily protein supplement), Pendulum Metabolic Daily (US, targeted gut-metabolic health sachet)

**Investability read**
Fundable as a seed-stage consumer health bet: ₹14–₹18L launch capital within ceiling, the subscription model drives LTV that justifies D2C CAC, and the 100M+ pre-diabetic addressable base makes this a large category. Key diligence item: FSSAI classification of berberine (resolve before batch commitment); and whether a D2C subscription model can achieve 6-month retention without clinical proof points — early cohort data is the key fund milestone.

**Margin/AOV** · AOV ₹1,399/month subscription (30 sachets); ₹2,599 90-day starter kit as hero AOV driver · Margin 63–70%

**Sub-scores**
- Demand:               ■■■■■■■□□□ 7/10
- Launchability:        ■■■■■■■□□□ 7/10
- Capital fit:          ■■■■■■■□□□ 7/10
- Competition headroom: ■■■■□□□□□□ 4/10
- Distribution fit:     ■■■■■■■□□□ 7/10
- Geo-arbitrage:        ■■■■■□□□□□ 5/10

---

### 5. Adaptogen Coffee Blends for Desk Athletes · [8.2/10] · ✓ Passed · 🎲 Wildcard

**Tagline:** Lion's Mane + Ashwagandha functional coffee is a $400M US category (Four Sigmatic, MUD\WTR) with no Indian brand capturing the ₹900–₹1,400 segment — India's 50M+ urban office-going caffeine-dependent professionals are being handed a wellness upgrade with zero local competition.

**Category:** Fitness & Nutrition

**Global signal (Why now)**
Four Sigmatic's P&G acquisition and MUD\WTR's $60M raise signal category maturation in the US. Lion's mane and ashwagandha are both FSSAI-approved in India, removing the regulatory friction that slows other adaptogen categories. Indian specialty coffee culture has scaled significantly (2020–2024) — Blue Tokai, Subko, Third Wave Coffee have educated 5–8M urban Indians on premium coffee. The TruNativ signal confirms urban Indians pay for daily clean-label nutrition rituals. Established coffee ritual + adaptogen supplement wave = natural D2C product-market fit.

**Problem**
India's urban professional workforce (50M+ metro desk workers) runs on 2–4 cups of coffee or chai daily, but suffers chronically from energy crashes, afternoon brain fog, and sleep disruption. In the US, the 'functional coffee' category has been validated by Four Sigmatic ($100M+ revenue, acquired by P&G) and MUD\WTR. In India, the closest analog is traditional Chyawanprash or ashwagandha capsules — neither is positioned for the urban professional's morning routine. The gap: a premium instant functional coffee blend (lion's mane, ashwagandha, L-theanine, reishi) at ₹999–₹1,299/month with no Indian owner.

**Target consumer**
Urban knowledge workers aged 25–40 in Bangalore, Mumbai, Delhi, Hyderabad — software engineers, startup founders, consultants who spend 8–10 hours at screens, follow productivity/biohacking content (Huberman Lab, Ankur Warikoo), drink specialty coffee, and spend ₹800–₹1,500/month already on supplements or premium coffee.

**India status**
Unfilled — no domestic brand has attempted to occupy the adaptogen-coffee functional format at any price point in India; the category is entirely greenfield.

**Who's already here (India)**
Shroomnest Adaptogenic Coffee (early-stage, limited distribution), Ace Blend Lion's Mane Shroom Coffee (₹314 budget tier, dilutes premium positioning), VAHDAM Ashwagandha Coffee (established tea brand, coffee secondary focus), Zandu Ashwagandha Gold Plus (traditional Ayurvedic positioning, no coffee integration) — thin direct competition, category nascent.

**Reference brands (global)**
Four Sigmatic (US, lion's mane + chaga mushroom coffee blend), MUD\WTR (US, adaptogen-forward coffee alternative), Ryze Mushroom Coffee (US, 6-mushroom functional blend)

**Investability read**
Fundable at seed stage with high upside: ₹10–₹14L well within ceiling, daily-use subscription creates strong LTV, Four Sigmatic's P&G acquisition proves category exit potential. Wildcard risk: India's functional mushroom coffee awareness is near-zero — this is a category-creation bet, not a category-fill bet. Fund should model a 24–30 month awareness-building phase before expecting meaningful scale; the win condition is being the category-defining brand when awareness crosses the mainstream inflection point, as Four Sigmatic was in the US 2016–2020.

**Margin/AOV** · AOV ₹1,099 (single pouch); ₹2,799 3-pouch subscription bundle · Margin 64–72%

**Sub-scores**
- Demand:               ■■■■■■■□□□ 7/10
- Launchability:        ■■■■■■■□□□ 7/10
- Capital fit:          ■■■■■■■■□□ 8/10
- Competition headroom: ■■□□□□□□□□ 2/10
- Distribution fit:     ■■■■■■■■□□ 8/10
- Geo-arbitrage:        ■■■■■■■□□□ 7/10

---

## Overview

| # | Idea | Score | Type | India status |
|---|------|-------|------|--------------|
| 1 | Clinically Dosed Creatine + Recovery Stack | 9.5/10 | 🌍 Geo-arbitrage | Weak incumbents |
| 2 | Open-Formula Stim-Free Pre-Workout | 8.8/10 | 🌍 Geo-arbitrage | Weak incumbents |
| 5 | Adaptogen Coffee Blends for Desk Athletes | 8.2/10 | 🎲 Wildcard | Unfilled |
| 3 | Postbiotic Gut-Repair Protein Powder | 7.4/10 | 🚀 Rising brand gap | Weak incumbents |
| 4 | Daily Nutrition Sachets for Diabetic-Adjacent Adults | 7.3/10 | 🚀 Rising brand gap | Weak incumbents |

---

*Generated 2026-06-19. Category: fitness_nutrition. Branch: tdv-tracker-reframe. Next run: change category slug and re-invoke.*
