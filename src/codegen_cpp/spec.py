"""Specification models."""

import tomllib
from collections.abc import Iterable
from enum import Enum
from math import isfinite
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, model_validator


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


def find_duplicates(names: Iterable[str]) -> list[str]:
    """Return the names that occur more than once, in order of first repeat."""
    seen: set[str] = set()
    duplicates: dict[str, None] = {}
    for name in names:
        if name in seen:
            duplicates[name] = None
        seen.add(name)
    return list(duplicates)


class Column(BaseModel):
    name: str
    type: ScalarType


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


DefaultValue = bool | int | float | str

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


def check_default_value(column: Column, value: DefaultValue) -> str | None:
    """
    Return the reason why VALUE cannot be stored in COLUMN, or None.

    Note that `bool` is a subclass of `int` in Python,
    so booleans are checked before integers.
    """
    if column.type is ScalarType.bool:
        if not isinstance(value, bool):
            return "expects a boolean"
        return None

    if column.type is ScalarType.str:
        if not isinstance(value, str):
            return "expects a string"
        return None

    if column.type in FLOAT_TYPES:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "expects a number"
        if not isfinite(value):
            return "expects a finite number"
        return None

    if isinstance(value, bool) or not isinstance(value, int):
        return "expects an integer"

    bits = INTEGER_BITS[column.type]
    if column.type in SIGNED_TYPES:
        low, high = -(2 ** (bits - 1)), 2 ** (bits - 1) - 1
    else:
        low, high = 0, 2**bits - 1
    if not low <= value <= high:
        return f"expects an integer between {low} and {high}"
    return None


class TableClass(BaseModel):
    """The fields shared by every C++ class generated for a table."""

    KIND: ClassVar[str] = "table class"

    name: str
    table: str


class Reader(TableClass):
    """The fields shared by every reader that fills in a table."""

    KIND: ClassVar[str] = "reader"

    default_values: dict[str, DefaultValue] = {}


class CsvReader(Reader):
    KIND: ClassVar[str] = "csv_reader"


class ParquetReader(Reader):
    KIND: ClassVar[str] = "parquet_reader"


class CsvWriter(TableClass):
    KIND: ClassVar[str] = "csv_writer"


class Spec(BaseModel):
    tables: list[Table] = []
    csv_readers: list[CsvReader] = []
    parquet_readers: list[ParquetReader] = []
    csv_writers: list[CsvWriter] = []

    @property
    def readers(self) -> list[Reader]:
        """Return every reader of the specification."""
        return [*self.csv_readers, *self.parquet_readers]

    @property
    def table_classes(self) -> list[TableClass]:
        """Return every class generated for a table of the specification."""
        return [*self.readers, *self.csv_writers]

    @model_validator(mode="after")
    def check_references(self) -> "Spec":
        """
        Check that names are unique
        and that every reader refers to a defined table and its columns.
        """
        errors: list[str] = []

        # Tables and readers share one namespace.
        names = [table.name for table in self.tables]
        names += [generated.name for generated in self.table_classes]
        duplicates = find_duplicates(names)
        if duplicates:
            errors.append(f"duplicate table or reader names: {', '.join(duplicates)}")

        tables = {table.name: table for table in self.tables}
        for generated in self.table_classes:
            if generated.table not in tables:
                errors.append(
                    f"{generated.KIND} '{generated.name}' refers to "
                    f"undefined table '{generated.table}'"
                )

        for reader in self.readers:
            table = tables.get(reader.table)
            if table is None:
                continue

            columns = {column.name: column for column in table.columns}
            unknown = [name for name in reader.default_values if name not in columns]
            if unknown:
                errors.append(
                    f"{reader.KIND} '{reader.name}' lists default_values "
                    f"not in table '{table.name}': {', '.join(unknown)}"
                )

            for name, value in reader.default_values.items():
                column = columns.get(name)
                if column is None:
                    continue
                reason = check_default_value(column, value)
                if reason is not None:
                    errors.append(
                        f"{reader.KIND} '{reader.name}' has a default_value "
                        f"for column '{name}' that {reason}"
                    )

        if errors:
            raise ValueError("; ".join(errors))
        return self


SECTIONS = {
    "table": "tables",
    "csv_reader": "csv_readers",
    "parquet_reader": "parquet_readers",
    "csv_writer": "csv_writers",
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
