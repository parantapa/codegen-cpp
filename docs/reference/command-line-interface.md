# The command line interface

`codegen-cpp` holds three commands.
`generate` writes a header from a specification.
`make-config` writes a first draft of a specification from a data file.
`debug` reports what the tool makes of a specification.

## generate

`codegen-cpp generate SPEC_FILE`

This writes every section of the specification into a single header.
The header sits beside the specification it was generated from,
under the same name with `.hpp` in place of the extension,
so `spec.toml` becomes `spec.hpp` and `weather.toml` becomes `weather.hpp`.
`--output-file` (`-o`) writes it somewhere else instead:

```bash
codegen-cpp generate spec.toml --output-file include/measurements.hpp
```

The directories of the output file are created if they are missing,
and an output file that is already there is overwritten.

## make-config csv

`codegen-cpp make-config csv DATA_FILE`

```bash
codegen-cpp make-config csv measurements.csv.gz
```

This reads the columns of the file with pyarrow,
and writes `measurements.toml` beside it.
The specification holds the table that the file is read into,
a reader that reads it, and a writer that writes it back out.
`--output-file` is spelled `--output` (`-o`) here.
The default drops the suffixes of both the format and the codec,
so `measurements.csv.gz` and `measurements.csv`
are both described by `measurements.toml`.
An output file that is already there is overwritten.

The types are the ones pyarrow infers.
By default, it infers them from the first block of the file,
which is a megabyte of it.
A column that is integral for its first megabyte
and turns into text further down is declared `i64`.
It is then read as one until the file throws.

`--read-all` infers them from every row instead,
which types such a column by all of it.
The cost is that the whole file is read into memory.
The specification says which of the two it was generated with.

Note that the default reads more of the file than it infers from.
The streaming reader reads ahead,
by about ten megabytes at the default block size.
A file smaller than that is read from end to end,
and a file of any size above it is not.
Neither one holds more than a block at a time,
which is what `--read-all` gives up.

A column that a CSV holds but a table does not, such as a date,
is declared as `str` and noted in a comment.
Arrow converts such a column to a string on the way in.

The columns of a data file are rarely C++ identifiers,
so each one is turned into one:

- Whatever cannot appear in an identifier becomes an underscore.
- A run of underscores becomes one underscore.
- A name that begins with a digit is prefixed with an underscore.
- A name that C++ keeps for itself is followed by an underscore.

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

A file that names two of its columns the same
is reported rather than described.
A reader selects its columns by name,
and cannot tell those two apart.

## make-config parquet

`codegen-cpp make-config parquet DATA_FILE`

`make-config parquet` writes the same three sections,
named `MeasurementsParquetReader` and `MeasurementsParquetWriter`,
and everything above about names and defaults holds here too.
Two things differ.

Nothing is inferred and nothing but the footer is read,
because a Parquet file carries its schema inside it.
There is no `--read-all`, and no sampling to go wrong.

A group of the file becomes an aggregate type of its own,
named after the flattened key that reaches it.
A `LIST` becomes a `vector`, a `MAP` a `map`,
and a plain group a `struct`.
Each one is declared above the types that hold it:

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
so `biblio.first_page` is renamed and `topics.element.score` is defaulted.
A key that ends at an aggregate type takes no default.

A column stored as something no table can hold, such as a timestamp,
is left out rather than declared as something it is not.
A Parquet reader matches the type of what it reads exactly.
A reader over a table of scalar columns throws from its constructor,
and one over a table holding an aggregate type throws on the first batch.
A column of a group is left out whole
where anything below it cannot be held.
Each one is named in a comment at the top of the specification,
and reported on the command line.
A file that holds nothing a table can hold is an error.

A column left out costs nothing else.
A Parquet reader selects the columns it wants by name,
so the ones that are left read as they always do.

## debug parse-spec

`codegen-cpp debug parse-spec SPEC_FILE`

This reports how a specification is parsed, without generating anything:

```bash
codegen-cpp debug parse-spec examples/table1.toml
```
