"""Tests for parsing specification files."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from codegen_cpp.spec import (
    NUMERIC_TYPES,
    Dataset,
    FlatKey,
    Hdf5Reader,
    Hdf5Writer,
    NdArray,
    ScalarType,
    flatten_table,
    parse_spec,
    selected_arrays,
    sorted_aggregates,
)

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
    assert reader.default == {
        "quality": -1,
        "humidity": 0.0,
        "is_valid": False,
        "note": "",
    }

    # A reader may leave every column required.
    assert spec.csv_readers[1].default == {}

    # A reader may also say what the file calls a column.
    reader = spec.csv_readers[2]
    assert reader.default == {"latitude": 0.0, "longitude": 0.0}
    assert reader.name_in_file == {
        "station_id": "Station ID",
        "name": "Station Name",
    }


@pytest.mark.parametrize("section", ["table", "dataset", "csv_reader"])
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

GOOD_DATASET = """
[[dataset]]
name = "d"
dims = ["row", "col"]
arrays = [
    { name = "x", type = "f32" },
    { name = "y", type = "i8" },
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


@pytest.mark.parametrize(
    ("default", "reason"),
    [
        ('{ a = "x" }', "expects an integer"),
        ("{ a = true }", "expects an integer"),
        ("{ a = 1.5 }", "expects an integer"),
        ("{ a = 3000000000 }", "expects an integer between"),
        ("{ b = 1 }", "expects a string"),
    ],
)
def test_default_of_the_wrong_type_rejected(
    tmp_path: Path, default: str, reason: str
) -> None:
    """A default must fit the type of its column."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + "[[csv_reader]]\n"
        'name = "R"\n'
        'table = "t"\n'
        f"default = {default}\n",
    )

    with pytest.raises(ValidationError, match=reason):
        parse_spec(spec_file)


def test_defaults_accepted(tmp_path: Path) -> None:
    """A default of the right type is kept as it is."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + "[[csv_reader]]\n"
        'name = "R"\n'
        'table = "t"\n'
        'default = { a = -3, b = "n/a" }\n',
    )

    spec = parse_spec(spec_file)

    assert spec.csv_readers[0].default == {"a": -3, "b": "n/a"}


@pytest.mark.parametrize("section", ["csv_reader", "parquet_reader"])
def test_default_values_rejected(tmp_path: Path, section: str) -> None:
    """default_values is no longer read, and a spec that uses it is told so."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + f"[[{section}]]\n"
        'name = "R"\n'
        'table = "t"\n'
        "default_values = { a = 1 }\n",
    )

    with pytest.raises(
        ValidationError,
        match=f"{section} 'R' declares default_values, which is no longer read",
    ):
        parse_spec(spec_file)


def test_csv_reader_default_and_name_in_file_accepted(tmp_path: Path) -> None:
    """A CSV reader says what a Parquet reader says, keyed by column."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + "[[csv_reader]]\n"
        'name = "R"\n'
        'table = "t"\n'
        'default = { b = "n/a" }\n'
        'name_in_file = { a = "Column A" }\n',
    )

    spec = parse_spec(spec_file)

    reader = spec.csv_readers[0]
    assert reader.default == {"b": "n/a"}
    assert reader.name_in_file == {"a": "Column A"}


def test_csv_reader_default_and_name_in_file_default_to_empty(tmp_path: Path) -> None:
    """A CSV reader that says neither reads every column by its own name."""
    spec_file = write_spec(
        tmp_path, GOOD_TABLE + '[[csv_reader]]\nname = "R"\ntable = "t"\n'
    )

    reader = parse_spec(spec_file).csv_readers[0]

    assert reader.default == {}
    assert reader.name_in_file == {}


@pytest.mark.parametrize("key", ["zzz", "a.element", "b.x"])
def test_csv_reader_default_for_an_unknown_column_rejected(
    tmp_path: Path, key: str
) -> None:
    """A CSV holds the columns of a table and no level below them."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + "[[csv_reader]]\n"
        'name = "R"\n'
        'table = "t"\n'
        f'default = {{ "{key}" = 1 }}\n',
    )

    with pytest.raises(
        ValidationError,
        match=f"csv_reader 'R' has a default for '{key}', "
        "which table 't' does not hold",
    ):
        parse_spec(spec_file)


def test_csv_reader_default_of_the_wrong_type_rejected(tmp_path: Path) -> None:
    """A default has to fit the type of the column it names."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + "[[csv_reader]]\n"
        'name = "R"\n'
        'table = "t"\n'
        'default = { a = "x" }\n',
    )

    with pytest.raises(
        ValidationError,
        match="csv_reader 'R' has a default for 'a' that expects an integer",
    ):
        parse_spec(spec_file)


