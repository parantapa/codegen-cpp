"""Tests for the generate command and the header rendering."""

from pathlib import Path

from click.testing import CliRunner

from codegen_cpp.cli import cli
from codegen_cpp.codegen import (
    render_csv_reader,
    render_csv_writer,
    render_parquet_reader,
    render_parquet_writer,
    render_table,
)
from codegen_cpp.spec import (
    Column,
    CsvReader,
    CsvWriter,
    ParquetReader,
    ParquetWriter,
    ScalarType,
    Table,
)

EXAMPLE = Path(__file__).parent.parent / "examples" / "example1.toml"

TABLE = Table(
    name="Point",
    columns=[
        Column(name="id", type=ScalarType.u32),
        Column(name="label", type=ScalarType.str),
    ],
)


def test_render_table() -> None:
    """The rendered header declares a row struct and a column store."""
    header = render_table(TABLE)

    assert "#pragma once" in header
    assert "struct PointRow {" in header
    assert "    std::uint32_t id;" in header
    assert "    std::string label;" in header
    assert "struct Point {" in header
    assert "    std::vector<std::uint32_t> id;" in header
    assert "    std::vector<std::string> label;" in header
    assert "void push_back(const PointRow& row) {" in header
    assert "        const std::uint32_t& id_," in header
    assert "        const std::string& label_) {" in header
    assert "        id.push_back(id_);" in header
    assert "PointRow operator[](std::size_t i) const {" in header


