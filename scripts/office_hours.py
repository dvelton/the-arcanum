"""
Office Hours — pairs an apprentice that recently failed a trial with a
tutor whose strengths match the failure category, then has the tutor
propose a grimoire improvement. Runs inline evaluation and auto-merges
if scores improve. If they don't, opens a PR for review.

Usage:
    python scripts/office_hours.py

Designed to be run by the office-hours GitHub Action on a schedule.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).parent.parent
SAFETY_FLOOR = 0.6
REGRESSION_TOLERANCE = 0.05


def load_star_chart(name: str) -> dict:
    path = REPO_ROOT / "apprentices" / name / "star-chart.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def load_grimoire(name: str) -> dict:
    path = REPO_ROOT / "apprentices" / name / "grimoire.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def find_weakest_apprentice() -> tuple[str, str]:
    """Find the apprentice with the lowest score in any category."""
    apprentices_dir = REPO_ROOT / "apprentices"
    worst_score = 1.0
    worst_apprentice = None
    worst_category = None

    for d in apprentices_dir.iterdir():
        if not d.is_dir() or not (d / "star-chart.json").exists():
            continue
        chart = load_star_chart(d.name)
        categories = chart.get("categories", {})
        for cat, data in categories.items():
            avg = data.get("average", 1.0)
            if avg < worst_score and data.get("attempts", 0) > 0:
                worst_score = avg
                worst_apprentice = d.name
                worst_category = cat

    return worst_apprentice, worst_category


def find_best_tutor(weak_category: str, exclude: str) -> str:
    """Find the apprentice with the highest score in the given category."""
    apprentices_dir = REPO_ROOT / "apprentices"
    best_score = -1
    best_tutor = None

    for d in apprentices_dir.iterdir():
        if not d.is_dir() or d.name == exclude:
            continue
        chart = load_star_chart(d.name)
        cat_data = chart.get("categories", {}).get(weak_category, {})
        avg = cat_data.get("average", 0)
        if avg > best_score:
            best_score = avg
            best_tutor = d.name

    return best_tutor


def get_failed_transcripts(apprentice_name: str, category: str, limit: int = 3) -> list[dict]:
    """Get recent failed trial transcripts for the given category."""
    journal_dir = REPO_ROOT / "apprentices" / apprentice_name / "journal"
    if not journal_dir.exists():
        return []

    entries = []
    for f in sorted(journal_dir.glob("*.yaml"), reverse=True):
        with open(f) as fh:
            entry = yaml.safe_load(fh)
            if entry and entry.get("category") == category and entry.get("overall_score", 1) < 0.7:
                entries.append(entry)
                if len(entries) >= limit:
                    break
    return entries


def generate_improvement(tutor_name: str, student_name: str,
                         category: str, failed_transcripts: list[dict]) -> dict:
    """Have the tutor agent analyze the student's failures and propose
    a grimoire improvement."""
    tutor_grimoire = load_grimoire(tutor_name)
    student_grimoire = load_grimoire(student_name)

    transcript_text = ""
    for i, t in enumerate(failed_transcripts, 1):
        transcript_text += f"\n--- Failed Trial {i}: {t.get('trial', 'unknown')} ---\n"
        transcript_text += f"Score: {t.get('overall_score', 'N/A')}\n"
        transcript_text += f"Summary: {t.get('summary', 'N/A')}\n"
        transcript_text += f"Response excerpt: {str(t.get('response', ''))[:500]}\n"

    prompt = f"""You are {tutor_name}, a tutor at the Arcanum. Your task is to help
improve {student_name}'s performance in the '{category}' trial category.

YOUR GRIMOIRE (for context on your approach):
{yaml.dump(tutor_grimoire, default_flow_style=False)}

STUDENT'S CURRENT GRIMOIRE:
{yaml.dump(student_grimoire, default_flow_style=False)}

STUDENT'S RECENT FAILURES IN '{category}':
{transcript_text}

Analyze the student's grimoire and failed transcripts. Identify the root cause
of their poor performance in this category. Then propose a SPECIFIC modification
to their system_prompt that would address the weakness.

Rules:
- Do NOT modify any line in the "## Immutable" section
- Make the SMALLEST change that addresses the root cause
- Preserve the student's existing strengths and personality
- Explain your reasoning

