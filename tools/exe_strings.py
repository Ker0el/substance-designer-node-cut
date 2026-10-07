"""Dump the printable strings surrounding a needle inside a binary.

Menu item labels are stored as NUL-terminated strings laid out roughly in menu
order, so dumping the neighbourhood of a known label is a quick way to
reconstruct a whole menu. This is how we established that Designer's graph
context menu really has no Cut entry - only the two SVG entries in the 2D view
happen to contain the words "Cut Selection".

    python exe_strings.py "<path to Adobe Substance 3D Designer.exe>" "Paste elements present in clipboard"
    python exe_strings.py "<path to exe>" "Paste without links" "Delete and relink"
"""
import re
import sys

RUN = re.compile(rb"[\x20-\x7e]{4,}")


def context(data, needle, before=1200, after=1800):
    hits = [m.start() for m in re.finditer(re.escape(needle.encode()), data)]
    if not hits:
        print("=" * 70)
        print("needle %r not found" % needle)
        return
    for i, off in enumerate(hits):
        print("=" * 70)
        print("needle %r  hit %d/%d  offset=%d" % (needle, i + 1, len(hits), off))
        print("=" * 70)
        base = max(0, off - before)
        for m in RUN.finditer(data[base: off + after]):
            text = m.group().decode("ascii", "replace")
            if not text.startswith(("?$", "??")):
                print("  %+-7d %s" % (base + m.start() - off, text))


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    with open(argv[1], "rb") as handle:
        data = handle.read()
    for needle in argv[2:]:
        context(data, needle)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
