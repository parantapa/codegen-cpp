"""Generate a specification out of a data file."""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, NamedTuple

from .spec import MAP_KEY_TYPES, ScalarType, find_duplicates

# The Arrow types that a column of a table holds as they are,
# spelled the way pyarrow spells them.
# Everything else a CSV is read as, a date or a timestamp among them,
# is read as a string, which Arrow converts to on the way in.
ARROW_SCALAR_TYPES = {
    "int8": ScalarType.i8,
    "int16": ScalarType.i16,
    "int32": ScalarType.i32,
    "int64": ScalarType.i64,
    "uint8": ScalarType.u8,
    "uint16": ScalarType.u16,
    "uint32": ScalarType.u32,
    "uint64": ScalarType.u64,
    "float": ScalarType.f32,
    "double": ScalarType.f64,
    "bool": ScalarType.bool,
    "string": ScalarType.str,
    "large_string": ScalarType.str,
}

# The value a reader stores where a column of this type is null.
DEFAULT_VALUES = {
    ScalarType.i8: "0",
    ScalarType.i16: "0",
    ScalarType.i32: "0",
    ScalarType.i64: "0",
    ScalarType.u8: "0",
    ScalarType.u16: "0",
    ScalarType.u32: "0",
    ScalarType.u64: "0",
    ScalarType.f32: "0.0",
    ScalarType.f64: "0.0",
    ScalarType.bool: "false",
    ScalarType.str: '""',
}

# The suffixes stripped off a data file to name what is generated from it,
# so that 'measurements.csv.gz' is named after 'measurements'.
DATA_SUFFIXES = frozenset(
    {
        ".csv",
        ".tsv",
        ".txt",
        ".dat",
        ".parquet",
        ".pq",
        ".gz",
        ".zst",
        ".bz2",
        ".lz4",
    }
)

# The words that C++ keeps for itself,
# which a column of a data file is free to be named after.
CPP_KEYWORDS = frozenset("""
    alignas alignof and and_eq asm auto bitand bitor bool break case catch char
    char8_t char16_t char32_t class compl concept const consteval constexpr
    constinit const_cast continue co_await co_return co_yield decltype default
    delete do double dynamic_cast else enum explicit export extern false float
    for friend goto if inline int long mutable namespace new noexcept not not_eq
    nullptr operator or or_eq private protected public register reinterpret_cast
    requires return short signed sizeof static static_assert static_cast struct
    switch template this thread_local throw true try typedef typeid typename
    union unsigned using virtual void volatile wchar_t while xor xor_eq
    """.split())


class Column(NamedTuple):
    """One column of a data file, or one field of a group inside it."""

    # The name the table gives the column, always a C++ identifier,
    # and the name the file gives it, which may be anything at all.
    name: str
    name_in_file: str

    # A scalar type, or the name of an aggregate type declared beside it.
    type: ScalarType | str

    # What pyarrow read the column as,
    # which is noted where it is not the type the column ends up with.
    arrow_type: str


class Aggregate(NamedTuple):
    """One aggregate type that a nested column of a file needs."""

    # One of `vector`, `map` and `struct`.
    kind: str
    name: str

    # The type of an element of a vector.
    element: str = ""

    # The types of a key and of a value of a map.
    key: str = ""
    value: str = ""

    # The fields of a struct.
    fields: tuple[Column, ...] = ()


class Names(NamedTuple):
    """The names that the generated sections are declared under."""

    table: str
    reader: str
    writer: str


class Config(NamedTuple):
    """A specification drafted from a data file, ready to be written out."""

    data_file: Path

    # The kind of reader and writer that is generated, `csv` or `parquet`.
    section: str
    names: Names

    # Where the types came from, named in the banner of the specification.
    inferred_from: str

    columns: list[Column]

    # The aggregate types that the columns name, each declared before use.
    aggregates: list[Aggregate]

    # The flattened keys the reader renames, and the ones it defaults,
    # in the order the file holds the parts they name.
    name_in_file: list[tuple[str, str]]
    defaults: list[tuple[str, str]]

    # The columns of the file that no table can hold, with the reason.
    skipped: list[tuple[str, str]]


