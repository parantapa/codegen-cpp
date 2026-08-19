"""Specification models."""

import tomllib
from collections.abc import Iterable
from enum import Enum
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


class Reader(BaseModel):
    """The fields shared by every reader that fills in a table."""

    # The name of the section declaring this kind of reader.
    KIND: ClassVar[str] = "reader"

    name: str
    table: str
    nullable_columns: list[str] = []


class CsvReader(Reader):
    KIND: ClassVar[str] = "csv_reader"


class ParquetReader(Reader):
    KIND: ClassVar[str] = "parquet_reader"


class Spec(BaseModel):
    tables: list[Table] = []
    csv_readers: list[CsvReader] = []
    parquet_readers: list[ParquetReader] = []

    @property
    def readers(self) -> list[Reader]:
        """Return every reader of the specification."""
        return [*self.csv_readers, *self.parquet_readers]

    @model_validator(mode="after")
    def check_references(self) -> "Spec":
        """
        Check that names are unique
        and that every reader refers to a defined table and its columns.
        """
        errors: list[str] = []

        # Tables and readers share one namespace:
        # every one of them is generated into a header file of its own name.
        names = [table.name for table in self.tables]
        names += [reader.name for reader in self.readers]
        duplicates = find_duplicates(names)
        if duplicates:
            errors.append(f"duplicate table or reader names: {', '.join(duplicates)}")

        tables = {table.name: table for table in self.tables}
        for reader in self.readers:
            table = tables.get(reader.table)
            if table is None:
                errors.append(
                    f"{reader.KIND} '{reader.name}' refers to "
                    f"undefined table '{reader.table}'"
                )
                continue

            duplicates = find_duplicates(reader.nullable_columns)
            if duplicates:
                errors.append(
                    f"{reader.KIND} '{reader.name}' has duplicate "
                    f"nullable_columns: {', '.join(duplicates)}"
                )

            columns = {column.name for column in table.columns}
            unknown = [name for name in reader.nullable_columns if name not in columns]
            if unknown:
                errors.append(
                    f"{reader.KIND} '{reader.name}' lists nullable_columns "
                    f"not in table '{table.name}': {', '.join(unknown)}"
                )

        if errors:
            raise ValueError("; ".join(errors))
        return self


SECTIONS = {
    "table": "tables",
    "csv_reader": "csv_readers",
    "parquet_reader": "parquet_readers",
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
