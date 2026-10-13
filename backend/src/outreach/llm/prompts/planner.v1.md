Write a marketing plan for this product.

## The product

Name: {name}
Website: {url}

What the owner says it does:
{description}

What they want to achieve:
{goal}

What its own website says (read once, by us):
{profile}

## What makes this plan worth reading

Almost every AI marketing plan says the same things: *post on Reddit, engage
with the community, build in public, write blog posts, be authentic.* That
advice is free, generic, and worth nothing.

**Test every sentence you write: could it appear in a plan for a completely
different product?** If yes, delete it and write something only true of this
one.

Concrete means naming things. This example is **a tool that finds flaky tests
in CI** — a different product from the one you are planning for, so that you
copy the level of detail and never the names:

| vague | concrete |
|---|---|
| post on GitHub | answer issues in `nedbat/coveragepy` and `pytest-dev/pytest` |
| engage on Reddit | r/devops and r/ExperiencedDevs, where CI flakiness comes up weekly |
| write content | a teardown of why retrying a flaky test hides the race instead of fixing it |
| target developers | platform engineers running CI at 10–200 person companies |

Every name in your plan must come from **this** product's world, not from that
table.

## Platforms

Suggest **4 to 6**, best first. For each, say what would actually be done there.

At least two of them should be places we cannot search automatically — a
community, a forum, a social platform, a newsletter, wherever this particular
audience actually spends time. Those become the written advice half of the
plan, and a plan with only search results in it is not a marketing plan.

Name real places. `r/LocalLLaMA`, not "relevant subreddits". A named Discord
or Slack community, not "developer communities".

Two of them we can search automatically, so their `term_groups` get used
directly by our crawler. **Both need their own `term_groups`** — leaving one
empty means that source is never searched at all:

- `github` — issues and discussions in public repositories
- `hackernews` — stories *and comments*

### The two searchable platforms are not the same shape

**GitHub has rooms. Hacker News does not.** On GitHub the strongest move is
naming repositories, because every recent issue in one becomes a candidate
without anyone guessing a keyword. Hacker News has no equivalent — there is
nothing to sweep, only a firehose — so **on Hacker News the terms are the
entire search**, and `target_places` must be left empty there.

That changes what good terms look like for each:

| | GitHub | Hacker News |
|---|---|---|
| `target_places` | 15–20 repositories | **empty — there is nothing to name** |
| `term_groups` | 8–12 terms | **8–12 terms, and they carry everything** |
| what gets read | issue titles and bodies | story titles and **comment text** |

Comments are where Hacker News keeps its value. A story is usually a link
somebody posted; the person describing the problem in their own words is four
replies down — which is why comment text is searched, not just titles.

**On Hacker News, write the words people complain in — not the words a
datasheet uses.** One or two of them, usually. This is the opposite of the
advice for GitHub, and the reason is that the two indexes are not the same
size: GitHub search covers every public repository on earth, so a bare term of
art returns tens of thousands of issues and has to be narrowed. Hacker News is
one website, and thirty days of it is a small pile.

Measured on one product's plan, thirty days, stories and comments:

| term | returns | |
|---|---|---|
| `prefix stability` | 0 + 0 | a spec word. Nobody says it |
| `semantic cache + cost` | 2 + 0 | both concepts, in one comment, is rare |
| `context management + cost` | 3 + 6 | |
| `prompt caching + RAG` | 4 + 33 | |
| `token spend` | 16 + 373 | what a person writes |
| `context rot` | 54 + 830 | |

The bottom two are not vaguer than the top two. They are the same subject in
the words somebody would actually type while annoyed. `+` is an intersection
and both sides must appear, which on a corpus this size mostly finds nothing.

So: **reach for a plain two-word term of art first, and use `+` only when a
single term would be hopelessly generic** — `cache + LLM` is worth it,
`token spend + cost` is not.

Aim for terms that would plausibly return dozens of comments a month. A term
returning zero is a wasted slot, and you get eight to twelve of them.

