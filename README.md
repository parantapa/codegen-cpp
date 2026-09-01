# codegen-cpp

`codegen-cpp` is a C++ code generation utility written in Python.

It can be used to genereate C++ code from TOML specification files.
Presently it supports generation Struct-of-Array data structures
and code to read those tables to and from CSV and Parquet files
using [Apache Arrow](https://arrow.apache.org).
It also generates datasets of n-dimensional arrays
and functions that read them from,
and write them to, an [HDF5](https://www.hdfgroup.org/solutions/hdf5) file.

## Requirements

`codegen-cpp` itself needs Python 3.12 or later.
The code it generates needs a C++23 compiler,
Apache Arrow built with the CSV and Parquet support,
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
default_values = { note = "" }

[[parquet_writer]]
name = "MeasurementParquetWriter"
table = "Measurement"
```

Generate the header:

```bash
codegen-cpp generate spec.toml
```

This writes every section of the specification into a single header,
`spec.hpp`, sitting next to the specification it was generated from.
`--output-file` (`-o`) writes it somewhere else instead:

```bash
codegen-cpp generate spec.toml --output-file include/measurements.hpp
```

The directories of the output file are created if they are missing,
and an output file that is already there is overwritten.

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

The `examples` directory holds two annotated specifications
that double as a tutorial.
`examples/table1.toml` covers tables
and the CSV and Parquet classes that read and write them;
`examples/dataset1.toml` covers datasets of n-dimensional arrays
and the HDF5 functions that read and write those.
To see how a specification is parsed, without generating anything:

```bash
codegen-cpp debug parse-spec examples/table1.toml
```

## The specification

A specification is a TOML document
holding any number of sections of eleven kinds.
Every section is an array of tables, written `[[table]]`, `[[csv_reader]]`,
and so on.

| Section          | What it generates                               |
| ---------------- | ----------------------------------------------- |
| `table`          | the struct holding the rows                     |
| `dataset`        | the struct holding the n-dimensional arrays     |
| `vector`         | a name for a `std::vector`                      |
| `map`            | a name for a `std::map` or `std::unordered_map` |
| `struct`         | a struct of one member per field                |
| `csv_reader`     | a class reading the table from a CSV file       |
| `parquet_reader` | a class reading the table from a Parquet file   |
| `csv_writer`     | a class writing the table to a CSV file         |
| `parquet_writer` | a class writing the table to a Parquet file     |
| `hdf5_reader`    | a function reading a dataset from an HDF5 group |
| `hdf5_writer`    | a function writing a dataset into an HDF5 group |

Every section has a `name`,
which is used verbatim as the name of the generated class or function.
The names of all sections share one namespace and have to be unique.
Every reader and writer of a table names the `table`
it reads into or writes out,
and every reader or writer of a dataset names the `dataset`
it reads into or writes out.

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

A column may also name an aggregate type
declared by a `vector`, a `map` or a `struct` section of the same file.
The three cover the three shapes a group of a Parquet file can have,
and each is read from, and written to, that shape and no other:

| Section  | C++                                     | Parquet             |
| -------- | --------------------------------------- | ------------------- |
| `vector` | `std::vector<element>`                  | a group annotated LIST |
| `map`    | `std::map<key, value>`                  | a group annotated MAP  |
| `struct` | a struct of one member per field        | a plain group          |

A `vector` declares the type of one `element`,
a `map` the type of its `key` and of its `value`,
and a `struct` its `fields`, which read like the columns of a table.
A key of a map is one of the integer types or `str`,
and a map may set `is_unordered` to be held in a `std::unordered_map`,
which finds a key in constant time
and leaves the pairs in an order not worth relying on;
it defaults to `false`, which holds them in the order of their keys.

An aggregate type may name a scalar type or another aggregate type,
so the types stack as deep as a file does,
and the types it names may not lead back to it.
CSV has no way to hold any of the three,
so a `csv_reader` or a `csv_writer` over a table with such a column
is an error rather than a guess at an encoding.
Datasets are closed to them for the same reason they are closed to `str`.
See `examples/table2.toml`.

A dataset declares its `dims`, which name one dimension per axis,
and its `arrays`, each with a name and one of the numeric types above.
`bool` and `str` are not allowed,
because an array holds its elements densely and at a fixed size.
Every array of a dataset has the shape that the dims describe,
so the number of dims is the rank they share.
A dataset may also set `column_major`,
which stores the arrays so that the first dim varies fastest;
it defaults to `false`, which stores them row major,
so that the last dim varies fastest.
See `examples/dataset1.toml`.

Table readers may declare `default_values`,
a mapping of column names to the value stored
when that column is null in the input file.
A null in any other column is an error.
The value has to fit the type of its column.

A `parquet_reader` says the same thing about the parts of a nested column
with `default`, and says what the file calls one with `name_in_file`.
Both are keyed by the flattened key of the part they name:
the name of the column,
followed by one step for every level below it,
which is the name of a field of a struct,
`element` for the element of a vector,
and `value` for the value of a map.
So `biblio.first_page` is a field of a struct column,
`keywords.element` is one keyword,
and `topics.element.score` is the score of one topic of a vector of them.
Only a key that ends at a column or at a field of a struct may be renamed,
because a file matches the rest by position,
and only a key that ends at a scalar type takes a default,
because a null aggregate is read as the empty value of its own type:
a vector of no elements, a map of no keys,
or a struct whose fields each take their own default.

An `hdf5_reader` or an `hdf5_writer` may narrow the arrays it uses
with one of two lists.
`include` names the arrays that are used,
and `exclude` names the arrays that are not;
without either one every array of the dataset is used.
A list that is given may not be empty,
may only name arrays of the dataset it refers to,
and may not name the same array twice.
Declaring both lists is an error,
and so is a reader or writer left with no array at all.

## The generated code

The whole specification is generated into one header,
which opens with the headers that its sections need between them,
listed once each,
the standard library first and the libraries it binds to after it.
The definitions follow in an order
in which each one is declared after everything it names,
so the tables and the datasets lead
and the classes and functions over them follow.

Every aggregate type is written under the name that declares it,
above the tables and the types that hold it:

```cpp
using Keywords = std::vector<std::string>;
using Ids = std::map<std::string, std::string>;

struct Biblio {
    std::string volume;
    std::int32_t first_page;

    bool operator==(const Biblio&) const = default;
};
```

so the name of one is the C++ type of it wherever a column names it.

A `table` called `Measurement` becomes the struct `Measurement`,
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

For a dataset called `TileData` with dims `row` and `col`,
the generated struct holds one array per declared array.
Each is a `std::unique_ptr` owning the memory
and a `std::experimental::mdspan` of the dataset's rank giving access to it:

```cpp
struct TileData {
    static constexpr std::size_t rank = 2;

    template <typename T>
    using span_type = std::experimental::mdspan<
        T, std::experimental::dextents<std::size_t, rank>,
        std::experimental::layout_right>;

    std::vector<std::size_t> dims;

    std::unique_ptr<float[]> _mem_burn_time;
    span_type<float> burn_time;

    std::unique_ptr<std::int8_t[]> _mem_state;
    span_type<std::int8_t> state;

    TileData(std::size_t row, std::size_t col);

    TileData(const TileData&) = delete;
    TileData& operator=(const TileData&) = delete;

    std::size_t size() const noexcept;
};
```

The constructor takes one size per dimension,
stores them in `dims`,
and allocates every array without initializing its elements,
so an element has to be written before it is read.
The layout follows `column_major`:
`layout_left` when it is set, and `layout_right` otherwise.
Elements are read with the C++23 subscript:

```cpp
TileData tile(1024, 1024);
tile.burn_time[row, col] = 1.5f;
```

`mdspan` comes from the Kokkos reference implementation,
installed with Conan as `mdspan`;
see `conanfile.txt`.

Table readers append rows to a table of yours,
one batch at a time,
and table writers take one batch at a time:

```cpp
bool has_more_batches();        // readers
void read_batch(Table& table);  // readers, at most batch_size rows
void read_all(Table& table);    // readers, every row that is left

void write_batch(const Table& table);  // writers
void close();                          // writers
```

Neither reading method clears the table it is given,
so the rows it already holds are kept
and one table can collect the rows of several calls.
Reuse a table across the batches of a loop by calling `clear()` on it first,
which keeps the memory it has allocated.
The two may be mixed:
`read_all()` appends whatever the calls to `read_batch()` before it left.

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

An `hdf5_reader` called `read_tile_data` over the dataset `TileData`
becomes one free function over `<H5Cpp.h>` and the struct of the dataset:

```cpp
inline void read_tile_data(H5::H5File& file, const std::string& group_path,
                           TileData& data);
```

`data` is allocated by its caller,
because the reader fills the arrays in rather than sizing them.
The function opens the group `group_path` of the open file
and reads one HDF5 dataset per selected array, named after the array.
Every one of them has to have exactly the shape
and the datatype that the dataset declares.
The datatype is compared against the `H5::PredType` of the array,
so the class, the size, the signedness and the byte order
all have to agree;
an array stored the other way round is rejected rather than converted.
Anything that goes wrong is reported as a `std::runtime_error`,
including a missing group or array,
a shape or a datatype that does not match,
and any failure reported by HDF5 itself:

```cpp
H5::H5File file("sim.h5", H5F_ACC_RDONLY);
TileData tile(1024, 1024);
read_tile_data(file, "/sim/tile", tile);
```

HDF5 stores the elements of a dataset in row major order.
For a dataset that leaves `column_major` unset, and for any dataset
of rank one, that is the order its arrays are already stored in,
so the elements are read straight into them.
For a column major dataset of rank two or more
the elements are laid out again once they are read,
which needs a temporary buffer the size of one array;
the rank is known when the header is written,
so the loops that move them are written out one per dimension.

An `hdf5_writer` is its mirror image.
One called `write_tile_data` over the same dataset becomes:

```cpp
inline void write_tile_data(H5::H5File& file, const std::string& group_path,
                            const TileData& data);
```

The group is created if it is not there yet,
together with any group above it that is missing,
so writing into `/sim/tile` of an empty file works.
Every array is written with the datatype the dataset declares
and the shape `data` was allocated with,
which is exactly what the matching reader expects to find,
so a writer and a reader over the same dataset round trip.

An array the group already holds under the same name is replaced,
whatever shape and datatype it was stored with;
that is not an error.
HDF5 does not hand the space of the replaced array back to the file,
so a program that writes the same group over and over
grows the file each time.

For a column major dataset the elements are gathered into a buffer
on the way out, the same way the reader lays them out on the way in.
The file has to be open for writing;
a read-only file is reported like any other failure.

A reader or a writer contributes nothing but its one function:
the checks and the transfer are written out in place for every array,
so any number of them can share a header.
The generated code does not call `H5::Exception::dontPrint()`,
so HDF5 keeps printing its own errors to standard error
unless the program asks it to stop.

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

The tests under `tests/cpp` generate a header per specification,
write CSV and Parquet files with Arrow
and HDF5 files with both the HDF5 C++ API and the generated writers,
and read them back with the generated readers.
Arrow, HDF5 and `mdspan` are installed with Conan;
see `conanfile.txt` for the features they are built with.
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
