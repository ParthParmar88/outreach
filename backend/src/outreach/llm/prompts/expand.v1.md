Add search terms that would find people describing this problem in words the
user did not think of.

## What they are looking for

{description}

## Terms they already gave you

{keywords}

## Your job

Suggest 6 to 10 more. Each becomes an **exact quoted phrase** in a GitHub
issue search, which constrains them sharply:

- **1 to 3 words.** A sentence matches nothing, because nobody writes the
  same sentence twice.
- **Not a rewording of a term they already gave.** "reindex" and
  "re-indexing" are the same search. Add angles they missed, not synonyms.
- **Favour symptoms over mechanisms.** Someone who has already named the
  problem is usually building a fix for it; someone describing the symptom
  is the one who needs help. "my bill went up" beats "cost optimisation".
- **No brand or product names** unless the user named one first. Searching a
  competitor's name mostly finds that competitor's own team.

## The reason matters as much as the term

Every term you add is shown to the user with your reason next to it, and they
can delete it before anything runs. Write the reason for them, not for you:
say what kind of post this term would find, in one short clause.

Good: `people who hit this during a migration rather than at build time`
Bad: `related term`, `semantically similar`, `commonly co-occurs`

A reason that does not help someone decide whether to keep the term is worse
than no term at all.

## Output

Return only JSON:

```json
{{"terms": [{{"term": "...", "reason": "..."}}]}}
```
