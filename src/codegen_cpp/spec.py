"""Specification models."""

import tomllib
from collections.abc import Iterable
from enum import Enum
from math import isfinite
from pathlib import Path
from typing import Annotated, Any, ClassVar, NamedTuple

from pydantic import BaseModel, BeforeValidator, model_validator


class ScalarType(Enum):
    i8 = "i8"
    i16 = "i16"
    i32 = "i32"
    i64 = "i64"
    u8 = "u8"
    u16 = "u16"
    u32 = "u32"
    u64 = "u64"
    f32 = "f32"
    f64 = "f64"
    bool = "bool"
    str = "str"


INTEGER_BITS = {
    ScalarType.i8: 8,
    ScalarType.i16: 16,
    ScalarType.i32: 32,
    ScalarType.i64: 64,
    ScalarType.u8: 8,
    ScalarType.u16: 16,
    ScalarType.u32: 32,
    ScalarType.u64: 64,
}

SIGNED_TYPES = {ScalarType.i8, ScalarType.i16, ScalarType.i32, ScalarType.i64}

FLOAT_TYPES = {ScalarType.f32, ScalarType.f64}

INTEGER_TYPES = set(INTEGER_BITS)

NUMERIC_TYPES = INTEGER_TYPES | FLOAT_TYPES

MAP_KEY_TYPES = INTEGER_TYPES | {ScalarType.str}


def find_duplicates(names: Iterable[str]) -> list[str]:
    """Return the names that occur more than once, in order of first repeat."""
    seen: set[str] = set()
    duplicates: dict[str, None] = {}
    for name in names:
        if name in seen:
            duplicates[name] = None
        seen.add(name)
    return list(duplicates)


DefaultValue = bool | int | float | str


def check_default_value(type: ScalarType, value: DefaultValue) -> str | None:
    """
    Return the reason why VALUE cannot be stored in TYPE, or None.

    Note that `bool` is a subclass of `int` in Python,
    so booleans are checked before integers.
    """
    if type is ScalarType.bool:
        if not isinstance(value, bool):
            return "expects a boolean"
        return None

    if type is ScalarType.str:
        if not isinstance(value, str):
            return "expects a string"
        return None

    if type in FLOAT_TYPES:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "expects a number"
        if not isfinite(value):
            return "expects a finite number"
        return None

    if isinstance(value, bool) or not isinstance(value, int):
        return "expects an integer"

    bits = INTEGER_BITS[type]
    if type in SIGNED_TYPES:
        low, high = -(2 ** (bits - 1)), 2 ** (bits - 1) - 1
    else:
        low, high = 0, 2**bits - 1
    if not low <= value <= high:
        return f"expects an integer between {low} and {high}"
    return None


def parse_type_ref(value: Any) -> Any:
    """
    Turn the name of a scalar type into its ScalarType, and leave the rest.
    """
    if isinstance(value, str):
        try:
            return ScalarType(value)
        except ValueError:
            return value
    return value


TypeRef = Annotated[ScalarType | str, BeforeValidator(parse_type_ref)]


class Member(BaseModel):
    """
    The name and the type of one part of a table.

    A member says what a value is called in C++ and what shape it has,
    and nothing about the file it is read from:
    the name a reader looks for, and the value it stores for a null,
    are declared by the reader itself.
    """

    name: str
    type: TypeRef


class Column(Member):
    """One column of a table."""


class StructField(Member):
    """One field of a struct."""


class Vector(BaseModel):
    """
    A variable number of elements of one type.
    """

    KIND: ClassVar[str] = "vector"

    name: str
    element: TypeRef


class Map(BaseModel):
    """
    A variable number of keys of one type, each holding one value.
    """

    KIND: ClassVar[str] = "map"

    name: str
    key: ScalarType
    value: TypeRef

    # The pairs are held in a `std::map`, in the order of their keys,
    # unless is_unordered asks for a `std::unordered_map` instead.
    is_unordered: bool = False

    @model_validator(mode="after")
    def check_key(self) -> "Map":
        if self.key not in MAP_KEY_TYPES:
            allowed = ", ".join(
                scalar.value for scalar in ScalarType if scalar in MAP_KEY_TYPES
            )
            raise ValueError(
                f"map '{self.name}' has key type '{self.key.value}', "
                f"but a key is one of: {allowed}"
            )
        return self


