// Integration test for the generated readers.
// It writes CSV and Parquet files with Arrow,
// reads them back with the generated readers,
// and checks the rows and the errors that the readers report.

#include <cstdio>
#include <memory>
#include <string>
#include <vector>

#include <arrow/api.h>
#include <arrow/io/api.h>
#include <arrow/io/compressed.h>
#include <arrow/util/compression.h>
#include <parquet/arrow/reader.h>
#include <parquet/arrow/writer.h>

#include "tables.hpp"

namespace {

int failures = 0;

#define CHECK(condition)                                                      \
    do {                                                                      \
        if (!(condition)) {                                                   \
            std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition);  \
            ++failures;                                                       \
        }                                                                     \
    } while (false)

void check_ok(const arrow::Status& status, const char* what) {
    if (!status.ok()) {
        std::printf("FAIL %s: %s\n", what, status.ToString().c_str());
        ++failures;
    }
}

// Return the message of the exception thrown by f, or "" if it throws none.
template <typename F>
std::string error_of(F f) {
    try {
        f();
    } catch (const std::exception& e) {
        return e.what();
    }
    return "";
}

bool contains(const std::string& text, const std::string& part) {
    return text.find(part) != std::string::npos;
}

void write_file(const std::string& path, const std::string& contents) {
    std::FILE* file = std::fopen(path.c_str(), "w");
    std::fwrite(contents.data(), 1, contents.size(), file);
    std::fclose(file);
}

// Build an Arrow table with the columns of 'Point', in the given order.
std::shared_ptr<arrow::Table> point_table(
    const std::vector<std::string>& order,
    const std::vector<std::optional<std::int64_t>>& ids) {
    arrow::Int64Builder id_builder;
    arrow::StringBuilder label_builder;
    arrow::DoubleBuilder score_builder;
    arrow::BooleanBuilder flag_builder;

    for (std::size_t i = 0; i < ids.size(); ++i) {
        if (ids[i].has_value()) {
            check_ok(id_builder.Append(*ids[i]), "append id");
        } else {
            check_ok(id_builder.AppendNull(), "append null id");
        }
        check_ok(label_builder.Append("row" + std::to_string(i)), "append label");
        check_ok(score_builder.Append(0.5 + static_cast<double>(i)), "append score");
        check_ok(flag_builder.Append(i % 2 == 0), "append flag");
    }

    std::unordered_map<std::string, std::shared_ptr<arrow::Array>> arrays;
    std::unordered_map<std::string, std::shared_ptr<arrow::DataType>> types = {
        {"id", arrow::int64()},
        {"label", arrow::utf8()},
        {"score", arrow::float64()},
        {"flag", arrow::boolean()},
    };
    check_ok(id_builder.Finish(&arrays["id"]), "finish id");
    check_ok(label_builder.Finish(&arrays["label"]), "finish label");
    check_ok(score_builder.Finish(&arrays["score"]), "finish score");
    check_ok(flag_builder.Finish(&arrays["flag"]), "finish flag");

    std::vector<std::shared_ptr<arrow::Field>> fields;
    std::vector<std::shared_ptr<arrow::Array>> columns;
    for (const std::string& name : order) {
        fields.push_back(arrow::field(name, types[name]));
        columns.push_back(arrays[name]);
    }

    return arrow::Table::Make(arrow::schema(fields), columns);
}

void write_parquet(const std::string& path, const std::shared_ptr<arrow::Table>& table,
                   arrow::Compression::type codec) {
    auto maybe_output = arrow::io::FileOutputStream::Open(path);
    check_ok(maybe_output.status(), "open parquet output");

    auto properties = parquet::WriterProperties::Builder().compression(codec)->build();

    // A small chunk size stores the rows in several row groups.
    check_ok(parquet::arrow::WriteTable(*table, arrow::default_memory_pool(),
                                        *maybe_output, /*chunk_size=*/2, properties),
             "write parquet");
}

// Read every row of the reader in batches, and return the table holding them.
template <typename Reader>
Point read_all(Reader& reader, std::size_t expected_batches) {
    Point all;
    std::size_t batches = 0;

    // Every batch is appended to the table the one before it left behind.
    while (reader.has_more_batches()) {
        const std::size_t before = all.size();
        reader.read_batch(all);
        CHECK(all.size() > before);
        ++batches;
    }

    CHECK(batches == expected_batches);
    return all;
}

