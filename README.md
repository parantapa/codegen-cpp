# codegen-cpp

`codegen-cpp` is a C++ code generation utility written in Python.

It can be used to genereate C++ code from TOML specification files.
Presently it supports generation Struct-of-Array data structures
and code to read those tables to and from CSV and Parquet files
using [Apache Arrow](https://arrow.apache.org).

## Requirements

`codegen-cpp` itself needs Python 3.12 or later.
The code it generates needs a C++23 compiler
and Apache Arrow built with the CSV and Parquet support.

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
default_values = { note = "" }

[[parquet_writer]]
name = "MeasurementParquetWriter"
table = "Measurement"
```

Generate the headers:

```bash
codegen-cpp generate spec.toml --output-dir include
```

This writes one header per section, named after the section:
`include/Measurement.hpp`,
`include/MeasurementCsvReader.hpp`,
and `include/MeasurementParquetWriter.hpp`.

Use them to convert a CSV file into a Parquet file:

```cpp
#include "MeasurementCsvReader.hpp"
#include "MeasurementParquetWriter.hpp"

int main() {
    MeasurementCsvReader reader("measurements.csv.gz", 100000);
    MeasurementParquetWriter writer("measurements.parquet");

    while (reader.has_more_batches()) {
        const Measurement batch = reader.read_batch();
        writer.write_batch(batch);
    }

    writer.close();
    return 0;
}
```

`examples/table1.toml` is an exemplar specification
that shows features of the specification format..
To see how a specification is parsed, without generating anything:

```bash
codegen-cpp debug parse-spec examples/table1.toml
```

## The specification

A specification is a TOML document
holding any number of sections of five kinds.
Every section is an array of tables, written `[[table]]`, `[[csv_reader]]`,
and so on.

| Section            | What it generates                            |
| ------------------ | -------------------------------------------- |
| `table`            | the struct holding the rows                  |
| `csv_reader`       | a class reading the table from a CSV file    |
| `parquet_reader`   | a class reading the table from a Parquet file|
| `csv_writer`       | a class writing the table to a CSV file      |
| `parquet_writer`   | a class writing the table to a Parquet file  |

Every section has a `name`,
which is used verbatim as the name of the generated class
and of the header file holding it.
The names of all sections share one namespace and have to be unique.
Every reader and writer names the `table` it reads into or writes out.

A table declares its `columns`,
each with a name used verbatim as a C++ member name,
and one of the scalar types:

| Type                     | C++ type                              |
| ------------------------ | ------------------------------------- |
| `i8`, `i16`, `i32`, `i64`| `std::int8_t` ... `std::int64_t`      |
| `u8`, `u16`, `u32`, `u64`| `std::uint8_t` ... `std::uint64_t`    |
| `f32`, `f64`             | `float`, `double`                     |
| `bool`                   | `bool`                                |
| `str`                    | `std::string`                         |

Readers may declare `default_values`,
a mapping of column names to the value stored
when that column is null in the input file.
A null in any other column is an error.
The value has to fit the type of its column.

## The generated code

For a table called `Measurement`, `Measurement.hpp` defines the struct `Measurement`,
which holds the rows column by column, one `std::vector` per column.
Its nested struct `Measurement::row_type` holds a single row by value:

```cpp
struct Measurement {
    struct row_type {
        std::int64_t station_id;
        double temperature;
        std::string note;
    };

    std::vector<std::int64_t> station_id;
    std::vector<double> temperature;
    std::vector<std::string> note;

    Measurement() = default;
    Measurement(const Measurement&) = delete;
    Measurement& operator=(const Measurement&) = delete;
    Measurement(Measurement&&) = default;
    Measurement& operator=(Measurement&&) = default;

    std::size_t size() const noexcept;
    void clear() noexcept;
    void reserve(std::size_t n);
    void push_back(const row_type& row);
    void push_back(const std::int64_t& station_id_,
                   const double& temperature_,
                   const std::string& note_);
    row_type operator[](std::size_t i) const;
};
```

All the columns of a table have the same length,
which is what `size()` reports.
`operator[]` returns a copy of a row,
because the rows are not stored as rows.

Readers hand out one batch of rows at a time,
and writers take one batch at a time:

```cpp
bool has_more_batches();       // readers
Table read_batch();            // readers, at most batch_size rows

void write_batch(const Table& table);  // writers
void close();                          // writers
```

A writer replaces the file it opens if it already exists.
`close()` writes out what is left and releases the file;
calling it twice is allowed.
The destructor closes the file as well,
but only `close()` reports a failure to write.

The constructors take the path of the file,
and readers also take the number of rows per batch.
The remaining arguments are optional:

| Class            | Optional arguments                                                            |
| ---------------- | ----------------------------------------------------------------------------- |
| `csv_reader`     | `use_threads` (false), `block_size` (128 MB), `compression` (guessed)         |
| `parquet_reader` | `buffer_size` (128 MB)                                                        |
| `csv_writer`     | `compression` (guessed), `compression_level` (the codec's default)            |
| `parquet_writer` | `compression` (Zstandard), `compression_level`, `row_group_length` (128000)   |

For the CSV classes,
the compression is guessed from the suffix of the file name,
so `.gz`, `.zst`, `.bz2` and `.lz4` are compressed
and everything else is plain text.
Passing a codec explicitly overrides the guess.
Parquet files carry their compression inside them,
so the Parquet reader needs no such argument.

## Development

Install the package and its development dependencies
in a virtual environment, and run the tests:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

The project is formatted with `black`,
checked with `pycodestyle` and `pyright`.

## Testing the generated C++ code

The tests under `tests/cpp` generate headers,
write CSV and Parquet files with Arrow,
and read them back with the generated readers.
Arrow is installed with Conan;
see `conanfile.txt` for the features it is built with.
Note that Arrow needs C++20 or later,
which the default Conan profile does not ask for.

```bash
conan install . --build=missing -of build -s compiler.cppstd=20
cmake -S tests/cpp -B build/cpp \
    -DCMAKE_TOOLCHAIN_FILE="$PWD/build/build/Release/generators/conan_toolchain.cmake" \
    -DCMAKE_BUILD_TYPE=Release
cmake --build build/cpp
ctest --test-dir build/cpp --output-on-failure
```

## License

MIT, see `LICENSE`.
