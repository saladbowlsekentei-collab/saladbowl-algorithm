"""Update or verify the README policy table; no external services are used."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dressing.policy import load_policy
from dressing.presentation import policy_table

START = "<!-- policy:start -->"
END = "<!-- policy:end -->"


def expected_readme(text):
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError("README policy markers must appear exactly once")
    prefix, remaining = text.split(START)
    _, suffix = remaining.split(END)
    return prefix + START + "\n" + policy_table(load_policy()) + "\n" + END + suffix


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / "README.md"
    current = path.read_text(encoding="utf-8")
    expected = expected_readme(current)
    if args.check:
        if current != expected:
            print("README policy table differs from settings.toml", file=sys.stderr)
            return 1
        print("README policy table matches settings.toml")
    else:
        path.write_text(expected, encoding="utf-8")
        print("README policy table updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

