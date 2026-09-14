# The generated code

The whole specification is generated into one header.
It opens with the headers that its sections need between them,
listed once each.
The standard library comes first,
and the libraries it binds to after it.
The definitions follow in an order
in which each one is declared after everything it names.
The aggregate types therefore lead,
the tables and the datasets follow them,
and the classes over those come last.

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
and stores them in `dims`.
It allocates every array without initializing its elements,
so an element has to be written before it is read.
The layout follows `column_major`:
`layout_left` when it is set, and `layout_right` otherwise.
Elements are read with the C++23 subscript:

```cpp
TileData tile(1024, 1024);
tile.burn_time[row, col] = 1.5f;
```

`mdspan` comes from the Kokkos reference implementation,
installed with Conan as `mdspan`.
`conanfile.txt` names it.

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

Neither reading method clears the table it is given.
The rows it already holds are kept,
and one table can collect the rows of several calls.
A table reused across the batches of a loop takes `clear()` first,
which keeps the memory it already allocated.
The two methods mix:
`read_all()` appends whatever the calls to `read_batch()` before it left.

Every reader and writer holds the file it works on,
so none of them takes a copy.
The copy constructor and the copy assignment operator are deleted.

A writer replaces the file it opens if it already exists.
`close()` writes out what is left and releases the file.
A second call to it is allowed.
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
the compression is guessed from the suffix of the file name.
`.gz`, `.zst`, `.bz2` and `.lz4` are compressed,
and everything else is plain text.
A codec passed explicitly overrides the guess.
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
The datatype is compared against the `H5::PredType` of the array.
The class, the size, the signedness and the byte order all have to agree.
An array stored the other way round is rejected rather than converted.

`data` is allocated by its caller,
because the reader fills the arrays in rather than sizing them.
It is also what says what shape the file has to hold them in.
The rank and every extent are checked against it as the arrays are read.

Anything that goes wrong is reported as a `std::runtime_error`.
That covers a missing group or array,
a shape or a datatype that does not match,
and any failure reported by HDF5 itself:

```cpp
H5::H5File file("sim.h5", H5F_ACC_RDONLY);
TileDataHdf5Reader reader(file, "/sim/tile");

TileData tile(1024, 1024);
reader.read_dataset(tile);
```

The arrays are opened when the reader is constructed,
and their shape is checked when it reads.
The constructor therefore reports a missing array
or a datatype that does not match,
and `read_dataset` reports a shape that does not match.
Every read opens the arrays again out of the group the constructor holds.
A group that a writer lays out again while the reader is alive
is read back as it stands rather than as it was.
Neither read changes the reader, so a `const` one reads as well.

`read_partial_dataset` reads a contiguous part of every array
through an HDF5 hyperslab.
`offset` holds one index per dim of the dataset,
and says where the part begins in the file.
The shape `data` was allocated with says how large it is.
The whole of `data` is filled from the block of that shape at that offset:

```cpp
TileDataHdf5Reader reader(file, "/sim/tile");

TileData row(1, 1024);
std::array<std::size_t, 2> offset = {512, 0};
reader.read_partial_dataset(row, offset);
```

The file has to hold that much of every array beyond the offset,
which is checked one dimension at a time.
An offset of any other length is a `std::invalid_argument`.
Note that the whole read asks for the extents to match exactly,
where the partial read asks only for room.
The file is free to be larger than the part read out of it.

HDF5 stores the elements of a dataset in row major order.
For a dataset that leaves `column_major` unset, and for any dataset
of rank one, that is the order its arrays are already stored in.
The elements are then read straight into them.
For a column major dataset of rank two or more,
the elements are laid out again once they are read.
That needs a temporary buffer the size of one array.
The rank is known when the header is written,
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
together with any group above it that is missing.
A write into `/sim/tile` of an empty file therefore works.
`write_dataset` writes every array with the datatype the dataset declares
and the shape `data` was allocated with.
That is exactly what the matching reader expects to find,
so a writer and a reader over the same dataset round trip.
One writer can write its group as often as it is asked to,
with a dataset of a different shape each time.

`write_partial_dataset` is the mirror image of `read_partial_dataset`,
and writes the whole of `data` into the block of that shape
that begins at `offset`.
It writes into the arrays the group already holds rather than creating them,
because a part says nothing about how large the whole is.
The layout of a group and the fill of it are two separate steps:

```cpp
TileDataHdf5Writer writer(file, "/sim/tile");
writer.write_dataset(whole);                    // 1024 x 1024, once

TileData row(1, 1024);
std::array<std::size_t, 2> offset = {512, 0};
writer.write_partial_dataset(row, offset);      // one row of it, as often
```

Every array has to be there, to have room for the part beyond the offset,
and to be stored with the datatype the dataset declares.
A part is therefore never quietly converted into an array
that something else laid out differently.

`create_dataset` is the other way to lay a group out.
It creates every array with the shape `shape` names,
one extent per dim of the dataset, and writes nothing into them.
`write_dataset` asks for a dataset of the whole shape to write out instead.
An array that is larger than memory is laid out with `create_dataset`,
and filled in with `write_partial_dataset`.
Nothing larger than one part is ever allocated:

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
whatever shape and datatype it was stored with.
That is not an error.
HDF5 does not hand the space of the replaced array back to the file.
A program that writes the same group over and over
therefore grows the file each time.

For a column major dataset the elements are gathered into a buffer
on the way out.
The reader lays them out the same way on the way in.
The file has to be open for writing.
A read-only file is reported like any other failure.

A writer that declares a `chunk` builds one `H5::DSetCreatPropList`,
which every array it creates is given.
It cuts the chunk down to the shape those arrays are given.
It then puts the filters it declares on the list
in the order they are applied, the shuffle filter first.
Nothing of the sort is written for a writer that declares no layout,
which stores its arrays exactly as it always did.

A filter has to be there before anything is written through it.
A writer therefore looks for its own filters
before it creates the first array.
A reader looks for the filters of an array before it reads one.

A part written into an array that is already there
goes through whatever filters that array was created with.
`write_partial_dataset` therefore looks for those as well.
Any of them throws a `std::runtime_error` naming `HDF5_PLUGIN_PATH`
where the filter is missing,
rather than leaving HDF5 to report it further down.
A read is otherwise unaware of compression.
HDF5 decompresses an array as it reads it,
so a reader needs no filter declaration of its own.
A file written through a filter reads back through any reader of it.

A reader or a writer contributes nothing but its one class.
The checks and the transfer are written out in place for every array,
so any number of them can share a header.
The generated code does not call `H5::Exception::dontPrint()`,
so HDF5 keeps printing its own errors to standard error
unless the program asks it to stop.
