"""
Canonical category set for the consumer app / SaaS pipeline.
Kept separate from setup.py (physical products) so neither list pollutes the other.
"""
from __future__ import annotations

APP_CATEGORIES: dict[str, tuple[str, str]] = {
    "ai_tools":         ("AI Consumer Tools",     "AI assistants, AI writing, AI creative, AI productivity for everyday consumers"),
    "personal_finance": ("Personal Finance",       "budgeting, expense tracking, investment apps, savings, wealth management"),
    "mental_health":    ("Mental Health",          "therapy apps, meditation, mood tracking, anxiety management, sleep tech"),
    "fitness_apps":     ("Fitness & Health Apps",  "workout tracking, nutrition logging, health monitoring, wearable companion apps"),
    "creator_tools":    ("Creator & Freelancer",   "content creation tools, portfolio builders, client management, creator monetization"),
    "social_community": ("Social & Community",     "niche social networks, community platforms, interest-based apps"),
    "edtech":           ("Learning & Edtech",      "micro-learning, skill building, language apps, certifications"),
    "home_local":       ("Home & Local Services",  "home management, on-demand local services, hyperlocal discovery"),
    "entertainment":    ("Entertainment & Media",  "audio content, casual games, short-form interactive, IP-based apps"),
    "dating_social":    ("Dating & Relationships", "niche dating, relationship tools, social matching"),
}

# Human-readable search terms used by collectors to query each category
CATEGORY_SEARCH_TERMS: dict[str, str] = {
    "ai_tools":         "AI assistant productivity consumer app",
    "personal_finance": "personal finance budgeting investment app",
    "mental_health":    "mental health meditation therapy app",
    "fitness_apps":     "fitness workout health tracking app",
    "creator_tools":    "creator freelancer content tools app",
    "social_community": "social community niche network app",
    "edtech":           "learning education skills language app",
    "home_local":       "home services local discovery app",
    "entertainment":    "entertainment audio games media app",
    "dating_social":    "dating relationships social matching app",
}
