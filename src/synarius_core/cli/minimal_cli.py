from __future__ import annotations

import argparse
import re
from pathlib import Path

from synarius_core.controller import CommandError, MinimalController

ANSI_RESET = "\x1b[0m"
DEFAULT_OUTPUT_COLOR = "#ADD8E6"  # light blue
DEFAULT_PROMPT_COLOR = "#90EE90"  # light green


def _html_hex_to_ansi_fg(color: str) -> str:
    match = re.fullmatch(r"#([0-9a-fA-F]{6})", color.strip())
    if not match:
        raise ValueError(f"Invalid HTML color code: {color!r}")
    hex_value = match.group(1)
    r = int(hex_value[0:2], 16)
    g = int(hex_value[2:4], 16)
    b = int(hex_value[4:6], 16)
    return f"\x1b[38;2;{r};{g};{b}m"


def _colorize(text: str, html_color: str) -> str:
    return f"{_html_hex_to_ansi_fg(html_color)}{text}{ANSI_RESET}"


def _get_output_color(controller: MinimalController) -> str:
    try:
        value = controller.model.root.get("output_color")
        if isinstance(value, str):
            _html_hex_to_ansi_fg(value)  # validate
            return value
    except Exception:
        pass
    return DEFAULT_OUTPUT_COLOR


def _print_banner() -> None:
    print(_colorize("synarius-core minimal CLI", DEFAULT_OUTPUT_COLOR))
    print(_colorize("Type 'help' for commands, 'exit' to quit.", DEFAULT_OUTPUT_COLOR))


def _print_help() -> None:
    print(
        _colorize(
        "\n".join(
            [
                "Built-in commands:",
                "  help                    Show this help",
                "  exit | quit             Exit CLI",
                "  load <file.syn>         Load command-stack script",
                "",
                "Protocol commands:",
                "  ls, lsattr [-l], cd <path> (incl. @libraries/… for FMF libs), new …, select … (-p append, -m remove), set … (set -p @selection …), get …, del … | del @selected",
                "  fmu inspect <path.fmu> | fmu bind <ref> [from=<path>] | fmu reload <ref> [path=<path>]",
            ]
        ),
        DEFAULT_OUTPUT_COLOR,
        )
    )


def run_repl(controller: MinimalController) -> int:
    _print_banner()
    while True:
        prompt_path = str(controller.current.get("prompt_path")) if controller.current is not None else "<none>"
        try:
            # Print colored prompt separately; keep input() prompt plain to avoid ANSI cursor glitches.
            print(_colorize(f"{prompt_path}>", DEFAULT_PROMPT_COLOR), end=" ", flush=True)
            line = input()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        stripped = line.strip()
        if not stripped:
            continue
        if stripped in {"exit", "quit"}:
            return 0
        if stripped == "help":
            _print_help()
            continue

        try:
            result = controller.execute(stripped)
        except CommandError as exc:
            print(_colorize(f"error: {exc}", "#FF6666"))
            continue
        except Exception as exc:  # Defensive guard for CLI UX.
            print(_colorize(f"error: {exc}", "#FF6666"))
            continue

        if result is not None and result != "":
            print(_colorize(result, _get_output_color(controller)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="synarius-core minimal protocol CLI")
    parser.add_argument(
        "--load",
        type=Path,
        help="Optional .syn command-stack file to load before entering REPL.",
    )
    args = parser.parse_args(argv)

    controller = MinimalController()
    if args.load is not None:
        try:
            result = controller.execute(f'load "{args.load}"')
            if result:
                print(_colorize(result, _get_output_color(controller)))
        except Exception as exc:
            print(_colorize(f"error: failed to load startup file: {exc}", "#FF6666"))
            return 2

    return run_repl(controller)


if __name__ == "__main__":
    raise SystemExit(main())
