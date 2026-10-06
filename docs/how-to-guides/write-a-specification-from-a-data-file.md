# How to write a specification from a data file

The table of a wide file is tedious to write by hand.
`make-config` writes a first draft of one from the file itself.
Use `make-config csv` for a CSV file,
and `make-config parquet` for a Parquet one:

```bash
codegen-cpp make-config csv measurements.csv.gz
```

This command reads the columns of the file with pyarrow,
and writes `measurements.toml` beside it.
The draft holds the table that the file is read into.
It also holds a reader that reads it,
and a writer that writes it back out.
If you want the draft somewhere else, pass `--output` (`-o`).
If a column of a CSV file changes type below the part that pyarrow reads,
pass `--read-all`.
The [command line reference](../reference/command-line-interface.md)
describes both options,
and what `make-config` makes of the columns of a file.

Then, before you edit the draft, read the comments in it.
The comment at the top says what pyarrow inferred the types from.
If the file holds columns that no table can hold,
that comment also lists them, each with the reason it was left out.
If pyarrow reads a CSV column as a type that no table holds, such as a date,
the draft declares the column `str`.
A `# read as '...'` comment after the column names the type that pyarrow read.
If a column needs another type, change its `type`.

The draft gives a default to every part that ends at a scalar type.
As a result, the generated reader reads a file with nulls in it,
and does not throw.
To make a null in one part an error,
drop the key of that part from `default`.

The draft gives the writer the same `name_in_file` as the reader.
As a result, the writer uses the same column names
as the file that the reader read.
To write the names of the table instead,
drop the `name_in_file` section of the writer.
The [specification reference](../reference/specification.md)
describes every section a draft can hold.

Generate the header from the draft
the way you generate one from any specification:

```bash
codegen-cpp generate measurements.toml
```
