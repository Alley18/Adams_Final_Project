from __future__ import annotations

from pathlib import Path

ROOT = Path('/home/ubuntu/AI-driver-assistant1_major_improved/frontend/dashboard/mobile_live_client_only/lib')
PAIRS = {'(': ')', '[': ']', '{': '}'}
OPEN = set(PAIRS)
CLOSE = set(PAIRS.values())


def check_balance(path: Path) -> list[str]:
    text = path.read_text(encoding='utf-8')
    stack: list[tuple[str, int]] = []
    problems: list[str] = []
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    escape = False
    for i, ch in enumerate(text):
        nxt = text[i + 1] if i + 1 < len(text) else ''
        if in_line_comment:
            if ch == '\n':
                in_line_comment = False
            continue
        if in_block_comment:
            if ch == '*' and nxt == '/':
                in_block_comment = False
            continue
        if not in_single and not in_double:
            if ch == '/' and nxt == '/':
                in_line_comment = True
                continue
            if ch == '/' and nxt == '*':
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
                    problems.append(f'unmatched close {ch} at {i}')
                else:
                    op, pos = stack.pop()
                    if PAIRS[op] != ch:
                        problems.append(f'mismatch {op}@{pos} closed by {ch}@{i}')
        escape = (ch == '\\' and not escape)
        if ch != '\\':
            escape = False
    if stack:
        problems.append(f'unclosed delimiters: {stack[-5:]}')
    return problems


def main() -> None:
    failures = {}
    for path in sorted(ROOT.rglob('*.dart')):
        issues = check_balance(path)
        if issues:
            failures[str(path.relative_to(ROOT))] = issues
    if failures:
        for path, issues in failures.items():
            print(path)
            for issue in issues:
                print('  -', issue)
        raise SystemExit(1)
    print('Mobile source text validation passed for', len(list(ROOT.rglob('*.dart'))), 'Dart files.')


if __name__ == '__main__':
    main()