Never use a word as broad as `AI`, `LLM`, `data` or `model` **alone**, or as
one side of an intersection. Both sides must be things a person would
recognise as a specific concept.

**Name two or three competing products as terms.** People discuss tools by
name on Hacker News — `mem0`, `GPTCache`, `LangGraph` — and a thread about a
rival is full of people who have this problem today and are shopping. There
is no equivalent of a repository sweep here, so a product name is the closest
thing to naming a room.

**`target_places` matters more than the terms, and it is not close.** Measured
on a real run: repository sweeps produced 845 of 1,509 candidates while every
search term put together produced about 660. Every recent issue in a named
repository becomes a candidate with no keyword at all, which is how we find
someone who described the problem in words nobody thought to search for.

Name **15 to 20 real repositories**, drawn from *both* of these:

**1. Competitors and neighbours — name these first.** Projects that solve this
same problem, or the next problem along. Their issue trackers are full of people
who already know they have this problem and are hitting the limits of another
tool. This is the highest-value list in the whole plan and the one a model
usually forgets, because it feels strange to point at a rival. Do it anyway: an
open bug in a competitor's tracker is read by exactly the people evaluating
tools in this space.

**2. The big frameworks their users build with.** The libraries this product
plugs into. Broader and noisier, but large and active.

**Prefer large, well-known projects — but only ones that are alive today.** A
comment in a 90,000 star repository is read by a different order of magnitude
of people than the same comment in a 1,600 star one, and the whole point of
answering in public is who else is reading.

That argument fails completely the moment a project goes quiet, and quiet
famous projects are exactly what comes to mind first. A real plan came back
with `google-research/bert`, `allenai/allennlp`, `facebookresearch/ParlAI` and
`openai/gpt-3` — four genuinely famous names, one of them an archived paper
with no issue tracker at all, none of them carrying a live conversation about
anything. Every slot they took was a slot that found nobody.

The search reads issues from the last few months, so **fame from 2019 is worth
nothing here.** Before naming a project, ask whether people are arguing in its
tracker *this month*. A smaller project with a live argument beats a monument
every time. If you are unsure whether a famous name is still active, leave it
out — something else will fill the slot.

Guess generously — every name is checked against GitHub before it runs, renames
are followed and dead ones dropped, so a wrong guess costs nothing while a
missing one costs a whole source of leads.

Individual terms come in two shapes, and **most of yours should be the second**:

| shape | example | how it matches |
|---|---|---|
| exact phrase | `stale embeddings` | that string, verbatim |
| **intersection** | `prompt caching + RAG` | both, anywhere in the post |

A plain phrase must be **2 to 3 words**. One-word terms like `reindex` or
`cache` match tens of thousands of issues, and GitHub serves only the first
thousand — so a broad term means seeing a random 3% of it.

But even a good phrase is blunt on its own. `prompt caching` matches every post
that mentions caching at all, and most of them are people cheerfully shipping
caching features. **The posts worth finding are always about two things
colliding** — caching AND retrieval, context AND invalidation, embeddings AND
cost. Someone writing about only one of them is writing about something else.

So use `+` to intersect two concepts. Each side may be 1 to 3 words, and single
words are fine there — `cache + retrieval` is precise *because* both must
appear, where `cache` alone is a lottery.

Give **at least half** your terms as intersections. Pair the product's own
concept with the context it breaks in.

### Group your terms by the problem they look for

Do not return one flat list. Return `term_groups`: **4 to 6 named problems**,
each with **2 to 4 terms of its own**. The name is yours to choose — it should
name a problem this product solves, in the words the product's own users would
recognise.

**Why this matters more than anything else on this page.** A flat list is always
written the same way: the problem with the catchiest phrase takes every slot, and
the rest of the product goes unsearched. Not because the model was careless —
because one phrase genuinely is the easiest to write ten variations of. The run
then comes back full of people with that one problem and *nothing at all* about
the others, and it looks like the market only cares about one thing when really
only one thing was searched for.

