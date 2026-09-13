#!/usr/bin/env python3
r"""Recompute the entry-count badges in README.md from README.md itself.

This does not touch placement, sorting, or links -- it only fixes the
`` `N` `` counts that follow each entry in the Contents (TOC) block and the
two Part-level summary lines, so a manually added or removed entry does not
leave a stale count behind. It has no dependency on the survey repository.

Algorithm: the TOC lists every section as `- [Label](#anchor) \`N\`` (top
level) or `  - [Label](#anchor) \`N\`` (nested under the previous top-level
anchor). Walking the body, each `<div id="ANCHOR"></div>` that matches a TOC
anchor opens a region that runs until the next such anchor; the number of
`- **...` entry lines inside that region is the anchor's direct count. A
top-level anchor with children (§2 Human verifiers, for instance) never
carries entries directly -- its count is the sum of its children's counts.
Anchors used only to mark where a flat list starts in the body (e.g.
`vbench.all`) are invisible here because they never appear in the TOC, so
their entries are simply counted as part of the enclosing TOC anchor's
region.

Usage:
    python3 tools/update_counts.py            # rewrite README.md in place
    python3 tools/update_counts.py --check    # exit 1 if it would change
"""
import argparse
import re
import sys

TOC_BULLET = re.compile(r"^(?P<indent>\s*)- \[[^\]]*\]\(#(?P<anchor>[\w.\-]+)\) `(?P<count>\d+)`\s*$")
DIV_ANCHOR = re.compile(r'^<div id="([\w.\-]+)"></div>\s*$')
ENTRY_LINE = re.compile(r"^- \*\*`")
PART_MARK = re.compile(r"^\*\*Part (I|II)\b")
PART_I_SUMMARY = re.compile(r"^`(\d+)` papers across the four judge sources, following §2 to §5 of the survey\.$")
PART_II_SUMMARY = re.compile(r"^`(\d+)` papers\. The first five groups follow §6, which asks")


def parse_toc(lines):
    """Return (top_level order list, {anchor: part}, {anchor: [child anchors]})."""
    order, part_of, children = [], {}, {}
    current_part, current_top = None, None
    in_toc = False
    for line in lines:
        if line.startswith("## 🗂️ Contents"):
            in_toc = True
            continue
        if in_toc and line.startswith("Also: [Citation]"):
            break
        if not in_toc:
            continue
        m = PART_MARK.match(line)
        if m:
            current_part = m.group(1)
            continue
        m = TOC_BULLET.match(line)
        if not m:
            continue
        anchor = m.group("anchor")
        nested = len(m.group("indent")) > 0
        if not nested:
            order.append(anchor)
            part_of[anchor] = current_part
            children[anchor] = []
            current_top = anchor
        else:
            children.setdefault(current_top, []).append(anchor)
            part_of[anchor] = current_part
    return order, part_of, children


def direct_counts(lines, known_anchors):
    """Count `- **` entry lines inside the region owned by each known anchor."""
    anchor_at_line = []
    for i, line in enumerate(lines):
        m = DIV_ANCHOR.match(line)
        if m and m.group(1) in known_anchors:
            anchor_at_line.append((i, m.group(1)))
    counts = {a: 0 for a in known_anchors}
    for idx, (start, anchor) in enumerate(anchor_at_line):
        end = anchor_at_line[idx + 1][0] if idx + 1 < len(anchor_at_line) else len(lines)
        for line in lines[start + 1:end]:
            if ENTRY_LINE.match(line):
                counts[anchor] += 1
    return counts


def total_counts(order, children, direct):
    totals = {}

    def total_of(anchor):
        if anchor in totals:
            return totals[anchor]
        kids = children.get(anchor) or []
        if kids:
            if direct.get(anchor, 0):
                print(f"warning: {anchor!r} has both children and {direct[anchor]} "
                      f"entries filed directly under it; those are not counted", file=sys.stderr)
            t = sum(total_of(k) for k in kids)
        else:
            t = direct.get(anchor, 0)
        totals[anchor] = t
        return t

    for a in order:
        total_of(a)
        for k in children.get(a) or []:
            total_of(k)
    return totals


def rewrite(text):
    lines = text.split("\n")
    order, part_of, children = parse_toc(lines)
    known = set(order) | {c for kids in children.values() for c in kids}
    direct = direct_counts(lines, known)
    totals = total_counts(order, children, direct)

    out = []
    for line in lines:
        m = TOC_BULLET.match(line)
        if m:
            anchor = m.group("anchor")
            new_count = totals.get(anchor)
            if new_count is not None:
                line = re.sub(r"`\d+`\s*$", f"`{new_count}`", line)
            out.append(line)
            continue
        m = PART_I_SUMMARY.match(line)
        if m:
            part1 = sum(totals[a] for a in order if part_of.get(a) == "I")
            out.append(f"`{part1}` papers across the four judge sources, following §2 to §5 of the survey.")
            continue
        m = PART_II_SUMMARY.match(line)
        if m:
            part2 = sum(totals[a] for a in order if part_of.get(a) == "II")
            out.append(re.sub(r"^`\d+`", f"`{part2}`", line))
            continue
        out.append(line)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--readme", default="README.md")
    ap.add_argument("--check", action="store_true", help="exit 1 if counts are stale, without writing")
    args = ap.parse_args()

    original = open(args.readme, encoding="utf-8").read()
    updated = rewrite(original)

    if updated == original:
        print("counts are up to date")
        return 0

    if args.check:
        print("counts are stale; run `python3 tools/update_counts.py` and commit the result", file=sys.stderr)
        for a, b in zip(original.split("\n"), updated.split("\n")):
            if a != b:
                print(f"  - {a}\n  + {b}", file=sys.stderr)
        return 1

    open(args.readme, "w", encoding="utf-8").write(updated)
    print(f"updated counts in {args.readme}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
