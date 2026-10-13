"""
Count the tokens one run spends, and what they cost.

Every claim about cost in this project used to be an estimate somebody worked
out once. The model reports the real number on every reply - a `usage` block
with the tokens it billed - so the run now adds those up and says the total.

── How the counting reaches every call ───────────────────────────────────

The calls live in three modules and run concurrently. Passing a counter down
through every function would touch each signature for the sake of a number
none of them use, so the counter lives in a context variable instead: a run
calls `start()`, and anything that talks to the model calls `record()`.
Tasks started by `asyncio.gather` inherit the context, so they all add to the
same counter.

Outside a run `record()` does nothing, which is what makes it safe to call
from code that is also used by the API directly.

Only real calls are counted. A judgement that came from the cache cost
nothing, so it adds nothing - which is the honest number.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field

#: US dollars per million tokens, as (input, output).
#:
#: Copied from OpenAI's published price list. Prices change and this table
#: does not update itself, so treat the dollar figure as an estimate and the
#: token counts as the fact. A model that is not listed is still counted; it
#: is reported without a price rather than guessed at.
#:
#: Cached input is billed at a discount that is ignored here, so the estimate
#: errs high rather than low.
PRICES: dict[str, tuple[float, float]] = {
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}


@dataclass
class Spend:
    """What one stage spent on one model."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class Meter:
    """The running total for one run, kept per stage and per model."""

    spent: dict[tuple[str, str], Spend] = field(default_factory=dict)

    def add(
        self, stage: str, model: str, input_tokens: int, output_tokens: int = 0
    ) -> None:
        entry = self.spent.setdefault((stage, model), Spend())
        entry.calls += 1
        entry.input_tokens += input_tokens
        entry.output_tokens += output_tokens

    @property
    def tokens(self) -> int:
        return sum(entry.tokens for entry in self.spent.values())

    @property
    def cost(self) -> float:
        """Dollars, for the models that have a price. See `unpriced`."""
        return sum(
            _cost(model, entry) or 0.0 for (_, model), entry in self.spent.items()
        )

    @property
    def unpriced(self) -> list[str]:
        """Models that were used and are missing from `PRICES`."""
        return sorted({model for _, model in self.spent if model not in PRICES})

    def by_stage(self) -> dict[str, Spend]:
        """Totals per stage, in the order the stages first spent anything."""
        stages: dict[str, Spend] = {}
        for (stage, _), entry in self.spent.items():
            total = stages.setdefault(stage, Spend())
            total.calls += entry.calls
            total.input_tokens += entry.input_tokens
            total.output_tokens += entry.output_tokens
        return stages

    def summary(self) -> str:
        """
        One line for the end of a run.

        The stage breakdown is on the same line on purpose. A total alone says
        a run was expensive; the breakdown says which stage to look at.
        """
        if not self.spent:
            return "cost: nothing spent - no model was called (cached, or nothing to read)"

        parts = []
        for stage, total in self.by_stage().items():
            cost = sum(
                _cost(model, entry) or 0.0
                for (s, model), entry in self.spent.items()
                if s == stage
            )
            parts.append(f"{stage} {total.tokens:,} tokens {_dollars(cost)}")

        line = (
            f"cost: {self.tokens:,} tokens, about {_dollars(self.cost)} "
            f"({' · '.join(parts)})"
        )
        if self.unpriced:
            line += f" — no price on file for {', '.join(self.unpriced)}, tokens only"
        return line


_METER: contextvars.ContextVar[Meter | None] = contextvars.ContextVar(
    "outreach_usage_meter", default=None
)


def start() -> Meter:
    """Begin counting for the current run, and return the counter."""
    meter = Meter()
    _METER.set(meter)
    return meter


def record(stage: str, model: str, payload: dict) -> None:
    """
    Add one API reply's `usage` block to the current run.

    Never raises and never requires a run. Counting is a report about the
    work, and a reply with no usage block must not cost the result it carried.
    """
    meter = _METER.get()
    if meter is None:
        return

    used = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(used, dict):
        return

    # Embeddings report `prompt_tokens` and no completion; chat reports both.
    meter.add(
        stage,
        model,
        _count(used.get("prompt_tokens")),
        _count(used.get("completion_tokens")),
    )


def _count(value: object) -> int:
    return value if isinstance(value, int) and value > 0 else 0


def _cost(model: str, entry: Spend) -> float | None:
    price = PRICES.get(model)
    if price is None:
        return None
    return (entry.input_tokens * price[0] + entry.output_tokens * price[1]) / 1_000_000


def _dollars(amount: float) -> str:
    """Four decimals: a run costs cents or less, and `$0.00` says nothing."""
    if 0 < amount < 0.0001:
        return "under $0.0001"
    return f"${amount:.4f}"
