"""Command line interface for codegen-cpp."""

import tomllib
from pathlib import Path

import click
from pydantic import ValidationError
from rich.console import Console

from . import __version__
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
    "--output-dir",
    "-o",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Directory where generated sources are written.",
)
def generate(spec_file: Path, output_dir: Path) -> None:
    """Generate C++ sources from SPEC_FILE."""
    console.print(
        f"Generating from [bold]{spec_file}[/bold] " f"into [bold]{output_dir}[/bold]"
    )


@cli.command("parse-spec")
@click.argument(
    "spec_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
def parse_spec_command(spec_file: Path) -> None:
    """Parse SPEC_FILE and print the parsed specification."""
    try:
        spec = parse_spec(spec_file)
    except (tomllib.TOMLDecodeError, ValidationError) as e:
        raise click.ClickException(f"Failed to parse {spec_file}:\n{e}") from e

    console.print(spec)