def reserve(name: str, taken: set[str]) -> str:
    """Return NAME, numbered apart from the names TAKEN already holds."""
    candidate = name
    suffix = 1
    while candidate in taken:
        suffix += 1
        candidate = f"{name}_{suffix}"

    taken.add(candidate)
    return candidate


def identifier(name: str, fallback: str) -> str:
    """
    Return NAME as a C++ identifier, or FALLBACK if nothing is left of it.

    Everything that may not appear in an identifier becomes an underscore,
    a run of underscores becomes one,
    and the underscores at either end are dropped,
    so that a name of punctuation alone falls back
    rather than becoming underscores alone.
    """
    cleaned = re.sub(r"[^0-9A-Za-z_]+", "_", name)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = fallback

    # An identifier does not begin with a digit, and is not a keyword.
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    if cleaned in CPP_KEYWORDS:
        cleaned = f"{cleaned}_"

    return cleaned


def unique(names: Iterable[str]) -> list[str]:
    """
    Return NAMES with the repeated ones numbered apart, in order.

    Two names of a file may become one identifier,
    which a table may not declare twice,
    so the second one and every one after it is numbered.
    """
    taken: set[str] = set()
    return [reserve(name, taken) for name in names]


def base_name(data_file: Path) -> str:
    """
    Return the name of DATA_FILE without the suffixes that say what it holds.

    Both the suffix of the format and the suffix of the codec are dropped,
    so that 'measurements.csv.gz' and 'measurements.csv'
    are named after the same thing.
    """
    stem = data_file
    while stem.suffix.lower() in DATA_SUFFIXES:
        stem = stem.with_suffix("")

    return stem.name


def type_name(base: str) -> str:
    """Return BASE as the name of a C++ type, one capital per word."""
    words = [word for word in re.split(r"[^0-9A-Za-z]+", base) if word]
    joined = "".join(word[0].upper() + word[1:] for word in words)

    return identifier(joined, "Data")


def config_names(data_file: Path, format: str) -> Names:
    """
    Return the names that the sections generated from DATA_FILE take.

    FORMAT is the reader and writer that is generated, spelled the way
    the name of a class is, so `Csv` or `Parquet`.
    """
    table = type_name(base_name(data_file))

    return Names(
        table=table,
        reader=f"{table}{format}Reader",
        writer=f"{table}{format}Writer",
    )


def config_file(data_file: Path) -> Path:
    """Return the specification DATA_FILE is written to unless asked otherwise."""
    return data_file.with_name(f"{base_name(data_file)}.toml")


def type_spelling(type: ScalarType | str) -> str:
    """Return TYPE the way a specification spells it."""
    return type.value if isinstance(type, ScalarType) else type


def check_names_in_file(data_file: Path, names: Iterable[str], where: str) -> None:
    """Throw unless NAMES, which a reader selects WHERE by, are all different."""
    repeated = find_duplicates(names)
    if repeated:
        raise ValueError(
            f"{data_file} names more than one {where} "
            f"{', '.join(repr(name) for name in repeated)}, "
            "which a reader that selects its columns by name cannot tell apart"
        )


def table_columns(
    data_file: Path, fields: list[Any], where: str = "column"
) -> list[Column]:
    """
    Return one column per field of FIELDS, named the way a table names one.

    The types are left as pyarrow read them,
    because a CSV holds nothing but scalars
    and a Parquet file needs the walk below to turn a group into a type.
    """
    check_names_in_file(data_file, (field.name for field in fields), where)

    names = unique(
        identifier(field.name, f"column_{index + 1}")
        for index, field in enumerate(fields)
    )

    return [
        Column(
            name=name,
            name_in_file=field.name,
            type=ARROW_SCALAR_TYPES.get(str(field.type), ScalarType.str),
            arrow_type=str(field.type),
        )
        for name, field in zip(names, fields)
    ]


