"""Generate the cpp code."""

from jinja2 import Environment, PackageLoader, StrictUndefined

from .spec import (
    Column,
    CsvReader,
    CsvWriter,
    Dataset,
    DefaultValue,
    Hdf5Reader,
    Hdf5Writer,
    ParquetReader,
    ParquetWriter,
    Reader,
    ScalarType,
    Table,
    selected_arrays,
)

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


ARROW_BUILDER_TYPES = {
    ScalarType.i8: "arrow::Int8Builder",
    ScalarType.i16: "arrow::Int16Builder",
    ScalarType.i32: "arrow::Int32Builder",
    ScalarType.i64: "arrow::Int64Builder",
    ScalarType.u8: "arrow::UInt8Builder",
    ScalarType.u16: "arrow::UInt16Builder",
    ScalarType.u32: "arrow::UInt32Builder",
    ScalarType.u64: "arrow::UInt64Builder",
    ScalarType.f32: "arrow::FloatBuilder",
    ScalarType.f64: "arrow::DoubleBuilder",
    ScalarType.bool: "arrow::BooleanBuilder",
    ScalarType.str: "arrow::StringBuilder",
}


# The HDF5 predefined types describing the memory that an array is read into.
# They name the layout of the running machine,
# so the library converts the byte order of the file while it reads.
HDF5_NATIVE_TYPES = {
    ScalarType.i8: "H5::PredType::NATIVE_INT8",
    ScalarType.i16: "H5::PredType::NATIVE_INT16",
    ScalarType.i32: "H5::PredType::NATIVE_INT32",
    ScalarType.i64: "H5::PredType::NATIVE_INT64",
    ScalarType.u8: "H5::PredType::NATIVE_UINT8",
    ScalarType.u16: "H5::PredType::NATIVE_UINT16",
    ScalarType.u32: "H5::PredType::NATIVE_UINT32",
    ScalarType.u64: "H5::PredType::NATIVE_UINT64",
    ScalarType.f32: "H5::PredType::NATIVE_FLOAT",
    ScalarType.f64: "H5::PredType::NATIVE_DOUBLE",
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


def arrow_builder_type(type: ScalarType) -> str:
    """Return the Arrow builder class building a column of TYPE."""
    return ARROW_BUILDER_TYPES[type]


def hdf5_native_type(type: ScalarType) -> str:
    """Return the HDF5 predefined type of the memory holding TYPE."""
    return HDF5_NATIVE_TYPES[type]


def required_columns(table: Table, reader: Reader) -> list[Column]:
    """Return the columns of TABLE that READER does not allow to be null."""
    return [
        column for column in table.columns if column.name not in reader.default_values
    ]


# The characters that need to be escaped in a C++ string literal.
CPP_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def cpp_literal(value: DefaultValue, type: ScalarType) -> str:
    """
    Return VALUE as a C++ expression of the C++ type of TYPE.

    The value is spelled as a construction of its type,
    so that it can be used where the type has to match exactly.
    """
    if type is ScalarType.bool:
        literal = "true" if value else "false"
    elif type is ScalarType.str:
        escaped = "".join(CPP_ESCAPES.get(c, c) for c in str(value))
        literal = f'"{escaped}"'
    elif type in (ScalarType.f32, ScalarType.f64):
        literal = repr(float(value))  # type: ignore[arg-type]
    else:
        literal = repr(int(value))  # type: ignore[arg-type]

    return f"{cpp_type(type)}({literal})"


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
    env.filters["arrow_builder_type"] = arrow_builder_type
    env.filters["required_columns"] = required_columns
    env.filters["selected_arrays"] = selected_arrays
    env.filters["hdf5_native_type"] = hdf5_native_type
    env.filters["cpp_literal"] = cpp_literal
    return env


ENVIRONMENT = make_environment()


def render_table(table: Table) -> str:
    """Return the contents of the C++ header defining TABLE."""
    return ENVIRONMENT.get_template("table.hpp.jinja").render(table=table)


def table_header_name(table: Table) -> str:
    """Return the file name of the C++ header defining TABLE."""
    return f"{table.name}.hpp"


def render_dataset(dataset: Dataset) -> str:
    """Return the contents of the C++ header defining DATASET."""
    return ENVIRONMENT.get_template("dataset.hpp.jinja").render(dataset=dataset)


def dataset_header_name(dataset: Dataset) -> str:
    """Return the file name of the C++ header defining DATASET."""
    return f"{dataset.name}.hpp"


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


def render_csv_writer(csv_writer: CsvWriter, table: Table) -> str:
    """
    Return the contents of the C++ header defining CSV_WRITER.

    TABLE is the table that CSV_WRITER writes out.
    """
    template = ENVIRONMENT.get_template("csv_writer.hpp.jinja")
    return template.render(csv_writer=csv_writer, table=table)


def csv_writer_header_name(csv_writer: CsvWriter) -> str:
    """Return the file name of the C++ header defining CSV_WRITER."""
    return f"{csv_writer.name}.hpp"


def render_parquet_writer(parquet_writer: ParquetWriter, table: Table) -> str:
    """
    Return the contents of the C++ header defining PARQUET_WRITER.

    TABLE is the table that PARQUET_WRITER writes out.
    """
    template = ENVIRONMENT.get_template("parquet_writer.hpp.jinja")
    return template.render(parquet_writer=parquet_writer, table=table)


def parquet_writer_header_name(parquet_writer: ParquetWriter) -> str:
    """Return the file name of the C++ header defining PARQUET_WRITER."""
    return f"{parquet_writer.name}.hpp"


def render_hdf5_reader(hdf5_reader: Hdf5Reader, dataset: Dataset) -> str:
    """
    Return the contents of the C++ header defining HDF5_READER.

    DATASET is the dataset that HDF5_READER fills in.
    """
    template = ENVIRONMENT.get_template("hdf5_reader.hpp.jinja")
    return template.render(hdf5_reader=hdf5_reader, dataset=dataset)


def hdf5_reader_header_name(hdf5_reader: Hdf5Reader) -> str:
    """Return the file name of the C++ header defining HDF5_READER."""
    return f"{hdf5_reader.name}.hpp"


def render_hdf5_writer(hdf5_writer: Hdf5Writer, dataset: Dataset) -> str:
    """
    Return the contents of the C++ header defining HDF5_WRITER.

    DATASET is the dataset that HDF5_WRITER writes out.
    """
    template = ENVIRONMENT.get_template("hdf5_writer.hpp.jinja")
    return template.render(hdf5_writer=hdf5_writer, dataset=dataset)


def hdf5_writer_header_name(hdf5_writer: Hdf5Writer) -> str:
    """Return the file name of the C++ header defining HDF5_WRITER."""
    return f"{hdf5_writer.name}.hpp"
