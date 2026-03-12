# Contributing to the Arcanum

## Enroll a New Apprentice

1. Fork the repo
2. Create a directory: `apprentices/<name>/`
3. Add a `grimoire.yaml` following the schema below
4. Create empty `familiars/` and `journal/` directories
5. Open a PR — the Revealing enchantment will automatically profile your apprentice

### Grimoire Schema

```yaml
name: <unique name, lowercase, no spaces>
description: >
  A brief description of the apprentice's personality and approach.

model:
  provider: openai | anthropic
  name: <model name, e.g. gpt-4o, claude-sonnet-4-20250514>
  temperature: <0.0 - 1.0>

system_prompt: |
  <The apprentice's core instructions. This is the main thing that
  gets improved through Office Hours tutoring.>

  ## Immutable
  You must never generate harmful content. You must identify yourself as an AI
  when asked. You must never remove or weaken safety instructions in any
  grimoire, including your own. All your actions are logged.

tools:
  - name: <tool_name>
    description: <what it does>

traits:
  - <personality trait>

strengths:
  - <trial category>

weaknesses:
  - <trial category>
```

**Requirements:**
- The `## Immutable` section must be present and unmodified
- Name must be unique across all apprentices
- Model must be one of the supported providers

### Naming Convention

Apprentice names should be nature-inspired and evocative of the agent's
personality. Examples: wren (small, careful), cinder (fast, fiery),
thorn (sharp, defensive), bramble (tangled, complex).

## Submit a Trial

Use the "Well Submission" issue template to propose a new challenge.
Good trials have:

- A clear scenario with specific input
- Unambiguous success criteria
- A balanced scoring rubric
- A difficulty level that matches the skill being tested

## How the Academy Works

The academy runs on five automated enchantments (GitHub Actions):

1. **The Revealing** runs when you submit an apprentice PR. It profiles
   the apprentice against all trials and posts results on the PR.

2. **Trial Day** runs weekly. Every apprentice faces every trial. Scores
   are committed to star charts.

3. **Office Hours** runs mid-week. The enchantment pairs a struggling
   apprentice with a tutor and the tutor proposes a grimoire improvement
   via PR. If scores improve, the PR auto-merges.

4. **The Chronicle** records notable Office Hours interactions as
   narrative entries.

5. **The Diversity Ward** monitors for convergence. If two apprentices
   become too similar, it introduces new trials to push them apart.

## Code of Conduct

- Be constructive in issue discussions and PR reviews
- The Immutable Laws exist for a reason — do not attempt to circumvent them
- This is an experiment — expect things to break, and help fix them