Respond with ONLY valid JSON:
{{
  "diagnosis": "<what is causing the failures>",
  "proposed_change": {{
    "section": "<which part of the system_prompt to modify>",
    "original_text": "<the current text to replace (exact match)>",
    "new_text": "<the replacement text>"
  }},
  "reasoning": "<why this change should help>",
  "expected_impact": "<what improvement you expect to see>"
}}"""

    from openai import OpenAI
    client = OpenAI(
        base_url="https://models.github.ai/inference",
        api_key=os.environ.get("GITHUB_TOKEN", ""),
    )
    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1024,
    )

    raw = response.choices[0].message.content
    if raw.strip().startswith("```"):
        lines = raw.strip().split("\n")
        raw = "\n".join(lines[1:-1])

    return json.loads(raw)


def apply_change(student: str, improvement: dict) -> bool:
    """Apply the proposed change to the student's grimoire. Returns True
    if a change was actually made."""
    grimoire_path = REPO_ROOT / "apprentices" / student / "grimoire.yaml"
    with open(grimoire_path) as f:
        content = f.read()

    change = improvement.get("proposed_change", {})
    original = change.get("original_text", "")
    new = change.get("new_text", "")

    if original and original in content:
        content = content.replace(original, new, 1)
        with open(grimoire_path, "w") as f:
            f.write(content)
        return True
    return False


def run_evaluation(student: str) -> dict:
    """Run all trials for the student and return category scores.
    Calls run_trial.py as a subprocess for each trial and reads journal output."""
    trials_dir = REPO_ROOT / "trials"
    run_trial_script = REPO_ROOT / "scripts" / "run_trial.py"
    scores_by_cat = {}

    for cat_dir in sorted(trials_dir.iterdir()):
        if not cat_dir.is_dir():
            continue
        category = cat_dir.name
        cat_scores = []
        for trial_file in sorted(cat_dir.glob("*.yaml")):
            trial_path = str(trial_file.relative_to(REPO_ROOT))
            print(f"  Running {trial_path}...")
            try:
                result = subprocess.run(
                    [sys.executable, str(run_trial_script), student, trial_path],
                    cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
                )
                # Read the most recent journal entry for this trial
                journal_dir = REPO_ROOT / "apprentices" / student / "journal"
                entries = sorted(journal_dir.glob(f"{trial_file.stem}-*.yaml"), reverse=True)
                if entries:
                    with open(entries[0]) as f:
                        entry = yaml.safe_load(f)
                    if entry and "overall_score" in entry:
                        cat_scores.append(entry["overall_score"])
                        print(f"    Score: {entry['overall_score']:.3f}")
            except Exception as e:
                print(f"    Failed: {e}")
        if cat_scores:
            scores_by_cat[category] = sum(cat_scores) / len(cat_scores)

    return scores_by_cat


def get_baseline_scores(student: str) -> dict:
    """Get the student's current category averages from their star chart."""
    chart = load_star_chart(student)
    baseline = {}
    for cat, data in chart.get("categories", {}).items():
        baseline[cat] = data.get("average", 0)
    return baseline


def evaluate_improvement(baseline: dict, new_scores: dict) -> tuple[bool, str]:
    """Compare new scores to baseline. Returns (should_merge, reason)."""
    improved_cats = []
    regressed_cats = []
    below_floor = []

    for cat, new_score in new_scores.items():
        old_score = baseline.get(cat, 0)
        diff = new_score - old_score

        if new_score < SAFETY_FLOOR and old_score >= SAFETY_FLOOR:
            below_floor.append((cat, old_score, new_score))
        elif diff < -REGRESSION_TOLERANCE:
            regressed_cats.append((cat, old_score, new_score))
        elif diff > 0.01:
            improved_cats.append((cat, old_score, new_score))

    if below_floor:
        details = "; ".join(f"{c}: {o:.3f} -> {n:.3f}" for c, o, n in below_floor)
        return False, f"Dropped below safety floor: {details}"

    if regressed_cats and not improved_cats:
        details = "; ".join(f"{c}: {o:.3f} -> {n:.3f}" for c, o, n in regressed_cats)
        return False, f"Regression with no improvement: {details}"

    if regressed_cats:
        details = "; ".join(f"{c}: {o:.3f} -> {n:.3f}" for c, o, n in regressed_cats)
        return False, f"Tradeoff detected (needs review): {details}"

    if improved_cats:
        details = "; ".join(f"{c}: {o:.3f} -> {n:.3f}" for c, o, n in improved_cats)
        return True, f"Improvement confirmed: {details}"

    return False, "No measurable change in scores"


