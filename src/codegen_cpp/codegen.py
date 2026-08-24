"""Generate the cpp code."""

from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

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
    Spec,
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


class Includes(NamedTuple):
    """
    The headers that a generated construct needs.

    The two groups are listed apart in the generated file,
    the standard library first
    and the libraries that the generated code binds to after it.
    """

    std: frozenset[str]
    external: frozenset[str] = frozenset()


def merge_includes(includes: Iterable[Includes]) -> Includes:
    """Return the union of INCLUDES, group by group."""
    std: set[str] = set()
    external: set[str] = set()
    for group in includes:
        std |= group.std
        external |= group.external
    return Includes(std=frozenset(std), external=frozenset(external))


def format_includes(includes: Includes) -> str:
    """Return INCLUDES as the '#include' lines heading a header."""
    groups = [sorted(includes.std), sorted(includes.external)]
    return "\n\n".join(
        "\n".join(f"#include <{header}>" for header in group)
        for group in groups
        if group
    )


TABLE_INCLUDES = Includes(std=frozenset({"cstddef", "cstdint", "string", "vector"}))

DATASET_INCLUDES = Includes(
    std=frozenset({"cstddef", "cstdint", "memory", "stdexcept", "vector"}),
    external=frozenset({"experimental/mdspan"}),
)

CSV_READER_INCLUDES = Includes(
    std=frozenset(
        {
            "algorithm",
            "cstddef",
            "cstdint",
            "memory",
            "optional",
            "stdexcept",
            "string",
            "utility",
            "vector",
        }
    ),
    external=frozenset(
        {
            "arrow/api.h",
            "arrow/csv/api.h",
            "arrow/io/api.h",
            "arrow/io/compressed.h",
            "arrow/util/compression.h",
        }
    ),
)

PARQUET_READER_INCLUDES = Includes(
    std=frozenset(
        {
            "algorithm",
            "cstddef",
            "cstdint",
            "memory",
            "numeric",
            "stdexcept",
            "string",
            "utility",
            "vector",
        }
    ),
    external=frozenset(
        {
            "arrow/api.h",
            "arrow/io/api.h",
            "parquet/arrow/reader.h",
            "parquet/properties.h",
        }
    ),
)

CSV_WRITER_INCLUDES = Includes(
    std=frozenset(
        {
            "cstddef",
            "cstdint",
            "memory",
            "optional",
            "stdexcept",
            "string",
            "utility",
            "vector",
        }
    ),
    external=frozenset(
        {
            "arrow/api.h",
            "arrow/csv/api.h",
            "arrow/io/api.h",
            "arrow/io/compressed.h",
            "arrow/ipc/writer.h",
            "arrow/util/compression.h",
        }
    ),
)

PARQUET_WRITER_INCLUDES = Includes(
    std=frozenset(
        {
            "cstddef",
            "cstdint",
            "memory",
            "stdexcept",
            "string",
            "utility",
            "vector",
        }
    ),
    external=frozenset(
        {
            "arrow/api.h",
            "arrow/io/api.h",
            "arrow/util/compression.h",
            "parquet/arrow/writer.h",
        }
    ),
)


def hdf5_includes(dataset: Dataset) -> Includes:
    """Return the headers that an HDF5 reader or writer of DATASET needs."""
    std = {"array", "cstddef", "stdexcept", "string"}

    # A column major dataset of rank two or more is transposed as it is
    # read or written, which needs a buffer and the index arithmetic over it.
    if dataset.column_major and dataset.ndim > 1:
        std |= {"cstdint", "vector"}

    return Includes(std=frozenset(std), external=frozenset({"H5Cpp.h"}))


def render_table(table: Table) -> str:
    """Return the C++ definition of TABLE."""
    return ENVIRONMENT.get_template("table.hpp.jinja").render(table=table)


def render_dataset(dataset: Dataset) -> str:
    """Return the C++ definition of DATASET."""
    return ENVIRONMENT.get_template("dataset.hpp.jinja").render(dataset=dataset)


def render_csv_reader(csv_reader: CsvReader, table: Table) -> str:
    """
    Return the C++ definition of CSV_READER.

    TABLE is the table that CSV_READER fills in.
    """
    template = ENVIRONMENT.get_template("csv_reader.hpp.jinja")
    return template.render(csv_reader=csv_reader, table=table)


