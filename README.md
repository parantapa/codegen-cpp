# codegen-cpp

`codegen-cpp` is a C++ code generation utility written in Python.

It can be used to generate C++ code from TOML specification files.
Presently it supports generating Struct-of-Array data structures
and code that reads those tables from,
and writes them to, CSV and Parquet files
using [Apache Arrow](https://arrow.apache.org).
It also generates datasets of n-dimensional arrays
and classes that read them from,
and write them to, an [HDF5](https://www.hdfgroup.org/solutions/hdf5) file.

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

The `examples` directory holds three annotated specifications
that double as a tutorial.
`examples/table1.toml` covers tables
and the CSV and Parquet classes that read and write them;
`examples/table2.toml` covers the aggregate types
that a column of a table may hold;
`examples/dataset1.toml` covers datasets of n-dimensional arrays
and the HDF5 classes that read and write those.
To see how a specification is parsed, without generating anything:

```bash
codegen-cpp debug parse-spec examples/table1.toml
```

## Starting from a data file

Writing the table of a wide file by hand is tedious,
so `make-config` writes a first draft of one from the file itself,
`make-config csv` from a CSV file and `make-config parquet` from a Parquet one:

```bash
codegen-cpp make-config csv measurements.csv.gz
```

This reads the columns of the file with pyarrow,
and writes `measurements.toml` beside it,
holding the table the file is read into,
a reader that reads it and a writer that writes it back out.
`--output-file` is spelled `--output` (`-o`) here,
and the default drops the suffixes of both the format and the codec,
so `measurements.csv.gz` and `measurements.csv`
are both described by `measurements.toml`.
An output file that is already there is overwritten.

The types are the ones pyarrow infers.
By default it infers them from the first block of the file,
which is a megabyte of it,
so a column that is integral for its first megabyte
and turns into text further down is declared `i64`
and read as one until the file throws.
`--read-all` infers them from every row instead,
which types such a column by all of it,
at the cost of reading the whole file into memory.
The specification says which of the two it was generated with.

Note that the default reads more of the file than it infers from.
The streaming reader reads ahead,
by about ten megabytes at the default block size,
so a file smaller than that is read from end to end,
and a file of any size above it is not.
Neither one holds more than a block at a time,
which is what `--read-all` gives up.

A column that a CSV holds but a table does not, such as a date,
is declared as `str` and noted in a comment,
because Arrow converts it to a string on the way in.

The columns of a data file are rarely C++ identifiers,
so each one is turned into one:
whatever may not appear in an identifier becomes an underscore,
a run of underscores becomes one,
a name that would begin with a digit is prefixed with one,
and a name that C++ keeps for itself is followed by one.
Two names that come out the same are numbered apart.
The reader maps each of them back with `name_in_file`,
so `Station ID` in the file is `Station_ID` in the table:

```toml
[[table]]
name = "Measurements"
columns = [
    { name = "Station_ID", type = "i64" },
    { name = "temp_C", type = "f64" },
    { name = "when", type = "str" },  # read as 'date32[day]'
]

[[csv_reader]]
name = "MeasurementsCsvReader"
table = "Measurements"

[csv_reader.name_in_file]
Station_ID = "Station ID"
temp_C = "temp (C)"

[csv_reader.default]
Station_ID = 0
temp_C = 0.0
when = ""

[[csv_writer]]
name = "MeasurementsCsvWriter"
table = "Measurements"

[csv_writer.name_in_file]
Station_ID = "Station ID"
temp_C = "temp (C)"
```

Every column is given a default,
so a draft reads a file with holes in it rather than throwing;
drop a column from `default` to make a null in it an error.
The writer is given the same `name_in_file` as the reader,
so a table read out of one file is written back into its like;
drop that section to write the names of the table instead.

A file that names two of its columns the same
is reported rather than described,
because a reader selects its columns by name
and cannot tell those two apart.

### From a Parquet file

`make-config parquet` writes the same three sections,
named `MeasurementsParquetReader` and `MeasurementsParquetWriter`,
and everything above about names and defaults holds here too.
Two things differ.

Nothing is inferred and nothing but the footer is read,
because a Parquet file carries its schema inside it,
so there is no `--read-all` and no sampling to go wrong.

A group of the file becomes an aggregate type of its own,
named after the flattened key that reaches it,
so a `LIST` becomes a `vector`, a `MAP` a `map`,
and a plain group a `struct`,
each declared above the types that hold it:

```toml
[[struct]]
name = "TopicsElement"
fields = [
    { name = "name", type = "str" },
    { name = "score", type = "f64" },
]

[[vector]]
name = "Topics"
element = "TopicsElement"
```

The reader then names and defaults every part by its flattened key,
so `biblio.first_page` is renamed and `topics.element.score` is defaulted,
and a key that ends at an aggregate type takes no default.

A column stored as something no table can hold, such as a timestamp,
is left out rather than declared as something it is not,
because a Parquet reader matches the type of what it reads exactly
and would throw on the first batch.
A column of a group is left out whole
where anything below it cannot be held.
Each one is named in a comment at the top of the specification
and reported on the command line,
and a file that holds nothing a table can hold is an error.
Leaving a column out costs nothing else:
a Parquet reader selects the columns it wants by name,
so the ones that are left read as they always would.

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
| `hdf5_reader`    | a class reading a dataset from an HDF5 group    |
| `hdf5_writer`    | a class writing a dataset into an HDF5 group    |

Every section has a `name`,
which is used verbatim as the name of the generated class.
The names of all sections share one namespace and have to be unique.
Every reader and writer of a table names the `table`
it reads into or writes out,
and every reader or writer of a dataset names the `dataset`
it reads into or writes out.

A table declares its `columns`,
each with a name used verbatim as a C++ member name,
and one of the scalar types:

| Type                      | C++ type                           |
| ------------------------- | ---------------------------------- |
| `i8`, `i16`, `i32`, `i64` | `std::int8_t` ... `std::int64_t`   |
| `u8`, `u16`, `u32`, `u64` | `std::uint8_t` ... `std::uint64_t` |
| `f32`, `f64`              | `float`, `double`                  |
| `bool`                    | `bool`                             |
| `str`                     | `std::string`                      |

A column may also name an aggregate type
declared by a `vector`, a `map` or a `struct` section of the same file.
The three cover the three shapes a group of a Parquet file can have,
and each is read from, and written to, that shape and no other:

| Section  | C++                              | Parquet                |
| -------- | -------------------------------- | ---------------------- |
| `vector` | `std::vector<element>`           | a group annotated LIST |
| `map`    | `std::map<key, value>`           | a group annotated MAP  |
| `struct` | a struct of one member per field | a plain group          |

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
so a `csv_reader` over a table with such a column,
or a `csv_writer` that writes one,
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

A table reader says what it has to say about a file
one part of the table at a time,
through `default` and `name_in_file`,
each keyed by the flattened key of the part it names.
`default` is the value stored where the file holds a null,
and a null that no default answers for is an error;
the value has to fit the type of the part it names.
`name_in_file` is the name the file gives the part,
where that is not the name the specification uses,
so a column awkwardly named in the file
is not awkwardly named in every line of C++ that touches it.
Renaming two parts of one group to one name is an error.

A `csv_writer` and a `parquet_writer` take `name_in_file` as well,
keyed the same way and read the other way around:
it is the name the writer gives the part in the file it writes,
so a table read under the names of the specification
is written back out under the names the file uses.
A writer takes no `default`,
because a table holds a value for every part of every row it holds.

A `csv_writer` and a `parquet_writer` may also narrow the columns they write,
with the same two lists that an `hdf5_reader` and an `hdf5_writer` take.
`include` names the columns that are written,
and `exclude` names the columns that are not;
without either one every column of the table is written.
A column that is left out is not written at all,
so the file holds the columns of the writer rather than of the table,
and a reader of the whole table does not find them all in it.
A list that is given may not be empty,
may only name columns of the table the writer refers to,
and may not name the same column twice.
Declaring both lists is an error,
and so is a writer left with no column at all.
A `csv_writer` over a table with a column that no CSV can hold
is fine as long as it leaves that column out.

Earlier versions spelled `default` as `default_values`,
which is no longer read;
a specification that still declares it is rejected rather than ignored.

For a `csv_reader` or a `csv_writer`
a flattened key is the name of a column and nothing else,
because a CSV holds no level below one.
A `parquet_reader` or a `parquet_writer`
reaches into a nested column with the same keys:
the name of the column,
followed by one step for every level below it:
the name of a field of a struct,
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
with the same two lists, over the arrays of its dataset.
`include` names the arrays that are used,
and `exclude` names the arrays that are not;
without either one every array of the dataset is used.
A list that is given may not be empty,
may only name arrays of the dataset it refers to,
and may not name the same array twice.
Declaring both lists is an error,
and so is a reader or writer left with no array at all.

An `hdf5_writer` may also say how the arrays are laid out in the file.
`chunk` is the shape of one chunk, one extent per dim of the dataset,
and every extent of it is at least one;
it turns the contiguous layout that a writer uses by default
into the chunked layout that a filter needs.
An extent that reaches past the array it is stored along
is cut down to the array when the file is written,
so one chunk fits a dataset of any size.

`compression` names the filter the chunks are compressed with:

| Codec     | Level   | Where it comes from                   |
| --------- | ------- | ------------------------------------- |
| `none`    |         | the default, which compresses nothing |
| `deflate` | 0 to 9  | zlib, which is built into HDF5 itself |
| `zstd`    | 1 to 22 | a plugin that HDF5 loads at run time  |
| `lz4`     |         | a plugin that HDF5 loads at run time  |

`compression_level` tunes the codecs that take a level,
and is an error for the ones that do not.
A codec that takes one and is left without it
compresses the way the plugin holding it was built to,
except `deflate`, which is asked for at level 6.
`shuffle` puts the shuffle filter before the compressor,
which sorts the bytes of the elements by position
and usually pays for itself on an array of numbers.
Every one of the three asks for `chunk` as well,
because a filter only applies to an array stored in chunks.

Everything but `deflate` lives in a plugin
that HDF5 loads at run time out of the directories
that the `HDF5_PLUGIN_PATH` environment variable names,
so a program that writes or reads through one
needs the plugin beside it rather than linked into it.
The `hdf5_plugins` package builds them;
see the build instructions below.

## The generated code

The whole specification is generated into one header,
which opens with the headers that its sections need between them,
listed once each,
the standard library first and the libraries it binds to after it.
The definitions follow in an order
in which each one is declared after everything it names,
so the tables and the datasets lead
and the classes over them follow.

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

Every reader and writer holds the file it works on,
so none of them can be copied:
the copy constructor and the copy assignment operator are deleted.

A writer replaces the file it opens if it already exists.
`close()` writes out what is left and releases the file;
calling it twice is allowed.
The destructor closes the file as well,
but only `close()` reports a failure to write.

The constructors take the path of the file,
and readers also take the number of rows per batch.
The remaining arguments are optional:

| Class            | Optional arguments                                                          |
| ---------------- | --------------------------------------------------------------------------- |
| `csv_reader`     | `use_threads` (false), `block_size` (128 MB), `compression` (guessed)       |
| `parquet_reader` | `buffer_size` (128 MB)                                                      |
| `csv_writer`     | `compression` (guessed), `compression_level` (the codec's default)          |
| `parquet_writer` | `compression` (Zstandard), `compression_level`, `row_group_length` (128000) |

For the CSV classes,
the compression is guessed from the suffix of the file name,
so `.gz`, `.zst`, `.bz2` and `.lz4` are compressed
and everything else is plain text.
Passing a codec explicitly overrides the guess.
Parquet files carry their compression inside them,
so the Parquet reader needs no such argument.

An `hdf5_reader` called `TileDataHdf5Reader` over the dataset `TileData`
becomes one class over `<H5Cpp.h>` and the struct of the dataset:

```cpp
class TileDataHdf5Reader {
  public:
    TileDataHdf5Reader(H5::H5File& file, const std::string& group_path);

    TileDataHdf5Reader(const TileDataHdf5Reader&) = delete;
    TileDataHdf5Reader& operator=(const TileDataHdf5Reader&) = delete;

    void read_dataset(TileData& data) const;
    void read_partial_dataset(TileData& data,
                              std::span<const std::size_t> offset) const;
};
```

The constructor opens the group `group_path` of the open file
and looks one HDF5 dataset up in it per selected array,
named after the array.
Every array has to be there,
and to be stored with the datatype that the dataset declares for it.
The datatype is compared against the `H5::PredType` of the array,
so the class, the size, the signedness and the byte order
all have to agree;
an array stored the other way round is rejected rather than converted.

`data` is allocated by its caller,
because the reader fills the arrays in rather than sizing them,
and it is what says what shape the file has to hold them in:
the rank and every extent are checked against it as the arrays are read.
Anything that goes wrong is reported as a `std::runtime_error`,
including a missing group or array,
a shape or a datatype that does not match,
and any failure reported by HDF5 itself:

```cpp
H5::H5File file("sim.h5", H5F_ACC_RDONLY);
TileDataHdf5Reader reader(file, "/sim/tile");

TileData tile(1024, 1024);
reader.read_dataset(tile);
```

The arrays are opened when the reader is constructed
and their shape is checked when it reads,
so a missing array or a datatype that does not match
is reported by the constructor,
and a shape that does not match by `read_dataset`.
Every read opens them again out of the group the constructor holds,
so a group that a writer lays out again while the reader is alive
is read back as it stands rather than as it was;
neither read changes the reader, so a `const` one reads as well.

`read_partial_dataset` reads a contiguous part of every array
through an HDF5 hyperslab.
`offset` holds one index per dim of the dataset and says where the part
begins in the file; the shape `data` was allocated with says how large it is,
so the whole of `data` is filled from the block of that shape at that offset:

```cpp
TileDataHdf5Reader reader(file, "/sim/tile");

TileData row(1, 1024);
std::array<std::size_t, 2> offset = {512, 0};
reader.read_partial_dataset(row, offset);
```

The file has to hold that much of every array beyond the offset,
which is checked one dimension at a time,
and an offset of any other length is a `std::invalid_argument`.
Note that the whole read asks for the extents to match exactly,
where the partial read asks only for room:
the file is free to be larger than the part being read out of it.

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
One called `TileDataHdf5Writer` over the same dataset becomes:

```cpp
class TileDataHdf5Writer {
  public:
    TileDataHdf5Writer(H5::H5File& file, const std::string& group_path);

    TileDataHdf5Writer(const TileDataHdf5Writer&) = delete;
    TileDataHdf5Writer& operator=(const TileDataHdf5Writer&) = delete;

    void write_dataset(const TileData& data);
    void create_dataset(std::span<const std::size_t> shape);
    void write_partial_dataset(const TileData& data,
                               std::span<const std::size_t> offset);
};
```

The constructor creates the group if it is not there yet,
together with any group above it that is missing,
so writing into `/sim/tile` of an empty file works.
`write_dataset` writes every array with the datatype the dataset declares
and the shape `data` was allocated with,
which is exactly what the matching reader expects to find,
so a writer and a reader over the same dataset round trip.
One writer may write its group as often as it is asked to,
with a dataset of a different shape each time.

`write_partial_dataset` is the mirror image of `read_partial_dataset`,
and writes the whole of `data` into the block of that shape
that begins at `offset`.
It writes into the arrays the group already holds rather than creating them,
because a part says nothing about how large the whole is,
so laying a group out and filling it in are two separate steps:

```cpp
TileDataHdf5Writer writer(file, "/sim/tile");
writer.write_dataset(whole);                    // 1024 x 1024, once

TileData row(1, 1024);
std::array<std::size_t, 2> offset = {512, 0};
writer.write_partial_dataset(row, offset);      // one row of it, as often
```

Every array has to be there, to have room for the part beyond the offset,
and to be stored with the datatype the dataset declares,
so a part is never quietly converted into an array
that something else laid out differently.

`create_dataset` is the other way to lay a group out.
It creates every array with the shape `shape` names,
one extent per dim of the dataset, and writes nothing into them,
where `write_dataset` asks for a dataset of the whole shape to write out.
An array that is larger than memory is laid out with `create_dataset`
and filled in with `write_partial_dataset`,
so nothing larger than one part is ever allocated:

```cpp
TileDataHdf5Writer writer(file, "/sim/tile");
std::array<std::size_t, 2> shape = {1048576, 1024};
writer.create_dataset(shape);                   // 1 M x 1 K, and no memory

TileData row(1, 1024);
for (std::size_t r = 0; r < 1048576; ++r) {
    std::array<std::size_t, 2> offset = {r, 0};
    writer.write_partial_dataset(row, offset);
}
```

A shape of any other length is a `std::invalid_argument`,
the way an offset of the wrong length is.

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

A writer that declares a `chunk` builds one `H5::DSetCreatPropList`,
which every array it creates is given,
cuts the chunk down to the shape those arrays are given,
and puts the filters it declares on the list in the order they are applied,
the shuffle filter first.
Nothing of the sort is written for a writer that declares no layout,
which stores its arrays exactly as it always did.

A filter has to be there before anything is written through it,
so a writer looks for its own filters before it creates the first array,
and a reader looks for the filters of an array before it reads one.
A part written into an array that is already there
goes through whatever filters that array was created with,
so `write_partial_dataset` looks for those as well.
Any of them throws a `std::runtime_error` naming `HDF5_PLUGIN_PATH`
where the filter is missing,
rather than leaving HDF5 to report it further down.
Reading is otherwise unaware of compression:
HDF5 decompresses an array as it reads it,
so a reader needs no filter declaration of its own,
and a file written through a filter reads back through any reader of it.

A reader or a writer contributes nothing but its one class:
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
and checked with `pycodestyle` and `pyright`.

## Testing the generated C++ code

The tests under `tests/cpp` generate a header per specification,
write CSV and Parquet files with Arrow
and HDF5 files with both the HDF5 C++ API and the generated writers,
and read them back with the generated readers.
Arrow, HDF5, `hdf5_plugins` and `mdspan` are installed with Conan;
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

`hdf5_plugins` comes from the
[`pb-conan-index`](https://github.com/parantapa/pb-conan-index) remote
and holds the compression filters that HDF5 loads at run time.
The CMake project points the HDF5 tests at the directory it packages them in,
so `ctest` finds them without any environment of its own;
a program of your own finds them
through the `HDF5_PLUGIN_PATH` environment variable,
which the Conan run environment sets for you.
The `hdf5_without_plugins` test runs the same binary with that path cleared,
and checks what a writer and a reader report when a filter is missing.
Only the filters that the tests use are built;
`conanfile.txt` says which, and turns the rest off.

A filter is loaded into the running program,
so it has to reach the HDF5 it was built against.
Against a shared HDF5 it links to the library like anything else.
Against a static one it is built with its HDF5 symbols left undefined
and looks them up in the program that loaded it,
which is why the tests link `hdf5_plugins::hdf5_plugins`:
the package puts `-rdynamic` on the executables that use it.
The generated code is the same either way.
Both are tested:

```bash
conan install . --build=missing -of build-shared -s compiler.cppstd=20 \
    -o "hdf5/*:shared=True"
cmake -S tests/cpp -B build-shared/cpp \
    -DCMAKE_TOOLCHAIN_FILE="$PWD/build-shared/build/Release/generators/conan_toolchain.cmake" \
    -DCMAKE_BUILD_TYPE=Release
cmake --build build-shared/cpp
ctest --test-dir build-shared/cpp --output-on-failure
```

## License

MIT, see `LICENSE`.
