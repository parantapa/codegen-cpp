# How to write a specification from a data file

The table of a wide file is tedious to write by hand.
`make-config` writes a first draft of one from the file itself.
Use `make-config csv` for a CSV file,
and `make-config parquet` for a Parquet one:

```bash
codegen-cpp make-config csv measurements.csv.gz
```

This reads the columns of the file with pyarrow,
and writes `measurements.toml` beside it.
The draft holds the table that the file is read into.
It also holds a reader that reads it,
and a writer that writes it back out.
If you want the draft somewhere else, pass `--output` (`-o`).
If a CSV file changes type further down than pyarrow reads,
pass `--read-all`.
The [command line reference](../reference/command-line-interface.md)
describes both options,
and what `make-config` makes of the columns of a file.

Then edit the draft.
Every part that ends at a scalar type is given a default,
so a draft reads a file with holes in it rather than throwing.
To make a null an error, drop that key from `default`.

The writer is given the same `name_in_file` as the reader.
A table read out of one file is then written back into its like.
To write the names of the table instead, drop that section.
The [specification reference](../reference/specification.md)
describes every section a draft can hold.

Generate the header from the draft
the way you generate one from any specification:

```bash
codegen-cpp generate measurements.toml
```