def test_csv_reader_name_in_file_for_an_unknown_column_rejected(
    tmp_path: Path,
) -> None:
    """A reader may only rename a column that the table declares."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + "[[csv_reader]]\n"
        'name = "R"\n'
        'table = "t"\n'
        'name_in_file = { zzz = "x" }\n',
    )

    with pytest.raises(
        ValidationError,
        match="csv_reader 'R' has a name_in_file for 'zzz', "
        "which table 't' does not hold",
    ):
        parse_spec(spec_file)


def test_csv_reader_that_reads_two_columns_by_one_name_rejected(
    tmp_path: Path,
) -> None:
    """Renaming may not make two columns of a table share a name."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + "[[csv_reader]]\n"
        'name = "R"\n'
        'table = "t"\n'
        'name_in_file = { a = "b" }\n',
    )

    with pytest.raises(
        ValidationError,
        match="csv_reader 'R' reads two parts of table 't' by one name: b",
    ):
        parse_spec(spec_file)


NESTED_TABLE = """
[[struct]]
name = "S"
fields = [{ name = "x", type = "i32" }]

[[vector]]
name = "V"
element = "i32"

[[table]]
name = "t"
columns = [
    { name = "a", type = "i32" },
    { name = "s", type = "S" },
    { name = "v", type = "V" },
]
"""


@pytest.mark.parametrize("section", ["csv_writer", "parquet_writer"])
def test_writer_name_in_file_accepted(tmp_path: Path, section: str) -> None:
    """A writer says what the file is to call a column, the way a reader does."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + f"[[{section}]]\n"
        'name = "W"\n'
        'table = "t"\n'
        'name_in_file = { a = "Column A" }\n',
    )

    writer = parse_spec(spec_file).writers[0]

    assert writer.name_in_file == {"a": "Column A"}


@pytest.mark.parametrize("section", ["csv_writer", "parquet_writer"])
def test_writer_name_in_file_defaults_to_empty(tmp_path: Path, section: str) -> None:
    """A writer that says nothing writes every column under its own name."""
    spec_file = write_spec(
        tmp_path, GOOD_TABLE + f'[[{section}]]\nname = "W"\ntable = "t"\n'
    )

    assert parse_spec(spec_file).writers[0].name_in_file == {}


@pytest.mark.parametrize("section", ["csv_writer", "parquet_writer"])
@pytest.mark.parametrize("key", ["zzz", "a.element"])
def test_writer_name_in_file_for_an_unknown_column_rejected(
    tmp_path: Path, section: str, key: str
) -> None:
    """A writer may only rename a part that the table declares."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + f"[[{section}]]\n"
        'name = "W"\n'
        'table = "t"\n'
        f'name_in_file = {{ "{key}" = "x" }}\n',
    )

    with pytest.raises(
        ValidationError,
        match=f"{section} 'W' has a name_in_file for '{key}', "
        "which table 't' does not hold",
    ):
        parse_spec(spec_file)


def test_parquet_writer_name_in_file_names_a_field_of_a_struct(
    tmp_path: Path,
) -> None:
    """A Parquet writer reaches a field of a struct, the way a reader does."""
    spec_file = write_spec(
        tmp_path,
        NESTED_TABLE + "[[parquet_writer]]\n"
        'name = "W"\n'
        'table = "t"\n'
        'name_in_file = { "s.x" = "across" }\n',
    )

    writer = parse_spec(spec_file).parquet_writers[0]

    assert writer.name_in_file == {"s.x": "across"}