class Struct(BaseModel):
    """
    A fixed set of named fields, each with its own type.
    """

    KIND: ClassVar[str] = "struct"

    name: str
    fields: list[StructField]

    @model_validator(mode="after")
    def check_fields(self) -> "Struct":
        if not self.fields:
            raise ValueError(f"struct '{self.name}' has no fields")

        duplicates = find_duplicates(field.name for field in self.fields)
        if duplicates:
            raise ValueError(
                f"struct '{self.name}' has duplicate fields: "
                f"{', '.join(duplicates)}"
            )
        return self


Aggregate = Vector | Map | Struct


def referenced_types(aggregate: Aggregate) -> list[str]:
    """Return the aggregate types that AGGREGATE names, in declaration order."""
    if isinstance(aggregate, Vector):
        types: list[ScalarType | str] = [aggregate.element]
    elif isinstance(aggregate, Map):
        types = [aggregate.value]
    else:
        types = [field.type for field in aggregate.fields]

    return [type for type in types if not isinstance(type, ScalarType)]


def find_type_cycles(aggregates: dict[str, Aggregate]) -> list[list[str]]:
    """
    Return one cycle per group of aggregate types that contain one another.
    """
    done: set[str] = set()
    cycles: dict[tuple[str, ...], list[str]] = {}

    def visit(name: str, path: list[str]) -> None:
        if name in path:
            start = path.index(name)
            cycle = path[start:]
            cycles.setdefault(tuple(sorted(cycle)), cycle)
            return
        if name in done:
            return

        path.append(name)
        for referenced in referenced_types(aggregates[name]):
            if referenced in aggregates:
                visit(referenced, path)
        path.pop()
        done.add(name)

    for name in aggregates:
        visit(name, [])

    return list(cycles.values())


def sorted_aggregates(aggregates: dict[str, Aggregate]) -> list[Aggregate]:
    """
    Return the aggregate types in an order that declares each of them
    before the types that name it.

    The declared types have to be acyclic, or this does not terminate;
    `find_type_cycles` reports the ones that are not.
    """
    ordered: dict[str, Aggregate] = {}

    def visit(name: str) -> None:
        if name in ordered:
            return

        for referenced in referenced_types(aggregates[name]):
            if referenced in aggregates:
                visit(referenced)
        ordered[name] = aggregates[name]

    for name in aggregates:
        visit(name)

    return list(ordered.values())


# The steps a key takes through the levels Parquet does not name after a field.
# They are the names Parquet gives those levels itself,
# in the `element` child of a LIST and the `value` child of a MAP.
VECTOR_STEP = "element"
MAP_STEP = "value"


class FlatKey(NamedTuple):
    """One key of the flattened form of a table, and what it names."""

    type: ScalarType | str

    # Whether the last step of the key names a column or a field of a struct,
    # which is what a file names in turn,
    # and so what `name_in_file` of a reader may replace.
    # The element of a vector and the value of a map are matched by position,
    # so neither is named by the file or by the specification.
    is_named: bool


def flatten_table(
    table: "Table", aggregates: dict[str, Aggregate]
) -> dict[str, FlatKey]:
    """
    Return every key of TABLE in its flattened form, in declaration order.

    A key is the name of a column
    followed by one step per level below it:
    the name of a field of a struct,
    `element` for the element of a vector,
    and `value` for the value of a map.
    The key of a map is never a step of its own,
    because a key of a Parquet MAP is never null
    and is never matched against the specification.

    A type that is not declared stops the walk where it stands,
    and the caller reports it.
    The declared types have to be acyclic, or this does not terminate.
    """
    keys: dict[str, FlatKey] = {}

    def walk(key: str, type: ScalarType | str, is_named: bool) -> None:
        keys[key] = FlatKey(type=type, is_named=is_named)
        if isinstance(type, ScalarType):
            return

        aggregate = aggregates.get(type)
        if aggregate is None:
            return

        if isinstance(aggregate, Vector):
            walk(f"{key}.{VECTOR_STEP}", aggregate.element, False)
        elif isinstance(aggregate, Map):
            walk(f"{key}.{MAP_STEP}", aggregate.value, False)
        else:
            for field in aggregate.fields:
                walk(f"{key}.{field.name}", field.type, True)

    for column in table.columns:
        walk(column.name, column.type, True)

    return keys


class Table(BaseModel):
    name: str
    columns: list[Column]

    @model_validator(mode="after")
    def check_columns(self) -> "Table":
        if not self.columns:
            raise ValueError(f"table '{self.name}' has no columns")

        duplicates = find_duplicates(column.name for column in self.columns)
        if duplicates:
            raise ValueError(
                f"table '{self.name}' has duplicate columns: "
                f"{', '.join(duplicates)}"
            )
        return self


