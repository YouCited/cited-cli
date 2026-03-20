from __future__ import annotations

import sys

import typer

from cited_cli.output.formatter import OutputContext, print_error
from cited_cli.utils.errors import ExitCode


def is_interactive() -> bool:
    """Return True when stdin is a TTY (interactive terminal)."""
    return sys.stdin.isatty()


def can_prompt(out: OutputContext) -> bool:
    """Return True when interactive prompting is allowed (not JSON mode, is TTY)."""
    return not out.json_mode and is_interactive()


def prompt_if_missing(
    value: str | None,
    flag_name: str,
    prompt_text: str,
    out: OutputContext,
) -> str:
    """Return *value* if set, prompt interactively if possible, or error."""
    if value is not None:
        return value
    if can_prompt(out):
        return typer.prompt(prompt_text)
    print_error(f"Missing required option: {flag_name}", out)
    raise typer.Exit(ExitCode.VALIDATION_ERROR)


def prompt_choice(
    value: str | None,
    flag_name: str,
    prompt_text: str,
    choices: list[str],
    out: OutputContext,
) -> str:
    """Return *value* if set, show a numbered menu if interactive, or error."""
    if value is not None:
        if value not in choices:
            print_error(
                f"Invalid value '{value}' for {flag_name}. "
                f"Valid: {', '.join(choices)}",
                out,
            )
            raise typer.Exit(ExitCode.VALIDATION_ERROR)
        return value
    if can_prompt(out):
        out.console.print(f"\n[bold]{prompt_text}[/bold]")
        for i, choice in enumerate(choices, 1):
            out.console.print(f"  {i}. {choice}")
        while True:
            raw = typer.prompt("Enter number or value")
            if raw in choices:
                return raw
            try:
                idx = int(raw)
                if 1 <= idx <= len(choices):
                    return choices[idx - 1]
            except ValueError:
                pass
            out.console.print(
                f"[yellow]Invalid selection. Choose 1–{len(choices)}"
                " or type the value.[/yellow]"
            )
    print_error(f"Missing required option: {flag_name}", out)
    raise typer.Exit(ExitCode.VALIDATION_ERROR)


def confirm_action(message: str, out: OutputContext, *, skip: bool = False) -> None:
    """Ask for confirmation. Skips if *skip* is True or in JSON mode."""
    if skip or out.json_mode:
        return
    if not can_prompt(out):
        print_error("Cannot confirm in non-interactive mode. Use --yes to skip.", out)
        raise typer.Exit(ExitCode.VALIDATION_ERROR)
    typer.confirm(message, abort=True)