def read_csv_columns(data_file: Path, read_all: bool = False) -> list[Column]:
    """
    Return one column per column of the CSV file DATA_FILE, in order.

    The names and the types are the ones pyarrow reads off the file,
    and the compression is guessed from the name of the file.

    The types are inferred from the first block of the file,
    which is the whole of a small one and the beginning of a large one,
    so a column that changes character further down is typed by its head.
    READ_ALL infers them from every row instead,
    which types such a column by all of it
    at the cost of holding the whole file in memory.
    """
    # pyarrow is only needed to read a data file,
    # so it is imported here rather than by every other command.
    import pyarrow.csv

    if read_all:
        fields = list(pyarrow.csv.read_csv(data_file).schema)
    else:
        fields = list(pyarrow.csv.open_csv(data_file).schema)

    return table_columns(data_file, fields)


class Unsupported(Exception):
    """Raised where a file holds something no column of a table can hold."""


class Walk(NamedTuple):
    """What building the types of a nested file collects along the way."""

    # The names already declared, which every generated name steps around.
    taken: set[str]

    aggregates: list[Aggregate]
    name_in_file: list[tuple[str, str]]
    defaults: list[tuple[str, str]]


def new_walk(taken: set[str]) -> Walk:
    """Return an empty walk that steps around the names TAKEN holds."""
    return Walk(taken=set(taken), aggregates=[], name_in_file=[], defaults=[])


def merge_walk(walk: Walk, scratch: Walk) -> None:
    """Fold everything SCRATCH collected into WALK."""
    walk.taken.update(scratch.taken)
    walk.aggregates.extend(scratch.aggregates)
    walk.name_in_file.extend(scratch.name_in_file)
    walk.defaults.extend(scratch.defaults)


def scalar_of(arrow_type: Any) -> ScalarType:
    """Return the scalar type ARROW_TYPE is held as, or throw."""
    scalar = ARROW_SCALAR_TYPES.get(str(arrow_type))
    if scalar is None:
        raise Unsupported(str(arrow_type))

    return scalar


def build_type(arrow_type: Any, key: str, walk: Walk) -> ScalarType | str:
    """
    Return what the part of a table that KEY names holds.

    A group of the file becomes an aggregate type named after the key,
    declared below the types it is built out of,
    and a scalar becomes itself and takes a default.
    Anything else throws, because a table has no way to hold it.
    """
    import pyarrow as pa

    if pa.types.is_list(arrow_type) or pa.types.is_large_list(arrow_type):
        name = reserve(type_name(key), walk.taken)
        element = build_type(arrow_type.value_type, f"{key}.element", walk)
        walk.aggregates.append(
            Aggregate(kind="vector", name=name, element=type_spelling(element))
        )
        return name

    if pa.types.is_map(arrow_type):
        name = reserve(type_name(key), walk.taken)
        map_key = scalar_of(arrow_type.key_type)
        if map_key not in MAP_KEY_TYPES:
            raise Unsupported(f"a map keyed by {arrow_type.key_type}")

        value = build_type(arrow_type.item_type, f"{key}.value", walk)
        walk.aggregates.append(
            Aggregate(
                kind="map",
                name=name,
                key=map_key.value,
                value=type_spelling(value),
            )
        )
        return name

    if pa.types.is_struct(arrow_type):
        if arrow_type.num_fields == 0:
            raise Unsupported("a group of no fields")

        name = reserve(type_name(key), walk.taken)
        members: set[str] = set()
        fields: list[Column] = []
        for index in range(arrow_type.num_fields):
            field = arrow_type.field(index)
            member = reserve(identifier(field.name, f"field_{index + 1}"), members)
            below = f"{key}.{member}"

            fields.append(
                Column(
                    name=member,
                    name_in_file=field.name,
                    type=build_type(field.type, below, walk),
                    arrow_type=str(field.type),
                )
            )
            # A field of a group is named by the file, so it may be renamed.
            if member != field.name:
                walk.name_in_file.append((below, field.name))

        walk.aggregates.append(
            Aggregate(kind="struct", name=name, fields=tuple(fields))
        )
        return name

    scalar = scalar_of(arrow_type)

    # Only a key that ends at a scalar takes a default;
    # a null aggregate is read as the empty value of its own type.
    walk.defaults.append((key, DEFAULT_VALUES[scalar]))
    return scalar


