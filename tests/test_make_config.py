"""Tests for generating a specification out of a data file."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from codegen_cpp.cli import cli
from codegen_cpp.codegen import render_spec
from codegen_cpp.make_config import (
    base_name,
    config_file,
    config_names,
    csv_config,
    identifier,
    parquet_config,
    read_csv_columns,
    render_config,
    toml_key,
    toml_string,
    type_name,
    unique,
)
from codegen_cpp.spec import ScalarType, parse_spec

CSV = (
    "Station ID,temp (C),temp-C,note,flag,1st,class,,empty,when\n"
    "1,1.5,2.5,a,true,7,x,q,,2024-01-02\n"
    "2,,3.5,b,false,8,y,r,,2024-01-03\n"
)


def write_csv(tmp_path: Path, name: str = "readings.csv", text: str = CSV) -> Path:
    """Write TEXT to a CSV file inside TMP_PATH and return its path."""
    data_file = tmp_path / name
    data_file.write_text(text)
    return data_file


def test_identifier_keeps_a_name_that_is_one() -> None:
    """A name that is already an identifier is used as it is."""
    assert identifier("station_id", "x") == "station_id"
    assert identifier("Temp2", "x") == "Temp2"


def test_identifier_replaces_what_may_not_appear_in_one() -> None:
    """Everything an identifier may not hold becomes an underscore."""
    assert identifier("Station ID", "x") == "Station_ID"
    assert identifier("temp (C)", "x") == "temp_C"
    assert identifier("a.b/c", "x") == "a_b_c"


def test_identifier_collapses_and_trims_underscores() -> None:
    """A run of underscores becomes one, and the ends are trimmed."""
    assert identifier("a   b", "x") == "a_b"
    assert identifier("  name  ", "x") == "name"
    assert identifier("__name__", "x") == "name"


def test_identifier_does_not_begin_with_a_digit() -> None:
    """An identifier may not begin with a digit."""
    assert identifier("1st", "x") == "_1st"
    assert identifier("2024 total", "x") == "_2024_total"


def test_identifier_steps_around_a_keyword() -> None:
    """A column named after a C++ keyword is named beside it instead."""
    assert identifier("class", "x") == "class_"
    assert identifier("int", "x") == "int_"
    assert identifier("Class", "x") == "Class"


def test_identifier_falls_back_when_nothing_is_left() -> None:
    """A name of punctuation alone falls back rather than becoming nothing."""
    assert identifier("", "column_3") == "column_3"
    assert identifier("---", "column_3") == "column_3"


def test_unique_numbers_the_repeated_names_apart() -> None:
    """Two names that become one identifier are numbered apart, in order."""
    assert unique(["a", "b", "a", "a"]) == ["a", "b", "a_2", "a_3"]


def test_unique_skips_a_number_that_is_taken() -> None:
    """Numbering a name apart does not take a name that is already used."""
    assert unique(["a", "a_2", "a"]) == ["a", "a_2", "a_3"]


def test_base_name_drops_the_suffixes_of_the_format_and_the_codec() -> None:
    """A file is named after what it holds, not after how it is stored."""
    assert base_name(Path("measurements.parquet")) == "measurements"
    assert base_name(Path("measurements.csv")) == "measurements"
    assert base_name(Path("measurements.csv.gz")) == "measurements"
    assert base_name(Path("/tmp/a/measurements.tsv.zst")) == "measurements"
    assert base_name(Path("measurements")) == "measurements"


def test_type_name_is_one_capital_per_word() -> None:
    """A file name becomes a C++ type name the way the examples spell one."""
    assert type_name("station_data") == "StationData"
    assert type_name("measurements") == "Measurements"
    assert type_name("my-data 2024") == "MyData2024"
    assert type_name("2024") == "_2024"
    assert type_name("---") == "Data"


def test_config_names_are_derived_from_the_data_file() -> None:
    """The table, the reader and the writer are named after the file."""
    names = config_names(Path("/tmp/station_data.csv.gz"), "Csv")

    assert names.table == "StationData"
    assert names.reader == "StationDataCsvReader"
    assert names.writer == "StationDataCsvWriter"


def test_config_names_are_named_after_the_format() -> None:
    """A Parquet reader and writer are named the way a CSV one is."""
    names = config_names(Path("/tmp/station_data.parquet"), "Parquet")

    assert names.table == "StationData"
    assert names.reader == "StationDataParquetReader"
    assert names.writer == "StationDataParquetWriter"


def test_config_file_replaces_the_suffixes_with_toml() -> None:
    """The specification is written beside the file it describes."""
    assert config_file(Path("/tmp/a/readings.csv.gz")) == Path("/tmp/a/readings.toml")


def test_toml_string_escapes_what_a_basic_string_may_not_hold() -> None:
    """A name of a file reaches the specification as a TOML basic string."""
    assert toml_string("plain") == '"plain"'
    assert toml_string('a"b') == '"a\\"b"'
    assert toml_string("a\\b") == '"a\\\\b"'
    assert toml_string("a\tb") == '"a\\tb"'
    assert toml_string("a\x01b") == '"a\\u0001b"'


def test_toml_key_quotes_only_where_it_has_to() -> None:
    """A key that a bare key may spell is left bare."""
    assert toml_key("station_id") == "station_id"
    assert toml_key("_1st") == "_1st"
    assert toml_key("a b") == '"a b"'


def test_read_csv_columns_reads_the_names_and_the_types(tmp_path: Path) -> None:
    """The columns are read off the file, in the order it holds them."""
    columns = read_csv_columns(write_csv(tmp_path))

    assert [column.name for column in columns] == [
        "Station_ID",
        "temp_C",
        "temp_C_2",
        "note",
        "flag",
        "_1st",
        "class_",
        "column_8",
        "empty",
        "when",
    ]
    assert [column.name_in_file for column in columns[:3]] == [
        "Station ID",
        "temp (C)",
        "temp-C",
    ]
    assert [column.type for column in columns[:5]] == [
        ScalarType.i64,
        ScalarType.f64,
        ScalarType.f64,
        ScalarType.str,
        ScalarType.bool,
    ]


def test_read_csv_columns_reads_what_no_column_holds_as_a_string(
    tmp_path: Path,
) -> None:
    """A date and a column of nothing but nulls are read as strings."""
    columns = {column.name: column for column in read_csv_columns(write_csv(tmp_path))}

    assert columns["when"].type is ScalarType.str
    assert columns["when"].arrow_type == "date32[day]"
    assert columns["empty"].type is ScalarType.str
    assert columns["empty"].arrow_type == "null"


def test_read_csv_columns_reads_a_compressed_file(tmp_path: Path) -> None:
    """The compression of a file is guessed from its name."""
    import gzip

    data_file = tmp_path / "readings.csv.gz"
    data_file.write_bytes(gzip.compress(CSV.encode()))

    columns = read_csv_columns(data_file)

    assert [column.name for column in columns[:2]] == ["Station_ID", "temp_C"]


def write_late_change_csv(tmp_path: Path) -> Path:
    """
    Write a CSV whose first column stops being an integer past the first block.

    The rows before the change fill more than the block
    that the types are inferred from by default,
    so the head of the file and the whole of it disagree about the column.
    """
    data_file = tmp_path / "readings.csv"
    rows = "".join(f"{i},{i}\n" for i in range(150_000))
    data_file.write_text(f"a,b\n{rows}oops,7\n")

    assert data_file.stat().st_size > 1 << 20
    return data_file


def test_read_csv_columns_types_a_column_by_the_first_block(
    tmp_path: Path,
) -> None:
    """By default a column is typed by the head of the file."""
    columns = read_csv_columns(write_late_change_csv(tmp_path))

    assert [column.type for column in columns] == [ScalarType.i64, ScalarType.i64]


def test_read_csv_columns_reads_all_of_the_file(tmp_path: Path) -> None:
    """read_all types a column by every row rather than by the first block."""
    columns = read_csv_columns(write_late_change_csv(tmp_path), read_all=True)

    assert [column.type for column in columns] == [ScalarType.str, ScalarType.i64]


def test_read_all_agrees_on_a_file_of_one_block(tmp_path: Path) -> None:
    """A file that fits in one block is typed the same either way."""
    data_file = write_csv(tmp_path)

    head = read_csv_columns(data_file)
    whole = read_csv_columns(data_file, read_all=True)

    assert [column.type for column in head] == [column.type for column in whole]
    assert [column.name for column in head] == [column.name for column in whole]


def test_csv_config_says_how_the_types_were_inferred(tmp_path: Path) -> None:
    """A draft says where its types came from."""
    data_file = write_csv(tmp_path)

    assert "read off the first block of the file" in csv_config(data_file)
    assert "read off all of the file" in csv_config(data_file, read_all=True)


def test_make_config_reads_all_of_the_file(tmp_path: Path) -> None:
    """--read-all types a column by every row of the data file."""
    data_file = write_late_change_csv(tmp_path)
    output = tmp_path / "readings.toml"

    result = CliRunner().invoke(
        cli, ["make-config", "csv", str(data_file), "--read-all", "-o", str(output)]
    )

    assert result.exit_code == 0
    table = parse_spec(output).tables[0]
    assert [column.type for column in table.columns] == [
        ScalarType.str,
        ScalarType.i64,
    ]


def test_make_config_reads_the_first_block_by_default(tmp_path: Path) -> None:
    """Without --read-all the types come off the head of the data file."""
    data_file = write_late_change_csv(tmp_path)
    output = tmp_path / "readings.toml"

    result = CliRunner().invoke(
        cli, ["make-config", "csv", str(data_file), "-o", str(output)]
    )

    assert result.exit_code == 0
    table = parse_spec(output).tables[0]
    assert [column.type for column in table.columns] == [
        ScalarType.i64,
        ScalarType.i64,
    ]


def test_csv_config_parses_as_a_specification(tmp_path: Path) -> None:
    """What the command writes is a specification the generator accepts."""
    data_file = write_csv(tmp_path)
    spec_file = tmp_path / "readings.toml"
    spec_file.write_text(csv_config(data_file))

    spec = parse_spec(spec_file)

    assert [table.name for table in spec.tables] == ["Readings"]
    assert [reader.name for reader in spec.csv_readers] == ["ReadingsCsvReader"]
    assert [writer.name for writer in spec.csv_writers] == ["ReadingsCsvWriter"]

    table = spec.tables[0]
    assert [column.name for column in table.columns[:3]] == [
        "Station_ID",
        "temp_C",
        "temp_C_2",
    ]


def test_csv_config_names_every_renamed_column_in_the_file(tmp_path: Path) -> None:
    """A column the file spells differently is mapped by name_in_file."""
    data_file = write_csv(tmp_path)
    spec_file = tmp_path / "readings.toml"
    spec_file.write_text(csv_config(data_file))

    reader = parse_spec(spec_file).csv_readers[0]

    assert reader.name_in_file["Station_ID"] == "Station ID"
    assert reader.name_in_file["temp_C"] == "temp (C)"
    assert reader.name_in_file["class_"] == "class"

    # A column the table spells the way the file does is not renamed.
    assert "note" not in reader.name_in_file


def test_csv_config_writes_the_names_the_reader_reads(tmp_path: Path) -> None:
    """The writer is given the names the reader looks for."""
    data_file = write_csv(tmp_path)
    spec_file = tmp_path / "readings.toml"
    spec_file.write_text(csv_config(data_file))

    spec = parse_spec(spec_file)

    assert spec.csv_writers[0].name_in_file == spec.csv_readers[0].name_in_file
    assert spec.csv_writers[0].name_in_file["Station_ID"] == "Station ID"


def test_csv_config_renames_nothing_where_the_file_names_it_the_way(
    tmp_path: Path,
) -> None:
    """A file that names every column as the table does asks for no renaming."""
    data_file = write_csv(tmp_path, text="station_id,note\n1,a\n")
    spec_file = tmp_path / "readings.toml"
    spec_file.write_text(csv_config(data_file))

    spec = parse_spec(spec_file)

    assert "name_in_file" not in spec_file.read_text()
    assert spec.csv_readers[0].name_in_file == {}
    assert spec.csv_writers[0].name_in_file == {}


def test_csv_config_defaults_every_column(tmp_path: Path) -> None:
    """Every column takes a default, so no column of the file may not be null."""
    data_file = write_csv(tmp_path)
    spec_file = tmp_path / "readings.toml"
    spec_file.write_text(csv_config(data_file))

    spec = parse_spec(spec_file)
    reader = spec.csv_readers[0]

    assert set(reader.default) == {column.name for column in spec.tables[0].columns}
    assert reader.default["Station_ID"] == 0
    assert reader.default["temp_C"] == 0.0
    assert reader.default["flag"] is False
    assert reader.default["note"] == ""


def test_csv_config_renders_a_header(tmp_path: Path) -> None:
    """The specification generates the header it describes."""
    data_file = write_csv(tmp_path)
    spec_file = tmp_path / "readings.toml"
    spec_file.write_text(csv_config(data_file))

    header = render_spec(parse_spec(spec_file), spec_file)

    assert "struct Readings {" in header
    assert "class ReadingsCsvReader {" in header
    assert "class ReadingsCsvWriter {" in header
    assert '"Station ID",' in header
    assert "std::int64_t Station_ID;" in header


def test_csv_config_notes_a_type_no_column_holds(tmp_path: Path) -> None:
    """A column read as something no column holds says so."""
    config = csv_config(write_csv(tmp_path))

    assert "# read as 'date32[day]'" in config
    assert "# read as 'null'" in config


def test_make_config_writes_beside_the_data_file(tmp_path: Path) -> None:
    """Without --output the specification is named after the data file."""
    data_file = write_csv(tmp_path, "readings.csv.gz")
    data_file.write_bytes(__import__("gzip").compress(CSV.encode()))

    result = CliRunner().invoke(cli, ["make-config", "csv", str(data_file)])

    assert result.exit_code == 0
    assert (tmp_path / "readings.toml").exists()
    assert "readings.toml" in result.output


def test_make_config_writes_to_the_output_file(tmp_path: Path) -> None:
    """--output writes the specification somewhere else."""
    data_file = write_csv(tmp_path)
    output = tmp_path / "spec" / "readings.toml"

    result = CliRunner().invoke(
        cli, ["make-config", "csv", str(data_file), "--output", str(output)]
    )

    assert result.exit_code == 0
    assert output.exists()
    assert not (tmp_path / "readings.toml").exists()


def test_make_config_overwrites_the_output_file(tmp_path: Path) -> None:
    """A specification that is already there is replaced."""
    data_file = write_csv(tmp_path)
    output = tmp_path / "readings.toml"
    output.write_text("stale\n")

    result = CliRunner().invoke(
        cli, ["make-config", "csv", str(data_file), "-o", str(output)]
    )

    assert result.exit_code == 0
    assert "stale" not in output.read_text()


def test_make_config_reports_a_missing_data_file(tmp_path: Path) -> None:
    """A data file that is not there is reported rather than read."""
    result = CliRunner().invoke(
        cli, ["make-config", "csv", str(tmp_path / "no_such_file.csv")]
    )

    assert result.exit_code != 0


def test_make_config_reports_a_file_it_cannot_read(tmp_path: Path) -> None:
    """A file that holds no CSV is reported instead of raising."""
    data_file = tmp_path / "readings.csv"
    data_file.write_text("")

    result = CliRunner().invoke(cli, ["make-config", "csv", str(data_file)])

    assert result.exit_code != 0
    assert "Failed to read" in result.output


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("a,b\n1,2\n", ["a", "b"]),
        ("a b,a-b\n1,2\n", ["a_b", "a_b_2"]),
        ("a,A\n1,2\n", ["a", "A"]),
    ],
)
def test_csv_config_columns_are_unique(
    tmp_path: Path, header: str, expected: list[str]
) -> None:
    """Two columns of a file never become one column of a table."""
    data_file = write_csv(tmp_path, text=header)
    spec_file = tmp_path / "readings.toml"
    spec_file.write_text(csv_config(data_file))

    table = parse_spec(spec_file).tables[0]

    assert [column.name for column in table.columns] == expected


def test_csv_config_rejects_a_file_that_repeats_a_column_name(
    tmp_path: Path,
) -> None:
    """A reader selects its columns by name, so two of one name are an error."""
    data_file = write_csv(tmp_path, text="a,b,a\n1,2,3\n")

    with pytest.raises(ValueError, match="names more than one column 'a'"):
        csv_config(data_file)


def test_make_config_reports_a_repeated_column_name(tmp_path: Path) -> None:
    """The repeated name is reported rather than written out as a bad spec."""
    data_file = write_csv(tmp_path, text="a,b,a\n1,2,3\n")

    result = CliRunner().invoke(cli, ["make-config", "csv", str(data_file)])

    assert result.exit_code != 0
    assert "names more than one column 'a'" in result.output
    assert not (tmp_path / "readings.toml").exists()


def write_parquet(tmp_path: Path, fields: list[tuple[str, object]]) -> Path:
    """Write an empty Parquet file of FIELDS into TMP_PATH and return its path."""
    import pyarrow as pa
    import pyarrow.parquet

    schema = pa.schema(fields)
    table = pa.table(
        {field.name: pa.array([], type=field.type) for field in schema},
        schema=schema,
    )

    data_file = tmp_path / "works.parquet"
    pyarrow.parquet.write_table(table, data_file)
    return data_file


def nested_parquet(tmp_path: Path) -> Path:
    """Write a Parquet file holding one of every shape a group can have."""
    import pyarrow as pa

    return write_parquet(
        tmp_path,
        [
            ("Station ID", pa.int64()),
            ("keywords", pa.list_(pa.string())),
            ("ids", pa.map_(pa.string(), pa.string())),
            (
                "biblio",
                pa.struct([("volume", pa.string()), ("first page", pa.int32())]),
            ),
            ("topics", pa.list_(pa.struct([("name", pa.string())]))),
            ("affiliations", pa.list_(pa.list_(pa.string()))),
        ],
    )


def parquet_spec(tmp_path: Path, data_file: Path) -> Path:
    """Write the specification of DATA_FILE and return the file holding it."""
    spec_file = tmp_path / "works.toml"
    spec_file.write_text(render_config(parquet_config(data_file)))
    return spec_file


def test_parquet_config_declares_the_table_the_reader_and_the_writer(
    tmp_path: Path,
) -> None:
    """A Parquet file is described the way a CSV file is."""
    import pyarrow as pa

    data_file = write_parquet(tmp_path, [("a", pa.int32()), ("b", pa.string())])
    spec = parse_spec(parquet_spec(tmp_path, data_file))

    assert [table.name for table in spec.tables] == ["Works"]
    assert [reader.name for reader in spec.parquet_readers] == ["WorksParquetReader"]
    assert [writer.name for writer in spec.parquet_writers] == ["WorksParquetWriter"]
    assert not spec.csv_readers

    table = spec.tables[0]
    assert [(c.name, c.type) for c in table.columns] == [
        ("a", ScalarType.i32),
        ("b", ScalarType.str),
    ]


def test_parquet_config_declares_an_aggregate_per_group(tmp_path: Path) -> None:
    """A group of the file becomes the aggregate type of its shape."""
    spec = parse_spec(parquet_spec(tmp_path, nested_parquet(tmp_path)))

    vectors = {vector.name: vector for vector in spec.vectors}
    maps = {map_.name: map_ for map_ in spec.maps}
    structs = {struct.name: struct for struct in spec.structs}

    assert vectors["Keywords"].element is ScalarType.str
    assert maps["Ids"].key is ScalarType.str
    assert maps["Ids"].value is ScalarType.str
    assert [field.name for field in structs["Biblio"].fields] == [
        "volume",
        "first_page",
    ]

    # A group below a group is a type of its own, named after the key.
    assert vectors["Topics"].element == "TopicsElement"
    assert [field.name for field in structs["TopicsElement"].fields] == ["name"]
    assert vectors["Affiliations"].element == "AffiliationsElement"
    assert vectors["AffiliationsElement"].element is ScalarType.str


def test_parquet_config_names_every_part_by_its_flattened_key(
    tmp_path: Path,
) -> None:
    """A field of a group is renamed and defaulted by its flattened key."""
    reader = parse_spec(parquet_spec(tmp_path, nested_parquet(tmp_path)))
    reader = reader.parquet_readers[0]

    assert reader.name_in_file["Station_ID"] == "Station ID"
    assert reader.name_in_file["biblio.first_page"] == "first page"

    # Only a key that ends at a scalar takes a default.
    assert reader.default["keywords.element"] == ""
    assert reader.default["ids.value"] == ""
    assert reader.default["topics.element.name"] == ""
    assert reader.default["affiliations.element.element"] == ""
    assert "keywords" not in reader.default
    assert "biblio" not in reader.default


def test_parquet_config_writes_the_names_the_reader_reads(tmp_path: Path) -> None:
    """The writer names a field of a group the way the reader does."""
    spec = parse_spec(parquet_spec(tmp_path, nested_parquet(tmp_path)))

    writer = spec.parquet_writers[0]
    assert writer.name_in_file == spec.parquet_readers[0].name_in_file
    assert writer.name_in_file["Station_ID"] == "Station ID"
    assert writer.name_in_file["biblio.first_page"] == "first page"


def test_parquet_config_leaves_out_a_column_no_table_can_hold(
    tmp_path: Path,
) -> None:
    """A Parquet reader matches types exactly, so a column it cannot is skipped."""
    import pyarrow as pa

    data_file = write_parquet(
        tmp_path,
        [("a", pa.int32()), ("when", pa.timestamp("us")), ("b", pa.string())],
    )
    config = parquet_config(data_file)

    assert [name for name, _ in config.skipped] == ["when"]
    assert [column.name for column in config.columns] == ["a", "b"]

    spec = parse_spec(parquet_spec(tmp_path, data_file))
    assert [column.name for column in spec.tables[0].columns] == ["a", "b"]


def test_parquet_config_leaves_out_a_group_holding_one(tmp_path: Path) -> None:
    """A column is left out whole where anything below it cannot be held."""
    import pyarrow as pa

    data_file = write_parquet(
        tmp_path,
        [
            ("a", pa.int32()),
            ("stamps", pa.list_(pa.timestamp("us"))),
        ],
    )
    config = parquet_config(data_file)

    assert [name for name, _ in config.skipped] == ["stamps"]
    assert [column.name for column in config.columns] == ["a"]

    # The vector it would have needed is not declared either.
    assert config.aggregates == []


def test_parquet_config_rejects_a_map_no_key_can_hold(tmp_path: Path) -> None:
    """A map key is an integer or a string, so one of doubles is left out."""
    import pyarrow as pa

    data_file = write_parquet(
        tmp_path,
        [("a", pa.int32()), ("scores", pa.map_(pa.float64(), pa.int32()))],
    )
    config = parquet_config(data_file)

    assert [name for name, _ in config.skipped] == ["scores"]


def test_parquet_config_rejects_a_file_it_can_hold_nothing_of(
    tmp_path: Path,
) -> None:
    """A file of nothing a table can hold is reported rather than described."""
    import pyarrow as pa

    data_file = write_parquet(tmp_path, [("when", pa.timestamp("us"))])

    with pytest.raises(ValueError, match="holds no column that a table can hold"):
        parquet_config(data_file)


def test_parquet_config_rejects_a_repeated_column_name(tmp_path: Path) -> None:
    """A reader selects its columns by name, so two of one name are an error."""
    import pyarrow as pa

    data_file = write_parquet(tmp_path, [("a", pa.int32()), ("a", pa.string())])

    with pytest.raises(ValueError, match="names more than one column 'a'"):
        parquet_config(data_file)


def test_parquet_config_renders_a_header(tmp_path: Path) -> None:
    """The specification generates the header it describes."""
    spec_file = parquet_spec(tmp_path, nested_parquet(tmp_path))

    header = render_spec(parse_spec(spec_file), spec_file)

    assert "using Keywords = std::vector<std::string>;" in header
    assert "using Ids = std::map<std::string, std::string>;" in header
    assert "struct Biblio {" in header
    assert "class WorksParquetReader {" in header
    assert "class WorksParquetWriter {" in header
    assert '"Station ID"' in header
    assert '"first page"' in header


def test_parquet_config_says_it_read_the_schema(tmp_path: Path) -> None:
    """A draft says where its types came from, and they are not inferred."""
    import pyarrow as pa

    data_file = write_parquet(tmp_path, [("a", pa.int32())])

    assert "read off the schema the file carries" in render_config(
        parquet_config(data_file)
    )


def test_make_config_parquet_writes_beside_the_data_file(tmp_path: Path) -> None:
    """Without --output the specification is named after the data file."""
    data_file = nested_parquet(tmp_path)

    result = CliRunner().invoke(cli, ["make-config", "parquet", str(data_file)])

    assert result.exit_code == 0
    assert (tmp_path / "works.toml").exists()


def test_make_config_parquet_reports_what_it_left_out(tmp_path: Path) -> None:
    """A column that is not read is reported, not only written into a comment."""
    import pyarrow as pa

    data_file = write_parquet(
        tmp_path, [("a", pa.int32()), ("when", pa.timestamp("us"))]
    )

    result = CliRunner().invoke(cli, ["make-config", "parquet", str(data_file)])

    assert result.exit_code == 0
    assert "Left out" in result.output
    assert "when" in result.output
    assert "left out" in (tmp_path / "works.toml").read_text()


def test_make_config_parquet_has_no_read_all(tmp_path: Path) -> None:
    """A Parquet file carries its schema, so there is nothing to infer."""
    import pyarrow as pa

    data_file = write_parquet(tmp_path, [("a", pa.int32())])

    result = CliRunner().invoke(
        cli, ["make-config", "parquet", str(data_file), "--read-all"]
    )

    assert result.exit_code != 0
