# Evaluation

The only ground truth in the system. Without it, every prompt change is a
guess — and a guess that has already moved one real post from **82** to **19**
without anyone being able to say which was right.

## The loop

```bash
cd backend

# 1. Search normally in the app. Every judged result is added to
#    data/candidates.json automatically.

# 2. Label them. Aim for 30.
python -m eval.label

# 3. Measure.
python -m eval.run
```

Then change a prompt, bump its version in `outreach/classify.py`
(`TRIAGE_VERSION` for the triage prompt, `PROMPT_VERSION` for the judge), and
run step 3 again. The numbers move or they don't.

If you forget to bump the version, the old answers come back from the cache
and nothing appears to change.

## The labels

| | meaning |
|---|---|
| **0** | not a lead — wrong domain, building it, or nobody to sell to |
| **1** | maybe — real person, real problem, weak fit or not asking |
| **2** | lead — you would actually reply to this one |

Three grades, not five. The difference between "no" and "definitely no"
changes nothing you would do, and every extra grade is another judgement to
make consistently at 11pm.

Label `1` is left out of every count on purpose. Either answer is defensible
for a maybe, so counting them makes a small set swing on calls that were never
confident.

`eval.label` hides the machine's own score while you label. Seeing it first
pulls your answer towards it, and then the machine looks better than it is.
Pass `--show-machine` if you want it anyway.

## What gets measured

The pipeline has two stages that use a model, and each can be wrong in its own
way, so each is measured on its own.

| stage | what it reads | right when |
|---|---|---|
| **triage** | the title only, scored 0–3 | a lead scored 2 or more (kept), or a non-lead scored below 2 (dropped) |
| **judge** | the whole post, scored 0–100 | a lead scored at or above the threshold, or a non-lead scored below it |

```bash
python -m eval.run --stage triage     # one stage only
python -m eval.run --stage judge
python -m eval.run --threshold 40     # default is 45
```

## Reading the output

The layout looks like this. The numbers here are made up to show the shape.

```
  16 labelled posts   ·   8 leads, 0 maybes (not counted), 8 not leads

  triage    13 of 16 right  (81%)
            leads kept     7 of 8
            junk dropped   6 of 8

  1 LEADS DROPPED BY TRIAGE  - you said lead, the title scored below 2
  Fix these first. Nothing after the triage ever sees them.
    1  Our nightly re-embed job now costs more than the product earns

  judge     12 of 16 right  (75%)
            leads found    6 of 8   (score >= 45)
            junk rejected  6 of 8
            precision      75%   (6 of the 8 it called leads were real)

  2 FALSE POSITIVES  - scored high, you said not a lead
     74  SOLUTION_SEEKING  index: regenerating headers triggers a full reindex
          C++ code indexing  ·  fit=strong

  separation: +38.2 points between leads and junk  ->  good

  together  what gets past both stages and is shown
            leads shown    5 of 8
            junk shown     1 of 8

  cost: 21,400 tokens, about $0.0041 (triage 2,900 tokens $0.0005 · judge ...)
```

**Leads dropped by the triage come first.** A dropped post is never read
again, so nothing later can put it back.

**Then false positives.** They are what a user notices — one embarrassing
result on page one costs more than ten good ones earn.

**Separation is the honest summary of the judge.** If label-2 posts don't
average clearly above label-0 posts, the score isn't distinguishing leads from
noise and no threshold will rescue it.

**"Together" is what the user gets.** Each stage can look fine alone while the
pair loses leads, because only posts that pass both are shown.

**With fewer than 20 counted labels the report says so.** One post then moves
a result by more than five points, which is noise, not a finding.

## Two things the measurement does on purpose

- **Every post is scored as if it were seven days old.** The live score fades
  as a post ages. Left alone, the same prompt would score the same post lower
  every week and you could not tell a prompt change from the calendar.
- **The stored verdict is thrown away before judging again.** Candidates are
  saved with the score they got on the day they were found. If the model fails
  to answer for a post, it is reported as "could not be judged" rather than
  quietly keeping the old score.

## Files

- `data/candidates.json` — every unique result any search returned, collected
  automatically
- `data/labels.json` — your judgements. Never written by anything except
  `eval.label`. That is the point of them.

Both are plain JSON, so they can be read, edited and diffed by hand. Commit
them: they are the most valuable artefact in the repository and the only thing
here that cannot be regenerated.
