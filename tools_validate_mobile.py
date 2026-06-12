from __future__ import annotations

import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_ROOTS = (
    PROJECT_ROOT / "mobile_app" / "lib",
    PROJECT_ROOT / "frontend" / "dashboard" / "mobile_live_client_only" / "lib",
)

PAIRS = {"(": ")", "[": "]", "{": "}"}
OPEN = set(PAIRS)
CLOSE = set(PAIRS.values())


def check_balance(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    stack: list[tuple[str, int]] = []
    problems: list[str] = []
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    escape = False

    for i, ch in enumerate(text):
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
            continue

        if not in_single and not in_double:
            if ch == "/" and nxt == "/":
                in_line_comment = True
                continue
            if ch == "/" and nxt == "*":
                in_block_comment = True
                continue

        if ch == "'" and not in_double and not escape:
            in_single = not in_single
        elif ch == '"' and not in_single and not escape:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch in OPEN:
                stack.append((ch, i))
            elif ch in CLOSE:
                if not stack:
                    problems.append(f"unmatched close {ch} at {i}")
                else:
                    op, pos = stack.pop()
                    if PAIRS[op] != ch:
                        problems.append(f"mismatch {op}@{pos} closed by {ch}@{i}")

        escape = ch == "\\" and not escape
        if ch != "\\":
            escape = False

    if stack:
        problems.append(f"unclosed delimiters: {stack[-5:]}")

    return problems


def dart_roots(raw_roots: list[str] | None) -> list[Path]:
    if raw_roots:
        return [Path(root).resolve() for root in raw_roots]
    return [root for root in DEFAULT_ROOTS if root.exists()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Lightweight Dart delimiter validation.")
    parser.add_argument(
        "roots",
        nargs="*",
        help="Optional Dart source roots. Defaults to both ADAMS Flutter lib folders.",
    )
    args = parser.parse_args()

    roots = dart_roots(args.roots)
    if not roots:
        raise SystemExit("No Dart source roots found.")

    failures: dict[str, list[str]] = {}
    checked = 0

    for root in roots:
        if not root.exists():
            failures[str(root)] = ["path does not exist"]
            continue

        for path in sorted(root.rglob("*.dart")):
            checked += 1
            issues = check_balance(path)
            if issues:
                failures[str(path.relative_to(PROJECT_ROOT))] = issues

    if failures:
        for path, issues in failures.items():
            print(path)
            for issue in issues:
                print("  -", issue)
        raise SystemExit(1)

    print(f"Mobile source text validation passed for {checked} Dart files.")


if __name__ == "__main__":
    main()
