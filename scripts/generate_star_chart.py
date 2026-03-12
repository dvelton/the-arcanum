"""
Star Chart Generator — aggregates trial results into a performance profile.

Usage:
    python scripts/generate_star_chart.py <apprentice_name>
    python scripts/generate_star_chart.py --all

Output:
    Writes/updates apprentices/<name>/star-chart.json
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).parent.parent


def load_journal_entries(apprentice_name: str) -> list[dict]:
    journal_dir = REPO_ROOT / "apprentices" / apprentice_name / "journal"
    if not journal_dir.exists():
        return []

    entries = []
    for f in sorted(journal_dir.glob("*.yaml")):
        with open(f) as fh:
            entry = yaml.safe_load(fh)
            if entry:
                entries.append(entry)
    return entries


def compute_star_chart(apprentice_name: str, entries: list[dict]) -> dict:
    # Group scores by category
    category_scores = defaultdict(list)
    trial_scores = defaultdict(list)
    all_scores = []

    for entry in entries:
        category = entry.get("category", "unknown")
        trial = entry.get("trial", "unknown")
        score = entry.get("overall_score", 0)

        category_scores[category].append(score)
        trial_scores[f"{category}/{trial}"].append(score)
        all_scores.append(score)

    # Compute category averages (most recent 5 attempts)
    categories = {}
    for cat, scores in category_scores.items():
        recent = scores[-5:]
        categories[cat] = {
            "average": round(sum(recent) / len(recent), 3) if recent else 0,
            "best": round(max(scores), 3) if scores else 0,
            "latest": round(scores[-1], 3) if scores else 0,
            "attempts": len(scores),
        }

    # Compute trial-level detail
    trials = {}
    for trial_key, scores in trial_scores.items():
        recent = scores[-3:]
        trials[trial_key] = {
            "average": round(sum(recent) / len(recent), 3) if recent else 0,
            "best": round(max(scores), 3) if scores else 0,
            "latest": round(scores[-1], 3) if scores else 0,
            "attempts": len(scores),
        }

    # Overall
    overall = round(sum(all_scores) / len(all_scores), 3) if all_scores else 0
    recent_overall = all_scores[-10:]
    recent_avg = round(sum(recent_overall) / len(recent_overall), 3) if recent_overall else 0

    # Identify strengths and weaknesses
    sorted_cats = sorted(categories.items(), key=lambda x: x[1]["average"], reverse=True)
    strengths = [c[0] for c in sorted_cats[:2]] if len(sorted_cats) >= 2 else [c[0] for c in sorted_cats]
    weaknesses = [c[0] for c in sorted_cats[-2:]] if len(sorted_cats) >= 2 else []

    # Trend: compare last 5 scores to previous 5
    trend = "stable"
    if len(all_scores) >= 10:
        prev = sum(all_scores[-10:-5]) / 5
        curr = sum(all_scores[-5:]) / 5
        if curr > prev + 0.05:
            trend = "improving"
        elif curr < prev - 0.05:
            trend = "declining"

    return {
        "apprentice": apprentice_name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "overall": {
            "lifetime_average": overall,
            "recent_average": recent_avg,
            "total_trials": len(all_scores),
            "trend": trend,
        },
        "categories": categories,
        "trials": trials,
        "strengths": strengths,
        "weaknesses": weaknesses,
    }


def save_star_chart(apprentice_name: str, chart: dict):
    path = REPO_ROOT / "apprentices" / apprentice_name / "star-chart.json"
    with open(path, "w") as f:
        json.dump(chart, f, indent=2)
    return path


def process_apprentice(name: str):
    entries = load_journal_entries(name)
    chart = compute_star_chart(name, entries)
    path = save_star_chart(name, chart)
    print(f"  {name}: {chart['overall']['total_trials']} trials, "
          f"avg {chart['overall']['lifetime_average']:.3f}, "
          f"trend: {chart['overall']['trend']} -> {path}")
    return chart


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <apprentice_name|--all>")
        sys.exit(1)

    if sys.argv[1] == "--all":
        apprentices_dir = REPO_ROOT / "apprentices"
        names = [d.name for d in apprentices_dir.iterdir()
                 if d.is_dir() and (d / "grimoire.yaml").exists()]
        print(f"Generating star charts for {len(names)} apprentices...")
        for name in sorted(names):
            process_apprentice(name)
    else:
        process_apprentice(sys.argv[1])


if __name__ == "__main__":
    main()
