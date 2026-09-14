# codegen-cpp

`codegen-cpp` is a C++ code generation utility written in Python.

It generates C++ code from TOML specification files.
Today it generates Struct-of-Array data structures,
and the code that reads those tables from CSV and Parquet files.
The same code writes them back, through [Apache Arrow](https://arrow.apache.org).
It also generates datasets of n-dimensional arrays,
and the classes that read them
from an [HDF5](https://www.hdfgroup.org/solutions/hdf5) file
and write them to one.

## Requirements

`codegen-cpp` itself needs Python 3.12 or later.
The code it generates needs a C++23 compiler,
Apache Arrow built with CSV and Parquet support,
and HDF5 built with its C++ API.

## Installation

```bash
python -m venv .venv
.venv/bin/pip install .
```

## Usage

Write a specification, for example `spec.toml`:

```toml
[[table]]
name = "Measurement"
columns = [
    { name = "station_id", type = "i64" },
    { name = "temperature", type = "f64" },
    { name = "note", type = "str" },
]

[[csv_reader]]
name = "MeasurementCsvReader"
table = "Measurement"
default = { note = "" }

[[parquet_writer]]
name = "MeasurementParquetWriter"
table = "Measurement"
```

Generate the header:

```bash
codegen-cpp generate spec.toml
```

Use the header to convert a CSV file into a Parquet file:

```cpp
#include "spec.hpp"

int main() {
    MeasurementCsvReader reader("measurements.csv.gz", 100000);
    MeasurementParquetWriter writer("measurements.parquet");

    Measurement batch;
    while (reader.has_more_batches()) {
        batch.clear();
        reader.read_batch(batch);
        writer.write_batch(batch);
    }

    writer.close();
    return 0;
}
```

## Documentation

| Document | What it holds |
| -------- | ------------- |
| [Convert a CSV file into a Parquet file](docs/tutorials/convert-a-csv-file-into-a-parquet-file.md) | a first specification, and the program that moves rows through it |
| [Store nested columns in a Parquet file](docs/tutorials/store-nested-columns-in-a-parquet-file.md) | vectors, maps and structs as the columns of a table |
| [Fill an HDF5 file one window at a time](docs/tutorials/fill-an-hdf5-file-one-window-at-a-time.md) | datasets of n-dimensional arrays, written through HDF5 |
| [How to write a specification from a data file](docs/how-to-guides/write-a-specification-from-a-data-file.md) | drafting a specification from a CSV or a Parquet file |
| [The specification](docs/reference/specification.md) | every section a specification holds, and what each one declares |
| [The command line interface](docs/reference/command-line-interface.md) | every command and option of `codegen-cpp` |
| [The generated code](docs/reference/generated-code.md) | the types and the classes the generator writes, and how they behave |

- [Developer notes](docs/developer-notes.md)
- Report a bug at <https://github.com/parantapa/codegen-cpp/issues>

## License

MIT, see `LICENSE`.
