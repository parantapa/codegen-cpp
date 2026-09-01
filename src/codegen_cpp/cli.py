"""Command line interface for codegen-cpp."""

from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .codegen import header_file, render_spec
from .make_config import config_file, csv_config, parquet_config, render_config
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


@cli.group("make-config")
def make_config() -> None:
    """Generate a specification out of a data file."""


@make_config.command("csv")
@click.argument(
    "data_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--output",
    "-o",
    "output_file",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help=(
        "File the generated specification is written to,"
        " overwriting it if it exists."
        "  [default: DATA_FILE without its suffixes and with '.toml' instead]"
    ),
)
@click.option(
    "--read-all",
    "read_all",
    is_flag=True,
    default=False,
    help=(
        "Infer the column types from every row of DATA_FILE"
        " rather than from its first block,"
        " which reads the whole file into memory."
    ),
)
def make_config_csv(data_file: Path, output_file: Path | None, read_all: bool) -> None:
    """Generate a specification for the CSV file DATA_FILE."""
    try:
        config = csv_config(data_file, read_all)
    except Exception as e:
        raise click.ClickException(f"Failed to read {data_file}:\n{e}") from e

    write_config(config, data_file, output_file)


@make_config.command("parquet")
@click.argument(
    "data_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--output",
    "-o",
    "output_file",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help=(
        "File the generated specification is written to,"
        " overwriting it if it exists."
        "  [default: DATA_FILE without its suffixes and with '.toml' instead]"
    ),
)
def make_config_parquet(data_file: Path, output_file: Path | None) -> None:
    """Generate a specification for the Parquet file DATA_FILE."""
    try:
        config = parquet_config(data_file)
    except Exception as e:
        raise click.ClickException(f"Failed to read {data_file}:\n{e}") from e

    write_config(render_config(config), data_file, output_file)

    # A column the table cannot hold is not read, which is worth saying twice.
    for name, reason in config.skipped:
        console.print(
            f"[yellow]Left out[/yellow] column {name!r}, stored as {reason}",
            soft_wrap=True,
        )


def write_config(config: str, data_file: Path, output_file: Path | None) -> None:
    """Write CONFIG out, beside DATA_FILE unless OUTPUT_FILE says otherwise."""
    if output_file is None:
        output_file = config_file(data_file)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(config)
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