def read_parquet_schema(data_file: Path) -> list[Any]:
    """
    Return the fields of the Parquet file DATA_FILE, in order.

    A Parquet file carries its schema in its footer,
    so nothing is inferred and nothing but the footer is read.
    """
    import pyarrow.parquet

    return list(pyarrow.parquet.read_schema(data_file))


def parquet_config(data_file: Path) -> Config:
    """
    Return the specification that describes the Parquet file DATA_FILE.

    A column of a group becomes an aggregate type of its own,
    named after the flattened key that reaches it,
    and a column the file stores as something no table can hold is left out
    rather than declared as something it is not,
    because a Parquet reader matches the type of what it reads exactly.
    """
    fields = read_parquet_schema(data_file)
    check_names_in_file(data_file, (field.name for field in fields), "column")

    names = config_names(data_file, "Parquet")
    walk = new_walk({names.table, names.reader, names.writer})

    members: set[str] = set()
    columns: list[Column] = []
    skipped: list[tuple[str, str]] = []

    for index, field in enumerate(fields):
        member = reserve(identifier(field.name, f"column_{index + 1}"), members)

        # A column is built on its own, so one the table cannot hold
        # takes nothing with it when it is left out.
        scratch = new_walk(walk.taken)
        try:
            type = build_type(field.type, member, scratch)
        except Unsupported as e:
            members.discard(member)
            skipped.append((field.name, str(e)))
            continue

        merge_walk(walk, scratch)
        columns.append(
            Column(
                name=member,
                name_in_file=field.name,
                type=type,
                arrow_type=str(field.type),
            )
        )
        if member != field.name:
            walk.name_in_file.append((member, field.name))

    if not columns:
        raise ValueError(f"{data_file} holds no column that a table can hold")

    return Config(
        data_file=data_file,
        section="parquet",
        names=names,
        inferred_from="the schema the file carries",
        columns=columns,
        aggregates=walk.aggregates,
        name_in_file=walk.name_in_file,
        defaults=walk.defaults,
        skipped=skipped,
    )


def csv_columns_config(data_file: Path, read_all: bool = False) -> Config:
    """
    Return the specification that describes the CSV file DATA_FILE.

    READ_ALL infers the column types from every row of the file
    rather than from its first block.
    """
    columns = read_csv_columns(data_file, read_all)
    if not columns:
        raise ValueError(f"{data_file} has no columns")

    return Config(
        data_file=data_file,
        section="csv",
        names=config_names(data_file, "Csv"),
        inferred_from=(
            "all of the file" if read_all else "the first block of the file"
        ),
        columns=columns,
        aggregates=[],
        name_in_file=[
            (column.name, column.name_in_file)
            for column in columns
            if column.name != column.name_in_file
        ],
        defaults=[
            (column.name, DEFAULT_VALUES[column.type])
            for column in columns
            if isinstance(column.type, ScalarType)
        ],
        skipped=[],
    )


# The characters that need to be escaped in a TOML basic string.
TOML_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


def toml_string(value: str) -> str:
    """Return VALUE as a TOML basic string, quotes and all."""
    escaped = "".join(
        TOML_ESCAPES.get(c, c if c >= " " and c != "\x7f" else f"\\u{ord(c):04X}")
        for c in value
    )

    return f'"{escaped}"'


def toml_key(name: str) -> str:
    """Return NAME as a TOML key, quoted only where it has to be."""
    if re.fullmatch(r"[0-9A-Za-z_-]+", name):
        return name

    return toml_string(name)