const std::string kCsv =
    "id,label,score,flag\n"
    "10,alpha,1.5,true\n"
    "11,beta,2.5,false\n"
    "12,gamma,,true\n"
    "13,delta,4.5,false\n"
    "14,epsilon,5.5,true\n";

void test_csv_reads_every_row() {
    write_file("points.csv", kCsv);

    PointCsvReader reader("points.csv", 2);
    const Point points = read_all(reader, 3);

    CHECK(points.size() == 5);
    CHECK(points.id == (std::vector<std::int64_t>{10, 11, 12, 13, 14}));
    CHECK(points[0].label == "alpha");
    CHECK(points[4].label == "epsilon");
    CHECK(points[1].score == 2.5);
    CHECK(points[0].flag == true);
    CHECK(points[1].flag == false);

    // 'score' has a default value, which replaces the missing value.
    CHECK(points[2].score == -1.5);
}

// Write contents to path, compressed with codec.
void write_compressed(const std::string& path, const std::string& contents,
                      arrow::Compression::type codec_type) {
    auto output = arrow::io::FileOutputStream::Open(path);
    check_ok(output.status(), "open compressed output");

    auto codec = arrow::util::Codec::Create(codec_type);
    check_ok(codec.status(), "create codec");

    auto stream = arrow::io::CompressedOutputStream::Make((*codec).get(), *output);
    check_ok(stream.status(), "make compressed stream");

    check_ok((*stream)->Write(contents.data(), static_cast<std::int64_t>(contents.size())),
             "write compressed");
    check_ok((*stream)->Close(), "close compressed stream");
    check_ok((*output)->Close(), "close compressed output");
}

void check_reads_the_rows(Point points) {
    CHECK(points.size() == 5);
    CHECK(points.id == (std::vector<std::int64_t>{10, 11, 12, 13, 14}));
    CHECK(points[0].label == "alpha");
    CHECK(points[4].label == "epsilon");
}

void test_csv_reader_infers_the_compression() {
    write_compressed("points.csv.gz", kCsv, arrow::Compression::GZIP);
    write_compressed("points.csv.zst", kCsv, arrow::Compression::ZSTD);

    PointCsvReader gzip_reader("points.csv.gz", 8);
    check_reads_the_rows(read_all(gzip_reader, 1));

    PointCsvReader zstd_reader("points.csv.zst", 8);
    check_reads_the_rows(read_all(zstd_reader, 1));
}

void test_csv_reader_compression_can_be_given() {
    // A compressed file whose name says nothing about its compression.
    write_compressed("compressed.csv", kCsv, arrow::Compression::GZIP);

    PointCsvReader reader("compressed.csv", 8, false,
                          PointCsvReader::default_block_size,
                          arrow::Compression::GZIP);
    check_reads_the_rows(read_all(reader, 1));

    // Without being told, the reader treats it as plain text and fails.
    CHECK(!error_of([] {
               PointCsvReader plain("compressed.csv", 8);
               Point rows;
               plain.read_batch(rows);
           }).empty());

    // An uncompressed file named like a compressed one.
    write_file("plain.csv.gz", kCsv);

    PointCsvReader plain_reader("plain.csv.gz", 8, false,
                                PointCsvReader::default_block_size,
                                arrow::Compression::UNCOMPRESSED);
    check_reads_the_rows(read_all(plain_reader, 1));
}

void test_csv_reader_options() {
    write_file("points.csv", kCsv);

    // Threaded parsing with a block size that splits the file.
    PointCsvReader threaded("points.csv", 8, /*use_threads=*/true,
                            /*block_size=*/64);
    const Point points = read_all(threaded, 1);

    CHECK(points.size() == 5);
    CHECK(points.id == (std::vector<std::int64_t>{10, 11, 12, 13, 14}));
    CHECK(points[4].label == "epsilon");

    // A block has to be able to hold something.
    CHECK(contains(error_of([] { PointCsvReader reader("points.csv", 4, false, 0); }),
                   "block_size must be larger than zero"));
}

void test_csv_rejects_a_null_in_a_required_column() {
    write_file("bad_points.csv", "id,label,score,flag\n,alpha,1.5,true\n");

    PointCsvReader reader("bad_points.csv", 4);
    Point rows;
    const std::string error = error_of([&] { reader.read_batch(rows); });

    CHECK(contains(error, "column 'id' contains null values"));
}

void test_csv_reports_a_missing_file() {
    const std::string error =
        error_of([] { PointCsvReader reader("no_such_file.csv", 4); });

    CHECK(contains(error, "failed to open 'no_such_file.csv'"));
}