def test_parquet_writer_name_in_file_for_a_part_matched_by_position_rejected(
    tmp_path: Path,
) -> None:
    """The element of a vector is written where it stands, under no name."""
    spec_file = write_spec(
        tmp_path,
        NESTED_TABLE + "[[parquet_writer]]\n"
        'name = "W"\n'
        'table = "t"\n'
        'name_in_file = { "v.element" = "x" }\n',
    )

    with pytest.raises(
        ValidationError,
        match="parquet_writer 'W' has a name_in_file for 'v.element', "
        "which a Parquet file matches by position rather than by name",
    ):
        parse_spec(spec_file)


@pytest.mark.parametrize("section", ["csv_writer", "parquet_writer"])
def test_writer_that_writes_two_columns_by_one_name_rejected(
    tmp_path: Path, section: str
) -> None:
    """Renaming may not make two columns of a table share a name."""
    spec_file = write_spec(
        tmp_path,
        GOOD_TABLE + f"[[{section}]]\n"
        'name = "W"\n'
        'table = "t"\n'
        'name_in_file = { a = "b" }\n',
    )

    with pytest.raises(
        ValidationError,
        match=f"{section} 'W' writes two parts of table 't' by one name: b",
    ):
        parse_spec(spec_file)


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
        "StationImportCsvReader",
    ]
    assert [r.name for r in spec.parquet_readers] == ["MeasurementParquetReader"]
    assert [w.name for w in spec.csv_writers] == [
        "MeasurementCsvWriter",
        "StationCsvWriter",
        "StationExportCsvWriter",
    ]

    # A writer says what the file is to call a column, the way a reader does.
    assert spec.csv_writers[2].name_in_file == {
        "station_id": "Station ID",
        "name": "Station Name",
    }
    assert [w.name for w in spec.parquet_writers] == ["MeasurementParquetWriter"]


def test_annotated_example_uses_every_scalar_type() -> None:
    """The example declares a column of every scalar type."""
    spec = parse_spec(EXAMPLE)
    used = {column.type for table in spec.tables for column in table.columns}

    assert used == set(ScalarType)


DATASET_EXAMPLE = Path(__file__).parent.parent / "examples" / "dataset1.toml"

NUMERIC_TYPES_IN_ORDER = [scalar for scalar in ScalarType if scalar in NUMERIC_TYPES]


def test_parse_dataset_example_spec() -> None:
    """The bundled n-dimensional array example parses its datasets."""
    spec = parse_spec(DATASET_EXAMPLE)

    assert [dataset.name for dataset in spec.datasets] == [
        "Series",
        "Raster",
        "Volume",
    ]

    raster = spec.datasets[1]
    assert raster.dims == ["row", "col"]
    assert raster.ndim == 2
    assert [array.name for array in raster.arrays] == [
        "elevation",
        "slope",
        "population",
        "land_class",
        "region_id",
        "mask",
    ]
    assert raster.arrays[0].type is ScalarType.f64
    assert raster.arrays[-1].type is ScalarType.i8

    # The rank of a dataset is the number of dims it names.
    assert [dataset.ndim for dataset in spec.datasets] == [1, 2, 3]

    # Storage is row major unless the dataset asks for column major.
    assert [dataset.column_major for dataset in spec.datasets] == [
        False,
        False,
        True,
    ]


def test_dataset_example_uses_every_numeric_type() -> None:
    """The example declares an array of every type a dataset may hold."""
    spec = parse_spec(DATASET_EXAMPLE)
    used = {array.type for dataset in spec.datasets for array in dataset.arrays}

    assert used == NUMERIC_TYPES


def test_dataset_without_dims_rejected(tmp_path: Path) -> None:
    """A dataset has to name at least one dimension."""
    spec_file = write_spec(
        tmp_path,
        "[[dataset]]\n"
        'name = "d"\n'
        "dims = []\n"
        'arrays = [{ name = "x", type = "f32" }]\n',
    )

    with pytest.raises(ValidationError, match="dataset 'd' has no dims"):
        parse_spec(spec_file)


def test_dataset_without_arrays_rejected(tmp_path: Path) -> None:
    """A dataset has to declare at least one array."""
    spec_file = write_spec(
        tmp_path,
        "[[dataset]]\n" 'name = "d"\n' 'dims = ["row"]\n' "arrays = []\n",
    )

    with pytest.raises(ValidationError, match="dataset 'd' has no arrays"):
        parse_spec(spec_file)


