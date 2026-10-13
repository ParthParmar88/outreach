Read this product's own website and write down what it is and who needs it.

## Why this is being asked

The result is used to find people online who have the problem this product
solves. So the useful half is not what the product does — it is **what goes
wrong for someone who does not have it**.

## The trap to avoid

Websites are written in marketing language. Nobody with the problem types
that language. They type what broke.

| the site says | someone with the problem says |
|---|---|
| context engineering platform | my index still returns the old text |
| cost optimisation | my bill tripled |
| enterprise-grade retrieval | search stopped finding new docs |

`pain_words` must be the right-hand column. If you find yourself copying a
phrase from a heading, it belongs in `keywords`, not there.

## What to write

| field | what goes in it |
|---|---|
| `summary` | 2 sentences. What it does, mechanically. For an engineer, not a buyer. |
| `domain` | 2 to 5 words naming the kind of system. e.g. `LLM vector retrieval`, `Kubernetes operators`, `CI build caching` |
| `problems` | 3 to 6 problems it solves, each stated as a problem, not a feature |
| `keywords` | 5 to 10 terms the product's own world uses |
| `pain_words` | 8 to 15 short phrases a frustrated user would type. 1 to 4 words each. |
| `competitors` | names only, if the site mentions any. Empty list if not. |
| `buyer` | one sentence: who has this problem and can pay to fix it |

`domain` matters more than it looks. It is used later to reject posts that
describe the same *shape* of problem in a different kind of system — a code
indexer rebuilding after a header change looks identical to a vector store
rebuilding after a document change, and only one of them is a customer.

If the site is too thin to answer a field honestly, leave it empty. A guess
is worse than a gap, because everything downstream will trust it.

## The website

{markdown}

## Output

Return only JSON:

```json
{{
  "summary": "...",
  "domain": "...",
  "problems": ["..."],
  "keywords": ["..."],
  "pain_words": ["..."],
  "competitors": ["..."],
  "buyer": "..."
}}
```
