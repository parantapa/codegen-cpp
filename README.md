# codegen-cpp

`codegen-cpp` reads a TOML specification and generates header-only C++23 classes
that read and write tables and n-dimensional arrays in CSV, Parquet and HDF5 files.

Today it generates tables, stored as a struct of arrays,
and the code that reads those tables from CSV and Parquet files.
The same code writes them back, through [Apache Arrow](https://arrow.apache.org).
It also generates datasets of n-dimensional arrays,
and the classes that read them
from an [HDF5](https://www.hdfgroup.org/solutions/hdf5) file
and write them to one.

## Installation

`codegen-cpp` itself needs Python 3.12 or later.
The code it generates needs a C++23 compiler,
Apache Arrow built with CSV and Parquet support,
and HDF5 built with its C++ API.
A dataset also needs the Kokkos reference implementation of `mdspan`.

Install the generator into a virtual environment.
Then activate the environment, so that `codegen-cpp` is on the path:

```bash
git clone https://github.com/parantapa/codegen-cpp.git
cd codegen-cpp
python -m venv .venv
source .venv/bin/activate
pip install .
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

The command prints the file it wrote:

```text
Generated spec.hpp
```

Write a CSV file to read, for example `measurements.csv`:

```text
station_id,temperature,note
1,21.5,sunny
2,19.0,
```

Use the header to convert a CSV file into a Parquet file:

```cpp
#include "spec.hpp"

int main() {
    MeasurementCsvReader reader("measurements.csv", 100000);
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

The program writes the two rows to `measurements.parquet`.
[Convert a CSV file into a Parquet file](docs/tutorials/convert-a-csv-file-into-a-parquet-file.md)
says how to build it against Arrow.

## Documentation

| Document | What it holds |
| -------- | ------------- |
| [Convert a CSV file into a Parquet file](docs/tutorials/convert-a-csv-file-into-a-parquet-file.md) | a first specification, and the program that moves rows through it |
| [Store nested columns in a Parquet file](docs/tutorials/store-nested-columns-in-a-parquet-file.md) | vectors, maps and structs as the columns of a table |
| [Fill an HDF5 file one window at a time](docs/tutorials/fill-an-hdf5-file-one-window-at-a-time.md) | datasets of n-dimensional arrays, written through HDF5 |
| [How to write a specification from a data file](docs/how-to-guides/write-a-specification-from-a-data-file.md) | a first draft of a specification, made from a CSV or a Parquet file |
| [The specification](docs/reference/specification.md) | every section a specification holds, and what each one declares |
| [The command line interface](docs/reference/command-line-interface.md) | every command and option of `codegen-cpp` |
| [The generated code](docs/reference/generated-code.md) | the types and the classes the generator writes, and how they behave |

## Developer documentation

| Document | What it holds |
| -------- | ------------- |
| [Developer notes](docs/developer-notes.md) | the source layout, the tools and libraries, the design decisions, and how the generated C++ code is tested |

Report a bug at <https://github.com/parantapa/codegen-cpp/issues>.

## License

MIT, see `LICENSE`.
