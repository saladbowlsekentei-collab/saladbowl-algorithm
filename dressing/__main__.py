"""Read one JSON file and print one deterministic ranking."""

import argparse
import json
from pathlib import Path
import sys

from . import InputError, evaluate, load_policy, parse_payload
from .policy import DEFAULT_PATH


MAX_INPUT_BYTES = 4 * 1024 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("JSON object contains duplicate keys")
        result[key] = value
    return result


def _invalid_constant(value):
    raise InputError("JSON contains a non-finite number")


def main(argv=None):
    parser = argparse.ArgumentParser(description="SaladBowl / Dressing event evaluator")
    parser.add_argument("input", type=Path, help="classified events in JSON format")
    parser.add_argument("--policy", type=Path, default=DEFAULT_PATH, help="policy TOML file")
    args = parser.parse_args(argv)
    try:
        with args.input.open("rb") as stream:
            data = stream.read(MAX_INPUT_BYTES + 1)
        if len(data) > MAX_INPUT_BYTES:
            raise InputError("input exceeds 4 MiB")
        raw = json.loads(data, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        result = evaluate(parse_payload(raw), load_policy(args.policy))
    except OSError:
        print("error: could not read the input or policy file", file=sys.stderr)
        return 2
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        print("error: invalid JSON input", file=sys.stderr)
        return 2
    except (InputError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