void test_parquet_reads_every_row(arrow::Compression::type codec,
                                  const std::string& path) {
    write_parquet(path, point_table({"id", "label", "score", "flag"},
                                    {10, 11, 12, 13, 14}),
                  codec);

    PointParquetReader reader(path, 2);
    const Point points = read_all(reader, 3);

    CHECK(points.size() == 5);
    CHECK(points.id == (std::vector<std::int64_t>{10, 11, 12, 13, 14}));
    CHECK(points[0].label == "row0");
    CHECK(points[4].label == "row4");
    CHECK(points[2].score == 2.5);
    CHECK(points[0].flag == true);
    CHECK(points[1].flag == false);
}

void test_parquet_reads_columns_by_name() {
    // The Parquet file stores the columns in a different order.
    write_parquet("shuffled.parquet",
                  point_table({"flag", "score", "label", "id"}, {10, 11, 12}),
                  arrow::Compression::SNAPPY);

    PointParquetReader reader("shuffled.parquet", 8);
    const Point points = read_all(reader, 1);

    CHECK(points.size() == 3);
    CHECK(points.id == (std::vector<std::int64_t>{10, 11, 12}));
    CHECK(points[0].label == "row0");
    CHECK(points[1].score == 1.5);
    CHECK(points[2].flag == true);
}

void test_parquet_uses_the_default_of_a_null_column() {
    arrow::Int64Builder id_builder;
    arrow::StringBuilder label_builder;
    arrow::DoubleBuilder score_builder;
    arrow::BooleanBuilder flag_builder;

    check_ok(id_builder.Append(7), "append id");
    check_ok(label_builder.AppendNull(), "append null label");
    check_ok(score_builder.AppendNull(), "append null score");
    check_ok(flag_builder.Append(true), "append flag");

    std::shared_ptr<arrow::Array> id, label, score, flag;
    check_ok(id_builder.Finish(&id), "finish id");
    check_ok(label_builder.Finish(&label), "finish label");
    check_ok(score_builder.Finish(&score), "finish score");
    check_ok(flag_builder.Finish(&flag), "finish flag");

    const auto schema = arrow::schema({
        arrow::field("id", arrow::int64()),
        arrow::field("label", arrow::utf8()),
        arrow::field("score", arrow::float64()),
        arrow::field("flag", arrow::boolean()),
    });
    write_parquet("defaults.parquet",
                  arrow::Table::Make(schema, {id, label, score, flag}),
                  arrow::Compression::SNAPPY);

    PointParquetReader reader("defaults.parquet", 8);
    const Point points = read_all(reader, 1);

    CHECK(points.size() == 1);
    CHECK(points[0].label == "missing");
    CHECK(points[0].score == -1.5);
}

void test_parquet_rejects_a_null_in_a_required_column() {
    write_parquet("null_points.parquet",
                  point_table({"id", "label", "score", "flag"},
                              {10, std::nullopt, 12}),
                  arrow::Compression::SNAPPY);

    PointParquetReader reader("null_points.parquet", 8);
    Point rows;
    const std::string error = error_of([&] { reader.read_batch(rows); });

    CHECK(contains(error, "column 'id' of 'null_points.parquet'"));
    CHECK(contains(error, "contains null values"));
}

void test_parquet_rejects_a_missing_column() {
    write_parquet("partial.parquet", point_table({"id", "label", "flag"}, {10, 11}),
                  arrow::Compression::SNAPPY);

    const std::string error =
        error_of([] { PointParquetReader reader("partial.parquet", 8); });

    CHECK(contains(error, "'partial.parquet' has no column 'score'"));
}

void test_readers_read_all_of_what_is_left() {
    // 'points.csv' and 'points.parquet' both hold the five rows of kCsv.
    PointCsvReader csv_reader("points.csv", 2);
    Point points;
    csv_reader.read_batch(points);
    CHECK(points.size() == 2);

    // read_all appends the rows that read_batch left, and stops at the end.
    csv_reader.read_all(points);
    CHECK(points.size() == 5);
    CHECK(points.id == (std::vector<std::int64_t>{10, 11, 12, 13, 14}));
    CHECK(points[4].label == "epsilon");
    CHECK(!csv_reader.has_more_batches());

    csv_reader.read_all(points);
    CHECK(points.size() == 5);

    // A table that is read into keeps the rows it already holds.
    PointParquetReader parquet_reader("points.parquet", 8);
    parquet_reader.read_all(points);
    CHECK(points.size() == 10);
    CHECK(points[4].label == "epsilon");
    CHECK(points[5].label == "row0");
    CHECK(points.id == (std::vector<std::int64_t>{10, 11, 12, 13, 14, 10, 11, 12, 13, 14}));
}