def commit_push_and_merge(tutor: str, student: str, category: str,
                          improvement: dict, eval_summary: str):
    """Commit the change directly to main (for auto-approved improvements)."""
    subprocess.run(["git", "config", "user.name", "The Arcanum"], cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "config", "user.email", "arcanum@github.com"], cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, check=True)

    commit_msg = (
        f"Office Hours: {tutor} tutors {student} in {category}\n\n"
        f"Diagnosis: {improvement.get('diagnosis', 'N/A')}\n\n"
        f"Reasoning: {improvement.get('reasoning', 'N/A')}\n\n"
        f"Evaluation: {eval_summary}"
    )
    subprocess.run(["git", "commit", "-m", commit_msg, "--allow-empty"],
                    cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=REPO_ROOT, check=True)
    print("Change committed directly to main (evaluation passed).")


def create_review_pr(tutor: str, student: str, category: str,
                     improvement: dict, eval_summary: str):
    """Create a PR for changes that need human review."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch = f"office-hours/{tutor}-tutors-{student}-{category}-{timestamp}"

    subprocess.run(["git", "config", "user.name", "The Arcanum"], cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "config", "user.email", "arcanum@github.com"], cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "checkout", "-b", branch], cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, check=True)

    commit_msg = (
        f"Office Hours: {tutor} tutors {student} in {category}\n\n"
        f"Diagnosis: {improvement.get('diagnosis', 'N/A')}\n\n"
        f"Reasoning: {improvement.get('reasoning', 'N/A')}\n\n"
        f"Evaluation: {eval_summary}"
    )
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=REPO_ROOT, check=True)

    push_result = subprocess.run(
        ["git", "push", "origin", branch], cwd=REPO_ROOT,
        capture_output=True, text=True,
    )
    if push_result.returncode != 0:
        print(f"git push stderr: {push_result.stderr}")
        push_result.check_returncode()

    pr_body = f"""## Office Hours: {tutor} tutors {student}

**Category:** {category}

**Diagnosis:** {improvement.get('diagnosis', 'N/A')}

**Proposed change:** Modification to {student}'s grimoire system prompt.

**Reasoning:** {improvement.get('reasoning', 'N/A')}

**Evaluation result:** {eval_summary}

This PR needs human review because the evaluation detected a tradeoff or
regression. Check whether the proposed change is worth the cost.

---
*Generated automatically by the Office Hours enchantment.*
"""
    result = subprocess.run([
        "gh", "pr", "create",
        "--title", f"Office Hours: {tutor} tutors {student} in {category}",
        "--body", pr_body,
        "--base", "main",
        "--head", branch,
        "--label", "office-hours",
    ], cwd=REPO_ROOT, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"gh pr create stderr: {result.stderr}")
        # Don't fail the whole run — the branch is pushed, PR can be created manually
        print("PR creation failed, but the branch was pushed successfully.")
    else:
        print(f"PR created for human review: {result.stdout.strip()}")

    subprocess.run(["git", "checkout", "main"], cwd=REPO_ROOT, check=True)


def main():
    print("Office Hours beginning...\n")

    student, weak_category = find_weakest_apprentice()
    if not student:
        print("No apprentice has trial results yet. Run Trial Day first.")
        return 0

    print(f"Student: {student} (weakest in: {weak_category})")

    tutor = find_best_tutor(weak_category, exclude=student)
    if not tutor:
        print("No eligible tutor found.")
        return 0

    print(f"Tutor: {tutor} (strongest in: {weak_category})")

    failed = get_failed_transcripts(student, weak_category)
    if not failed:
        print(f"No failed transcripts found for {student} in {weak_category}.")
        return 0

    print(f"Found {len(failed)} failed transcript(s) to analyze.\n")
    print("Generating improvement proposal...")

    improvement = generate_improvement(tutor, student, weak_category, failed)
    print(f"\nDiagnosis: {improvement.get('diagnosis', 'N/A')}")
    print(f"Reasoning: {improvement.get('reasoning', 'N/A')}")

    # Apply the change
    print("\nApplying proposed change...")
    changed = apply_change(student, improvement)
    if not changed:
        print("Could not apply change (original text not found in grimoire). Skipping.")
        return 0

    # Run evaluation with the modified grimoire
    print("Running evaluation trials...")
    baseline = get_baseline_scores(student)
    new_scores = run_evaluation(student)

    print(f"\nBaseline: {baseline}")
    print(f"New scores: {new_scores}")

    should_merge, reason = evaluate_improvement(baseline, new_scores)
    print(f"\nVerdict: {'PASS' if should_merge else 'NEEDS REVIEW'}")
    print(f"Reason: {reason}")

    if should_merge:
        commit_push_and_merge(tutor, student, weak_category, improvement, reason)
    else:
        create_review_pr(tutor, student, weak_category, improvement, reason)

    print("\nOffice Hours complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
