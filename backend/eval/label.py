"""
Label candidates by hand. This is the only ground truth in the system.

    python -m eval.label
    python -m eval.label --relabel        also revisit ones already done
    python -m eval.label --show-machine   also show what the machine scored it

Shows one result at a time. Press 0, 1 or 2. Press s to skip, q to stop -
progress is saved after every answer, so stopping halfway costs nothing.

Thirty labels is enough to catch a prompt change that matters. Aim for that
before worrying about more.
"""

from __future__ import annotations

import argparse
import sys
import textwrap

from eval import store

RULE = "─" * 78


def show(index: int, total: int, data: dict, show_machine: bool = False) -> None:
    body = " ".join((data.get("body") or "").split())

    print(f"\n{RULE}")
    print(f"  {index}/{total}   {data.get('container')}   @{data.get('author')}")
    print(f"  {data.get('created_at', '')[:10]}   "
          f"{data.get('comments', 0)} comments, {data.get('score', 0)} reactions")
    print(RULE)
    print()
    print(textwrap.fill(data.get("title") or "(no title)", 76,
                        initial_indent="  ", subsequent_indent="  "))
    print()
    for line in textwrap.wrap(body[:700], 76):
        print(f"  {line}")
    if len(body) > 700:
        print("  ...")
    print()
    print(f"  {data.get('url')}")
    print()

    # What the machine said. Hidden unless asked for: seeing its score before
    # you answer pulls your label towards it, and labels that agree with the
    # machine because they were copied from it make it look better than it is.
    if show_machine and data.get("intent"):
        print(f"  machine: {data.get('intent')}  fit={data.get('fit')}  "
              f"domain={data.get('post_domain')}  score={data.get('opportunity')}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relabel", action="store_true", help="Revisit labelled items too.")
    parser.add_argument("--show-machine", action="store_true",
                        help="Show the machine's own verdict under each post.")
    args = parser.parse_args()

    candidates = store.load_candidates()
    labels = store.load_labels()

    if not candidates:
        print("\nNo candidates yet. Run a search first - they are collected "
              "automatically.\n")
        return 1

    todo = [k for k in candidates if args.relabel or k not in labels]
    if not todo:
        print(f"\nAll {len(candidates)} candidates already labelled. "
              f"Use --relabel to revisit.\n")
        return 0

    print(f"\n{len(todo)} to label. {len(labels)} done already.")
    print("\n".join(f"  {n}  {text}" for n, text in store.MEANING.items()))
    print("  s  skip        q  save and quit")

    for position, k in enumerate(todo, 1):
        show(position, len(todo), candidates[k], args.show_machine)

        while True:
            try:
                answer = input("  label [0/1/2/s/q] > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "q"

            if answer == "q":
                store.save_labels(labels)
                print(f"\nSaved. {len(labels)} labelled in total.\n")
                return 0
            if answer == "s":
                break
            if answer in {"0", "1", "2"}:
                labels[k] = {
                    "label": int(answer),
                    "title": candidates[k].get("title"),
                    "url": candidates[k].get("url"),
                }
                # Saved every time rather than at the end. Losing twenty
                # judgements to a closed terminal would be infuriating.
                store.save_labels(labels)
                break
            print("  0, 1, 2, s or q.")

    print(f"\nDone. {len(labels)} labelled.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