void test_readers_reject_a_zero_batch_size() {
    CHECK(contains(error_of([] { PointCsvReader reader("points.csv", 0); }),
                   "batch_size must be larger than zero"));
    CHECK(contains(error_of([] { PointParquetReader reader("points.parquet", 0); }),
                   "batch_size must be larger than zero"));
}

void test_csv_writer_round_trip() {
    Point points;
    points.push_back(1, "alpha", 1.5, true);
    points.push_back(2, "beta", 2.5, false);
    points.push_back(3, "with,comma", 3.5, true);

    {
        PointCsvWriter writer("written.csv");
        writer.write_batch(points);

        Point more;
        more.push_back(4, "delta", 4.5, false);
        writer.write_batch(more);

        writer.close();
        // Closing twice is allowed.
        writer.close();

        // Writing to a closed writer is an error.
        CHECK(contains(error_of([&] { writer.write_batch(more); }), "is closed"));
    }

    PointCsvReader reader("written.csv", 3);
    const Point read_back = read_all(reader, 2);

    CHECK(read_back.size() == 4);
    CHECK(read_back.id == (std::vector<std::int64_t>{1, 2, 3, 4}));
    CHECK(read_back[0].label == "alpha");
    CHECK(read_back[2].label == "with,comma");
    CHECK(read_back[3].label == "delta");
    CHECK(read_back[1].score == 2.5);
    CHECK(read_back[0].flag == true);
    CHECK(read_back[1].flag == false);
}

void test_csv_writer_compresses() {
    Point points;
    points.push_back(1, "alpha", 1.5, true);
    points.push_back(2, "beta", 2.5, false);

    // The compression is guessed from the name of the file.
    for (const char* name : {"out.csv.gz", "out.csv.zst"}) {
        const std::string path = name;
        PointCsvWriter writer(path);
        writer.write_batch(points);
        writer.close();

        // The reader guesses the same compression from the same name.
        PointCsvReader reader(path, 8);
        const Point read_back = read_all(reader, 1);

        CHECK(read_back.size() == 2);
        CHECK(read_back[0].label == "alpha");
        CHECK(read_back[1].score == 2.5);
    }

    // An explicit codec and level, on a file whose name says nothing.
    {
        PointCsvWriter writer("out.csv.data", arrow::Compression::GZIP, 9);
        writer.write_batch(points);
        writer.close();
    }

    PointCsvReader reader("out.csv.data", 8, false,
                          PointCsvReader::default_block_size,
                          arrow::Compression::GZIP);
    const Point read_back = read_all(reader, 1);
    CHECK(read_back.size() == 2);
    CHECK(read_back[1].label == "beta");

    // The file really is compressed: it does not start with the header row.
    std::FILE* file = std::fopen("out.csv.data", "rb");
    char start[2] = {0, 0};
    CHECK(std::fread(start, 1, sizeof(start), file) == sizeof(start));
    std::fclose(file);
    CHECK(static_cast<unsigned char>(start[0]) == 0x1f);
    CHECK(static_cast<unsigned char>(start[1]) == 0x8b);

    // Uncompressed can be asked for even when the name suggests otherwise.
    {
        PointCsvWriter writer("plain_out.csv.gz", arrow::Compression::UNCOMPRESSED);
        writer.write_batch(points);
        writer.close();
    }

    PointCsvReader plain("plain_out.csv.gz", 8, false,
                         PointCsvReader::default_block_size,
                         arrow::Compression::UNCOMPRESSED);
    CHECK(read_all(plain, 1).size() == 2);
}

void test_csv_writer_closes_itself() {
    {
        PointCsvWriter writer("closed_by_destructor.csv");
        Point points;
        points.push_back(9, "omega", 9.5, true);
        writer.write_batch(points);
    }

    PointCsvReader reader("closed_by_destructor.csv", 8);
    const Point read_back = read_all(reader, 1);

    CHECK(read_back.size() == 1);
    CHECK(read_back[0].label == "omega");
}

void test_csv_writer_reports_a_bad_path() {
    const std::string error =
        error_of([] { PointCsvWriter writer("no_such_directory/out.csv"); });

    CHECK(contains(error, "failed to open 'no_such_directory/out.csv'"));
}

