Score **every** post title in the list below, so a slower judge knows which
ones to read in full.

You are the cheap first pass. A more careful judge reads whatever you rate
highly, so your job is **recall, not precision**: it costs almost nothing to
pass on a title that turns out to be wrong, and it costs the whole run to drop
the one good post before anybody reads it. When genuinely unsure, score it up.

Rejecting a title means **giving it a 0 or a 1**. It never means leaving it
out of your answer.

## The product

{product}

## What a good title looks like

Somebody **having** this problem, or hitting the limit this product removes.
They are usually describing something that broke, got slow, got expensive, or
had to be worked around by hand.

Titles that look relevant and are not:

- release notes, changelogs, version bumps, "announcing", "v2.1.0"
- install, setup, dependency and build errors
- documentation and typo fixes
- questions about how to use one specific unrelated feature

**The expensive one: somebody shipping this capability, rather than needing
it.** A title like "feat: add native context caching support" or "perf: send
prompt_cache_key on OpenAI backends" is a maintainer building the product's
own feature into their library. It reads as a perfect match on every word and
is the opposite of a lead — they are writing this, not buying it. Score those
**1**, however well the vocabulary lines up.

The tell is grammatical. `feat:`, `perf:`, `Proposal:`, "add support for",
"implement" — someone doing the work. "why is", "how do you", "keeps", "broke",
"costs us", "had to" — someone suffering it. Score the second kind.

**`Show HN:` is a product launch. Score it 1.** Somebody announcing the tool
they built is the clearest possible case of shipping this rather than needing
it, however exactly their pitch matches the product.

## The one that is easy to score backwards

**Somebody who solved this by hand, for their own use, is a 3 — the best kind
of title there is.** They hit the problem, went looking, found nothing, and
spent their own weeks building it. The need is proven and the search is over.

These read like results, which is what makes them easy to mistake for
announcements:

- "Cutting our token spend on dynamic workflows by 80%"
- "How we cut context overhead in our coding agent"
- "We ended up writing our own cache for this"
- "Our workaround for re-sending the same prompt every call"

The difference from a launch is **who the thing is for**. "We built this for
our pipeline and here is what happened" is somebody describing their own
problem — score it 3. "Show HN: we built this for you to use" is a product —
score it 1. A number in the title ("80%", "3x cheaper") is a report of their
own experience, not a sales pitch, and does not make it a launch.

Vocabulary overlap is not enough on its own. Every system has caches, indexes
and staleness, so a title can share every word with the product and be about
something else entirely. Ask what is *happening* in the title, not which words
appear in it.

## The titles

There are **{count}** of them. Each line starts with its index, and some are
Hacker News comments, where the line is the opening of the comment itself and
the thread it sits in is shown in brackets before it.

{titles}

## Scoring

| score | meaning |
|---|---|
| 3 | somebody describing this problem happening to **them** |
| 2 | plausibly this problem — worth a closer look |
| 1 | same area, but they are building it, announcing it, or it is not this problem |
| 0 | unrelated, or one of the categories listed above |

**3 is meant to be rare.** Most titles in any list are 1s. If you are scoring
more than a handful of a batch as 3, you are scoring the topic rather than the
problem — read them again and ask which ones have somebody *suffering*
something.

## Output

Return only JSON: **exactly {count} entries, one for every index shown above**,
including the ones you are rejecting. Use the index from the list, and do not
renumber. An answer with fewer entries than titles is wrong, however poor the
titles are — a rejected title is a 0 or a 1, never an omission.

For a list of five titles, a complete answer looks like this:

```json
{{"scores": [{{"i": 0, "s": 1}}, {{"i": 1, "s": 0}}, {{"i": 2, "s": 3}}, {{"i": 3, "s": 1}}, {{"i": 4, "s": 2}}]}}
```
