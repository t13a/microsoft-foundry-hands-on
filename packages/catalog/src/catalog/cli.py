"""カタログの CLI (F-DEV-08)。

catalog validate [DIR]   DIR (既定は data) の CSV を検証する
"""

import argparse
import sys

from catalog.loader import load, validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="catalog", description="出茂市のサービスカタログ")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate", help="CSV を検証する")
    check.add_argument("directory", nargs="?", default="data")
    args = parser.parse_args(argv)

    violations = validate(args.directory)
    if violations:
        for violation in violations:
            print(violation, file=sys.stderr)
        print(f"{len(violations)} 件の違反があります", file=sys.stderr)
        return 1
    catalog = load(args.directory)
    print(f"OK: カテゴリ {len(catalog.categories)} 件、サービス {len(catalog.services)} 件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
