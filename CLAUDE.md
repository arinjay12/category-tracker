# India D2C — Claude Code Skill

Loaded for Claude Code sessions inside this repo. Captures current state, architecture, key decisions, and conventions so a fresh session can pick up without re-deriving everything.

**Last updated:** 2026-05-26 (initial public release prep).

## What this is

A Claude Code skill that finds launchable D2C product ideas for the Indian market. Users invoke it in chat ("find me d2c ideas in India") and get 5 ranked product idea cards tuned to their capital ceiling, picked categories, distribution channels, and hard excludes. Pipeline: signal collection → enrichment → idea generation → competitor mapping → evaluation → markdown render.

Extracted from Sanket's personal cron-job D2C idea finder, rebuilt as a chat-driven, single-user-installable skill.

## Current state

- **Repo**: `github.com/sanketn/india-d2c` (currently **PRIVATE** while co-founder tests; will flip to public)
- **Local folder**: `~/Documents/claude-projects-main/india-d2c/`
- **Symlink**: `~/.claude/skills/india-d2c` → local folder
- **Skill name (frontmatter)**: `india-d2c`
- **First commit**: `0c8ea5b` — "Initial release: India D2C idea finder (Claude Code skill)"

## Architecture

**Pipeline (6 stages, ~12-18 min per run):**

1. **Collection** (5 collectors, each filters to picked categories):
   - `india_marketplaces_collector` — 17+ Indian marketplaces incl. quick commerce (cap 15 queries/run)
   - `exploration_collector` — per-category Reddit subs + YouTube reviews + Quora (2-6 queries per picked category)
   - `rising_brands_collector` — 4 US D2C publications (sampled from per-category pools)
   - `amazon_us_collector` — 1 cross-platform Reddit+Amazon query per picked category
   - `google_trends_collector` — pytrends; frequently rate-limited (expected)
2. **Enrichment** — Sonnet validates signals via tool-using web searches, in batches of 20
3. **Idea generation** — Sonnet produces 5 ideas (5-9 min — the slowest single stage)
4. **Competitor mapping** — Haiku synthesizes 6 Exa searches per idea (parallel, concurrency cap 5)
5. **Scoring + tagging** — Haiku scores each idea; flagged (not dropped) if below thresholds
6. **Render + archive** — markdown to `user_data/latest_ideas.md`, JSON snapshot, archive to `user_data/runs/<timestamp>_ideas.{md,json}`

**Agents** (4 total): signal_enrichment, idea, competitor_enrichment, evaluation. (No learning_agent — deliberately removed.)

**Models**: Sonnet 4.6 for heavy reasoning (enrichment, idea gen), Haiku 4.5 for bulk classification (competitor, evaluation, dedup). IDs in `scripts/utils/models.py`.

## Critical conventions

### 1. profile.yaml is user-editable ONLY

`user_data/profile.yaml` contains exactly four user-tunable blocks: `market.capital_ceiling_lakhs`, `categories`, `distribution`, `hard_excludes`. Internal config (scoring weights, filter thresholds, AOV floor, model IDs, max ideas per run) lives in `scripts/utils/config.py` and `scripts/utils/models.py` — physically NOT in profile.yaml. This means when Claude reads profile.yaml, there's nothing internal to accidentally leak as a "user setting."

### 2. No em-dashes in user-facing output

Per Sanket's global rule (em-dashes are an LLM tell). Use commas, periods, parentheses, sentence breaks. Applies to all rendered output, README, SKILL.md, and any chat copy. Em-dashes are OK in code comments / docstrings (not user-facing).

### 3. No script names in user-facing chat language

When Claude in chat tells the user to do something, use plain English. Say "ask me to find new ideas" not "run find_ideas.py". Say "I'll apply that" not "I'll run update_profile.py". Script names stay in instructions TO Claude (which Claude reads but never speaks).

### 4. Profile changes happen via plain English in chat

User says "drop pet", "bump capital to 15L", "add fashion" etc. Claude maps to canonical keys and runs the right `update_profile.py` command. Vague requests ("I want to change my channels") trigger a numbered-list flow that mirrors onboarding Q1/Q2/Q3. NEVER tell the user to "edit profile.yaml" directly.

### 5. "What are my settings" → always run `update_profile.py --show`

Do NOT compose a settings answer by reading profile.yaml directly and improvising. The script is the single source of truth for what counts as "settings."

### 6. Past runs are in `user_data/runs/`