def test_duplicate_dims_rejected(tmp_path: Path) -> None:
    """A dataset may not name the same dimension twice."""
    spec_file = write_spec(
        tmp_path,
        "[[dataset]]\n"
        'name = "d"\n'
        'dims = ["row", "row"]\n'
        'arrays = [{ name = "x", type = "f32" }]\n',
    )

    with pytest.raises(ValidationError, match="duplicate dims: row"):
        parse_spec(spec_file)


def test_duplicate_array_names_rejected(tmp_path: Path) -> None:
    """A dataset may not declare the same array twice."""
    spec_file = write_spec(
        tmp_path,
        "[[dataset]]\n"
        'name = "d"\n'
        'dims = ["row"]\n'
        'arrays = [{ name = "x", type = "f32" },'
        ' { name = "x", type = "i8" }]\n',
    )

    with pytest.raises(ValidationError, match="duplicate arrays: x"):
        parse_spec(spec_file)


@pytest.mark.parametrize("scalar", ["bool", "str"])
def test_non_numeric_array_type_rejected(tmp_path: Path, scalar: str) -> None:
    """An array holds a number, so `bool` and `str` are not allowed."""
    spec_file = write_spec(
        tmp_path,
        "[[dataset]]\n"
        'name = "d"\n'
        'dims = ["row"]\n'
        f'arrays = [{{ name = "x", type = "{scalar}" }}]\n',
    )

    with pytest.raises(ValidationError, match=f"array 'x' has type '{scalar}'"):
        parse_spec(spec_file)


def test_every_numeric_type_accepted(tmp_path: Path) -> None:
    """An array may hold any of the integer and floating point types."""
    arrays = ", ".join(
        f'{{ name = "a{index}", type = "{scalar.value}" }}'
        for index, scalar in enumerate(NUMERIC_TYPES_IN_ORDER)
    )
    spec_file = write_spec(
        tmp_path,
        "[[dataset]]\n" 'name = "d"\n' 'dims = ["row"]\n' f"arrays = [{arrays}]\n",
    )

    spec = parse_spec(spec_file)

    assert {array.type for array in spec.datasets[0].arrays} == set(
        NUMERIC_TYPES_IN_ORDER
    )


def test_duplicate_dataset_names_rejected(tmp_path: Path) -> None:
    """Two datasets may not share a name."""
    spec_file = write_spec(tmp_path, GOOD_DATASET + GOOD_DATASET)

    with pytest.raises(ValidationError, match="duplicate table or reader names: d"):
        parse_spec(spec_file)


def test_dataset_and_table_share_one_namespace(tmp_path: Path) -> None:
    """A dataset may not take the name of a table."""
    dataset = GOOD_DATASET.replace('name = "d"', 'name = "t"')
    spec_file = write_spec(tmp_path, GOOD_TABLE + dataset)

    with pytest.raises(ValidationError, match="duplicate table or reader names: t"):
        parse_spec(spec_file)


GOOD_HDF5_DATASET = """
[[dataset]]
name = "d"
dims = ["row", "col"]
arrays = [
    { name = "x", type = "f32" },
    { name = "y", type = "i8" },
    { name = "z", type = "u16" },
]
"""


def test_parse_hdf5_readers() -> None:
    """The bundled n-dimensional array example parses its HDF5 readers."""
    spec = parse_spec(DATASET_EXAMPLE)

    assert [reader.name for reader in spec.hdf5_readers] == [
        "read_series",
        "read_raster",
        "read_raster_mask",
        "read_raster_layers",
        "read_volume",
    ]

    # Without include or exclude every array of the dataset is read.
    series = spec.hdf5_readers[0]
    assert series.dataset == "Series"
    assert series.include is None
    assert series.exclude is None

    assert spec.hdf5_readers[2].include == ["mask"]
    assert spec.hdf5_readers[3].exclude == ["mask"]


def test_selected_arrays_without_include_or_exclude() -> None:
    """A reader that lists neither reads every array, in declaration order."""
    spec = parse_spec(DATASET_EXAMPLE)
    dataset = spec.datasets[0]
    reader = spec.hdf5_readers[0]

    assert selected_arrays(dataset, reader) == dataset.arrays


