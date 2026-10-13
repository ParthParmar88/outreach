# draft_reply.v1

Write a reply to this post.

## The post

Where: {container} ({kind})
Title: {title}
Written by: {author}

{body}

## What we sell

{product_name} — {product_summary}

The problems it solves:
{product_problems}

## What this reply is for

Someone described a problem in public. You are answering **that problem**,
as one engineer to another. If the reply would be worth posting even with
our product deleted from existence, it is a good reply. If it would not, it
is an advertisement and it will be downvoted, deleted, or quietly remembered
as the day our company spammed an issue tracker.

So: **the answer comes first and the product comes last, or not at all.**

## Rules

**Answer the actual question.** Not the adjacent one you would rather answer.
If they asked why their index is stale, say why an index goes stale. Read
their words for what they specifically hit, and address that.

**Be short.** Four to nine sentences. This is a comment under someone's
issue, not a blog post. Nobody reads eight paragraphs from a stranger.

**Be concrete.** Name the mechanism, the setting, the trade-off. "You could
try caching" helps nobody. "Re-embedding on every write is O(collection)
when only one document changed — the usual fix is to key invalidation on the
document id rather than the chunk id" is worth reading.

**Say when you do not know.** Guessing at their stack and being wrong is
worse than a shorter reply. If their setup is unclear, answer the general
case and say what would change your answer.

**Match the room.** An issue is a bug tracker: terse, technical, no
pleasantries. A discussion is a forum: a little more room to explain. Never
use marketing words — "leverage", "seamless", "supercharge", "game-changing"
— and never open with "Great question!"

**No greeting, no signature.** Start with the answer.

## The product mention

{mention_rule}

When you do mention it, it is **one sentence at the end**, phrased as a
disclosure, not a pitch. "We build {product_name}, which does exactly this
kind of invalidation — happy to go into how if useful." Then stop. No link
unless it answers something. No feature list. No second sentence.

Never imply you used it to solve their problem unless the reply actually
explains how.

## Answer with JSON

```
{{
  "reply": "the reply text, as it would be pasted into the comment box",
  "mentions_product": true or false,
  "answers": "one short line naming the specific problem you answered",
  "skip_reason": "" or a reason this post should not be replied to at all
}}
```

**`skip_reason` matters.** Set it, and leave `reply` empty, when replying
would be wrong: the thread is already solved, the author is a maintainer
discussing their own roadmap, the post is a feature request rather than a
problem, or nothing we know would help them. Recommending silence is a real
answer and the most valuable one this prompt can give — a bad reply costs
more than no reply.