Every run gets archived with a timestamped filename. The user can ask "show me past runs" / "show me run #N" / "show me the run from [date]" in chat. ONLY look in `~/.claude/skills/india-d2c/user_data/runs/` — never look at the user's personal d2c-idea-finder folder or any other location.

## What NOT to revert (decisions made in this session — don't undo)

These were all deliberate removals/changes. If a future session thinks "should we add this back?" — read the conversation history first.

- ❌ Killed `learned_context.md` and `search_directives.json` (deleted)
- ❌ Killed `apply_feedback.py` + `feedback_log.jsonl` (no feedback log; reactions are conversational)
- ❌ Killed `category_boost` / `--boost-category` (categories are binary picked/not)
- ❌ Killed `superpower` tier / `--tier` flag (channels are binary available/not, use `--add-channel` / `--remove-channel`)
- ❌ Killed `time_sensitive` badge (heuristic was too coarse)
- ❌ Killed `gtm_amplifiers` field (merged into single GTM section that shows ideal playbook)
- ❌ Killed `Brand positioning` rendered section (single word didn't earn the line; field still exists for diversity constraint)
- ❌ Moved `scoring_weights`, `filters`, `min_aov`, `max_ideas_per_run` OUT of profile.yaml into `utils/config.py`
- ❌ Removed paternalistic always-on hard excludes (only user's explicit excludes apply now)

## Common tasks

- **Run pipeline**: `./venv/bin/python scripts/find_ideas.py` (add `--fresh` to ignore checkpoint)
- **Update profile**: `./venv/bin/python scripts/update_profile.py --show` or `--add-category X` / `--remove-category X` / `--add-channel X` / `--remove-channel X` / `--add-exclude X` / `--remove-exclude X` / `--capital N`
- **Set API keys**: `./venv/bin/python scripts/set_key.py --exa <key> --anthropic <key>`
- **Run from scratch**: `rm -rf user_data/* && ./venv/bin/python scripts/setup.py --config '<json>'`

## File layout

```
india-d2c/
├── SKILL.md                  # Claude Code skill instructions (~680 lines)
├── README.md                 # Public-facing docs (~280 lines)
├── LICENSE                   # MIT
├── .env.example              # API key template
├── .gitignore                # excludes .env, user_data/, venv/, logs/, *.db
├── requirements.txt          # pip deps: anthropic, exa-py, pytrends, pyyaml, etc.
├── CLAUDE.md                 # this file
├── scripts/
│   ├── setup.py              # first-time onboarding (writes user_data/)
│   ├── find_ideas.py         # main pipeline runner
│   ├── update_profile.py     # edit profile.yaml from chat-driven requests
│   ├── set_key.py            # add/update API keys in .env
│   ├── render_markdown.py    # format ideas for chat
│   ├── collectors/           # 5 signal collectors (Exa + pytrends)
│   ├── agents/               # 4 LLM agents
│   └── utils/                # config (internal pipeline tuning), models (Claude IDs),
│                             # db, dedup, labels, logger, signal_schema, tools
├── venv/                     # auto-created by setup.py (gitignored)
└── user_data/                # gitignored — user's profile, keys, state, history
    ├── profile.yaml          # ONLY user-editable fields (capital, categories, channels, excludes)
    ├── .env                  # user's Exa + Anthropic API keys
    ├── state.db              # SQLite for dedup
    ├── latest_ideas.md       # most recent run output
    ├── latest_ideas.json     # structured snapshot
    └── runs/                 # archive of every run, by timestamp
```

## Known issues / pending

- **Brand_angle homogeneity**: Sonnet sometimes defaults to "honest" for many ideas. We added a diversity constraint in the prompt (≥3 different values across 5 ideas) but it doesn't fully solve. Acceptable for v1.
- **Google Trends rate-limiting**: pytrends frequently gets 429s (~90% of queries blocked). Treated as a backup confirmation signal; the other 4 collectors carry the load.
- **First fresh-clone test**: should verify the install path works on a machine that's never had the skill (untested by anyone other than Sanket).
- **Co-founder testing in progress**: repo is private during this; flip to public when ready.

## Sanket context

- Author: Sanket Nadhani (PM, not engineer; mostly built this with Claude Code)
- GitHub: sanketn
- X handle: sanketnadhani
- Email: sanket@yippa.io (company), sanket.nadhani@gmail.com (personal)
- Repos in same workspace: `apr` (AI Page Readiness tool), `agent-army-canva-apps` (marketing automation), `d2c-idea-finder` (the original personal cron job this was extracted from — DO NOT touch this; it's separate from the skill repo)