class NdArray(BaseModel):
    name: str
    type: ScalarType

    @model_validator(mode="after")
    def check_type(self) -> "NdArray":
        if self.type not in NUMERIC_TYPES:
            allowed = ", ".join(
                scalar.value for scalar in ScalarType if scalar in NUMERIC_TYPES
            )
            raise ValueError(
                f"array '{self.name}' has type '{self.type.value}', "
                f"but an array holds one of: {allowed}"
            )
        return self


class Dataset(BaseModel):
    name: str
    dims: list[str]
    arrays: list[NdArray]

    # The arrays are stored in row major order,
    # in which the last dim varies fastest,
    # unless column_major asks for the first dim to vary fastest instead.
    column_major: bool = False

    @property
    def ndim(self) -> int:
        """Return the rank shared by the arrays of the dataset."""
        return len(self.dims)

    @model_validator(mode="after")
    def check_dims(self) -> "Dataset":
        if not self.dims:
            raise ValueError(f"dataset '{self.name}' has no dims")

        duplicates = find_duplicates(self.dims)
        if duplicates:
            raise ValueError(
                f"dataset '{self.name}' has duplicate dims: {', '.join(duplicates)}"
            )
        return self

    @model_validator(mode="after")
    def check_arrays(self) -> "Dataset":
        if not self.arrays:
            raise ValueError(f"dataset '{self.name}' has no arrays")

        duplicates = find_duplicates(array.name for array in self.arrays)
        if duplicates:
            raise ValueError(
                f"dataset '{self.name}' has duplicate arrays: "
                f"{', '.join(duplicates)}"
            )
        return self


class TableClass(BaseModel):
    """The fields shared by every C++ class generated for a table."""

    KIND: ClassVar[str] = "table class"

    name: str
    table: str

    # Keyed by the flattened keys of the table that is read or written.
    # A CSV file holds one column and no level below it,
    # so a CSV reader or writer keys them by the names of the columns;
    # a Parquet reader or writer reaches a field of a struct at any depth,
    # the element of a vector and the value of a map alike.
    #
    # `name_in_file` is the name the file gives the part,
    # which a reader looks for and a writer writes,
    # where that is not the name the specification uses.
    name_in_file: dict[str, str] = {}


class Reader(TableClass):
    """The fields shared by every reader that fills in a table."""

    KIND: ClassVar[str] = "reader"

    # Keyed by the flattened keys of the table that is read,
    # the way `name_in_file` is.
    # `default` is what the reader stores where the file holds a null,
    # and a null that no default answers for is an error.
    default: dict[str, DefaultValue] = {}

    @model_validator(mode="before")
    @classmethod
    def check_default_values(cls, data: Any) -> Any:
        """
        Reject default_values, which default replaced.

        The two said the same thing, and a specification that still says it
        the old way is told so rather than read as one that says nothing.
        """
        if isinstance(data, dict) and "default_values" in data:
            name = data.get("name")
            where = f" '{name}'" if isinstance(name, str) and name else ""
            raise ValueError(
                f"{cls.KIND}{where} declares default_values, "
                "which is no longer read; declare default instead"
            )
        return data


class CsvReader(Reader):
    KIND: ClassVar[str] = "csv_reader"


class ParquetReader(Reader):
    KIND: ClassVar[str] = "parquet_reader"


class Writer(TableClass):
    """The fields shared by every writer that writes out a table."""

    KIND: ClassVar[str] = "writer"


class CsvWriter(Writer):
    KIND: ClassVar[str] = "csv_writer"


class ParquetWriter(Writer):
    KIND: ClassVar[str] = "parquet_writer"


def table_class_keys(
    generated: TableClass, table: Table, aggregates: dict[str, Aggregate]
) -> dict[str, FlatKey]:
    """
    Return the keys of TABLE that GENERATED may name,
    and what each of them names.

    A CSV file holds nothing but the columns of a table,
    so a CSV reader or writer names those and nothing below them,
    and a Parquet reader or writer names every key of the flattened table.
    """
    if isinstance(generated, (CsvReader, CsvWriter)):
        return {
            column.name: FlatKey(type=column.type, is_named=True)
            for column in table.columns
        }

    return flatten_table(table, aggregates)


class DatasetClass(BaseModel):
    """The fields shared by every C++ function generated for a dataset."""

    KIND: ClassVar[str] = "dataset class"

    name: str
    dataset: str


