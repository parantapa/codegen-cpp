"""Tests for the generate command and the header rendering."""

from pathlib import Path

from click.testing import CliRunner

from codegen_cpp.cli import cli
from codegen_cpp.codegen import (
    render_csv_reader,
    render_csv_writer,
    render_dataset,
    render_hdf5_reader,
    render_hdf5_writer,
    render_parquet_reader,
    render_parquet_writer,
    render_table,
)
from codegen_cpp.spec import (
    Column,
    CsvReader,
    CsvWriter,
    Dataset,
    Hdf5Reader,
    Hdf5Writer,
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
    assert "if (batch.column(0)->null_count() != 0) [[unlikely]] {" in header
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
    assert "if (buffer_size <= 0) [[unlikely]] {" in header
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

    assert "if (schema.num_fields() != 2) [[unlikely]] {" in header
    assert 'if (schema.field(0)->name() != "id") [[unlikely]] {' in header
    assert 'if (schema.field(1)->name() != "label") [[unlikely]] {' in header


def test_render_parquet_reader_null_handling() -> None:
    """Only the columns that are not nullable are checked for nulls."""
    header = render_parquet_reader(PARQUET_READER, TABLE)

    assert "if (batch.column(0)->null_count() != 0) [[unlikely]] {" in header
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


DATASET_EXAMPLE = Path(__file__).parent.parent / "examples" / "dataset1.toml"

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


def test_render_dataset_is_row_major_by_default() -> None:
    """Without `column_major` the arrays are stored row major."""
    header = render_dataset(DATASET)

    assert "std::experimental::layout_right>;" in header
    assert "stored in row major order" in header
    assert "so 'col' varies fastest" in header
    assert "layout_left" not in header


def test_render_dataset_column_major() -> None:
    """With `column_major` the arrays are stored column major."""
    header = render_dataset(DATASET.model_copy(update={"column_major": True}))

    assert "std::experimental::layout_left>;" in header
    assert "stored in column major order" in header
    assert "so 'row' varies fastest" in header
    assert "layout_right" not in header


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
        cli, ["generate", str(DATASET_EXAMPLE), "--output-dir", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output

    for name in ("Series", "Raster", "Volume"):
        header = tmp_path / f"{name}.hpp"
        assert header.is_file()
        assert f"struct {name} {{" in header.read_text()

    # Only Volume asks for column major storage in the example.
    assert "layout_right" in (tmp_path / "Raster.hpp").read_text()
    assert "layout_left" in (tmp_path / "Volume.hpp").read_text()


HDF5_READER = Hdf5Reader(name="read_tile_data", dataset="TileData")


def test_render_hdf5_reader() -> None:
    """The rendered header defines a function over the dataset header."""
    header = render_hdf5_reader(HDF5_READER, DATASET)

    assert "#pragma once" in header
    assert "#include <H5Cpp.h>" in header
    assert '#include "TileData.hpp"' in header
    assert "inline void read_tile_data(H5::H5File& file," in header
    assert "const std::string& group_path," in header
    assert "TileData& data) {" in header
    assert "const H5::Group group = file.openGroup(group_path);" in header


def test_render_hdf5_reader_declares_nothing_but_the_function() -> None:
    """The macros expand in place, so the header holds one function."""
    header = render_hdf5_reader(HDF5_READER, DATASET)

    # Everything else is a comment, an include, or indented inside the body.
    top_level = [
        line
        for line in header.splitlines()
        if line and not line.startswith((" ", "}", "#", "//"))
    ]
    assert len(top_level) == 1
    assert top_level[0].startswith("inline void read_tile_data(")

    assert "namespace" not in header
    assert "template" not in header


def test_render_hdf5_reader_reads_every_array_by_default() -> None:
    """Without include or exclude every array of the dataset is read."""
    header = render_hdf5_reader(HDF5_READER, DATASET)

    assert 'const std::string path = group_path + "/burn_time";' in header
    assert 'const std::string path = group_path + "/state";' in header
    assert 'if (!group.nameExists("burn_time")) [[unlikely]] {' in header
    assert 'const H5::DataSet array = group.openDataSet("state");' in header


def test_render_hdf5_reader_include() -> None:
    """An include list reads only the arrays it names."""
    reader = Hdf5Reader(name="read_seed", dataset="TileData", include=["state"])
    header = render_hdf5_reader(reader, DATASET)

    assert 'const std::string path = group_path + "/state";' in header
    assert "burn_time" not in header
    assert "// Read the array state" in header


def test_render_hdf5_reader_exclude() -> None:
    """An exclude list reads every array it does not name."""
    reader = Hdf5Reader(name="read_rest", dataset="TileData", exclude=["state"])
    header = render_hdf5_reader(reader, DATASET)

    assert 'const std::string path = group_path + "/burn_time";' in header
    assert "state" not in header


def test_render_hdf5_reader_pins_the_datatypes() -> None:
    """Every array is checked against the predefined type it declares."""
    header = render_hdf5_reader(HDF5_READER, DATASET)

    assert "const H5::DataType stored = array.getDataType();" in header
    assert "if (stored != H5::PredType::NATIVE_FLOAT) [[unlikely]] {" in header
    assert "if (stored != H5::PredType::NATIVE_INT8) [[unlikely]] {" in header
    assert "\"' is not stored as 'f32'\");" in header
    assert "\"' is not stored as 'i8'\");" in header

    # One comparison covers every property, so none is spelled out by hand.
    assert "H5T_" not in header
    assert "getClass()" not in header
    assert "getSign()" not in header


def test_render_hdf5_reader_checks_the_shape() -> None:
    """The rank and every extent are checked against the allocated dataset."""
    header = render_hdf5_reader(HDF5_READER, DATASET)

    assert "const H5::DataSpace space = array.getSpace();" in header
    assert "if (space.getSimpleExtentNdims() != 2) [[unlikely]] {" in header
    assert "std::array<hsize_t, TileData::rank> extents;" in header
    assert "space.getSimpleExtentDims(extents.data());" in header
    assert "for (std::size_t i = 0; i < TileData::rank; ++i) {" in header
    assert "const hsize_t declared = static_cast<hsize_t>(data.dims[i]);" in header
    assert "if (extents[i] != declared) [[unlikely]] {" in header


def test_render_hdf5_reader_of_an_unsigned_array() -> None:
    """An unsigned array is checked against the unsigned predefined type."""
    dataset = Dataset(
        name="Counts",
        dims=["row"],
        arrays=[NdArray(name="hits", type=ScalarType.u16)],
    )
    reader = Hdf5Reader(name="read_counts", dataset="Counts")
    header = render_hdf5_reader(reader, dataset)

    assert "if (stored != H5::PredType::NATIVE_UINT16) [[unlikely]] {" in header
    assert "H5T_" not in header


def test_render_hdf5_reader_reports_errors_as_runtime_errors() -> None:
    """Everything that goes wrong is reported as a std::runtime_error."""
    header = render_hdf5_reader(HDF5_READER, DATASET)

    assert "} catch (const H5::Exception& e) {" in header
    assert 'throw std::runtime_error("failed to read \'" + group_path + "\': " +' in (
        header
    )
    assert '"\' is not in the HDF5 file");' in header


def test_render_hdf5_reader_of_a_row_major_dataset_reads_in_place() -> None:
    """A row major dataset is stored the way HDF5 reads, so it reads directly."""
    header = render_hdf5_reader(HDF5_READER, DATASET)

    assert "array.read(data._mem_burn_time.get()," in header
    assert "H5::PredType::NATIVE_FLOAT);" in header
    assert "buffer" not in header
    assert "#include <vector>" not in header


def test_render_hdf5_reader_of_a_column_major_dataset_lays_out_again() -> None:
    """A column major dataset of rank two or more is laid out after reading."""
    header = render_hdf5_reader(
        HDF5_READER, DATASET.model_copy(update={"column_major": True})
    )

    assert "#include <vector>" in header
    assert "std::vector<float> buffer(data.size());" in header
    assert "array.read(buffer.data(), H5::PredType::NATIVE_FLOAT);" in header
    assert "std::size_t element = 0;" in header
    assert "for (std::size_t i0 = 0; i0 < data.dims[0]; ++i0) {" in header
    assert "for (std::size_t i1 = 0; i1 < data.dims[1]; ++i1) {" in header
    assert "data.burn_time[i0, i1] = buffer[element++];" in header


def test_render_hdf5_reader_unrolls_the_loops_of_every_rank() -> None:
    """The rank is known when the header is written, so the loops are unrolled."""
    dataset = Dataset(
        name="SimOutput",
        dims=["tick", "row", "col"],
        arrays=[NdArray(name="state", type=ScalarType.i8)],
        column_major=True,
    )
    reader = Hdf5Reader(name="read_sim_output", dataset="SimOutput")
    header = render_hdf5_reader(reader, dataset)

    assert "for (std::size_t i2 = 0; i2 < data.dims[2]; ++i2) {" in header
    assert "data.state[i0, i1, i2] = buffer[element++];" in header
    assert "for (std::size_t i3" not in header


def test_render_hdf5_reader_of_a_one_dimensional_dataset_reads_in_place() -> None:
    """Rank one is the same either way, so it reads directly."""
    dataset = Dataset(
        name="TickData",
        dims=["tick"],
        arrays=[NdArray(name="wind_speed", type=ScalarType.f32)],
    )
    reader = Hdf5Reader(name="read_tick_data", dataset="TickData")
    header = render_hdf5_reader(reader, dataset)

    assert "array.read(data._mem_wind_speed.get()," in header
    assert "buffer" not in header


def test_generate_writes_one_header_per_hdf5_reader(tmp_path: Path) -> None:
    """Generate writes a header named after every HDF5 reader of the spec."""
    result = CliRunner().invoke(
        cli, ["generate", str(DATASET_EXAMPLE), "--output-dir", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "Raster.hpp",
        "Series.hpp",
        "Volume.hpp",
        "read_raster.hpp",
        "read_raster_layers.hpp",
        "read_raster_mask.hpp",
        "read_series.hpp",
        "read_volume.hpp",
        "write_raster.hpp",
        "write_raster_layers.hpp",
        "write_raster_mask.hpp",
        "write_series.hpp",
        "write_volume.hpp",
    ]

    text = (tmp_path / "read_raster.hpp").read_text()
    assert '#include "Raster.hpp"' in text
    assert "inline void read_raster(H5::H5File& file," in text

    # 'read_raster_layers' excludes 'mask' and 'read_raster_mask' has only it.
    assert "mask" not in (tmp_path / "read_raster_layers.hpp").read_text()
    assert "elevation" not in (tmp_path / "read_raster_mask.hpp").read_text()

    # Only the reader of the column major dataset lays the elements out again.
    assert "buffer" in (tmp_path / "read_volume.hpp").read_text()
    assert "buffer" not in text


HDF5_WRITER = Hdf5Writer(name="write_tile_data", dataset="TileData")


def test_render_hdf5_writer() -> None:
    """The rendered header defines a function over the dataset header."""
    header = render_hdf5_writer(HDF5_WRITER, DATASET)

    assert "#pragma once" in header
    assert "#include <H5Cpp.h>" in header
    assert '#include "TileData.hpp"' in header
    assert "inline void write_tile_data(H5::H5File& file," in header
    assert "const std::string& group_path," in header
    assert "const TileData& data) {" in header


def test_render_hdf5_writer_declares_nothing_but_the_function() -> None:
    """The macros expand in place, so the header holds one function."""
    header = render_hdf5_writer(HDF5_WRITER, DATASET)

    top_level = [
        line
        for line in header.splitlines()
        if line and not line.startswith((" ", "}", "#", "//"))
    ]
    assert len(top_level) == 1
    assert top_level[0].startswith("inline void write_tile_data(")

    assert "namespace" not in header
    assert "template" not in header


def test_render_hdf5_writer_creates_the_groups_that_are_missing() -> None:
    """The path is walked a name at a time, creating what is not there."""
    header = render_hdf5_writer(HDF5_WRITER, DATASET)

    assert 'H5::Group group = file.openGroup("/");' in header
    assert "const std::size_t end = group_path.find('/', begin);" in header
    assert "group = group.nameExists(name) ? group.openGroup(name)" in header
    assert ": group.createGroup(name);" in header


def test_render_hdf5_writer_replaces_an_array_that_is_there() -> None:
    """An array the group already holds is unlinked and created again."""
    header = render_hdf5_writer(HDF5_WRITER, DATASET)

    assert 'if (group.nameExists("burn_time")) {' in header
    assert 'group.unlink("burn_time");' in header
    assert "const H5::DataSet array = group.createDataSet(" in header
    assert '"burn_time", H5::PredType::NATIVE_FLOAT, space);' in header


def test_render_hdf5_writer_builds_one_dataspace_for_every_array() -> None:
    """Every array shares the shape data was allocated with."""
    header = render_hdf5_writer(HDF5_WRITER, DATASET)

    assert "std::array<hsize_t, TileData::rank> extents;" in header
    assert "extents[i] = static_cast<hsize_t>(data.dims[i]);" in header
    assert "const H5::DataSpace space(static_cast<int>(TileData::rank)," in header


def test_render_hdf5_writer_include() -> None:
    """An include list writes only the arrays it names."""
    writer = Hdf5Writer(name="write_seed", dataset="TileData", include=["state"])
    header = render_hdf5_writer(writer, DATASET)

    assert 'group.createDataSet(\n                "state"' in header
    assert "burn_time" not in header
    assert "// Write the array state" in header


def test_render_hdf5_writer_exclude() -> None:
    """An exclude list writes every array it does not name."""
    writer = Hdf5Writer(name="write_rest", dataset="TileData", exclude=["state"])
    header = render_hdf5_writer(writer, DATASET)

    assert "burn_time" in header
    assert "state" not in header


def test_render_hdf5_writer_of_a_row_major_dataset_writes_in_place() -> None:
    """A row major dataset is stored the way HDF5 writes, so it goes as it is."""
    header = render_hdf5_writer(HDF5_WRITER, DATASET)

    assert "array.write(data._mem_burn_time.get()," in header
    assert "buffer" not in header
    assert "#include <vector>" not in header


def test_render_hdf5_writer_of_a_column_major_dataset_gathers_first() -> None:
    """A column major dataset of rank two or more is gathered before writing."""
    header = render_hdf5_writer(
        HDF5_WRITER, DATASET.model_copy(update={"column_major": True})
    )

    assert "#include <vector>" in header
    assert "std::vector<float> buffer(data.size());" in header
    assert "for (std::size_t i0 = 0; i0 < data.dims[0]; ++i0) {" in header
    assert "buffer[element++] = data.burn_time[i0, i1];" in header
    assert "array.write(buffer.data(), H5::PredType::NATIVE_FLOAT);" in header


def test_render_hdf5_writer_reports_errors_as_runtime_errors() -> None:
    """Everything that goes wrong is reported as a std::runtime_error."""
    header = render_hdf5_writer(HDF5_WRITER, DATASET)

    assert "} catch (const H5::Exception& e) {" in header
    assert 'throw std::runtime_error("failed to write \'" + group_path' in header


def test_generate_writes_one_header_per_hdf5_writer(tmp_path: Path) -> None:
    """Generate writes a header named after every HDF5 writer of the spec."""
    result = CliRunner().invoke(
        cli, ["generate", str(DATASET_EXAMPLE), "--output-dir", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output

    header = tmp_path / "write_raster.hpp"
    text = header.read_text()
    assert '#include "Raster.hpp"' in text
    assert "inline void write_raster(H5::H5File& file," in text
    assert "const Raster& data) {" in text

    # The lists narrow a writer the same way they narrow a reader.
    assert "mask" not in (tmp_path / "write_raster_layers.hpp").read_text()
    assert "elevation" not in (tmp_path / "write_raster_mask.hpp").read_text()


def throw_only_ifs_without_the_hint(header: str) -> list[str]:
    """
    Return the `if` statements of HEADER that throw without `[[unlikely]]`.

    An `if` counts when the block it opens holds one `throw` and nothing
    else, which is the shape the templates are asked to annotate.
    """
    lines = header.split("\n")
    missing: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("if (") or not stripped.endswith("{"):
            continue

        indent = len(line) - len(line.lstrip())
        end = index + 1
        while (
            end < len(lines)
            and lines[end].strip() != "}"
            or (
                end < len(lines)
                and len(lines[end]) - len(lines[end].lstrip()) != indent
            )
        ):
            end += 1
            if end >= len(lines):
                break

        first = index + 1
        body = " ".join(
            b.strip()
            for b in lines[first:end]
            if b.strip() and not b.strip().startswith("//")
        )
        throws_only = body.startswith("throw") and body.count(";") == 1
        if throws_only and "[[unlikely]]" not in stripped:
            missing.append(stripped)
    return missing


def test_every_generated_throw_is_marked_unlikely() -> None:
    """A branch that only throws is annotated in every generated header."""
    headers = [
        render_table(TABLE),
        render_dataset(DATASET),
        render_csv_reader(READER, TABLE),
        render_csv_writer(WRITER, TABLE),
        render_parquet_reader(PARQUET_READER, TABLE),
        render_parquet_writer(PARQUET_WRITER, TABLE),
        render_hdf5_reader(HDF5_READER, DATASET),
        render_hdf5_writer(HDF5_WRITER, DATASET),
    ]

    for header in headers:
        assert throw_only_ifs_without_the_hint(header) == []


def test_the_hint_is_not_put_on_branches_that_do_more() -> None:
    """A branch that does something other than throw is left alone."""
    header = render_csv_reader(READER, TABLE)

    # These return or fall through instead of throwing.
    assert "if (batch_ == nullptr) {" in header
    assert 'if (path.ends_with(".gz")) {' in header
    assert "if (done_) {" in header