def test_selected_arrays_with_include() -> None:
    """An include list keeps only the arrays it names."""
    spec = parse_spec(DATASET_EXAMPLE)
    dataset = spec.datasets[1]
    reader = spec.hdf5_readers[2]

    assert [array.name for array in selected_arrays(dataset, reader)] == ["mask"]


def test_selected_arrays_with_exclude() -> None:
    """An exclude list drops the arrays it names and keeps the rest."""
    spec = parse_spec(DATASET_EXAMPLE)
    dataset = spec.datasets[1]
    reader = spec.hdf5_readers[3]

    assert [array.name for array in selected_arrays(dataset, reader)] == [
        "elevation",
        "slope",
        "population",
        "land_class",
        "region_id",
    ]


def test_selected_arrays_keeps_the_declaration_order() -> None:
    """The selected arrays follow the dataset, not the include list."""
    dataset = Dataset(
        name="d",
        dims=["row"],
        arrays=[
            NdArray(name="x", type=ScalarType.f32),
            NdArray(name="y", type=ScalarType.i8),
            NdArray(name="z", type=ScalarType.u16),
        ],
    )
    reader = Hdf5Reader(name="r", dataset="d", include=["z", "x"])

    assert [array.name for array in selected_arrays(dataset, reader)] == ["x", "z"]


# The include and exclude rules are the same for readers and for writers.
HDF5_SECTIONS = ["hdf5_reader", "hdf5_writer"]


@pytest.mark.parametrize("section", HDF5_SECTIONS)
def test_hdf5_with_both_include_and_exclude_rejected(
    tmp_path: Path, section: str
) -> None:
    """A reader or writer may not narrow its arrays from both ends."""
    spec_file = write_spec(
        tmp_path,
        GOOD_HDF5_DATASET + f"[[{section}]]\n"
        'name = "r"\n'
        'dataset = "d"\n'
        'include = ["x"]\n'
        'exclude = ["y"]\n',
    )

    with pytest.raises(ValidationError, match="lists both include and exclude"):
        parse_spec(spec_file)


@pytest.mark.parametrize("section", HDF5_SECTIONS)
@pytest.mark.parametrize("kind", ["include", "exclude"])
def test_hdf5_with_an_empty_list_rejected(
    tmp_path: Path, section: str, kind: str
) -> None:
    """An include or exclude list that is given may not be empty."""
    spec_file = write_spec(
        tmp_path,
        GOOD_HDF5_DATASET + f"[[{section}]]\n"
        'name = "r"\n'
        'dataset = "d"\n'
        f"{kind} = []\n",
    )

    with pytest.raises(ValidationError, match=f"has an empty {kind} list"):
        parse_spec(spec_file)


@pytest.mark.parametrize("section", HDF5_SECTIONS)
@pytest.mark.parametrize("kind", ["include", "exclude"])
def test_hdf5_with_a_duplicate_array_rejected(
    tmp_path: Path, section: str, kind: str
) -> None:
    """An include or exclude list may not name the same array twice."""
    spec_file = write_spec(
        tmp_path,
        GOOD_HDF5_DATASET + f"[[{section}]]\n"
        'name = "r"\n'
        'dataset = "d"\n'
        f'{kind} = ["x", "x"]\n',
    )

    with pytest.raises(ValidationError, match=f"duplicate {kind} arrays: x"):
        parse_spec(spec_file)


@pytest.mark.parametrize("section", HDF5_SECTIONS)
@pytest.mark.parametrize("kind", ["include", "exclude"])
def test_hdf5_with_an_unknown_array_rejected(
    tmp_path: Path, section: str, kind: str
) -> None:
    """An include or exclude list may only name arrays of the dataset."""
    spec_file = write_spec(
        tmp_path,
        GOOD_HDF5_DATASET + f"[[{section}]]\n"
        'name = "r"\n'
        'dataset = "d"\n'
        f'{kind} = ["x", "zzz"]\n',
    )

    with pytest.raises(
        ValidationError,
        match=f"lists {kind} arrays not in dataset 'd': zzz",
    ):
        parse_spec(spec_file)