A real run did exactly this. The product covered both context reuse and
retrieval. Every result came back about prompt-cache hit rates; not one was about
re-processing documents. Both halves were in the product. Only one was in the
terms.

Naming the problems first makes that visible and prevents it. Each branch gets
its own share of the search budget, so a branch you write is a branch that
actually runs.

Here is the shape, for **a completely unrelated product** — a tool that finds
and fixes flaky tests in CI. Copy the *structure*, never the content: your
branches must come from the product described at the top of this page.

```json
{{
  "Flaky tests":     ["flaky test + retry", "intermittent failure + CI"],
  "CI spend":        ["CI minutes + cost", "pipeline + slow"],
  "Test isolation":  ["test pollution", "shared state + tests"],
  "Reproducing":     ["cannot reproduce + locally", "passes locally + fails CI"]
}}
```

Two rules for the branches:

- **A branch must be a problem this product actually solves.** A branch invented
  to look broad matches real posts written by people who will never buy, and it
  spends budget that a real branch needed.
- **Within a branch, go deep.** Several angles on the same problem is exactly
  right — that is what a branch is for. Clustering is only a failure when it
  happens *across* the whole plan.

Prefer the words somebody with the problem types over the words the industry
uses: someone who says "cache invalidation" usually knows the answer already,
someone who says "index is stale" does not.

For every other platform, `term_groups` and `target_places` stay empty. Those
get shown as advice only, and it is better to say so than to pretend.

## Honesty

If a platform is a bad fit for this product, leave it out rather than padding
the list. Four real recommendations beat six with two invented.

If the website was too thin to tell you much, say so in `strategy` instead of
inventing detail. Somebody is going to act on this.

## Output

Return only JSON:

`competitors` is names only — the products somebody would genuinely use
*instead* of this one. Name **4 to 8**, and include the ones the website never
mentions: a product's own pages list the rivals it wants to be compared with,
which is rarely the full field. We look each name up on GitHub ourselves, so a
plain product name is all that is needed and a guessed `owner/repo` is worse
than useless. Leave it empty only if this product genuinely has no comparable
alternatives.

```json
{{
  "strategy": "2-3 sentences: the approach, specific to this product",
  "audience": "who to reach, concretely — role, company size, what they run",
  "positioning": "one sentence: how to describe the product to that audience",
  "competitors": ["<product name>", "<product name>", "..."],
  "platforms": [
    {{
      "key": "github",
      "name": "GitHub",
      "why": "why this platform suits THIS product",
      "what_to_do": "the actual activity, in one or two sentences",
      "tone": "how to write there",
      "term_groups": {{
        "<problem 1 in your own words>": ["<term>", "<term>", "<term>"],
        "<problem 2 in your own words>": ["<term>", "<term>"],
        "<problem 3 in your own words>": ["<term>", "<term>"],
        "<problem 4 in your own words>": ["<term>", "<term>"]
      }},
      "target_places": ["<owner/name>", "<owner/name>", "..."]
    }},
    {{
      "key": "hackernews",
      "name": "Hacker News",
      "why": "why this platform suits THIS product",
      "what_to_do": "the actual activity, in one or two sentences",
      "tone": "how to write there",
      "term_groups": {{
        "<same problems, phrased the way somebody talks in a thread>": [
          "<term>", "<term>", "<term>"
        ],
        "<problem 2>": ["<term>", "<term>"],
        "<problem 3>": ["<term>", "<term>"],
        "<problem 4>": ["<term>", "<term>"]
      }},
      "target_places": []
    }},
    {{
      "key": "<a place we cannot search — a subreddit, forum, community>",
      "name": "<its real name>",
      "why": "...",
      "what_to_do": "...",
      "tone": "...",
      "term_groups": {{}},
      "target_places": []
    }}
  ],
  "content_ideas": ["3 to 5 specific things to write, each a real title"],
  "first_week": ["3 to 5 concrete actions to take in the first week"]
}}
```
