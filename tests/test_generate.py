"""Tests for the generate command and the header rendering."""

from pathlib import Path

from click.testing import CliRunner

from codegen_cpp.cli import cli
from codegen_cpp.codegen import (
    render_csv_reader,
    render_csv_writer,
    render_dataset,
    render_parquet_reader,
    render_parquet_writer,
    render_table,
)
from codegen_cpp.spec import (
    Column,
    CsvReader,
    CsvWriter,
    Dataset,
    NdArray,
    ParquetReader,
    ParquetWriter,
    ScalarType,
    Table,
)

EXAMPLE = Path(__file__).parent.parent / "examples" / "table1.toml"

TABLE = Table(
    name="Point",
    columns=[
        Column(name="id", type=ScalarType.u32),
        Column(name="label", type=ScalarType.str),
    ],
)


def test_render_table() -> None:
    """The rendered header declares a column store with a nested row struct."""
    header = render_table(TABLE)

    assert "#pragma once" in header
    assert "struct Point {" in header
    assert "    struct row_type {" in header
    assert "        std::uint32_t id;" in header
    assert "        std::string label;" in header
    assert "    std::vector<std::uint32_t> id;" in header
    assert "    std::vector<std::string> label;" in header
    assert "void push_back(const row_type& row) {" in header
    assert "        const std::uint32_t& id_," in header
    assert "        const std::string& label_) {" in header
    assert "        id.push_back(id_);" in header
    assert "row_type operator[](std::size_t i) const {" in header
    assert "    Point() = default;" in header
    assert "    Point(const Point&) = delete;" in header
    assert "    Point& operator=(const Point&) = delete;" in header
    assert "    Point(Point&&) = default;" in header
    assert "    Point& operator=(Point&&) = default;" in header


def test_generate_writes_one_header_per_table(tmp_path: Path) -> None:
    """Generate writes a header named after every table of the spec."""
    result = CliRunner().invoke(
        cli, ["generate", str(EXAMPLE), "--output-dir", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output

    header = tmp_path / "Measurement.hpp"
    assert header.is_file()
    assert "struct row_type {" in header.read_text()


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
    assert "std::size_t batch_size," in header
    assert "std::int64_t buffer_size = default_buffer_size)" in header
    assert "bool has_more_batches() {" in header
    assert "Point read_batch() {" in header


def test_render_parquet_reader_sets_the_buffer_size() -> None:
    """The reader reads through a buffer of the size it is given."""
    header = render_parquet_reader(PARQUET_READER, TABLE)

    assert (
        "static constexpr std::int64_t default_buffer_size = 128 * 1024 * 1024;"
        in header
    )
    assert "if (buffer_size <= 0) {" in header
    assert "parquet::ReaderProperties reader_properties(" in header
    assert "reader_properties.enable_buffered_stream();" in header
    assert "reader_properties.set_buffer_size(buffer_size);" in header


def test_render_parquet_reader_reads_record_batches() -> None:
    """The reader projects the columns it needs and reads record batches."""
    header = render_parquet_reader(PARQUET_READER, TABLE)

    assert "parquet::arrow::FileReaderBuilder builder;" in header
    assert "builder.Open(std::move(input), reader_properties)" in header
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


NDARRAY_EXAMPLE = Path(__file__).parent.parent / "examples" / "ndarray.toml"

DATASET = Dataset(
    name="TileData",
    dims=["row", "col"],
    arrays=[
        NdArray(name="burn_time", type=ScalarType.f32),
        NdArray(name="state", type=ScalarType.i8),
    ],
)


def test_render_dataset() -> None:
    """The rendered header defines a struct of mdspans over owned memory."""
    header = render_dataset(DATASET)

    assert "#pragma once" in header
    assert "#include <experimental/mdspan>" in header
    assert "struct TileData {" in header
    assert "static constexpr std::size_t rank = 2;" in header
    assert "std::vector<std::size_t> dims;" in header

    # Every array owns its memory and hands out an mdspan over it.
    assert "std::unique_ptr<float[]> _mem_burn_time;" in header
    assert "span_type<float> burn_time;" in header
    assert "std::unique_ptr<std::int8_t[]> _mem_state;" in header
    assert "span_type<std::int8_t> state;" in header


def test_render_dataset_constructor_takes_every_dim() -> None:
    """The constructor takes one size per dimension and allocates the arrays."""
    header = render_dataset(DATASET)

    assert "TileData(" in header
    assert "        std::size_t row," in header
    assert "        std::size_t col)" in header
    assert ": dims{row, col}," in header
    assert "std::make_unique_for_overwrite<float[]>(" in header
    assert "burn_time(_mem_burn_time.get(), row, col)," in header
    assert "state(_mem_state.get(), row, col) {" in header


def test_render_dataset_is_column_major_by_default() -> None:
    """Without `row_major` the arrays are stored column major."""
    header = render_dataset(DATASET)

    assert "std::experimental::layout_left>;" in header
    assert "stored in column major order" in header
    assert "so 'row' varies fastest" in header
    assert "layout_right" not in header


def test_render_dataset_row_major() -> None:
    """With `row_major` the arrays are stored row major."""
    header = render_dataset(DATASET.model_copy(update={"row_major": True}))

    assert "std::experimental::layout_right>;" in header
    assert "stored in row major order" in header
    assert "so 'col' varies fastest" in header
    assert "layout_left" not in header


def test_render_dataset_is_not_copyable() -> None:
    """A dataset owns its memory, so it may not be copied."""
    header = render_dataset(DATASET)

    assert "TileData(const TileData&) = delete;" in header
    assert "TileData& operator=(const TileData&) = delete;" in header


def test_render_dataset_of_every_rank() -> None:
    """The rank of the mdspan follows the number of dims."""
    for dims in (["tick"], ["row", "col"], ["tick", "row", "col"]):
        dataset = Dataset(
            name="D",
            dims=dims,
            arrays=[NdArray(name="a", type=ScalarType.f64)],
        )
        header = render_dataset(dataset)

        assert f"static constexpr std::size_t rank = {len(dims)};" in header
        arguments = ", ".join(dims)
        assert f"a(_mem_a.get(), {arguments}) {{" in header


def test_generate_writes_one_header_per_dataset(tmp_path: Path) -> None:
    """Generate writes a header named after every dataset of the spec."""
    result = CliRunner().invoke(
        cli, ["generate", str(NDARRAY_EXAMPLE), "--output-dir", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output

    for name in ("TickData", "TileData", "SimOutput"):
        header = tmp_path / f"{name}.hpp"
        assert header.is_file()
        assert f"struct {name} {{" in header.read_text()

    # Only TileData asks for row major storage in the example.
    assert "layout_right" in (tmp_path / "TileData.hpp").read_text()
    assert "layout_left" in (tmp_path / "SimOutput.hpp").read_text()