def render_parquet_reader(parquet_reader: ParquetReader, table: Table) -> str:
    """
    Return the C++ definition of PARQUET_READER.

    TABLE is the table that PARQUET_READER fills in.
    """
    template = ENVIRONMENT.get_template("parquet_reader.hpp.jinja")
    return template.render(parquet_reader=parquet_reader, table=table)


def render_csv_writer(csv_writer: CsvWriter, table: Table) -> str:
    """
    Return the C++ definition of CSV_WRITER.

    TABLE is the table that CSV_WRITER writes out.
    """
    template = ENVIRONMENT.get_template("csv_writer.hpp.jinja")
    return template.render(csv_writer=csv_writer, table=table)


def render_parquet_writer(parquet_writer: ParquetWriter, table: Table) -> str:
    """
    Return the C++ definition of PARQUET_WRITER.

    TABLE is the table that PARQUET_WRITER writes out.
    """
    template = ENVIRONMENT.get_template("parquet_writer.hpp.jinja")
    return template.render(parquet_writer=parquet_writer, table=table)


def render_hdf5_reader(hdf5_reader: Hdf5Reader, dataset: Dataset) -> str:
    """
    Return the C++ definition of HDF5_READER.

    DATASET is the dataset that HDF5_READER fills in.
    """
    template = ENVIRONMENT.get_template("hdf5_reader.hpp.jinja")
    return template.render(hdf5_reader=hdf5_reader, dataset=dataset)


def render_hdf5_writer(hdf5_writer: Hdf5Writer, dataset: Dataset) -> str:
    """
    Return the C++ definition of HDF5_WRITER.

    DATASET is the dataset that HDF5_WRITER writes out.
    """
    template = ENVIRONMENT.get_template("hdf5_writer.hpp.jinja")
    return template.render(hdf5_writer=hdf5_writer, dataset=dataset)


def spec_parts(spec: Spec) -> tuple[Includes, list[str]]:
    """
    Return the headers that SPEC needs and the C++ definitions it declares.

    The definitions come out in an order in which each one is declared
    after everything it names,
    so tables and datasets lead and the classes over them follow.
    """
    tables = {table.name: table for table in spec.tables}
    datasets = {dataset.name: dataset for dataset in spec.datasets}

    includes: list[Includes] = []
    definitions: list[str] = []

    for table in spec.tables:
        includes.append(TABLE_INCLUDES)
        definitions.append(render_table(table))

    for dataset in spec.datasets:
        includes.append(DATASET_INCLUDES)
        definitions.append(render_dataset(dataset))

    for csv_reader in spec.csv_readers:
        includes.append(CSV_READER_INCLUDES)
        definitions.append(render_csv_reader(csv_reader, tables[csv_reader.table]))

    for parquet_reader in spec.parquet_readers:
        includes.append(PARQUET_READER_INCLUDES)
        definitions.append(
            render_parquet_reader(parquet_reader, tables[parquet_reader.table])
        )

    for csv_writer in spec.csv_writers:
        includes.append(CSV_WRITER_INCLUDES)
        definitions.append(render_csv_writer(csv_writer, tables[csv_writer.table]))

    for parquet_writer in spec.parquet_writers:
        includes.append(PARQUET_WRITER_INCLUDES)
        definitions.append(
            render_parquet_writer(parquet_writer, tables[parquet_writer.table])
        )

    for hdf5_reader in spec.hdf5_readers:
        dataset = datasets[hdf5_reader.dataset]
        includes.append(hdf5_includes(dataset))
        definitions.append(render_hdf5_reader(hdf5_reader, dataset))

    for hdf5_writer in spec.hdf5_writers:
        dataset = datasets[hdf5_writer.dataset]
        includes.append(hdf5_includes(dataset))
        definitions.append(render_hdf5_writer(hdf5_writer, dataset))

    return merge_includes(includes), definitions


def render_spec(spec: Spec, spec_file: Path) -> str:
    """
    Return the contents of the single C++ header holding all of SPEC.

    SPEC_FILE is the specification that SPEC was parsed from;
    it is named in the banner of the generated header.
    """
    includes, definitions = spec_parts(spec)

    sections = [
        "#pragma once",
        f"// Generated by codegen-cpp from '{spec_file.name}'.\n"
        "// Do not edit this file by hand.",
    ]
    if includes.std or includes.external:
        sections.append(format_includes(includes))
    sections += [definition.strip("\n") for definition in definitions]

    return "\n\n".join(sections) + "\n"


def header_file(spec_file: Path) -> Path:
    """Return the header that SPEC_FILE is generated into unless asked otherwise."""
    return spec_file.with_suffix(".hpp")