def test_generate_writes_one_header_per_table(tmp_path: Path) -> None:
    """Generate writes a header named after every table of the spec."""
    result = CliRunner().invoke(
        cli, ["generate", str(EXAMPLE), "--output-dir", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output

    header = tmp_path / "Measurement.hpp"
    assert header.is_file()
    assert "struct MeasurementRow {" in header.read_text()


def test_generate_creates_missing_output_dir(tmp_path: Path) -> None:
    """Generate creates the output directory when it does not exist."""
    output_dir = tmp_path / "nested" / "include"
    result = CliRunner().invoke(cli, ["generate", str(EXAMPLE), "-o", str(output_dir)])

    assert result.exit_code == 0, result.output
    assert (output_dir / "Measurement.hpp").is_file()


def test_generate_reports_invalid_spec(tmp_path: Path) -> None:
    """An invalid spec is reported as an error instead of a traceback."""
    spec_file = tmp_path / "spec.toml"
    spec_file.write_text('[[table]]\nname = "t"\ncolumns = []\n')

    result = CliRunner().invoke(cli, ["generate", str(spec_file), "-o", str(tmp_path)])

    assert result.exit_code != 0
    assert "has no columns" in result.output


READER = CsvReader(
    name="PointReader",
    table="Point",
    default_values={"label": "n/a"},
)


def test_render_csv_reader() -> None:
    """The rendered header defines a reader class over the table header."""
    header = render_csv_reader(READER, TABLE)

    assert '#include "Point.hpp"' in header
    assert "#include <arrow/csv/api.h>" in header
    assert "class PointReader {" in header
    assert "PointReader(const std::string& csv_file, std::size_t batch_size," in header
    assert "bool use_threads = false," in header
    assert "std::int32_t block_size = default_block_size," in header
    assert "std::optional<arrow::Compression::type> compression =" in header
    assert "std::nullopt)" in header
    assert "std::int32_t default_block_size = 128 * 1024 * 1024;" in header
    assert "bool has_more_batches() {" in header
    assert "Point read_batch() {" in header


def test_render_csv_reader_column_types() -> None:
    """The reader pins the Arrow types of the columns it reads."""
    header = render_csv_reader(READER, TABLE)

    assert '"id",' in header
    assert '{"id", arrow::uint32()},' in header
    assert '{"label", arrow::utf8()},' in header
    assert "static_cast<const arrow::UInt32Array*>(" in header
    assert "static_cast<const arrow::StringArray*>(" in header


def test_render_csv_reader_null_handling() -> None:
    """Only the columns that are not nullable are checked for nulls."""
    header = render_csv_reader(READER, TABLE)

    # 'id' is column 0 and is not nullable; 'label' is column 1 and is.
    assert "if (batch.column(0)->null_count() != 0) {" in header
    assert "\"column 'id' contains null values\"" in header
    assert "if (batch.column(1)->null_count() != 0) {" not in header

    # Nulls of a nullable column are read as the default value.
    assert "column_id->Value(i)," in header
    assert (
        'column_label->IsNull(i) ? std::string("n/a") '
        ": column_label->GetString(i)" in header
    )


def test_generate_writes_one_header_per_csv_reader(tmp_path: Path) -> None:
    """Generate writes a header for every CSV reader of the spec."""
    result = CliRunner().invoke(
        cli, ["generate", str(EXAMPLE), "--output-dir", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output

    header = tmp_path / "MeasurementCsvReader.hpp"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "Measurement.hpp",
        "MeasurementCsvReader.hpp",
        "MeasurementCsvWriter.hpp",
        "MeasurementParquetReader.hpp",
        "MeasurementParquetWriter.hpp",
        "Station.hpp",
        "StationCsvReader.hpp",
        "StationCsvWriter.hpp",
    ]

    text = header.read_text()
    assert "class MeasurementCsvReader {" in text
    assert '#include "Measurement.hpp"' in text
    assert "Measurement read_batch() {" in text


PARQUET_READER = ParquetReader(
    name="PointParquetReader",
    table="Point",
    default_values={"label": "n/a"},
)


def test_render_parquet_reader() -> None:
    """The rendered header defines a reader class over the table header."""
    header = render_parquet_reader(PARQUET_READER, TABLE)

    assert '#include "Point.hpp"' in header
    assert "#include <parquet/arrow/reader.h>" in header
    assert "class PointParquetReader {" in header
    assert "PointParquetReader(const std::string& parquet_file," in header
    assert "std::size_t batch_size)" in header
    assert "bool has_more_batches() {" in header
    assert "Point read_batch() {" in header


def test_render_parquet_reader_reads_record_batches() -> None:
    """The reader projects the columns it needs and reads record batches."""
    header = render_parquet_reader(PARQUET_READER, TABLE)

    assert "parquet::arrow::OpenFile(" in header
    assert "reader_->set_batch_size(" in header
    assert 'field_index(*schema, "id", arrow::uint32()),' in header
    assert 'field_index(*schema, "label", arrow::utf8()),' in header
    assert "reader_->GetRecordBatchReader(row_groups, columns)" in header
    assert "batches_->ReadNext(&batch)" in header
    assert "static_cast<const arrow::UInt32Array*>(" in header
    assert "static_cast<const arrow::StringArray*>(" in header


def test_render_parquet_reader_checks_the_schema() -> None:
    """The reader verifies the columns it is given, in order."""
    header = render_parquet_reader(PARQUET_READER, TABLE)

    assert "if (schema.num_fields() != 2) {" in header
    assert 'if (schema.field(0)->name() != "id") {' in header
    assert 'if (schema.field(1)->name() != "label") {' in header


def test_render_parquet_reader_null_handling() -> None:
    """Only the columns that are not nullable are checked for nulls."""
    header = render_parquet_reader(PARQUET_READER, TABLE)

    assert "if (batch.column(0)->null_count() != 0) {" in header
    assert "\"column 'id' of '\"" in header
    assert "if (batch.column(1)->null_count() != 0) {" not in header

    assert "column_id->Value(i)," in header
    assert (
        'column_label->IsNull(i) ? std::string("n/a") '
        ": column_label->GetString(i)" in header
    )


def test_generate_writes_one_header_per_parquet_reader(tmp_path: Path) -> None:
    """Generate writes a header for every Parquet reader of the spec."""
    result = CliRunner().invoke(
        cli, ["generate", str(EXAMPLE), "--output-dir", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output

    header = tmp_path / "MeasurementParquetReader.hpp"
    text = header.read_text()
    assert "class MeasurementParquetReader {" in text
    assert '#include "Measurement.hpp"' in text
    assert "Measurement read_batch() {" in text


WRITER = CsvWriter(name="PointCsvWriter", table="Point")


def test_render_csv_writer() -> None:
    """The rendered header defines a writer class over the table header."""
    header = render_csv_writer(WRITER, TABLE)

    assert '#include "Point.hpp"' in header
    assert "#include <arrow/csv/api.h>" in header
    assert "class PointCsvWriter {" in header
    assert "explicit PointCsvWriter(" in header
    assert "const std::string& csv_file," in header
    assert (
        "std::optional<arrow::Compression::type> compression = std::nullopt," in header
    )
    assert "int compression_level = arrow::util::kUseDefaultCompressionLevel)" in header
    assert "void write_batch(const Point& table) {" in header
    assert "void close() {" in header
    assert "~PointCsvWriter() {" in header


def test_render_csv_writer_builds_every_column() -> None:
    """Every column is built with the Arrow builder of its type."""
    header = render_csv_writer(WRITER, TABLE)

    assert 'arrow::field("id", arrow::uint32()),' in header
    assert 'arrow::field("label", arrow::utf8()),' in header
    assert "arrow::UInt32Builder builder_id;" in header
    assert "arrow::StringBuilder builder_label;" in header
    assert "builder_id.AppendValues(table.id)" in header
    assert "builder_label.AppendValues(table.label)" in header
    assert "writer_->WriteRecordBatch(*batch)" in header


def test_generate_writes_one_header_per_csv_writer(tmp_path: Path) -> None:
    """Generate writes a header for every CSV writer of the spec."""
    spec_file = tmp_path / "spec.toml"
    spec_file.write_text(
        "[[table]]\n"
        'name = "Point"\n'
        'columns = [{ name = "id", type = "u32" }]\n'
        "\n"
        "[[csv_writer]]\n"
        'name = "PointCsvWriter"\n'
        'table = "Point"\n'
    )
    output_dir = tmp_path / "out"

    result = CliRunner().invoke(
        cli, ["generate", str(spec_file), "--output-dir", str(output_dir)]
    )

    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in output_dir.iterdir()) == [
        "Point.hpp",
        "PointCsvWriter.hpp",
    ]
    assert "class PointCsvWriter {" in (output_dir / "PointCsvWriter.hpp").read_text()


PARQUET_WRITER = ParquetWriter(name="PointParquetWriter", table="Point")


def test_render_parquet_writer() -> None:
    """The rendered header defines a writer class over the table header."""
    header = render_parquet_writer(PARQUET_WRITER, TABLE)

    assert '#include "Point.hpp"' in header
    assert "#include <parquet/arrow/writer.h>" in header
    assert "class PointParquetWriter {" in header
    assert "explicit PointParquetWriter(" in header
    assert "const std::string& parquet_file," in header
    assert "void write_batch(const Point& table) {" in header
    assert "void close() {" in header
    assert "~PointParquetWriter() {" in header


def test_render_parquet_writer_writes_record_batches() -> None:
    """The writer builds the columns and writes them as record batches."""
    header = render_parquet_writer(PARQUET_WRITER, TABLE)

    assert 'arrow::field("id", arrow::uint32()),' in header
    assert "arrow::UInt32Builder builder_id;" in header
    assert "arrow::StringBuilder builder_label;" in header
    assert "parquet::arrow::FileWriter::Open(" in header
    assert ".compression(compression)" in header
    assert "arrow::Compression::type compression = arrow::Compression::ZSTD" in header
    assert "std::int64_t default_row_group_length = 128000;" in header
    assert "writer_->WriteRecordBatch(*batch)" in header


def test_generate_writes_one_header_per_parquet_writer(tmp_path: Path) -> None:
    """Generate writes a header for every Parquet writer of the spec."""
    spec_file = tmp_path / "spec.toml"
    spec_file.write_text(
        "[[table]]\n"
        'name = "Point"\n'
        'columns = [{ name = "id", type = "u32" }]\n'
        "\n"
        "[[parquet_writer]]\n"
        'name = "PointParquetWriter"\n'
        'table = "Point"\n'
    )
    output_dir = tmp_path / "out"

    result = CliRunner().invoke(
        cli, ["generate", str(spec_file), "--output-dir", str(output_dir)]
    )

    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in output_dir.iterdir()) == [
        "Point.hpp",
        "PointParquetWriter.hpp",
    ]
    text = (output_dir / "PointParquetWriter.hpp").read_text()
    assert "class PointParquetWriter {" in text


def test_render_csv_reader_infers_the_compression() -> None:
    """The reader guesses the codec from the name of the file it reads."""
    header = render_csv_reader(READER, TABLE)

    assert "#include <arrow/io/compressed.h>" in header
    assert 'if (path.ends_with(".gz")) {' in header
    assert "return arrow::Compression::GZIP;" in header
    assert 'if (path.ends_with(".zst")) {' in header
    assert "return arrow::Compression::ZSTD;" in header
    assert "compression.value_or(compression_of(csv_file_))" in header
    assert "arrow::io::CompressedInputStream::Make(codec_.get(), input)" in header


def test_render_csv_writer_infers_the_compression() -> None:
    """The writer guesses the codec from the name of the file it writes."""
    header = render_csv_writer(WRITER, TABLE)

    assert "#include <arrow/io/compressed.h>" in header
    assert 'if (path.ends_with(".gz")) {' in header
    assert "return arrow::Compression::ZSTD;" in header
    assert "compression.value_or(compression_of(csv_file_))" in header
    assert "arrow::util::CodecOptions(compression_level)" in header
    assert "arrow::io::CompressedOutputStream::Make(codec_.get(), output_)" in header
