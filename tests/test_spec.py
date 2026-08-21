"""Tests for parsing specification files."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from codegen_cpp.spec import ScalarType, parse_spec

EXAMPLE = Path(__file__).parent.parent / "examples" / "table1.toml"


def test_parse_example_spec() -> None:
    """The bundled example spec parses its table definitions."""
    spec = parse_spec(EXAMPLE)

    assert [table.name for table in spec.tables] == ["Measurement", "Station"]

    table = spec.tables[0]
    assert len(table.columns) == 12
    assert table.columns[0].name == "station_id"
    assert table.columns[0].type is ScalarType.i64
    assert table.columns[-1].name == "note"
    assert table.columns[-1].type is ScalarType.str


def test_parse_array_of_tables(tmp_path: Path) -> None:
    """Repeated `[[table]]` tables parse into multiple table definitions."""
    spec_file = tmp_path / "spec.toml"
    spec_file.write_text(
        "[[table]]\n"
        'name = "a"\n'
        'columns = [{ name = "x", type = "u32" }]\n'
        "\n"
        "[[table]]\n"
        'name = "b"\n'
        'columns = [{ name = "y", type = "str" }]\n'
    )

    spec = parse_spec(spec_file)

    assert [f.name for f in spec.tables] == ["a", "b"]
    assert spec.tables[1].columns[0].type is ScalarType.str


def test_parse_csv_readers() -> None:
    """The bundled example spec parses its CSV reader definitions."""
    spec = parse_spec(EXAMPLE)

    reader = spec.csv_readers[0]
    assert reader.name == "MeasurementCsvReader"
    assert reader.table == "Measurement"
    assert reader.default_values == {
        "quality": -1,
        "humidity": 0.0,
        "is_valid": False,
        "note": "",
    }

    # A reader may leave every column required.
    assert spec.csv_readers[1].default_values == {}


@pytest.mark.parametrize("section", ["table", "csv_reader"])
def test_single_table_section_rejected(tmp_path: Path, section: str) -> None:
    """Sections must be arrays of tables; a plain `[section]` is an error."""
    spec_file = tmp_path / "spec.toml"
    spec_file.write_text(f'[{section}]\nname = "x"\n')

    with pytest.raises(ValueError, match=rf"\[\[{section}\]\], not \[{section}\]"):
        parse_spec(spec_file)


def write_spec(tmp_path: Path, text: str) -> Path:
    """Write TEXT to a spec file inside TMP_PATH and return its path."""
    spec_file = tmp_path / "spec.toml"
    spec_file.write_text(text)
    return spec_file


GOOD_TABLE = """
[[table]]
name = "t"
columns = [
    { name = "a", type = "i32" },
    { name = "b", type = "str" },
]
"""


def test_duplicate_column_names_rejected(tmp_path: Path) -> None:
    """A table may not declare the same column twice."""
    spec_file = write_spec(
        tmp_path,
        "[[table]]\n"
        'name = "t"\n'
        'columns = [{ name = "a", type = "i32" },'
        ' { name = "a", type = "str" }]\n',
    )

    with pytest.raises(ValidationError, match="duplicate columns: a"):
        parse_spec(spec_file)


def test_duplicate_table_names_rejected(tmp_path: Path) -> None:
    """Two tables may not share a name."""
    spec_file = write_spec(tmp_path, GOOD_TABLE + GOOD_TABLE)

    with pytest.raises(ValidationError, match="duplicate table or reader names: t"):
        parse_spec(spec_file)


def test_duplicate_csv_reader_names_rejected(tmp_path: Path) -> None:
    """Two CSV readers may not share a name."""
    reader = '[[csv_reader]]\nname = "R"\ntable = "t"\n'
    spec_file = write_spec(tmp_path, GOOD_TABLE + reader + reader)

    with pytest.raises(ValidationError, match="duplicate table or reader names: R"):
        parse_spec(spec_file)


def test_unknown_table_reference_rejected(tmp_path: Path) -> None:
    """A CSV reader must refer to a defined table."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + '[[csv_reader]]\nname = "R"\ntable = "missing"\n',
    )

    with pytest.raises(ValidationError, match="undefined table 'missing'"):
        parse_spec(spec_file)


def test_unknown_default_value_column_rejected(tmp_path: Path) -> None:
    """Default values must be given for columns of the referenced table."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + "[[csv_reader]]\n"
        'name = "R"\n'
        'table = "t"\n'
        "default_values = { a = 1, zzz = 2 }\n",
    )

    with pytest.raises(ValidationError, match="not in table 't': zzz"):
        parse_spec(spec_file)


@pytest.mark.parametrize(
    ("default_value", "reason"),
    [
        ('{ a = "x" }', "expects an integer"),
        ("{ a = true }", "expects an integer"),
        ("{ a = 1.5 }", "expects an integer"),
        ("{ a = 3000000000 }", "expects an integer between"),
        ("{ b = 1 }", "expects a string"),
    ],
)
def test_default_value_of_the_wrong_type_rejected(
    tmp_path: Path, default_value: str, reason: str
) -> None:
    """A default value must fit the type of its column."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + "[[csv_reader]]\n"
        'name = "R"\n'
        'table = "t"\n'
        f"default_values = {default_value}\n",
    )

    with pytest.raises(ValidationError, match=reason):
        parse_spec(spec_file)


def test_default_values_accepted(tmp_path: Path) -> None:
    """A default value of the right type is kept as it is."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + "[[csv_reader]]\n"
        'name = "R"\n'
        'table = "t"\n'
        'default_values = { a = -3, b = "n/a" }\n',
    )

    spec = parse_spec(spec_file)

    assert spec.csv_readers[0].default_values == {"a": -3, "b": "n/a"}


def test_table_without_columns_rejected(tmp_path: Path) -> None:
    """A table must declare at least one column."""
    spec_file = write_spec(tmp_path, '[[table]]\nname = "t"\ncolumns = []\n')

    with pytest.raises(ValidationError, match="table 't' has no columns"):
        parse_spec(spec_file)


def test_annotated_example_parses() -> None:
    """The annotated example shows every kind of section."""
    spec = parse_spec(EXAMPLE)

    assert [t.name for t in spec.tables] == ["Measurement", "Station"]
    assert [r.name for r in spec.csv_readers] == [
        "MeasurementCsvReader",
        "StationCsvReader",
    ]
    assert [r.name for r in spec.parquet_readers] == ["MeasurementParquetReader"]
    assert [w.name for w in spec.csv_writers] == [
        "MeasurementCsvWriter",
        "StationCsvWriter",
    ]
    assert [w.name for w in spec.parquet_writers] == ["MeasurementParquetWriter"]


def test_annotated_example_uses_every_scalar_type() -> None:
    """The example declares a column of every scalar type."""
    spec = parse_spec(EXAMPLE)
    used = {column.type for table in spec.tables for column in table.columns}

    assert used == set(ScalarType)
