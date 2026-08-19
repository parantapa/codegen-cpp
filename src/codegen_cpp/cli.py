"""Command line interface for codegen-cpp."""

from pathlib import Path

import click
from rich.console import Console

from . import __version__

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
        f"Generating from [bold]{spec_file}[/bold] "
        f"into [bold]{output_dir}[/bold]"
    )
