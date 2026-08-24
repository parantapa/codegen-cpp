"""Command line interface for codegen-cpp."""

from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .codegen import header_file, render_spec
from .spec import parse_spec

console = Console()


@click.group()
@click.version_option(__version__, prog_name="codegen-cpp")
def cli() -> None:
    """Generate C++ code from declarative specifications."""


@cli.command()
@click.argument(
    "spec_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--output-file",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help=(
        "File the generated header is written to, overwriting it if it exists."
        "  [default: SPEC_FILE with its extension replaced by '.hpp']"
    ),
)
def generate(spec_file: Path, output_file: Path | None) -> None:
    """Generate a C++ header from SPEC_FILE."""
    try:
        spec = parse_spec(spec_file)
    except ValueError as e:
        raise click.ClickException(f"Failed to parse {spec_file}:\n{e}") from e

    if output_file is None:
        output_file = header_file(spec_file)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(render_spec(spec, spec_file))
    console.print(f"Generated [bold]{output_file}[/bold]", soft_wrap=True)


@cli.group()
def debug() -> None:
    """Inspect the intermediate results of the code generator."""


@debug.command("parse-spec")
@click.argument(
    "spec_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
def parse_spec_command(spec_file: Path) -> None:
    """Parse SPEC_FILE and print the parsed specification."""
    try:
        spec = parse_spec(spec_file)
    except ValueError as e:
        raise click.ClickException(f"Failed to parse {spec_file}:\n{e}") from e

    console.print(spec)
