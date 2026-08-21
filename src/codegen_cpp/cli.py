"""Command line interface for codegen-cpp."""

from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .codegen import (
    csv_reader_header_name,
    csv_writer_header_name,
    dataset_header_name,
    hdf5_reader_header_name,
    hdf5_writer_header_name,
    parquet_reader_header_name,
    parquet_writer_header_name,
    render_csv_reader,
    render_csv_writer,
    render_dataset,
    render_hdf5_reader,
    render_hdf5_writer,
    render_parquet_reader,
    render_parquet_writer,
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

    for dataset in spec.datasets:
        header = output_dir / dataset_header_name(dataset)
        header.write_text(render_dataset(dataset))
        console.print(f"Generated [bold]{header}[/bold]", soft_wrap=True)

    tables = {table.name: table for table in spec.tables}

    for csv_reader in spec.csv_readers:
        header = output_dir / csv_reader_header_name(csv_reader)
        header.write_text(render_csv_reader(csv_reader, tables[csv_reader.table]))
        console.print(f"Generated [bold]{header}[/bold]", soft_wrap=True)

    for parquet_reader in spec.parquet_readers:
        header = output_dir / parquet_reader_header_name(parquet_reader)
        header.write_text(
            render_parquet_reader(parquet_reader, tables[parquet_reader.table])
        )
        console.print(f"Generated [bold]{header}[/bold]", soft_wrap=True)

    for csv_writer in spec.csv_writers:
        header = output_dir / csv_writer_header_name(csv_writer)
        header.write_text(render_csv_writer(csv_writer, tables[csv_writer.table]))
        console.print(f"Generated [bold]{header}[/bold]", soft_wrap=True)

    for parquet_writer in spec.parquet_writers:
        header = output_dir / parquet_writer_header_name(parquet_writer)
        header.write_text(
            render_parquet_writer(parquet_writer, tables[parquet_writer.table])
        )
        console.print(f"Generated [bold]{header}[/bold]", soft_wrap=True)

    datasets = {dataset.name: dataset for dataset in spec.datasets}

    for hdf5_reader in spec.hdf5_readers:
        header = output_dir / hdf5_reader_header_name(hdf5_reader)
        header.write_text(
            render_hdf5_reader(hdf5_reader, datasets[hdf5_reader.dataset])
        )
        console.print(f"Generated [bold]{header}[/bold]", soft_wrap=True)

    for hdf5_writer in spec.hdf5_writers:
        header = output_dir / hdf5_writer_header_name(hdf5_writer)
        header.write_text(
            render_hdf5_writer(hdf5_writer, datasets[hdf5_writer.dataset])
        )
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