def render_member(column: Column, note_type: bool) -> str:
    """
    Return COLUMN as one entry of a list of columns or of fields.

    NOTE_TYPE says whether to note what the file stores the part as,
    which is worth saying only where the part settled for something else:
    a group that becomes an aggregate type is held exactly,
    and says nothing.
    """
    line = (
        f"    {{ name = {toml_string(column.name)}, "
        f"type = {toml_string(type_spelling(column.type))} }},"
    )
    settled = (
        isinstance(column.type, ScalarType)
        and column.arrow_type not in ARROW_SCALAR_TYPES
    )
    if note_type and settled:
        line += f"  # read as '{column.arrow_type}'"

    return line


def render_aggregate(aggregate: Aggregate) -> list[str]:
    """Return the section that declares AGGREGATE."""
    lines = [
        "",
        f"[[{aggregate.kind}]]",
        f"name = {toml_string(aggregate.name)}",
    ]

    if aggregate.kind == "vector":
        lines.append(f"element = {toml_string(aggregate.element)}")
    elif aggregate.kind == "map":
        lines.append(f"key = {toml_string(aggregate.key)}")
        lines.append(f"value = {toml_string(aggregate.value)}")
    else:
        lines.append("fields = [")
        lines += [render_member(field, False) for field in aggregate.fields]
        lines.append("]")

    return lines


def render_name_in_file(
    section: str, comment: list[str], name_in_file: list[tuple[str, str]]
) -> list[str]:
    """
    Return the section of SECTION that renames the parts NAME_IN_FILE holds.

    COMMENT heads it, and nothing is written at all
    where the file names every part the way the table does.
    """
    if not name_in_file:
        return []

    return [
        "",
        *comment,
        f"[{section}.name_in_file]",
        *(f"{toml_key(key)} = {toml_string(name)}" for key, name in name_in_file),
    ]


def render_config(config: Config) -> str:
    """
    Return CONFIG as the text of a specification.

    It declares the aggregate types the columns need,
    the table that the file is read into,
    a reader that reads it, and a writer that writes it back out.
    """
    lines = [
        f"# Generated by codegen-cpp from '{config.data_file.name}'.",
        f"# The types are the ones pyarrow read off {config.inferred_from};",
        "# check them, and the defaults below, before generating a header.",
    ]

    if config.skipped:
        lines += [
            "#",
            "# These columns of the file are left out,",
            "# because no column of a table holds what they are stored as:",
        ]
        lines += [f"#     {name}: {reason}" for name, reason in config.skipped]

    for aggregate in config.aggregates:
        lines += render_aggregate(aggregate)

    lines += [
        "",
        "[[table]]",
        f"name = {toml_string(config.names.table)}",
        "columns = [",
    ]
    lines += [render_member(column, True) for column in config.columns]
    lines += [
        "]",
        "",
        f"[[{config.section}_reader]]",
        f"name = {toml_string(config.names.reader)}",
        f"table = {toml_string(config.names.table)}",
    ]

    lines += render_name_in_file(
        f"{config.section}_reader",
        [
            "# The name the file gives a part of the table,",
            "# where that is not the name the table uses.",
        ],
        config.name_in_file,
    )

    lines += [
        "",
        "# The value stored where the file holds a null.",
        "# Drop a key from this list to make it an error for it to be null.",
        f"[{config.section}_reader.default]",
    ]
    lines += [f"{toml_key(key)} = {value}" for key, value in config.defaults]

    lines += [
        "",
        f"[[{config.section}_writer]]",
        f"name = {toml_string(config.names.writer)}",
        f"table = {toml_string(config.names.table)}",
    ]

    lines += render_name_in_file(
        f"{config.section}_writer",
        [
            "# The writer gives each part the name the reader looks for,",
            "# so a table read out of one file is written back into its like.",
            "# Drop this section to write the names that the table uses.",
        ],
        config.name_in_file,
    )

    lines.append("")

    return "\n".join(lines)


def csv_config(data_file: Path, read_all: bool = False) -> str:
    """
    Return the specification that describes the CSV file DATA_FILE.

    READ_ALL infers the column types from every row of the file
    rather than from its first block.
    """
    return render_config(csv_columns_config(data_file, read_all))
