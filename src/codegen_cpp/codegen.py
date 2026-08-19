"""Generate the cpp code."""

from jinja2 import Environment, PackageLoader, StrictUndefined

from .spec import ScalarType, Table

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


def cpp_type(type: ScalarType) -> str:
    """Return the C++ type used to represent TYPE."""
    return CPP_TYPES[type]


def make_environment() -> Environment:
    """Return the Jinja environment used to render the templates."""
    env = Environment(
        loader=PackageLoader("codegen_cpp", "templates"),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    env.filters["cpp_type"] = cpp_type
    return env


ENVIRONMENT = make_environment()


def render_table(table: Table) -> str:
    """Return the contents of the C++ header defining TABLE."""
    return ENVIRONMENT.get_template("table.hpp.jinja").render(table=table)


def table_header_name(table: Table) -> str:
    """Return the file name of the C++ header defining TABLE."""
    return f"{table.name}.hpp"
