Suggest search keywords for finding public developer discussions about a problem.

## What the user is looking for

{description}

## What makes a good keyword here

Each keyword becomes an **exact quoted phrase** in a GitHub issue search. That
constrains them sharply:

- **1 to 3 words.** Anything sentence-shaped matches nothing at all, because
  people do not write the same sentence twice.
- **Words people actually type**, not category names. A term of art like
  "cache invalidation" works because it is a fixed compound people reuse
  verbatim. A description like "how do I keep my index fresh" does not.
- **Symptoms over mechanisms where possible.** Someone who has already named
  the problem is usually building a fix for it; someone still describing the
  symptom is the one who needs help. Include both, but favour the symptom.
- **No brand names** unless the user named one. Searching for a competitor
  finds that competitor's own issue tracker, which is mostly their team.

Give 10 to 15. Order them most useful first.

## Output

Return only JSON:

```json
{{"keywords": ["...", "..."]}}
```
