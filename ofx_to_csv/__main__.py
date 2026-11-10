"""Command-line entry point."""
import argparse
import csv
import sys
from . import convert


def main():
    parser = argparse.ArgumentParser(description='Convert one bank or credit-card OFX statement to transaction CSV.')
    parser.add_argument("input")
    parser.add_argument("output", help="New output path; existing files are never overwritten")
    args = parser.parse_args()
    try:
        count = convert(args.input, args.output)
    except (ValueError, OSError, csv.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {count} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