void test_parquet_writer_round_trip() {
    Point points;
    points.push_back(1, "alpha", 1.5, true);
    points.push_back(2, "beta", 2.5, false);
    points.push_back(3, "gamma", 3.5, true);

    {
        PointParquetWriter writer("written.parquet");
        writer.write_batch(points);

        Point more;
        more.push_back(4, "delta", 4.5, false);
        writer.write_batch(more);

        writer.close();
        // Closing twice is allowed.
        writer.close();

        // Writing to a closed writer is an error.
        CHECK(contains(error_of([&] { writer.write_batch(more); }), "is closed"));
    }

    PointParquetReader reader("written.parquet", 3);
    const Point read_back = read_all(reader, 2);

    CHECK(read_back.size() == 4);
    CHECK(read_back.id == (std::vector<std::int64_t>{1, 2, 3, 4}));
    CHECK(read_back[0].label == "alpha");
    CHECK(read_back[3].label == "delta");
    CHECK(read_back[1].score == 2.5);
    CHECK(read_back[0].flag == true);
    CHECK(read_back[1].flag == false);
}

void test_parquet_writer_options() {
    Point points;
    for (std::int64_t i = 0; i < 5; ++i) {
        points.push_back(i, "row" + std::to_string(i), 0.5 + static_cast<double>(i),
                         i % 2 == 0);
    }

    {
        // Two rows per row group, and an explicit codec and level.
        PointParquetWriter writer("options.parquet", arrow::Compression::GZIP, 9, 2);
        writer.write_batch(points);
        writer.close();
    }

    // The rows are stored in three row groups of at most two rows.
    auto input = arrow::io::ReadableFile::Open("options.parquet");
    check_ok(input.status(), "open options.parquet");
    auto reader = parquet::arrow::OpenFile(*input, arrow::default_memory_pool());
    check_ok(reader.status(), "read options.parquet");
    CHECK((*reader)->num_row_groups() == 3);

    PointParquetReader points_reader("options.parquet", 8);
    const Point read_back = read_all(points_reader, 1);
    CHECK(read_back.size() == 5);
    CHECK(read_back[4].label == "row4");

    // A row group has to hold at least one row.
    CHECK(contains(error_of([] {
                       PointParquetWriter writer("bad.parquet",
                                                 arrow::Compression::ZSTD, 1, 0);
                   }),
                   "row_group_length must be larger than zero"));
}

void test_parquet_writer_closes_itself() {
    {
        PointParquetWriter writer("closed_by_destructor.parquet");
        Point points;
        points.push_back(9, "omega", 9.5, true);
        writer.write_batch(points);
    }

    PointParquetReader reader("closed_by_destructor.parquet", 8);
    const Point read_back = read_all(reader, 1);

    CHECK(read_back.size() == 1);
    CHECK(read_back[0].label == "omega");
}

void test_parquet_writer_reports_a_bad_path() {
    const std::string error =
        error_of([] { PointParquetWriter writer("no_such_directory/out.parquet"); });

    CHECK(contains(error, "failed to open 'no_such_directory/out.parquet'"));
}

}  // namespace

int main() {
    test_csv_reads_every_row();
    test_csv_reader_infers_the_compression();
    test_csv_reader_compression_can_be_given();
    test_csv_reader_options();
    test_csv_rejects_a_null_in_a_required_column();
    test_csv_reports_a_missing_file();

    test_parquet_reads_every_row(arrow::Compression::SNAPPY, "points.parquet");
    test_parquet_reads_every_row(arrow::Compression::GZIP, "points_gzip.parquet");
    test_parquet_reads_every_row(arrow::Compression::ZSTD, "points_zstd.parquet");
    test_parquet_reads_columns_by_name();
    test_parquet_uses_the_default_of_a_null_column();
    test_parquet_rejects_a_null_in_a_required_column();
    test_parquet_rejects_a_missing_column();

    test_readers_read_all_of_what_is_left();
    test_readers_reject_a_zero_batch_size();

    test_csv_writer_round_trip();
    test_csv_writer_compresses();
    test_csv_writer_closes_itself();
    test_csv_writer_reports_a_bad_path();

    test_parquet_writer_round_trip();
    test_parquet_writer_options();
    test_parquet_writer_closes_itself();
    test_parquet_writer_reports_a_bad_path();

    if (failures == 0) {
        std::printf("all checks passed\n");
        return 0;
    }
    std::printf("%d check(s) failed\n", failures);
    return 1;
}
