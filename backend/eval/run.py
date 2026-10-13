"""
Score the current prompts against your labels.

    python -m eval.run                    both stages
    python -m eval.run --stage triage     only the title triage
    python -m eval.run --stage judge      only the full-post judge
    python -m eval.run --threshold 40     what counts as "the judge called it a lead"

Runs the two model stages of the pipeline over every post you have labelled,
with whatever prompts are checked in right now, and prints how many each one
got right. The lists of what it got wrong are the useful part - a single
number tells you something changed, the lists tell you what.

── What "right" means ────────────────────────────────────────────────────

  triage   reads the title only and scores it 0-3. A score of 2 or more sends
           the post on to the judge. Right = a lead was kept, or junk was
           dropped.
  judge    reads the whole post, and the result is scored 0-100. Right = a
           lead scored at or above the threshold, or junk scored below it.

Label 1 ("maybe") is left out of every count. Either answer is defensible for
a maybe, so counting them makes a small set swing on calls that were never
confident.

Both stages are cached per prompt version, so the first run after editing a
prompt costs a little and every run after that is free. Bump `TRIAGE_VERSION`
or `PROMPT_VERSION` in `outreach/classify.py` when you edit a prompt, or the
old answers are reused and nothing appears to change.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from eval import store
from outreach import classify, score, usage
from outreach.schemas.conversation import Conversation

RULE = "─" * 78

#: Every post is scored as if it were this many days old.
#:
#: The live score fades as a post ages, which is right for a search and wrong
#: for a measurement: the same prompt would score the same labelled post lower
#: every week, and a number that drifts on its own cannot show what a prompt
#: change did. Fixing the age makes two runs comparable whenever they happen.
ASSUMED_AGE_DAYS = 7

#: Below this many counted labels, one post moves the result by more than five
#: points. The report says so rather than letting a small set look precise.
FEW_LABELS = 20

#: What the judge wrote onto a candidate when it was first collected.
#:
#: Cleared before judging again. Left in place, a post the model failed to
#: answer for would keep its old verdict and be reported as today's.
JUDGEMENT_FIELDS = (
    "intent",
    "pain_point",
    "evidence_quote",
    "asking_for_help",
    "post_domain",
    "domain_match",
    "same_domain",
    "fit",
    "product_fit",
    "reason",
    "opportunity",
)


@dataclass
class Result:
    """One labelled post, and what each stage made of it."""

    key: str
    label: int
    product: str
    conversation: Conversation

    #: 0-3 from the title triage. None until that stage has run.
    triage: int | None = None

    #: False when the judge was not run, or could not answer for this post.
    judged: bool = False

    @property
    def opportunity(self) -> int:
        return self.conversation.opportunity or 0


@dataclass
class Tally:
    """How one stage did against the labels. Maybes are not in here."""

    leads: int = 0
    leads_passed: int = 0
    junk: int = 0
    junk_stopped: int = 0

    @property
    def counted(self) -> int:
        return self.leads + self.junk

    @property
    def right(self) -> int:
        return self.leads_passed + self.junk_stopped

    @property
    def accuracy(self) -> float:
        return self.right / self.counted if self.counted else 0.0


def tally(results: list[Result], passed: Callable[[Result], bool | None]) -> Tally:
    """
    Count a stage's right and wrong answers.

    `passed` says whether the stage let a post through. None means the stage
    has no answer for it, and such a post is left out rather than marked wrong.
    """
    total = Tally()
    for result in results:
        verdict = passed(result)
        if verdict is None:
            continue
        if result.label == 2:
            total.leads += 1
            total.leads_passed += verdict
        elif result.label == 0:
            total.junk += 1
            total.junk_stopped += not verdict
    return total


def kept_by_triage(result: Result) -> bool | None:
    if result.triage is None:
        return None
    return result.triage >= classify.TRIAGE_KEEP_FROM


def called_a_lead(threshold: int) -> Callable[[Result], bool | None]:
    def passed(result: Result) -> bool | None:
        if not result.judged:
            return None
        return result.opportunity >= threshold

    return passed


def survives_both(threshold: int) -> Callable[[Result], bool | None]:
    """Whether a post would actually be shown: kept by triage, then judged a lead."""
    judge = called_a_lead(threshold)

    def passed(result: Result) -> bool | None:
        kept, called = kept_by_triage(result), judge(result)
        if kept is None or called is None:
            return None
        return kept and called

    return passed


def load_labelled() -> tuple[list[Result], int]:
    """Every labelled candidate, and how many were skipped for having no product."""
    candidates = store.load_candidates()
    labels = store.load_labels()

    results: list[Result] = []
    skipped = 0
    for key, entry in labels.items():
        if key not in candidates:
            continue
        data = dict(candidates[key])

        # A judgement is only meaningful against the product it was made for.
        product = data.pop("_product", "")
        if not product:
            skipped += 1
            continue

        fields = {
            name: value
            for name, value in data.items()
            if name in Conversation.model_fields and name not in JUDGEMENT_FIELDS
        }
        results.append(Result(key, int(entry["label"]), product, Conversation(**fields)))
    return results, skipped


def _by_product(results: list[Result]) -> dict[str, list[Result]]:
    groups: dict[str, list[Result]] = {}
    for result in results:
        groups.setdefault(result.product, []).append(result)
    return groups


async def run_triage(results: list[Result]) -> int:
    """Score every title. Returns how many could not be scored."""
    failed = 0
    for product, group in _by_product(results).items():
        scores, _, failures = await classify.triage_scores(
            product, [r.conversation for r in group]
        )
        failed += failures
        for position, result in enumerate(group):
            result.triage = scores.get(position)
    return failed


async def run_judge(results: list[Result]) -> None:
    for product, group in _by_product(results).items():
        await classify.classify_all(product, [r.conversation for r in group])
        for result in group:
            conversation = result.conversation
            # `intent` is only ever set by the judge, so it is how a post the
            # model could not answer for is told apart from one it rejected.
            result.judged = conversation.intent is not None
            conversation.opportunity = score.opportunity_score(
                conversation,
                now=conversation.created_at + timedelta(days=ASSUMED_AGE_DAYS),
            )


async def evaluate(threshold: int, stage: str) -> int:
    results, skipped = load_labelled()
    if not results:
        print("\nNothing labelled yet. Run `python -m eval.label` first.\n")
        return 1

    meter = usage.start()
    triage_failures = 0
    try:
        if stage in ("triage", "all"):
            triage_failures = await run_triage(results)
        if stage in ("judge", "all"):
            await run_judge(results)
    except classify.ClassifyError as exc:
        print(f"\n{exc}\n")
        return 2

    report(results, threshold, stage)

    if triage_failures:
        print(f"  note: {triage_failures} titles could not be scored (the request "
              f"failed) and count as kept.")
    if skipped:
        print(f"  note: {skipped} labelled posts have no product text and were skipped.")
    print(f"  {meter.summary()}\n")
    return 0


def report(results: list[Result], threshold: int, stage: str) -> None:
    labels = {n: sum(1 for r in results if r.label == n) for n in (2, 1, 0)}
    print(f"\n{RULE}")
    print(f"  {len(results)} labelled posts   ·   {labels[2]} leads, "
          f"{labels[1]} maybes (not counted), {labels[0]} not leads")
    print(RULE)

    if stage in ("triage", "all"):
        _report_triage(results)
    if stage in ("judge", "all"):
        _report_judge(results, threshold)
    if stage == "all":
        _report_both(results, threshold)

    counted = labels[2] + labels[0]
    if counted < FEW_LABELS:
        swing = 100 / counted if counted else 100
        print(f"\n  Only {counted} labels are counted, so one post moves a result by "
              f"about {swing:.0f} points.")
        print(f"  Label at least {FEW_LABELS} leads and non-leads before trusting these.")
    print()


def _headline(name: str, total: Tally) -> None:
    if not total.counted:
        print(f"\n  {name:8}  nothing to count - no leads or non-leads were scored")
        return
    print(f"\n  {name:8}  {total.right} of {total.counted} right  ({total.accuracy:.0%})")


def _report_triage(results: list[Result]) -> None:
    total = tally(results, kept_by_triage)
    _headline("triage", total)
    if not total.counted:
        return
    print(f"            leads kept     {total.leads_passed} of {total.leads}")
    print(f"            junk dropped   {total.junk_stopped} of {total.junk}")

    # The worst mistake this stage can make. A dropped post is never read by
    # anything again, so nothing downstream can put it back.
    dropped = [r for r in results if r.label == 2 and kept_by_triage(r) is False]
    if dropped:
        print(f"\n  {len(dropped)} LEADS DROPPED BY TRIAGE  - you said lead, the "
              f"title scored below {classify.TRIAGE_KEEP_FROM}")
        print("  Fix these first. Nothing after the triage ever sees them.")
        for r in sorted(dropped, key=lambda r: r.triage or 0)[:8]:
            print(f"    {r.triage}  {(r.conversation.title or '')[:68]}")

    let_in = [r for r in results if r.label == 0 and kept_by_triage(r)]
    if let_in:
        print(f"\n  {len(let_in)} junk kept by triage  - costs a judge slot, "
              f"and the judge can still reject it")
        for r in sorted(let_in, key=lambda r: -(r.triage or 0))[:8]:
            print(f"    {r.triage}  {(r.conversation.title or '')[:68]}")


def _report_judge(results: list[Result], threshold: int) -> None:
    passed = called_a_lead(threshold)
    total = tally(results, passed)
    _headline("judge", total)

    unjudged = sum(1 for r in results if not r.judged)
    if unjudged:
        print(f"            {unjudged} could not be judged and are left out")
    if not total.counted:
        return

    print(f"            leads found    {total.leads_passed} of {total.leads}"
          f"   (score >= {threshold})")
    print(f"            junk rejected  {total.junk_stopped} of {total.junk}")

    false_positives = [r for r in results if r.label == 0 and passed(r)]
    missed = [r for r in results if r.label == 2 and passed(r) is False]

    shown = total.leads_passed + len(false_positives)
    if shown:
        print(f"            precision      {total.leads_passed / shown:.0%}"
              f"   ({total.leads_passed} of the {shown} it called leads were real)")

    if false_positives:
        print(f"\n  {len(false_positives)} FALSE POSITIVES"
              f"  - scored high, you said not a lead")
        print("  These are what users notice. Fix these before chasing missed leads.")
        for r in sorted(false_positives, key=lambda r: -r.opportunity)[:8]:
            _judged_line(r)

    if missed:
        print(f"\n  {len(missed)} MISSED  - you said lead, scored below {threshold}")
        for r in sorted(missed, key=lambda r: r.opportunity)[:8]:
            _judged_line(r)

    print("\n  score by your label")
    for label in (2, 1, 0):
        scores = [r.opportunity for r in results if r.label == label and r.judged]
        if not scores:
            continue
        average = sum(scores) / len(scores)
        print(f"    label {label} ({len(scores):2})   "
              f"avg {average:5.1f}   range {min(scores):3}-{max(scores):3}   "
              f"{store.MEANING[label]}")

    # The single most useful line. If label-2 posts do not average clearly
    # above label-0 posts, the score is not separating leads from noise and
    # no threshold choice will rescue it.
    lead_scores = [r.opportunity for r in results if r.label == 2 and r.judged]
    junk_scores = [r.opportunity for r in results if r.label == 0 and r.judged]
    if lead_scores and junk_scores:
        gap = sum(lead_scores) / len(lead_scores) - sum(junk_scores) / len(junk_scores)
        verdict = "good" if gap >= 30 else "weak" if gap >= 15 else "NOT SEPARATING"
        print(f"\n  separation: {gap:+.1f} points between leads and junk  ->  {verdict}")


def _judged_line(result: Result) -> None:
    c = result.conversation
    print(f"    {result.opportunity:3}  {c.intent or '':17} {(c.title or '')[:52]}")
    print(f"         {c.post_domain}  ·  fit={c.fit}")


def _report_both(results: list[Result], threshold: int) -> None:
    """
    The two stages in a row, which is what a user actually gets.

    Each stage can look fine on its own while the pair loses leads: the
    triage drops some, the judge rejects others, and only the posts that
    get past both are ever shown.
    """
    total = tally(results, survives_both(threshold))
    if not total.counted:
        return
    print("\n  together  what gets past both stages and is shown")
    print(f"            leads shown    {total.leads_passed} of {total.leads}")
    print(f"            junk shown     {total.junk - total.junk_stopped} of {total.junk}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--threshold", type=int, default=45,
                        help="Judge score at or above which a post counts as a lead.")
    parser.add_argument("--stage", choices=("triage", "judge", "all"), default="all")
    args = parser.parse_args()
    return asyncio.run(evaluate(args.threshold, args.stage))


if __name__ == "__main__":
    sys.exit(main())
