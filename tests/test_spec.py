"""Tests for parsing specification files."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from codegen_cpp.spec import (
    NUMERIC_TYPES,
    Dataset,
    Hdf5Reader,
    NdArray,
    ScalarType,
    parse_spec,
    selected_arrays,
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
    assert reader.default_values == {
        "quality": -1,
        "humidity": 0.0,
        "is_valid": False,
        "note": "",
    }

    # A reader may leave every column required.
    assert spec.csv_readers[1].default_values == {}


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


NDARRAY_EXAMPLE = Path(__file__).parent.parent / "examples" / "ndarray.toml"

NUMERIC_TYPES_IN_ORDER = [scalar for scalar in ScalarType if scalar in NUMERIC_TYPES]


def test_parse_ndarray_example_spec() -> None:
    """The bundled n-dimensional array example parses its datasets."""
    spec = parse_spec(NDARRAY_EXAMPLE)

    assert [dataset.name for dataset in spec.datasets] == [
        "TickData",
        "TileData",
        "SimOutput",
    ]

    tile_data = spec.datasets[1]
    assert tile_data.dims == ["row", "col"]
    assert tile_data.ndim == 2
    assert [array.name for array in tile_data.arrays] == [
        "burn_time",
        "fuel",
        "moisture",
        "state",
    ]
    assert tile_data.arrays[0].type is ScalarType.f32
    assert tile_data.arrays[-1].type is ScalarType.i8

    # The rank of a dataset is the number of dims it names.
    assert [dataset.ndim for dataset in spec.datasets] == [1, 2, 3]

    # Storage is row major unless the dataset asks for column major.
    assert [dataset.column_major for dataset in spec.datasets] == [
        False,
        False,
        True,
    ]


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
    spec = parse_spec(NDARRAY_EXAMPLE)

    assert [reader.name for reader in spec.hdf5_readers] == [
        "read_tick_data",
        "read_tile_data",
        "read_seed_data",
    ]

    # Without include or exclude every array of the dataset is read.
    tick = spec.hdf5_readers[0]
    assert tick.dataset == "TickData"
    assert tick.include is None
    assert tick.exclude is None

    assert spec.hdf5_readers[1].exclude == ["state"]
    assert spec.hdf5_readers[2].include == ["state"]


def test_selected_arrays_without_include_or_exclude() -> None:
    """A reader that lists neither reads every array, in declaration order."""
    spec = parse_spec(NDARRAY_EXAMPLE)
    dataset = spec.datasets[0]
    reader = spec.hdf5_readers[0]

    assert selected_arrays(dataset, reader) == dataset.arrays


def test_selected_arrays_with_include() -> None:
    """An include list keeps only the arrays it names."""
    spec = parse_spec(NDARRAY_EXAMPLE)
    dataset = spec.datasets[1]
    reader = spec.hdf5_readers[2]

    assert [array.name for array in selected_arrays(dataset, reader)] == ["state"]


def test_selected_arrays_with_exclude() -> None:
    """An exclude list drops the arrays it names and keeps the rest."""
    spec = parse_spec(NDARRAY_EXAMPLE)
    dataset = spec.datasets[1]
    reader = spec.hdf5_readers[1]

    assert [array.name for array in selected_arrays(dataset, reader)] == [
        "burn_time",
        "fuel",
        "moisture",
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


def test_hdf5_reader_with_both_include_and_exclude_rejected(tmp_path: Path) -> None:
    """A reader may not narrow its arrays from both ends."""
    spec_file = write_spec(
        tmp_path,
        GOOD_HDF5_DATASET + "[[hdf5_reader]]\n"
        'name = "r"\n'
        'dataset = "d"\n'
        'include = ["x"]\n'
        'exclude = ["y"]\n',
    )

    with pytest.raises(ValidationError, match="lists both include and exclude"):
        parse_spec(spec_file)


@pytest.mark.parametrize("kind", ["include", "exclude"])
def test_hdf5_reader_with_an_empty_list_rejected(tmp_path: Path, kind: str) -> None:
    """An include or exclude list that is given may not be empty."""
    spec_file = write_spec(
        tmp_path,
        GOOD_HDF5_DATASET + "[[hdf5_reader]]\n"
        'name = "r"\n'
        'dataset = "d"\n'
        f"{kind} = []\n",
    )

    with pytest.raises(ValidationError, match=f"has an empty {kind} list"):
        parse_spec(spec_file)


@pytest.mark.parametrize("kind", ["include", "exclude"])
def test_hdf5_reader_with_a_duplicate_array_rejected(tmp_path: Path, kind: str) -> None:
    """An include or exclude list may not name the same array twice."""
    spec_file = write_spec(
        tmp_path,
        GOOD_HDF5_DATASET + "[[hdf5_reader]]\n"
        'name = "r"\n'
        'dataset = "d"\n'
        f'{kind} = ["x", "x"]\n',
    )

    with pytest.raises(ValidationError, match=f"duplicate {kind} arrays: x"):
        parse_spec(spec_file)


@pytest.mark.parametrize("kind", ["include", "exclude"])
def test_hdf5_reader_with_an_unknown_array_rejected(tmp_path: Path, kind: str) -> None:
    """An include or exclude list may only name arrays of the dataset."""
    spec_file = write_spec(
        tmp_path,
        GOOD_HDF5_DATASET + "[[hdf5_reader]]\n"
        'name = "r"\n'
        'dataset = "d"\n'
        f'{kind} = ["x", "zzz"]\n',
    )

    with pytest.raises(
        ValidationError,
        match=f"lists {kind} arrays not in dataset 'd': zzz",
    ):
        parse_spec(spec_file)


def test_hdf5_reader_that_excludes_every_array_rejected(tmp_path: Path) -> None:
    """A reader that is left with no array to read is an error."""
    spec_file = write_spec(
        tmp_path,
        GOOD_HDF5_DATASET + "[[hdf5_reader]]\n"
        'name = "r"\n'
        'dataset = "d"\n'
        'exclude = ["x", "y", "z"]\n',
    )

    with pytest.raises(ValidationError, match="reads no array of dataset 'd'"):
        parse_spec(spec_file)


def test_hdf5_reader_with_an_unknown_dataset_rejected(tmp_path: Path) -> None:
    """An HDF5 reader must refer to a defined dataset."""
    spec_file = write_spec(
        tmp_path,
        GOOD_HDF5_DATASET + '[[hdf5_reader]]\nname = "r"\ndataset = "missing"\n',
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
