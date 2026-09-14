# The specification

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
which is used verbatim as the name of what it generates.
A table, a dataset and a struct generate a struct of that name,
a vector and a map an alias of that name,
and a reader and a writer a class of that name.
The names of all sections share one namespace and have to be unique.
Every reader and writer of a table names the `table`
it reads into or writes out.
Every reader and writer of a dataset names the `dataset`
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

A column can also name an aggregate type
declared by a `vector`, a `map` or a `struct` section of the same file.
The three cover the three shapes a group of a Parquet file can have.
Each one is read from, and written to, that shape and no other:

| Section  | C++                              | Parquet                |
| -------- | -------------------------------- | ---------------------- |
| `vector` | `std::vector<element>`           | a group annotated LIST |
| `map`    | `std::map<key, value>`           | a group annotated MAP  |
| `struct` | a struct of one member per field | a plain group          |

A `vector` declares the type of one `element`,
and a `map` the type of its `key` and of its `value`.
A `struct` declares its `fields`, which read like the columns of a table.

A key of a map is one of the integer types or `str`.
A map can set `is_unordered`,
which holds the pairs in a `std::unordered_map`.
That finds a key in constant time,
and leaves the pairs in an order not worth relying on.
`is_unordered` defaults to `false`,
which holds the pairs in the order of their keys.

An aggregate type can name a scalar type or another aggregate type,
so the types stack as deep as a file does.
The types it names cannot lead back to it.
CSV has no way to hold any of the three.
A `csv_reader` over a table with such a column,
or a `csv_writer` that writes one,
is an error rather than a guess at an encoding.
Datasets are closed to them for the same reason they are closed to `str`.
`examples/table2.toml` shows them.

A dataset declares its `dims`, which name one dimension per axis.
It also declares its `arrays`,
each with a name and one of the numeric scalar types.
`bool` and `str` are not allowed,
because an array holds its elements densely and at a fixed size.
Every array of a dataset has the shape that the dims describe,
so the number of dims is the rank they share.

A dataset can also set `column_major`,
which stores the arrays so that the first dim varies fastest.
`column_major` defaults to `false`, which stores them row major,
so that the last dim varies fastest.
`examples/dataset1.toml` shows one.

A table reader says what it has to say about a file
one part of the table at a time,
through `default` and `name_in_file`.
Each of the two is keyed by the flattened key of the part it names.

`default` is the value stored where the file holds a null,
and a null that no default answers for is an error.
The value has to fit the type of the part it names.

`name_in_file` is the name the file gives the part,
where that is not the name the specification uses.
A column awkwardly named in the file
is then not awkwardly named in every line of C++ that touches it.
A rename that leaves two parts of one group under one name is an error.

A `csv_writer` and a `parquet_writer` take `name_in_file` as well,
keyed the same way and read the other way around.
It is the name the writer gives the part in the file it writes.
A table read under the names of the specification
is then written back out under the names the file uses.
A writer takes no `default`,
because a table holds a value for every part of every row it holds.

A `csv_writer` and a `parquet_writer` can also narrow the columns they write,
with the same two lists that an `hdf5_reader` and an `hdf5_writer` take.
`include` names the columns that are written,
and `exclude` names the columns that are not.
Without either one, every column of the table is written.

A column that is left out is not written at all,
so the file holds the columns of the writer rather than of the table.
A reader of the whole table does not find them all in it.
A list that is given cannot be empty.
It names only columns of the table the writer refers to,
and it cannot name the same column twice.
A writer that declares both lists is an error,
and so is one left with no column at all.
A `csv_writer` over a table with a column that no CSV can hold
is fine as long as it leaves that column out.

Earlier versions spelled `default` as `default_values`,
which is no longer read.
A specification that still declares it is rejected rather than ignored.

For a `csv_reader` or a `csv_writer`
a flattened key is the name of a column and nothing else,
because a CSV holds no level below one.
A `parquet_reader` or a `parquet_writer`
reaches into a nested column with the same keys.
A key is the name of the column,
followed by one step for every level below it:

- the name of a field of a struct
- `element` for the element of a vector
- `value` for the value of a map

So `biblio.first_page` is a field of a struct column,
and `keywords.element` is one keyword.
`topics.element.score` is the score of one topic of a vector of them.

`name_in_file` renames only a key
that ends at a column or at a field of a struct.
A file matches the rest by position.
Only a key that ends at a scalar type takes a default.
A null aggregate is read as the empty value of its own type:

- a vector of no elements
- a map of no keys
- a struct whose fields each take their own default

An `hdf5_reader` or an `hdf5_writer` can narrow the arrays it uses
with the same two lists, over the arrays of its dataset.
`include` names the arrays that are used,
and `exclude` names the arrays that are not.
Without either one, every array of the dataset is used.
A list that is given cannot be empty.
It names only arrays of the dataset it refers to,
and it cannot name the same array twice.
A reader or a writer that declares both lists is an error,
and so is one left with no array at all.

An `hdf5_writer` can also say how the arrays are laid out in the file.
`chunk` is the shape of one chunk, one extent per dim of the dataset,
and every extent of it is at least one.
It turns the contiguous layout that a writer uses by default
into the chunked layout that a filter needs.
An extent that reaches past the array it is stored along
is cut down to the array when the file is written.
One chunk therefore fits a dataset of any size.

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
compresses the way the plugin holding it was built to.
The exception is `deflate`, which is asked for at level 6.
`shuffle` puts the shuffle filter before the compressor,
which sorts the bytes of the elements by position.
It usually pays for itself on an array of numbers.
Every one of the three asks for `chunk` as well,
because a filter only applies to an array stored in chunks.

Everything but `deflate` lives in a plugin
that HDF5 loads at run time out of the directories
that the `HDF5_PLUGIN_PATH` environment variable names.
A program that writes or reads through one
needs the plugin beside it rather than linked into it.
The `hdf5_plugins` package builds them.
The [developer notes](../developer-notes.md) hold the build instructions.

## Examples

The `examples` directory holds three specifications
that exercise every section described here.
`examples/table1.toml` declares tables,
and the CSV and Parquet classes that read and write them.
`examples/table2.toml` declares the aggregate types
that a column of a table can hold.
`examples/dataset1.toml` declares datasets of n-dimensional arrays,
and the HDF5 classes that read and write those.
Each one generates a header of its own:

```bash
codegen-cpp generate examples/table1.toml
```

The tutorials build the same things one step at a time.
[Convert a CSV file into a Parquet file](../tutorials/convert-a-csv-file-into-a-parquet-file.md)
starts with tables,
[Store nested columns in a Parquet file](../tutorials/store-nested-columns-in-a-parquet-file.md)
continues with the aggregate types,
and [Fill an HDF5 file one window at a time](../tutorials/fill-an-hdf5-file-one-window-at-a-time.md)
covers the datasets.
