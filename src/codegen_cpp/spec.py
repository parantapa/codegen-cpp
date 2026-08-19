"""Specification models."""

import tomllib
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel


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


class Column(BaseModel):
    name: str
    type: ScalarType


class CsvFile(BaseModel):
    name: str
    columns: list[Column]


class Spec(BaseModel):
    csv_files: list[CsvFile]


def parse_spec(spec_file: Path) -> Spec:
    raw: dict[str, Any] = tomllib.loads(spec_file.read_text())

    csv_file = raw.pop("csv_file", None)
    if csv_file is not None:
        raw.setdefault(
            "csv_files", [csv_file] if isinstance(csv_file, dict) else csv_file
        )

    return Spec.model_validate(raw)
