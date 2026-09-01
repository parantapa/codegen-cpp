// Integration test for the aggregate types.
// It writes a Parquet file with the generated writer,
// reads it back with the generated readers,
// and writes one holding a null at every level with Arrow
// to check the defaults that the readers stand in for them.

#include <cstdio>
#include <memory>
#include <string>
#include <vector>

#include <arrow/api.h>
#include <arrow/io/api.h>
#include <parquet/arrow/writer.h>

#include "nested.hpp"

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

// Fill in two rows, one holding a value of every shape and one holding none.
void fill_rows(T& table) {
    table.push_back(T::row_type{
        .id = 1,
        .tags = {"alpha", "beta"},
        .points = {Point{.x = 1, .y = 1.5}, Point{.x = 2, .y = 2.5}},
        .counts = {{"a", 10}, {"b", 20}},
        .fast = {{2020, 3}, {2021, 4}},
        .nested = {{"one", "two"}, {}},
        .inner = Inner{.nums = {7, 8, 9}, .label = "first"},
    });
    table.push_back(T::row_type{
        .id = 2,
        .tags = {},
        .points = {},
        .counts = {},
        .fast = {},
        .nested = {},
        .inner = Inner{.nums = {}, .label = "second"},
    });
}

// Write a file whose every nested part holds a null somewhere:
// a null element, a null field, a null value,
// and a null vector, struct and map of their own.
void write_nulls(const std::string& path) {
    auto* pool = arrow::default_memory_pool();

    arrow::Int64Builder id(pool);
    check_ok(id.AppendValues({1, 2}), "append id");

    auto tag = std::make_shared<arrow::StringBuilder>(pool);
    arrow::ListBuilder tags(pool, tag,
                            arrow::list(arrow::field("element", arrow::utf8())));
    check_ok(tags.Append(), "open tags");
    check_ok(tag->Append("a"), "append tag");
    check_ok(tag->AppendNull(), "append null tag");
    check_ok(tags.AppendNull(), "append null tags");

    auto x = std::make_shared<arrow::Int32Builder>(pool);
    auto label = std::make_shared<arrow::StringBuilder>(pool);
    const auto pt_type = arrow::struct_(
        {arrow::field("x", arrow::int32()), arrow::field("label", arrow::utf8())});
    arrow::StructBuilder pt(pt_type, pool, {x, label});
    check_ok(pt.Append(), "open pt");
    check_ok(x->AppendNull(), "append null x");
    check_ok(label->Append("s"), "append label");
    check_ok(pt.AppendNull(), "append null pt");
    check_ok(x->AppendNull(), "append null x");
    check_ok(label->AppendNull(), "append null label");

    auto key = std::make_shared<arrow::StringBuilder>(pool);
    auto item = std::make_shared<arrow::Int64Builder>(pool);
    arrow::MapBuilder counts(
        pool, key, item,
        arrow::map(arrow::utf8(), arrow::field("value", arrow::int64())));
    check_ok(counts.Append(), "open counts");
    check_ok(key->Append("a"), "append key");
    check_ok(item->AppendNull(), "append null value");
    check_ok(counts.AppendNull(), "append null counts");

    std::shared_ptr<arrow::Array> id_array;
    std::shared_ptr<arrow::Array> tags_array;
    std::shared_ptr<arrow::Array> pt_array;
    std::shared_ptr<arrow::Array> counts_array;
    check_ok(id.Finish(&id_array), "finish id");
    check_ok(tags.Finish(&tags_array), "finish tags");
    check_ok(pt.Finish(&pt_array), "finish pt");
    check_ok(counts.Finish(&counts_array), "finish counts");

    const auto schema = arrow::schema({
        arrow::field("id", arrow::int64()),
        arrow::field("tags", tags_array->type()),
        arrow::field("pt", pt_type),
        arrow::field("counts", counts_array->type()),
    });
    const auto table =
        arrow::Table::Make(schema, {id_array, tags_array, pt_array, counts_array});

    auto output = arrow::io::FileOutputStream::Open(path).ValueOrDie();
    check_ok(parquet::arrow::WriteTable(*table, pool, output), "write nulls");
    check_ok(output->Close(), "close nulls");
}

// Every shape a column can hold is written out and read back unchanged.
void test_round_trip(const std::string& path) {
    T written;
    fill_rows(written);

    {
        TParquetWriter writer(path);
        writer.write_batch(written);
        writer.close();
    }

    T read;
    {
        TParquetReader reader(path, 100);
        reader.read_all(read);
    }

    CHECK(read.size() == 2);
    CHECK(read.id == written.id);
    CHECK(read.tags == written.tags);
    CHECK(read.points == written.points);
    CHECK(read.counts == written.counts);
    CHECK(read.fast == written.fast);
    CHECK(read.nested == written.nested);
    CHECK(read.inner == written.inner);
}

// A reader reads the columns it declares, under the names the file gives them.
void test_names_in_file(const std::string& path) {
    U read;
    {
        UParquetReader reader(path, 100);
        reader.read_all(read);
    }

    CHECK(read.size() == 2);
    CHECK(read.ident == std::vector<std::int64_t>({1, 2}));
    CHECK(read.spots.at(0).size() == 2);
    CHECK(read.spots.at(0).at(1).across == 2);
    CHECK(read.spots.at(0).at(1).down == 2.5);
    CHECK(read.spots.at(1).empty());
}

// A null is read as the default of the part holding it,
// and a null aggregate as the empty value of its own type.
void test_defaults(const std::string& path) {
    write_nulls(path);

    N read;
    {
        NParquetReader reader(path, 100);
        reader.read_all(read);
    }

    CHECK(read.size() == 2);
    CHECK(read.tags.at(0) == Tags({"a", "<none>"}));
    CHECK(read.tags.at(1).empty());
    CHECK(read.pt.at(0) == Pt({.x = -1, .label = "s"}));
    CHECK(read.pt.at(1) == Pt({.x = -1, .label = "<none>"}));
    CHECK(read.counts.at(0) == Counts({{"a", -1}}));
    CHECK(read.counts.at(1).empty());
}

// A file that does not hold a column of the table is reported.
void test_missing_column(const std::string& path) {
    const std::string error = error_of([&] { TParquetReader reader(path, 100); });

    CHECK(contains(error, "has no column 'points'"));
}

// A batch of rows is read at a time, and reading stops at the last row.
void test_batches(const std::string& path) {
    T read;
    TParquetReader reader(path, 1);

    CHECK(reader.has_more_batches());
    reader.read_batch(read);
    CHECK(read.size() == 1);
    CHECK(reader.has_more_batches());
    reader.read_batch(read);
    CHECK(read.size() == 2);
    CHECK(!reader.has_more_batches());
}

}  // namespace

int main() {
    const std::string path = "test_nested.parquet";
    const std::string nulls = "test_nested_nulls.parquet";

    test_round_trip(path);
    test_names_in_file(path);
    test_batches(path);
    test_defaults(nulls);
    test_missing_column(nulls);

    if (failures == 0) {
        std::printf("all tests passed\n");
    }
    return failures == 0 ? 0 : 1;
}