@pytest.mark.parametrize("section", HDF5_SECTIONS)
def test_hdf5_that_excludes_every_array_rejected(tmp_path: Path, section: str) -> None:
    """A reader or writer left with no array to use is an error."""
    spec_file = write_spec(
        tmp_path,
        GOOD_HDF5_DATASET + f"[[{section}]]\n"
        'name = "r"\n'
        'dataset = "d"\n'
        'exclude = ["x", "y", "z"]\n',
    )

    with pytest.raises(ValidationError, match="selects no array of dataset 'd'"):
        parse_spec(spec_file)


@pytest.mark.parametrize("section", HDF5_SECTIONS)
def test_hdf5_with_an_unknown_dataset_rejected(tmp_path: Path, section: str) -> None:
    """An HDF5 reader or writer must refer to a defined dataset."""
    spec_file = write_spec(
        tmp_path,
        GOOD_HDF5_DATASET + f'[[{section}]]\nname = "r"\ndataset = "missing"\n',
    )

    with pytest.raises(ValidationError, match="undefined dataset 'missing'"):
        parse_spec(spec_file)


def test_hdf5_reader_shares_the_one_namespace(tmp_path: Path) -> None:
    """An HDF5 reader may not take the name of a dataset."""
    spec_file = write_spec(
        tmp_path,
        GOOD_HDF5_DATASET + '[[hdf5_reader]]\nname = "d"\ndataset = "d"\n',
    )

    with pytest.raises(ValidationError, match="duplicate table or reader names: d"):
        parse_spec(spec_file)


def test_duplicate_hdf5_reader_names_rejected(tmp_path: Path) -> None:
    """Two HDF5 readers may not share a name."""
    reader = '[[hdf5_reader]]\nname = "r"\ndataset = "d"\n'
    spec_file = write_spec(tmp_path, GOOD_HDF5_DATASET + reader + reader)

    with pytest.raises(ValidationError, match="duplicate table or reader names: r"):
        parse_spec(spec_file)


def test_column_major_defaults_to_false(tmp_path: Path) -> None:
    """A dataset that says nothing stores its arrays row major."""
    spec_file = write_spec(tmp_path, GOOD_DATASET)

    spec = parse_spec(spec_file)

    assert spec.datasets[0].column_major is False


def test_column_major_is_kept(tmp_path: Path) -> None:
    """A dataset may ask for the first dim to vary fastest."""
    spec_file = write_spec(tmp_path, GOOD_DATASET + "column_major = true\n")

    spec = parse_spec(spec_file)

    assert spec.datasets[0].column_major is True


def test_parse_hdf5_writers() -> None:
    """The bundled n-dimensional array example parses its HDF5 writers."""
    spec = parse_spec(DATASET_EXAMPLE)

    assert [writer.name for writer in spec.hdf5_writers] == [
        "write_series",
        "write_raster",
        "write_raster_mask",
        "write_raster_layers",
        "write_volume",
    ]

    writer = spec.hdf5_writers[0]
    assert writer.dataset == "Series"
    assert writer.include is None
    assert writer.exclude is None

    # The lists mean the same thing for a writer as for a reader.
    assert spec.hdf5_writers[2].include == ["mask"]
    assert spec.hdf5_writers[3].exclude == ["mask"]


def test_hdf5_classes_hold_the_readers_and_the_writers() -> None:
    """Readers and writers share the checks that apply to both."""
    spec = parse_spec(DATASET_EXAMPLE)

    assert [c.KIND for c in spec.hdf5_classes] == ["hdf5_reader"] * 5 + [
        "hdf5_writer"
    ] * 5


def test_selected_arrays_of_a_writer() -> None:
    """A writer narrows its arrays the same way a reader does."""
    dataset = Dataset(
        name="d",
        dims=["row"],
        arrays=[
            NdArray(name="x", type=ScalarType.f32),
            NdArray(name="y", type=ScalarType.i8),
        ],
    )
    writer = Hdf5Writer(name="w", dataset="d", exclude=["x"])

    assert [array.name for array in selected_arrays(dataset, writer)] == ["y"]


def test_hdf5_writer_shares_the_one_namespace(tmp_path: Path) -> None:
    """A reader and a writer may not share a name."""
    spec_file = write_spec(
        tmp_path,
        GOOD_HDF5_DATASET + '[[hdf5_reader]]\nname = "f"\ndataset = "d"\n'
        '[[hdf5_writer]]\nname = "f"\ndataset = "d"\n',
    )

    with pytest.raises(ValidationError, match="duplicate table or reader names: f"):
        parse_spec(spec_file)