class Compression(Enum):
    """The filter that an HDF5 writer compresses its arrays with."""

    none = "none"
    deflate = "deflate"
    zstd = "zstd"
    lz4 = "lz4"
    bzip2 = "bzip2"
    lzf = "lzf"


# The range of the levels that a filter takes,
# for the filters that take one at all.
# A filter that is not named here is asked for without a level,
# and compresses the way the plugin holding it was built to.
COMPRESSION_LEVELS = {
    Compression.deflate: (0, 9),
    Compression.zstd: (1, 22),
    Compression.bzip2: (1, 9),
}


class Hdf5Class(DatasetClass):
    """The fields shared by every function over the arrays of an HDF5 group."""

    KIND: ClassVar[str] = "hdf5 class"

    # At most one of these may be given.
    # `include` names the arrays that are used,
    # and `exclude` names the arrays that are not;
    # without either one every array of the dataset is used.
    include: list[str] | None = None
    exclude: list[str] | None = None

    @model_validator(mode="after")
    def check_include_and_exclude(self) -> "Hdf5Class":
        if self.include is not None and self.exclude is not None:
            raise ValueError(
                f"{self.KIND} '{self.name}' lists both include and exclude"
            )

        for kind, names in (("include", self.include), ("exclude", self.exclude)):
            if names is None:
                continue
            if not names:
                raise ValueError(f"{self.KIND} '{self.name}' has an empty {kind} list")
            duplicates = find_duplicates(names)
            if duplicates:
                raise ValueError(
                    f"{self.KIND} '{self.name}' has duplicate {kind} arrays: "
                    f"{', '.join(duplicates)}"
                )
        return self


class Hdf5Reader(Hdf5Class):
    """A function reading the arrays of a dataset out of an HDF5 group."""

    KIND: ClassVar[str] = "hdf5_reader"


class Hdf5Writer(Hdf5Class):
    """A function writing the arrays of a dataset into an HDF5 group."""

    KIND: ClassVar[str] = "hdf5_writer"

    # How the arrays are laid out in the file.
    # `chunk` is the shape of one chunk, one extent per dim of the dataset,
    # and every extent of it is at least one.
    # An extent that reaches past the array it is stored along
    # is cut down to the array when the file is written,
    # so one chunk fits a dataset of any size.
    #
    # `compression` names the filter the chunks are compressed with,
    # `compression_level` tunes it where the filter takes a level,
    # and `shuffle` puts the shuffle filter before the compressor,
    # which usually pays for itself on an array of numbers.
    # A filter only applies to an array stored in chunks,
    # so any of the three asks for `chunk` as well.
    chunk: list[int] | None = None
    compression: Compression = Compression.none
    compression_level: int | None = None
    shuffle: bool = False

    @model_validator(mode="after")
    def check_chunk(self) -> "Hdf5Writer":
        if self.chunk is not None:
            if not self.chunk:
                raise ValueError(f"{self.KIND} '{self.name}' has an empty chunk")

            if any(extent < 1 for extent in self.chunk):
                raise ValueError(
                    f"{self.KIND} '{self.name}' has a chunk extent below one"
                )
            return self

        asked: list[str] = []
        if self.compression is not Compression.none:
            asked.append(f"compression '{self.compression.value}'")
        if self.shuffle:
            asked.append("shuffle")

        if asked:
            raise ValueError(
                f"{self.KIND} '{self.name}' asks for {' and '.join(asked)} "
                f"but declares no chunk, and a filter only applies to "
                f"an array stored in chunks"
            )
        return self

    @model_validator(mode="after")
    def check_compression_level(self) -> "Hdf5Writer":
        if self.compression_level is None:
            return self

        levels = COMPRESSION_LEVELS.get(self.compression)
        if levels is None:
            raise ValueError(
                f"{self.KIND} '{self.name}' has a compression_level, "
                f"which '{self.compression.value}' does not take"
            )

        low, high = levels
        if not low <= self.compression_level <= high:
            raise ValueError(
                f"{self.KIND} '{self.name}' has a compression_level of "
                f"{self.compression_level}, which is outside "
                f"{low}..{high} for '{self.compression.value}'"
            )
        return self


def selected_arrays(dataset: Dataset, hdf5_class: Hdf5Class) -> list[NdArray]:
    """
    Return the arrays of DATASET that HDF5_CLASS uses, in declaration order.

    The include and exclude lists of the reader or writer select them;
    without either one every array of the dataset is used.
    """
    if hdf5_class.include is not None:
        included = set(hdf5_class.include)
        return [array for array in dataset.arrays if array.name in included]

    if hdf5_class.exclude is not None:
        excluded = set(hdf5_class.exclude)
        return [array for array in dataset.arrays if array.name not in excluded]

    return list(dataset.arrays)


