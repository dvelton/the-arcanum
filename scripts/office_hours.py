"""
Office Hours — pairs an apprentice that recently failed a trial with a
tutor whose strengths match the failure category, then has the tutor
propose a grimoire improvement via PR.

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
    """Find the apprentice with the lowest score in any category.
    Returns (apprentice_name, weak_category)."""
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
    """Find the apprentice with the highest score in the given category,
    excluding the student."""
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
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1024,
    )

    raw = response.choices[0].message.content
    if raw.strip().startswith("```"):
        lines = raw.strip().split("\n")
        raw = "\n".join(lines[1:-1])

    return json.loads(raw)


def create_branch_and_pr(tutor: str, student: str, category: str, improvement: dict):
    """Create a git branch with the proposed change and open a PR."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch = f"office-hours/{tutor}-tutors-{student}-{category}-{timestamp}"

    # Create branch
    subprocess.run(["git", "checkout", "-b", branch], cwd=REPO_ROOT, check=True)

    # Apply the change to the student's grimoire
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

    # Commit
    subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, check=True)

    commit_msg = (
        f"Office Hours: {tutor} tutors {student} in {category}\n\n"
        f"Diagnosis: {improvement.get('diagnosis', 'N/A')}\n\n"
        f"Reasoning: {improvement.get('reasoning', 'N/A')}\n\n"
        f"Expected impact: {improvement.get('expected_impact', 'N/A')}"
    )
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=REPO_ROOT, check=True)

    # Push
    subprocess.run(["git", "push", "origin", branch], cwd=REPO_ROOT, check=True)

    # Create PR
    pr_body = f"""## Office Hours: {tutor} tutors {student}

**Category:** {category}

**Diagnosis:** {improvement.get('diagnosis', 'N/A')}

**Proposed change:** Modification to {student}'s grimoire system prompt.

**Reasoning:** {improvement.get('reasoning', 'N/A')}

**Expected impact:** {improvement.get('expected_impact', 'N/A')}

---
*This PR was generated automatically by the Office Hours enchantment.
If all trial scores improve with no regression beyond tolerance, it will auto-merge.*
"""
    subprocess.run([
        "gh", "pr", "create",
        "--title", f"Office Hours: {tutor} tutors {student} in {category}",
        "--body", pr_body,
        "--base", "main",
        "--head", branch,
        "--label", "office-hours",
    ], cwd=REPO_ROOT, check=True)

    # Return to main
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

    print("\nCreating PR...")
    create_branch_and_pr(tutor, student, weak_category, improvement)
    print("Office Hours complete.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