AGGREGATES = Path(__file__).parent.parent / "examples" / "table2.toml"


def test_parse_aggregate_types() -> None:
    """The bundled example spec parses its vectors, maps and structs."""
    spec = parse_spec(AGGREGATES)

    assert [vector.name for vector in spec.vectors] == [
        "Keywords",
        "Positions",
        "Topics",
        "Affiliations",
    ]
    assert spec.vectors[0].element is ScalarType.str
    assert spec.vectors[2].element == "TopicScore"

    ids, citations = spec.maps
    assert (ids.name, ids.key, ids.value, ids.is_unordered) == (
        "Ids",
        ScalarType.str,
        ScalarType.str,
        False,
    )
    assert (citations.name, citations.key, citations.value) == (
        "CitationsByYear",
        ScalarType.i64,
        ScalarType.u32,
    )
    assert citations.is_unordered

    biblio = spec.structs[0]
    assert biblio.name == "Biblio"
    assert [field.name for field in biblio.fields] == [
        "volume",
        "issue",
        "first_page",
        "last_page",
    ]
    assert biblio.fields[2].type is ScalarType.i32


def test_a_column_holds_an_aggregate_type() -> None:
    """A column names an aggregate type where it does not name a scalar one."""
    spec = parse_spec(AGGREGATES)

    work = spec.tables[0]
    assert work.name == "Work"
    assert work.columns[0].type is ScalarType.i64
    assert work.columns[2].type == "Keywords"
    assert work.columns[7].type == "CitationsByYear"


def test_sorted_aggregates_declares_a_type_before_the_types_that_name_it() -> None:
    """The types come out in an order that C++ can be written in."""
    spec = parse_spec(AGGREGATES)
    aggregates = {aggregate.name: aggregate for aggregate in spec.aggregates}

    ordered = [aggregate.name for aggregate in sorted_aggregates(aggregates)]

    assert sorted(ordered) == sorted(aggregates)
    assert ordered.index("TopicScore") < ordered.index("Topics")
    assert ordered.index("Keywords") < ordered.index("Affiliations")
    assert ordered.index("Positions") < ordered.index("MentionPositions")


def test_flatten_table_names_every_part_of_a_table() -> None:
    """A key names a column and one step for every level below it."""
    spec = parse_spec(AGGREGATES)
    aggregates = {aggregate.name: aggregate for aggregate in spec.aggregates}

    keys = flatten_table(spec.tables[0], aggregates)

    assert keys["work_id"] == FlatKey(type=ScalarType.i64, is_named=True)
    assert keys["keywords.element"] == FlatKey(type=ScalarType.str, is_named=False)
    assert keys["biblio.first_page"] == FlatKey(type=ScalarType.i32, is_named=True)
    assert keys["topics.element.score"] == FlatKey(type=ScalarType.f64, is_named=True)
    assert keys["affiliations.element.element"] == FlatKey(
        type=ScalarType.str, is_named=False
    )

    # A key of a map is never a step of its own.
    assert "ids.value" in keys
    assert "ids.key" not in keys


def test_spec_rejects_a_type_that_contains_itself(tmp_path: Path) -> None:
    """A type that leads back to itself is an error, not an endless column."""
    spec_file = tmp_path / "spec.toml"
    spec_file.write_text(
        '[[vector]]\nname = "A"\nelement = "B"\n\n'
        '[[vector]]\nname = "B"\nelement = "A"\n\n'
        '[[table]]\nname = "T"\ncolumns = [{ name = "a", type = "A" }]\n'
    )

    with pytest.raises(ValidationError, match="contain one another"):
        parse_spec(spec_file)


def test_spec_rejects_a_column_of_an_undefined_type(tmp_path: Path) -> None:
    """A type that is neither a scalar type nor declared is reported."""
    spec_file = tmp_path / "spec.toml"
    spec_file.write_text(
        '[[table]]\nname = "T"\ncolumns = [{ name = "a", type = "Missing" }]\n'
    )

    with pytest.raises(ValidationError, match="undefined type 'Missing'"):
        parse_spec(spec_file)