class Spec(BaseModel):
    tables: list[Table] = []
    datasets: list[Dataset] = []
    vectors: list[Vector] = []
    maps: list[Map] = []
    structs: list[Struct] = []
    csv_readers: list[CsvReader] = []
    parquet_readers: list[ParquetReader] = []
    csv_writers: list[CsvWriter] = []
    parquet_writers: list[ParquetWriter] = []
    hdf5_readers: list[Hdf5Reader] = []
    hdf5_writers: list[Hdf5Writer] = []

    @property
    def aggregates(self) -> list[Aggregate]:
        """Return every aggregate type of the specification."""
        return [*self.vectors, *self.maps, *self.structs]

    @property
    def readers(self) -> list[Reader]:
        """Return every reader of the specification."""
        return [*self.csv_readers, *self.parquet_readers]

    @property
    def writers(self) -> list[Writer]:
        """Return every writer of the specification."""
        return [*self.csv_writers, *self.parquet_writers]

    @property
    def table_classes(self) -> list[TableClass]:
        """Return every class generated for a table of the specification."""
        return [*self.readers, *self.writers]

    @property
    def hdf5_classes(self) -> list[Hdf5Class]:
        """Return every function generated over an HDF5 group."""
        return [*self.hdf5_readers, *self.hdf5_writers]

    @property
    def dataset_classes(self) -> list[DatasetClass]:
        """Return everything generated for a dataset of the specification."""
        return [*self.hdf5_classes]

    @model_validator(mode="after")
    def check_references(self) -> "Spec":
        """
        Check that names are unique
        and that every reader refers to a defined table and its columns.
        """
        errors: list[str] = []

        # Tables, datasets, aggregate types and readers share one namespace.
        names = [table.name for table in self.tables]
        names += [dataset.name for dataset in self.datasets]
        names += [aggregate.name for aggregate in self.aggregates]
        names += [generated.name for generated in self.table_classes]
        names += [generated.name for generated in self.dataset_classes]
        duplicates = find_duplicates(names)
        if duplicates:
            errors.append(f"duplicate table or reader names: {', '.join(duplicates)}")

        # A type that is not a scalar type has to be an aggregate type
        # declared in the same file,
        # and the aggregate types may not contain one another.
        aggregates = {aggregate.name: aggregate for aggregate in self.aggregates}
        for aggregate in self.aggregates:
            unknown = [
                name for name in referenced_types(aggregate) if name not in aggregates
            ]
            if unknown:
                errors.append(
                    f"{aggregate.KIND} '{aggregate.name}' refers to "
                    f"undefined types: {', '.join(unknown)}"
                )

        cycles = find_type_cycles(aggregates)
        for cycle in cycles:
            errors.append(
                f"aggregate types contain one another: "
                f"{' -> '.join([*cycle, cycle[0]])}"
            )

        for table in self.tables:
            for column in table.columns:
                if isinstance(column.type, str) and column.type not in aggregates:
                    errors.append(
                        f"table '{table.name}' column '{column.name}' refers to "
                        f"undefined type '{column.type}'"
                    )

        tables = {table.name: table for table in self.tables}
        for generated in self.table_classes:
            if generated.table not in tables:
                errors.append(
                    f"{generated.KIND} '{generated.name}' refers to "
                    f"undefined table '{generated.table}'"
                )

        for generated in [*self.csv_readers, *self.csv_writers]:
            table = tables.get(generated.table)
            if table is None:
                continue

            aggregate_columns = [
                column.name
                for column in table.columns
                if not isinstance(column.type, ScalarType)
            ]
            if aggregate_columns:
                errors.append(
                    f"{generated.KIND} '{generated.name}' uses table "
                    f"'{table.name}', which has columns no CSV can hold: "
                    f"{', '.join(aggregate_columns)}"
                )

        # A cycle would make the flattened form of a table infinite,
        # and is reported above, so the keys are only walked without one.
        for reader in self.readers if not cycles else []:
            table = tables.get(reader.table)
            if table is None:
                continue

            keys = table_class_keys(reader, table, aggregates)

            for key, value in reader.default.items():
                flat = keys.get(key)
                if flat is None:
                    errors.append(
                        f"{reader.KIND} '{reader.name}' has a default for "
                        f"'{key}', which table '{table.name}' does not hold"
                    )
                    continue
                if not isinstance(flat.type, ScalarType):
                    errors.append(
                        f"{reader.KIND} '{reader.name}' has a default for "
                        f"'{key}', which is of aggregate type '{flat.type}'"
                    )
                    continue
                reason = check_default_value(flat.type, value)
                if reason is not None:
                    errors.append(
                        f"{reader.KIND} '{reader.name}' has a default for "
                        f"'{key}' that {reason}"
                    )

        # A reader and a writer name a part of a file the same way,
        # the one to look for it and the other to write it.
        for generated in self.table_classes if not cycles else []:
            table = tables.get(generated.table)
            if table is None:
                continue

            keys = table_class_keys(generated, table, aggregates)
            verb = "reads" if isinstance(generated, Reader) else "writes"

            for key in generated.name_in_file:
                flat = keys.get(key)
                if flat is None:
                    errors.append(
                        f"{generated.KIND} '{generated.name}' has a "
                        f"name_in_file for '{key}', which table "
                        f"'{table.name}' does not hold"
                    )
                elif not flat.is_named:
                    errors.append(
                        f"{generated.KIND} '{generated.name}' has a "
                        f"name_in_file for '{key}', which a Parquet file "
                        f"matches by position rather than by name"
                    )

            # Renaming may not make two parts of one group share a name.
            groups: dict[str, list[str]] = {}
            for key, flat in keys.items():
                if not flat.is_named:
                    continue
                parent, _, last = key.rpartition(".")
                groups.setdefault(parent, []).append(
                    generated.name_in_file.get(key, last)
                )

            for parent, names in groups.items():
                duplicates = find_duplicates(names)
                if duplicates:
                    where = f"'{parent}'" if parent else f"table '{table.name}'"
                    errors.append(
                        f"{generated.KIND} '{generated.name}' {verb} two parts "
                        f"of {where} by one name: {', '.join(duplicates)}"
                    )

        datasets = {dataset.name: dataset for dataset in self.datasets}
        for generated in self.dataset_classes:
            if generated.dataset not in datasets:
                errors.append(
                    f"{generated.KIND} '{generated.name}' refers to "
                    f"undefined dataset '{generated.dataset}'"
                )

        for hdf5_class in self.hdf5_classes:
            dataset = datasets.get(hdf5_class.dataset)
            if dataset is None:
                continue

            declared = {array.name for array in dataset.arrays}
            for kind, listed in (
                ("include", hdf5_class.include),
                ("exclude", hdf5_class.exclude),
            ):
                if listed is None:
                    continue
                unknown = [name for name in listed if name not in declared]
                if unknown:
                    errors.append(
                        f"{hdf5_class.KIND} '{hdf5_class.name}' lists {kind} "
                        f"arrays not in dataset '{dataset.name}': "
                        f"{', '.join(unknown)}"
                    )

            if not selected_arrays(dataset, hdf5_class):
                errors.append(
                    f"{hdf5_class.KIND} '{hdf5_class.name}' selects no array "
                    f"of dataset '{dataset.name}'"
                )

            # A chunk has one extent per dim of the dataset it is stored in.
            chunk = hdf5_class.chunk if isinstance(hdf5_class, Hdf5Writer) else None
            if chunk is not None and len(chunk) != dataset.ndim:
                errors.append(
                    f"{hdf5_class.KIND} '{hdf5_class.name}' has a chunk of "
                    f"{len(chunk)} extents, but dataset '{dataset.name}' "
                    f"has {dataset.ndim} dims"
                )

        if errors:
            raise ValueError("; ".join(errors))
        return self


SECTIONS = {
    "vector": "vectors",
    "map": "maps",
    "struct": "structs",
    "table": "tables",
    "dataset": "datasets",
    "csv_reader": "csv_readers",
    "parquet_reader": "parquet_readers",
    "csv_writer": "csv_writers",
    "parquet_writer": "parquet_writers",
    "hdf5_reader": "hdf5_readers",
    "hdf5_writer": "hdf5_writers",
}


def parse_spec(spec_file: Path) -> Spec:
    raw: dict[str, Any] = tomllib.loads(spec_file.read_text())

    for singular, plural in SECTIONS.items():
        section = raw.pop(singular, None)
        if section is None:
            continue
        if not isinstance(section, list):
            raise ValueError(
                f"{spec_file}: sections must be declared as [[{singular}]], "
                f"not [{singular}]"
            )
        raw.setdefault(plural, section)

    return Spec.model_validate(raw)
