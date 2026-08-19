"""Command line interface for codegen-cpp."""

from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .codegen import (
    csv_reader_header_name,
    render_csv_reader,
    render_table,
    table_header_name,
)
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
    try:
        spec = parse_spec(spec_file)
    except ValueError as e:
        raise click.ClickException(f"Failed to parse {spec_file}:\n{e}") from e

    output_dir.mkdir(parents=True, exist_ok=True)

    for table in spec.tables:
        header = output_dir / table_header_name(table)
        header.write_text(render_table(table))
        console.print(f"Generated [bold]{header}[/bold]", soft_wrap=True)

    tables = {table.name: table for table in spec.tables}

    for csv_reader in spec.csv_readers:
        header = output_dir / csv_reader_header_name(csv_reader)
        header.write_text(render_csv_reader(csv_reader, tables[csv_reader.table]))
        console.print(f"Generated [bold]{header}[/bold]", soft_wrap=True)


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
