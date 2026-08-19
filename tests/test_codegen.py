"""Tests for the C++ code generation helpers."""

from codegen_cpp.codegen import (
    CPP_TYPES,
    ENVIRONMENT,
    cpp_literal,
    cpp_type,
    required_columns,
)
from codegen_cpp.spec import Column, CsvReader, ScalarType, Table


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


def test_required_columns_skips_the_ones_with_a_default() -> None:
    """Required columns are the columns that may not be null, in order."""
    reader = CsvReader(name="R", table="Point", default_values={"label": ""})

    assert [c.name for c in required_columns(TABLE, reader)] == ["id", "score"]


def test_required_columns_without_default_values() -> None:
    """Every column is required when no column has a default value."""
    reader = CsvReader(name="R", table="Point")

    assert required_columns(TABLE, reader) == TABLE.columns


def test_required_columns_with_every_column_defaulted() -> None:
    """No column is required when every column has a default value."""
    reader = CsvReader(
        name="R",
        table="Point",
        default_values={"id": 0, "label": "", "score": 0.0},
    )

    assert required_columns(TABLE, reader) == []


def test_required_columns_is_a_filter() -> None:
    """The filter is registered on the environment used by the templates."""
    assert ENVIRONMENT.filters["required_columns"] is required_columns


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
