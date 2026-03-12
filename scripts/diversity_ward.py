"""
Diversity Ward — detects convergence between apprentice grimoires and
introduces new selection pressure when agents become too similar.

Usage:
    python scripts/diversity_ward.py

Computes pairwise similarity between all grimoires. If any pair exceeds
the convergence threshold, opens an issue and (optionally) pulls a new
trial from the Well.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).parent.parent
CONVERGENCE_THRESHOLD = 0.85


def load_all_grimoires() -> dict[str, str]:
    """Load system prompts for all apprentices."""
    apprentices_dir = REPO_ROOT / "apprentices"
    grimoires = {}
    for d in sorted(apprentices_dir.iterdir()):
        grimoire_path = d / "grimoire.yaml"
        if d.is_dir() and grimoire_path.exists():
            with open(grimoire_path) as f:
                data = yaml.safe_load(f)
                grimoires[d.name] = data.get("system_prompt", "")
    return grimoires


def compute_similarity(text_a: str, text_b: str) -> float:
    """Compute Jaccard similarity on word trigrams."""
    def trigrams(text):
        words = text.lower().split()
        return set(
            tuple(words[i:i+3]) for i in range(len(words) - 2)
        )

    a_grams = trigrams(text_a)
    b_grams = trigrams(text_b)

    if not a_grams or not b_grams:
        return 0.0

    intersection = len(a_grams & b_grams)
    union = len(a_grams | b_grams)
    return intersection / union if union > 0 else 0.0


def check_convergence(grimoires: dict[str, str]) -> list[dict]:
    """Find all pairs that exceed the convergence threshold."""
    names = list(grimoires.keys())
    converging = []

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            sim = compute_similarity(grimoires[names[i]], grimoires[names[j]])
            if sim >= CONVERGENCE_THRESHOLD:
                converging.append({
                    "pair": (names[i], names[j]),
                    "similarity": round(sim, 3),
                })

    return converging


def pull_from_well() -> str | None:
    """Check if there are pending trials in the Well to introduce."""
    well_dir = REPO_ROOT / "the-well" / "open"
    candidates = list(well_dir.glob("*.yaml"))
    if candidates:
        return str(candidates[0].relative_to(REPO_ROOT))
    return None


def open_convergence_issue(converging: list[dict], new_trial: str | None):
    """Open a GitHub issue flagging the convergence."""
    pairs_text = "\n".join(
        f"- **{p['pair'][0]}** and **{p['pair'][1]}**: {p['similarity']:.1%} similar"
        for p in converging
    )

    trial_text = ""
    if new_trial:
        trial_text = f"\n\nA new trial has been pulled from the Well: `{new_trial}`"
    else:
        trial_text = ("\n\nNo pending trials in the Well. Consider submitting "
                      "a new challenge to create fresh selection pressure.")

    body = f"""## Diversity Ward Alert

The following apprentice pairs have exceeded the convergence threshold
({CONVERGENCE_THRESHOLD:.0%} similarity):

{pairs_text}

When apprentices converge, the academy loses the diversity that drives
creative improvement. New trials introduce fresh selection pressure that
pushes apprentices to specialize differently.
{trial_text}

---
*This issue was opened automatically by the Diversity Ward enchantment.*
"""

    subprocess.run([
        "gh", "issue", "create",
        "--title", "Diversity Ward: convergence detected",
        "--body", body,
        "--label", "diversity-ward",
    ], cwd=REPO_ROOT, check=True)


def main():
    print("Diversity Ward scanning...\n")

    grimoires = load_all_grimoires()
    print(f"Loaded {len(grimoires)} grimoires.")

    converging = check_convergence(grimoires)

    if not converging:
        print("No convergence detected. The academy remains diverse.")
        return 0

    print(f"\nConvergence detected in {len(converging)} pair(s):")
    for p in converging:
        print(f"  {p['pair'][0]} <-> {p['pair'][1]}: {p['similarity']:.1%}")

    new_trial = pull_from_well()
    if new_trial:
        print(f"\nPulling new trial from the Well: {new_trial}")

    print("\nOpening convergence issue...")
    open_convergence_issue(converging, new_trial)
    print("Diversity Ward complete.")

    return 1


if __name__ == "__main__":
    sys.exit(main())
