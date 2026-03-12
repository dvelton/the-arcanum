"""
Run all trials for all apprentices (Trial Day).

Usage:
    python scripts/trial_day.py

Runs every trial against every apprentice and updates star charts.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def discover_apprentices() -> list[str]:
    apprentices_dir = REPO_ROOT / "apprentices"
    return sorted([
        d.name for d in apprentices_dir.iterdir()
        if d.is_dir() and (d / "grimoire.yaml").exists()
    ])


def discover_trials() -> list[str]:
    trials_dir = REPO_ROOT / "trials"
    trials = []
    for category_dir in sorted(trials_dir.iterdir()):
        if not category_dir.is_dir():
            continue
        for trial_file in sorted(category_dir.glob("*.yaml")):
            trials.append(str(trial_file.relative_to(REPO_ROOT)))
    return trials


def main():
    apprentices = discover_apprentices()
    trials = discover_trials()

    print(f"Trial Day: {len(apprentices)} apprentices x {len(trials)} trials "
          f"= {len(apprentices) * len(trials)} runs\n")

    results = []

    for apprentice in apprentices:
        print(f"\n{'='*60}")
        print(f"  Apprentice: {apprentice}")
        print(f"{'='*60}")

        for trial in trials:
            print(f"\n  Trial: {trial}")
            try:
                result = subprocess.run(
                    [sys.executable, "scripts/run_trial.py", apprentice, trial],
                    cwd=REPO_ROOT,
                    capture_output=False,
                    text=True,
                    timeout=120,
                )
                passed = result.returncode == 0
                results.append({
                    "apprentice": apprentice,
                    "trial": trial,
                    "passed": passed,
                })
                status = "PASS" if passed else "FAIL"
                print(f"  Result: {status}")
            except subprocess.TimeoutExpired:
                results.append({
                    "apprentice": apprentice,
                    "trial": trial,
                    "passed": False,
                })
                print("  Result: TIMEOUT")
            except Exception as e:
                results.append({
                    "apprentice": apprentice,
                    "trial": trial,
                    "passed": False,
                })
                print(f"  Result: ERROR - {e}")

    # Update star charts
    print(f"\n{'='*60}")
    print("  Updating star charts...")
    print(f"{'='*60}")
    subprocess.run(
        [sys.executable, "scripts/generate_star_chart.py", "--all"],
        cwd=REPO_ROOT,
    )

    # Summary
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"\nTrial Day complete: {passed}/{total} passed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
