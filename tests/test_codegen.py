"""Tests for the C++ code generation helpers."""

from codegen_cpp.codegen import (
    CPP_TYPES,
    ENVIRONMENT,
    HDF5_NATIVE_TYPES,
    cpp_literal,
    cpp_string,
    cpp_type,
    hdf5_native_type,
    table_nodes,
)
from codegen_cpp.spec import (
    NUMERIC_TYPES,
    Column,
    CsvReader,
    CsvWriter,
    ScalarType,
    Table,
    selected_arrays,
)


def test_every_scalar_type_is_mapped() -> None:
    """Every member of ScalarType has a C++ spelling."""
    assert set(CPP_TYPES) == set(ScalarType)


def test_cpp_type() -> None:
    """Scalar types map to their expected C++ spellings."""
    assert cpp_type(ScalarType.i8) == "std::int8_t"
    assert cpp_type(ScalarType.u64) == "std::uint64_t"
    assert cpp_type(ScalarType.f32) == "float"
    assert cpp_type(ScalarType.f64) == "double"
    assert cpp_type(ScalarType.bool) == "bool"
    assert cpp_type(ScalarType.str) == "std::string"


TABLE = Table(
    name="Point",
    columns=[
        Column(name="id", type=ScalarType.u32),
        Column(name="label", type=ScalarType.str),
        Column(name="score", type=ScalarType.f64),
    ],
)


def test_table_nodes_without_a_reader() -> None:
    """A column of a table is its own node, named after itself."""
    nodes = table_nodes(TABLE)

    assert [node.key for node in nodes] == ["id", "label", "score"]
    assert [node.name_in_file for node in nodes] == ["id", "label", "score"]
    assert all(node.default is None for node in nodes)


def test_table_nodes_of_a_csv_reader_carry_its_defaults() -> None:
    """A column with a default is the one that may hold a null."""
    reader = CsvReader(name="R", table="Point", default={"label": ""})

    nodes = table_nodes(TABLE, None, reader)

    assert [node.default for node in nodes] == [None, 'std::string("")', None]


def test_table_nodes_of_a_csv_reader_carry_its_names_in_the_file() -> None:
    """A CSV reader looks for the name the file gives a column."""
    reader = CsvReader(name="R", table="Point", name_in_file={"id": "ident"})

    nodes = table_nodes(TABLE, None, reader)

    assert [node.name_in_file for node in nodes] == ["ident", "label", "score"]
    assert [node.member for node in nodes] == ["id", "label", "score"]


def test_table_nodes_of_a_csv_writer_carry_its_names_in_the_file() -> None:
    """A CSV writer writes a column under the name the file is to give it."""
    writer = CsvWriter(name="W", table="Point", name_in_file={"id": "ident"})

    nodes = table_nodes(TABLE, None, writer)

    assert [node.name_in_file for node in nodes] == ["ident", "label", "score"]
    assert [node.member for node in nodes] == ["id", "label", "score"]


def test_cpp_literal() -> None:
    """Default values are spelled as constructions of their C++ type."""
    assert cpp_literal(True, ScalarType.bool) == "bool(true)"
    assert cpp_literal(False, ScalarType.bool) == "bool(false)"
    assert cpp_literal(-7, ScalarType.i8) == "std::int8_t(-7)"
    assert cpp_literal(42, ScalarType.u64) == "std::uint64_t(42)"
    assert cpp_literal(2, ScalarType.f32) == "float(2.0)"
    assert cpp_literal(0.5, ScalarType.f64) == "double(0.5)"


def test_cpp_literal_escapes_strings() -> None:
    """String defaults are escaped for a C++ string literal."""
    assert cpp_literal("n/a", ScalarType.str) == 'std::string("n/a")'
    assert cpp_literal('a"b', ScalarType.str) == 'std::string("a\\"b")'
    assert cpp_literal("a\\b", ScalarType.str) == 'std::string("a\\\\b")'
    assert cpp_literal("a\nb", ScalarType.str) == 'std::string("a\\nb")'


def test_cpp_string() -> None:
    """A name that reaches the generated code is escaped for a C++ literal."""
    assert cpp_string("id") == '"id"'
    assert cpp_string('size ("m")') == '"size (\\"m\\")"'
    assert cpp_string("a\\b") == '"a\\\\b"'
    assert cpp_string("a\tb") == '"a\\tb"'


def test_cpp_string_is_a_filter() -> None:
    """The filter is registered on the environment used by the templates."""
    assert ENVIRONMENT.filters["cpp_string"] is cpp_string


def test_every_numeric_type_has_an_hdf5_spelling() -> None:
    """Every type that an array may hold maps to an HDF5 predefined type."""
    assert set(HDF5_NATIVE_TYPES) == NUMERIC_TYPES


def test_hdf5_native_type() -> None:
    """Arrays are read with the predefined type of the running machine."""
    assert hdf5_native_type(ScalarType.i8) == "H5::PredType::NATIVE_INT8"
    assert hdf5_native_type(ScalarType.u32) == "H5::PredType::NATIVE_UINT32"
    assert hdf5_native_type(ScalarType.f32) == "H5::PredType::NATIVE_FLOAT"
    assert hdf5_native_type(ScalarType.f64) == "H5::PredType::NATIVE_DOUBLE"


def test_hdf5_native_type_distinguishes_the_integers() -> None:
    """Size and signedness are carried by the predefined type itself."""
    assert hdf5_native_type(ScalarType.i16) != hdf5_native_type(ScalarType.u16)
    assert hdf5_native_type(ScalarType.i16) != hdf5_native_type(ScalarType.i32)
    assert hdf5_native_type(ScalarType.f32) != hdf5_native_type(ScalarType.f64)


def test_selected_arrays_is_a_filter() -> None:
    """The filter is registered on the environment used by the templates."""
    assert ENVIRONMENT.filters["selected_arrays"] is selected_arrays
