"""Generate the cpp code."""

from jinja2 import Environment, PackageLoader, StrictUndefined

from .spec import Column, CsvReader, ParquetReader, Reader, ScalarType, Table

CPP_TYPES = {
    ScalarType.i8: "std::int8_t",
    ScalarType.i16: "std::int16_t",
    ScalarType.i32: "std::int32_t",
    ScalarType.i64: "std::int64_t",
    ScalarType.u8: "std::uint8_t",
    ScalarType.u16: "std::uint16_t",
    ScalarType.u32: "std::uint32_t",
    ScalarType.u64: "std::uint64_t",
    ScalarType.f32: "float",
    ScalarType.f64: "double",
    ScalarType.bool: "bool",
    ScalarType.str: "std::string",
}


ARROW_TYPES = {
    ScalarType.i8: "arrow::int8()",
    ScalarType.i16: "arrow::int16()",
    ScalarType.i32: "arrow::int32()",
    ScalarType.i64: "arrow::int64()",
    ScalarType.u8: "arrow::uint8()",
    ScalarType.u16: "arrow::uint16()",
    ScalarType.u32: "arrow::uint32()",
    ScalarType.u64: "arrow::uint64()",
    ScalarType.f32: "arrow::float32()",
    ScalarType.f64: "arrow::float64()",
    ScalarType.bool: "arrow::boolean()",
    ScalarType.str: "arrow::utf8()",
}

ARROW_ARRAY_TYPES = {
    ScalarType.i8: "arrow::Int8Array",
    ScalarType.i16: "arrow::Int16Array",
    ScalarType.i32: "arrow::Int32Array",
    ScalarType.i64: "arrow::Int64Array",
    ScalarType.u8: "arrow::UInt8Array",
    ScalarType.u16: "arrow::UInt16Array",
    ScalarType.u32: "arrow::UInt32Array",
    ScalarType.u64: "arrow::UInt64Array",
    ScalarType.f32: "arrow::FloatArray",
    ScalarType.f64: "arrow::DoubleArray",
    ScalarType.bool: "arrow::BooleanArray",
    ScalarType.str: "arrow::StringArray",
}


def cpp_type(type: ScalarType) -> str:
    """Return the C++ type used to represent TYPE."""
    return CPP_TYPES[type]


def arrow_type(type: ScalarType) -> str:
    """Return the expression constructing the Arrow data type of TYPE."""
    return ARROW_TYPES[type]


def arrow_array_type(type: ScalarType) -> str:
    """Return the Arrow array class holding a column of TYPE."""
    return ARROW_ARRAY_TYPES[type]


def required_columns(table: Table, reader: Reader) -> list[Column]:
    """Return the columns of TABLE that READER does not allow to be null."""
    nullable = set(reader.nullable_columns)
    return [column for column in table.columns if column.name not in nullable]


def make_environment() -> Environment:
    """Return the Jinja environment used to render the templates."""
    env = Environment(
        loader=PackageLoader("codegen_cpp", "templates"),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    env.filters["cpp_type"] = cpp_type
    env.filters["arrow_type"] = arrow_type
    env.filters["arrow_array_type"] = arrow_array_type
    env.filters["required_columns"] = required_columns
    return env


ENVIRONMENT = make_environment()


def render_table(table: Table) -> str:
    """Return the contents of the C++ header defining TABLE."""
    return ENVIRONMENT.get_template("table.hpp.jinja").render(table=table)


def table_header_name(table: Table) -> str:
    """Return the file name of the C++ header defining TABLE."""
    return f"{table.name}.hpp"


def render_csv_reader(csv_reader: CsvReader, table: Table) -> str:
    """
    Return the contents of the C++ header defining CSV_READER.

    TABLE is the table that CSV_READER fills in.
    """
    template = ENVIRONMENT.get_template("csv_reader.hpp.jinja")
    return template.render(csv_reader=csv_reader, table=table)


def csv_reader_header_name(csv_reader: CsvReader) -> str:
    """Return the file name of the C++ header defining CSV_READER."""
    return f"{csv_reader.name}.hpp"


def render_parquet_reader(parquet_reader: ParquetReader, table: Table) -> str:
    """
    Return the contents of the C++ header defining PARQUET_READER.

    TABLE is the table that PARQUET_READER fills in.
    """
    template = ENVIRONMENT.get_template("parquet_reader.hpp.jinja")
    return template.render(parquet_reader=parquet_reader, table=table)


def parquet_reader_header_name(parquet_reader: ParquetReader) -> str:
    """Return the file name of the C++ header defining PARQUET_READER."""
    return f"{parquet_reader.name}.hpp"
