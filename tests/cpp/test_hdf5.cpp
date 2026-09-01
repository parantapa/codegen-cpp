// Integration test for the generated HDF5 readers.
// It writes HDF5 files with the HDF5 C++ API,
// reads them back with the generated readers,
// and checks the arrays and the errors that the readers report.

#include <array>
#include <cstdint>
#include <cstdio>
#include <exception>
#include <filesystem>
#include <string>
#include <vector>

#include <H5Cpp.h>

#include "datasets.hpp"

namespace {

int failures = 0;

// The condition is taken as a variadic argument,
// because the C++23 subscript of an mdspan spells its indices with commas,
// which the preprocessor would otherwise read as argument separators.
#define CHECK(...)                                                              \
    do {                                                                        \
        if (!(__VA_ARGS__)) {                                                    \
            std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #__VA_ARGS__);  \
            ++failures;                                                         \
        }                                                                       \
    } while (false)

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

// Open a reader on the group path of file and read it into data.
// A reader reports a missing or ill stored array as it is constructed,
// and a shape that does not match as it reads,
// so a test of either one goes through this.
template <typename Reader, typename Data>
void read_into(H5::H5File& file, const std::string& path, Data& data) {
    Reader reader(file, path);
    reader.read_dataset(data);
}

// Open a writer on the group path of file and write data into it.
template <typename Writer, typename Data>
void write_from(H5::H5File& file, const std::string& path, const Data& data) {
    Writer writer(file, path);
    writer.write_dataset(data);
}

// The shape that every array of 'Grid' is written and read with.
constexpr hsize_t grid_rows = 2;
constexpr hsize_t grid_cols = 3;

// The shape that every array of 'Field' is written and read with.
constexpr hsize_t field_x = 2;
constexpr hsize_t field_y = 3;
constexpr hsize_t field_z = 4;

// The values that the arrays of the test files hold.
// They are spelled as functions of the index,
// so that a value that lands in the wrong place is noticed.
double expected_temperature(std::size_t row, std::size_t col) {
    return 10.0 * static_cast<double>(row) + static_cast<double>(col) + 0.5;
}

std::int32_t expected_kind(std::size_t row, std::size_t col) {
    return static_cast<std::int32_t>(100 * row + col) - 50;
}

std::uint16_t expected_count(std::size_t row, std::size_t col) {
    return static_cast<std::uint16_t>(7 * row + col);
}

float expected_value(std::size_t x, std::size_t y, std::size_t z) {
    return static_cast<float>(100 * x + 10 * y + z);
}

std::int8_t expected_tag(std::size_t x, std::size_t y, std::size_t z) {
    return static_cast<std::int8_t>(x + y + z);
}

// Write values as the dataset called name of group,
// stored with file_type and handed over as memory_type.
// The elements of values are in row major order, the order HDF5 stores.
template <typename T>
void write_array(H5::Group& group, const std::string& name,
                 const std::vector<hsize_t>& dims, const H5::DataType& file_type,
                 const H5::DataType& memory_type, const std::vector<T>& values) {
    const H5::DataSpace space(static_cast<int>(dims.size()), dims.data());
    H5::DataSet dataset = group.createDataSet(name, file_type, space);
    dataset.write(values.data(), memory_type);
}

// Write the three arrays of 'Grid' into the group called path of file.
// The datatypes and the shape may be varied to test what the readers reject.
void write_grid_group(H5::H5File& file, const std::string& path,
                      const H5::DataType& temperature_type = H5::PredType::IEEE_F64LE,
                      const H5::DataType& kind_type = H5::PredType::STD_I32LE,
                      const H5::DataType& count_type = H5::PredType::STD_U16LE,
                      hsize_t rows = grid_rows, hsize_t cols = grid_cols) {
    H5::Group group = file.createGroup(path);
    const std::vector<hsize_t> dims{rows, cols};

    std::vector<double> temperature;
    std::vector<std::int32_t> kind;
    std::vector<std::uint16_t> count;
    for (std::size_t row = 0; row < rows; ++row) {
        for (std::size_t col = 0; col < cols; ++col) {
            temperature.push_back(expected_temperature(row, col));
            kind.push_back(expected_kind(row, col));
            count.push_back(expected_count(row, col));
        }
    }

    write_array(group, "temperature", dims, temperature_type,
                H5::PredType::NATIVE_DOUBLE, temperature);
    write_array(group, "kind", dims, kind_type, H5::PredType::NATIVE_INT32, kind);
    write_array(group, "count", dims, count_type, H5::PredType::NATIVE_UINT16, count);
}

// Write the two arrays of 'Field' into the group called path of file.
void write_field_group(H5::H5File& file, const std::string& path) {
    H5::Group group = file.createGroup(path);
    const std::vector<hsize_t> dims{field_x, field_y, field_z};

    std::vector<float> value;
    std::vector<std::int8_t> tag;
    for (std::size_t x = 0; x < field_x; ++x) {
        for (std::size_t y = 0; y < field_y; ++y) {
            for (std::size_t z = 0; z < field_z; ++z) {
                value.push_back(expected_value(x, y, z));
                tag.push_back(expected_tag(x, y, z));
            }
        }
    }

    write_array(group, "value", dims, H5::PredType::IEEE_F32LE,
                H5::PredType::NATIVE_FLOAT, value);
    write_array(group, "tag", dims, H5::PredType::STD_I8LE,
                H5::PredType::NATIVE_INT8, tag);
}

// The value written into every element of a grid before it is read,
// so that an array the reader is asked to skip can be told apart.
constexpr double untouched_temperature = -1.0;
constexpr std::int32_t untouched_kind = -1;
constexpr std::uint16_t untouched_count = 65535;

void fill_untouched(Grid& grid) {
    for (std::size_t row = 0; row < grid.dims[0]; ++row) {
        for (std::size_t col = 0; col < grid.dims[1]; ++col) {
            grid.temperature[row, col] = untouched_temperature;
            grid.kind[row, col] = untouched_kind;
            grid.count[row, col] = untouched_count;
        }
    }
}

void fill_expected(Grid& grid) {
    for (std::size_t row = 0; row < grid.dims[0]; ++row) {
        for (std::size_t col = 0; col < grid.dims[1]; ++col) {
            grid.temperature[row, col] = expected_temperature(row, col);
            grid.kind[row, col] = expected_kind(row, col);
            grid.count[row, col] = expected_count(row, col);
        }
    }
}

void check_grid_holds_the_expected(const Grid& grid) {
    for (std::size_t row = 0; row < grid_rows; ++row) {
        for (std::size_t col = 0; col < grid_cols; ++col) {
            CHECK(grid.temperature[row, col] == expected_temperature(row, col));
            CHECK(grid.kind[row, col] == expected_kind(row, col));
            CHECK(grid.count[row, col] == expected_count(row, col));
        }
    }
}

void fill_expected(Field& field) {
    for (std::size_t x = 0; x < field.dims[0]; ++x) {
        for (std::size_t y = 0; y < field.dims[1]; ++y) {
            for (std::size_t z = 0; z < field.dims[2]; ++z) {
                field.value[x, y, z] = expected_value(x, y, z);
                field.tag[x, y, z] = expected_tag(x, y, z);
            }
        }
    }
}

void check_field_holds_the_expected(const Field& field) {
    for (std::size_t x = 0; x < field_x; ++x) {
        for (std::size_t y = 0; y < field_y; ++y) {
            for (std::size_t z = 0; z < field_z; ++z) {
                CHECK(field.value[x, y, z] == expected_value(x, y, z));
                CHECK(field.tag[x, y, z] == expected_tag(x, y, z));
            }
        }
    }
}

// Write a file holding '/sim/grid' and '/sim/field', and return its name.
std::string write_test_file() {
    const std::string path = "sim.h5";
    H5::H5File file(path, H5F_ACC_TRUNC);
    H5::Group root = file.createGroup("/sim");
    write_grid_group(file, "/sim/grid");
    write_field_group(file, "/sim/field");
    return path;
}

void test_reads_every_array() {
    const std::string path = write_test_file();
    H5::H5File file(path, H5F_ACC_RDONLY);

    Grid grid(grid_rows, grid_cols);
    fill_untouched(grid);

    GridHdf5Reader reader(file, "/sim/grid");
    reader.read_dataset(grid);

    check_grid_holds_the_expected(grid);
}

void test_include_reads_only_the_arrays_it_lists() {
    const std::string path = write_test_file();
    H5::H5File file(path, H5F_ACC_RDONLY);

    Grid grid(grid_rows, grid_cols);
    fill_untouched(grid);
    read_into<GridTemperatureHdf5Reader>(file, "/sim/grid", grid);

    for (std::size_t row = 0; row < grid_rows; ++row) {
        for (std::size_t col = 0; col < grid_cols; ++col) {
            CHECK(grid.temperature[row, col] == expected_temperature(row, col));
            CHECK(grid.kind[row, col] == untouched_kind);
            CHECK(grid.count[row, col] == untouched_count);
        }
    }
}

void test_exclude_reads_every_other_array() {
    const std::string path = write_test_file();
    H5::H5File file(path, H5F_ACC_RDONLY);

    Grid grid(grid_rows, grid_cols);
    fill_untouched(grid);
    read_into<GridLabelsHdf5Reader>(file, "/sim/grid", grid);

    for (std::size_t row = 0; row < grid_rows; ++row) {
        for (std::size_t col = 0; col < grid_cols; ++col) {
            CHECK(grid.temperature[row, col] == untouched_temperature);
            CHECK(grid.kind[row, col] == expected_kind(row, col));
            CHECK(grid.count[row, col] == expected_count(row, col));
        }
    }
}

// 'Field' is stored column major, so the elements have to be laid out again
// after they are read; an element that lands in the wrong place shows up here.
void test_reads_a_column_major_dataset() {
    const std::string path = write_test_file();
    H5::H5File file(path, H5F_ACC_RDONLY);

    Field field(field_x, field_y, field_z);
    read_into<FieldHdf5Reader>(file, "/sim/field", field);

    check_field_holds_the_expected(field);
}

void test_reports_a_missing_group() {
    const std::string path = write_test_file();
    H5::H5File file(path, H5F_ACC_RDONLY);

    Grid grid(grid_rows, grid_cols);
    const std::string error =
        error_of([&] { read_into<GridHdf5Reader>(file, "/sim/missing", grid); });

    CHECK(contains(error, "failed to read '/sim/missing'"));
}

void test_reports_a_missing_array() {
    const std::string path = "missing_array.h5";
    {
        H5::H5File file(path, H5F_ACC_TRUNC);
        H5::Group group = file.createGroup("/grid");
        const std::vector<hsize_t> dims{grid_rows, grid_cols};
        write_array(group, "temperature", dims, H5::PredType::IEEE_F64LE,
                    H5::PredType::NATIVE_DOUBLE,
                    std::vector<double>(grid_rows * grid_cols, 0.0));
    }

    H5::H5File file(path, H5F_ACC_RDONLY);
    Grid grid(grid_rows, grid_cols);
    const std::string error =
        error_of([&] { read_into<GridHdf5Reader>(file, "/grid", grid); });

    CHECK(contains(error, "'/grid/kind' is not in the HDF5 file"));
}

// An array that the reader is not asked to read may be absent.
void test_a_skipped_array_may_be_missing() {
    const std::string path = "only_temperature.h5";
    {
        H5::H5File file(path, H5F_ACC_TRUNC);
        H5::Group group = file.createGroup("/grid");
        const std::vector<hsize_t> dims{grid_rows, grid_cols};
        std::vector<double> temperature;
        for (std::size_t row = 0; row < grid_rows; ++row) {
            for (std::size_t col = 0; col < grid_cols; ++col) {
                temperature.push_back(expected_temperature(row, col));
            }
        }
        write_array(group, "temperature", dims, H5::PredType::IEEE_F64LE,
                    H5::PredType::NATIVE_DOUBLE, temperature);
    }

    H5::H5File file(path, H5F_ACC_RDONLY);
    Grid grid(grid_rows, grid_cols);
    fill_untouched(grid);
    const std::string error =
        error_of([&] { read_into<GridTemperatureHdf5Reader>(file, "/grid", grid); });

    CHECK(error.empty());
    CHECK(grid.temperature[0, 0] == expected_temperature(0, 0));
}

void test_reports_a_shape_that_does_not_match() {
    const std::string path = "wrong_shape.h5";
    {
        H5::H5File file(path, H5F_ACC_TRUNC);
        write_grid_group(file, "/grid", H5::PredType::IEEE_F64LE,
                         H5::PredType::STD_I32LE, H5::PredType::STD_U16LE,
                         grid_rows + 1, grid_cols);
    }

    H5::H5File file(path, H5F_ACC_RDONLY);
    Grid grid(grid_rows, grid_cols);
    const std::string error =
        error_of([&] { read_into<GridHdf5Reader>(file, "/grid", grid); });

    CHECK(contains(error, "'/grid/temperature' has extent 3 instead of 2"));
    CHECK(contains(error, "along dimension 0"));
}

void test_reports_a_rank_that_does_not_match() {
    const std::string path = "wrong_rank.h5";
    {
        H5::H5File file(path, H5F_ACC_TRUNC);
        write_grid_group(file, "/grid");

        // One array alone is stored with the wrong rank, so the reader opens
        // all three and reports the rank as it reads rather than before.
        H5::Group group = file.openGroup("/grid");
        group.unlink("temperature");
        const std::vector<hsize_t> dims{grid_rows * grid_cols};
        write_array(group, "temperature", dims, H5::PredType::IEEE_F64LE,
                    H5::PredType::NATIVE_DOUBLE,
                    std::vector<double>(grid_rows * grid_cols, 0.0));
    }

    H5::H5File file(path, H5F_ACC_RDONLY);
    Grid grid(grid_rows, grid_cols);
    const std::string error =
        error_of([&] { read_into<GridHdf5Reader>(file, "/grid", grid); });

    CHECK(contains(error, "'/grid/temperature' does not have rank 2"));
}

// Comparing the datatypes catches every way one can differ,
// so each of these files is rejected for a different reason
// and reported the same way.
void check_grid_datatype_is_rejected(const std::string& path,
                                     const H5::DataType& temperature_type,
                                     const H5::DataType& kind_type,
                                     const H5::DataType& count_type,
                                     const std::string& rejected) {
    {
        H5::H5File file(path, H5F_ACC_TRUNC);
        write_grid_group(file, "/grid", temperature_type, kind_type, count_type);
    }

    H5::H5File file(path, H5F_ACC_RDONLY);
    Grid grid(grid_rows, grid_cols);
    const std::string error =
        error_of([&] { read_into<GridHdf5Reader>(file, "/grid", grid); });

    CHECK(contains(error, rejected));
}

void test_reports_a_datatype_of_the_wrong_class() {
    // 'kind' is declared as i32, but is stored as a float of the same size.
    check_grid_datatype_is_rejected(
        "wrong_class.h5", H5::PredType::IEEE_F64LE, H5::PredType::IEEE_F32LE,
        H5::PredType::STD_U16LE, "'/grid/kind' is not stored as 'i32'");
}

void test_reports_a_datatype_of_the_wrong_size() {
    // 'temperature' is declared as f64, but is stored as an f32.
    check_grid_datatype_is_rejected(
        "wrong_size.h5", H5::PredType::IEEE_F32LE, H5::PredType::STD_I32LE,
        H5::PredType::STD_U16LE, "'/grid/temperature' is not stored as 'f64'");
}

void test_reports_a_datatype_of_the_wrong_signedness() {
    // 'kind' is declared as i32, but is stored as a u32.
    check_grid_datatype_is_rejected(
        "wrong_sign.h5", H5::PredType::IEEE_F64LE, H5::PredType::STD_U32LE,
        H5::PredType::STD_U16LE, "'/grid/kind' is not stored as 'i32'");
}

// The byte order is one of the properties that a datatype carries,
// so an array of the right class, size and signedness is still rejected
// when it is stored the other way round.
void test_reports_a_datatype_of_the_wrong_byte_order() {
    check_grid_datatype_is_rejected(
        "wrong_order.h5", H5::PredType::IEEE_F64BE, H5::PredType::STD_I32LE,
        H5::PredType::STD_U16LE, "'/grid/temperature' is not stored as 'f64'");
}

// What the writer puts in a group is exactly what the reader takes back out.
void test_writes_a_row_major_dataset() {
    const std::string path = "written_grid.h5";
    {
        Grid grid(grid_rows, grid_cols);
        fill_expected(grid);

        H5::H5File file(path, H5F_ACC_TRUNC);
        GridHdf5Writer writer(file, "/out");
        writer.write_dataset(grid);
    }

    H5::H5File file(path, H5F_ACC_RDONLY);
    Grid grid(grid_rows, grid_cols);
    fill_untouched(grid);

    GridHdf5Reader reader(file, "/out");
    reader.read_dataset(grid);

    check_grid_holds_the_expected(grid);
}

// 'Field' is stored column major, so the elements are gathered before they
// are written and laid out again after they are read; an element that takes
// the wrong turn either way shows up here.
void test_writes_a_column_major_dataset() {
    const std::string path = "written_field.h5";
    {
        Field field(field_x, field_y, field_z);
        fill_expected(field);

        H5::H5File file(path, H5F_ACC_TRUNC);
        write_from<FieldHdf5Writer>(file, "/out", field);
    }

    H5::H5File file(path, H5F_ACC_RDONLY);
    Field field(field_x, field_y, field_z);
    read_into<FieldHdf5Reader>(file, "/out", field);

    check_field_holds_the_expected(field);
}

void test_write_creates_the_groups_that_are_missing() {
    const std::string path = "written_deep.h5";
    {
        Grid grid(grid_rows, grid_cols);
        fill_expected(grid);

        H5::H5File file(path, H5F_ACC_TRUNC);
        write_from<GridHdf5Writer>(file, "/a/b/c", grid);
    }

    H5::H5File file(path, H5F_ACC_RDONLY);
    CHECK(file.nameExists("/a"));
    CHECK(file.openGroup("/a").nameExists("b"));

    Grid grid(grid_rows, grid_cols);
    read_into<GridHdf5Reader>(file, "/a/b/c", grid);
    check_grid_holds_the_expected(grid);
}

// Writing over a group that already holds the arrays is not an error.
void test_write_replaces_the_arrays_that_are_there() {
    const std::string path = "written_twice.h5";
    {
        Grid grid(grid_rows, grid_cols);
        for (std::size_t row = 0; row < grid_rows; ++row) {
            for (std::size_t col = 0; col < grid_cols; ++col) {
                grid.temperature[row, col] = 0.0;
                grid.kind[row, col] = 0;
                grid.count[row, col] = 0;
            }
        }

        H5::H5File file(path, H5F_ACC_TRUNC);
        GridHdf5Writer writer(file, "/out");
        writer.write_dataset(grid);

        // The same writer writes the group again, over what it wrote before.
        fill_expected(grid);
        writer.write_dataset(grid);
    }

    H5::H5File file(path, H5F_ACC_RDONLY);
    Grid grid(grid_rows, grid_cols);
    read_into<GridHdf5Reader>(file, "/out", grid);

    check_grid_holds_the_expected(grid);
}

// The array that is replaced does not have to match what is written,
// so a group left over from something else is overwritten all the same.
void test_write_replaces_an_array_of_another_shape_and_datatype() {
    const std::string path = "written_over.h5";
    {
        H5::H5File file(path, H5F_ACC_TRUNC);
        H5::Group group = file.createGroup("/out");
        const std::vector<hsize_t> dims{1};
        write_array(group, "temperature", dims, H5::PredType::STD_I16LE,
                    H5::PredType::NATIVE_INT16, std::vector<std::int16_t>{7});
    }
    {
        Grid grid(grid_rows, grid_cols);
        fill_expected(grid);

        H5::H5File file(path, H5F_ACC_RDWR);
        write_from<GridHdf5Writer>(file, "/out", grid);
    }

    H5::H5File file(path, H5F_ACC_RDONLY);
    Grid grid(grid_rows, grid_cols);
    read_into<GridHdf5Reader>(file, "/out", grid);

    check_grid_holds_the_expected(grid);
}

void test_include_writes_only_the_arrays_it_lists() {
    const std::string path = "written_one.h5";
    {
        Grid grid(grid_rows, grid_cols);
        fill_expected(grid);

        H5::H5File file(path, H5F_ACC_TRUNC);
        write_from<GridTemperatureHdf5Writer>(file, "/out", grid);
    }

    H5::H5File file(path, H5F_ACC_RDONLY);
    const H5::Group group = file.openGroup("/out");
    CHECK(group.nameExists("temperature"));
    CHECK(!group.nameExists("kind"));
    CHECK(!group.nameExists("count"));

    Grid grid(grid_rows, grid_cols);
    fill_untouched(grid);
    read_into<GridTemperatureHdf5Reader>(file, "/out", grid);
    CHECK(grid.temperature[0, 0] == expected_temperature(0, 0));
    CHECK(grid.kind[0, 0] == untouched_kind);
}

// The name of the file that the compressed writers write,
// which the run without the plugins reads back.
const std::string kZstdFile = "written_grid_zstd.h5";

// Return the number of filters that the array called name of the group
// '/out' of the file called path is stored through.
int filters_of(const std::string& path, const std::string& name) {
    H5::H5File file(path, H5F_ACC_RDONLY);
    const H5::DataSet array = file.openDataSet("/out/" + name);
    return array.getCreatePlist().getNfilters();
}

// A chunk is worth asking for on its own, and asks for no filter.
void test_writes_a_chunked_dataset() {
    const std::string path = "written_grid_chunked.h5";
    {
        Grid grid(grid_rows, grid_cols);
        fill_expected(grid);

        H5::H5File file(path, H5F_ACC_TRUNC);
        write_from<GridChunkedHdf5Writer>(file, "/out", grid);
    }

    {
        H5::H5File file(path, H5F_ACC_RDONLY);
        const H5::DataSet array = file.openDataSet("/out/temperature");
        const H5::DSetCreatPropList plist = array.getCreatePlist();

        CHECK(plist.getLayout() == H5D_CHUNKED);
        CHECK(plist.getNfilters() == 0);

        std::array<hsize_t, 2> chunk = {0, 0};
        plist.getChunk(2, chunk.data());
        CHECK(chunk[0] == 1);
        CHECK(chunk[1] == 2);
    }

    H5::H5File file(path, H5F_ACC_RDONLY);
    Grid grid(grid_rows, grid_cols);
    fill_untouched(grid);
    read_into<GridHdf5Reader>(file, "/out", grid);

    check_grid_holds_the_expected(grid);
}

// Deflate is built into hdf5, so this round trip needs no plugin.
void test_writes_a_deflated_dataset() {
    const std::string path = "written_grid_deflate.h5";
    {
        Grid grid(grid_rows, grid_cols);
        fill_expected(grid);

        H5::H5File file(path, H5F_ACC_TRUNC);
        write_from<GridDeflateHdf5Writer>(file, "/out", grid);
    }

    // The shuffle filter and the compressor, in that order.
    CHECK(filters_of(path, "temperature") == 2);

    H5::H5File file(path, H5F_ACC_RDONLY);
    Grid grid(grid_rows, grid_cols);
    fill_untouched(grid);
    read_into<GridHdf5Reader>(file, "/out", grid);

    check_grid_holds_the_expected(grid);
}

// Zstandard is a filter that hdf5 loads at run time.
void test_writes_a_dataset_through_a_filter_of_a_plugin() {
    {
        Grid grid(grid_rows, grid_cols);
        fill_expected(grid);

        H5::H5File file(kZstdFile, H5F_ACC_TRUNC);
        write_from<GridZstdHdf5Writer>(file, "/out", grid);
    }

    CHECK(filters_of(kZstdFile, "temperature") == 2);

    {
        // The chunk of the writer reaches past the array,
        // so it was cut down to the array on the way out.
        H5::H5File file(kZstdFile, H5F_ACC_RDONLY);
        std::array<hsize_t, 2> chunk = {0, 0};
        file.openDataSet("/out/temperature").getCreatePlist().getChunk(
            2, chunk.data());
        CHECK(chunk[0] == grid_rows);
        CHECK(chunk[1] == grid_cols);
    }

    H5::H5File file(kZstdFile, H5F_ACC_RDONLY);
    Grid grid(grid_rows, grid_cols);
    fill_untouched(grid);
    read_into<GridHdf5Reader>(file, "/out", grid);

    check_grid_holds_the_expected(grid);
}

// A filter that takes no level is asked for with none.
void test_writes_a_dataset_through_a_filter_without_a_level() {
    const std::string path = "written_grid_lz4.h5";
    {
        Grid grid(grid_rows, grid_cols);
        fill_expected(grid);

        H5::H5File file(path, H5F_ACC_TRUNC);
        write_from<GridLz4Hdf5Writer>(file, "/out", grid);
    }

    CHECK(filters_of(path, "temperature") == 1);

    H5::H5File file(path, H5F_ACC_RDONLY);
    Grid grid(grid_rows, grid_cols);
    fill_untouched(grid);
    read_into<GridHdf5Reader>(file, "/out", grid);

    check_grid_holds_the_expected(grid);
}

// A column major dataset is gathered into row major order before it is
// compressed, so an element that takes a wrong turn shows up here.
void test_writes_a_compressed_column_major_dataset() {
    const std::string path = "written_field_zstd.h5";
    {
        Field field(field_x, field_y, field_z);
        fill_expected(field);

        H5::H5File file(path, H5F_ACC_TRUNC);
        write_from<FieldZstdHdf5Writer>(file, "/out", field);
    }

    CHECK(filters_of(path, "value") == 2);

    H5::H5File file(path, H5F_ACC_RDONLY);
    Field field(field_x, field_y, field_z);
    read_into<FieldHdf5Reader>(file, "/out", field);

    check_field_holds_the_expected(field);
}

// Without the plugin, a writer says so before it writes anything,
// and a reader says so about the file that was written with it.
// This runs with HDF5_PLUGIN_PATH cleared,
// after the run that leaves the file behind.
void test_reports_a_filter_that_is_not_there() {
    Grid grid(grid_rows, grid_cols);
    fill_expected(grid);

    H5::H5File out("written_grid_no_plugin.h5", H5F_ACC_TRUNC);
    const std::string write_error =
        error_of([&] { write_from<GridZstdHdf5Writer>(out, "/out", grid); });
    CHECK(contains(write_error, "the 'zstd' filter is not available"));
    CHECK(contains(write_error, "HDF5_PLUGIN_PATH"));

    // Deflate is built into hdf5, so it is there whatever the plugin path is.
    CHECK(error_of([&] {
              write_from<GridDeflateHdf5Writer>(out, "/deflate", grid);
          }).empty());

    // The run with the plugins leaves the file behind, and ctest orders it
    // before this one; on its own there is nothing here to read back.
    if (!std::filesystem::exists(kZstdFile)) {
        std::printf("FAIL '%s' is not there; run the 'hdf5' test first\n",
                    kZstdFile.c_str());
        ++failures;
        return;
    }

    H5::H5File file(kZstdFile, H5F_ACC_RDONLY);
    const std::string read_error =
        error_of([&] { read_into<GridHdf5Reader>(file, "/out", grid); });
    CHECK(contains(read_error, "is stored with a filter that is not available"));
    CHECK(contains(read_error, "HDF5_PLUGIN_PATH"));
}

// A part of every array is read and written through a hyperslab,
// which the offset places and the shape of the dataset sizes.
void test_reads_and_writes_a_part_of_a_dataset() {
    const std::string path = "partial_grid.h5";
    {
        Grid grid(grid_rows, grid_cols);
        fill_expected(grid);

        H5::H5File file(path, H5F_ACC_TRUNC);
        write_from<GridHdf5Writer>(file, "/out", grid);
    }

    // One row of the file fills a dataset of one row.
    {
        H5::H5File file(path, H5F_ACC_RDONLY);
        GridHdf5Reader reader(file, "/out");

        Grid row(1, grid_cols);
        fill_untouched(row);
        std::array<std::size_t, 2> offset = {1, 0};
        reader.read_partial_dataset(row, offset);

        for (std::size_t col = 0; col < grid_cols; ++col) {
            CHECK(row.temperature[0, col] == expected_temperature(1, col));
            CHECK(row.kind[0, col] == expected_kind(1, col));
            CHECK(row.count[0, col] == expected_count(1, col));
        }
    }

    // Another row of it is written on its own, over what was there.
    {
        H5::H5File file(path, H5F_ACC_RDWR);
        GridHdf5Writer writer(file, "/out");

        Grid row(1, grid_cols);
        for (std::size_t col = 0; col < grid_cols; ++col) {
            row.temperature[0, col] = -1.5;
            row.kind[0, col] = -2;
            row.count[0, col] = 3;
        }

        std::array<std::size_t, 2> offset = {0, 0};
        writer.write_partial_dataset(row, offset);
    }

    H5::H5File file(path, H5F_ACC_RDONLY);
    Grid grid(grid_rows, grid_cols);
    read_into<GridHdf5Reader>(file, "/out", grid);

    for (std::size_t col = 0; col < grid_cols; ++col) {
        CHECK(grid.temperature[0, col] == -1.5);
        CHECK(grid.kind[0, col] == -2);
        CHECK(grid.count[0, col] == 3);

        // The row that was not written keeps what it held.
        CHECK(grid.temperature[1, col] == expected_temperature(1, col));
        CHECK(grid.kind[1, col] == expected_kind(1, col));
    }
}

// 'Field' is stored column major, so a part of it is gathered and laid out
// again around the hyperslab, one part at a time.
void test_reads_and_writes_a_part_of_a_column_major_dataset() {
    const std::string path = "partial_field.h5";
    {
        Field field(field_x, field_y, field_z);
        fill_expected(field);

        H5::H5File file(path, H5F_ACC_TRUNC);
        write_from<FieldHdf5Writer>(file, "/out", field);
    }

    {
        H5::H5File file(path, H5F_ACC_RDONLY);
        FieldHdf5Reader reader(file, "/out");

        Field part(1, field_y, field_z);
        std::array<std::size_t, 3> offset = {1, 0, 0};
        reader.read_partial_dataset(part, offset);

        for (std::size_t y = 0; y < field_y; ++y) {
            for (std::size_t z = 0; z < field_z; ++z) {
                CHECK(part.value[0, y, z] == expected_value(1, y, z));
                CHECK(part.tag[0, y, z] == expected_tag(1, y, z));
            }
        }
    }

    {
        H5::H5File file(path, H5F_ACC_RDWR);
        FieldHdf5Writer writer(file, "/out");

        Field part(1, field_y, field_z);
        for (std::size_t y = 0; y < field_y; ++y) {
            for (std::size_t z = 0; z < field_z; ++z) {
                part.value[0, y, z] = -expected_value(0, y, z);
                part.tag[0, y, z] = 0;
            }
        }

        std::array<std::size_t, 3> offset = {0, 0, 0};
        writer.write_partial_dataset(part, offset);
    }

    H5::H5File file(path, H5F_ACC_RDONLY);
    Field field(field_x, field_y, field_z);
    read_into<FieldHdf5Reader>(file, "/out", field);

    for (std::size_t y = 0; y < field_y; ++y) {
        for (std::size_t z = 0; z < field_z; ++z) {
            CHECK(field.value[0, y, z] == -expected_value(0, y, z));
            CHECK(field.tag[0, y, z] == 0);

            // The part that was not written keeps what it held.
            CHECK(field.value[1, y, z] == expected_value(1, y, z));
            CHECK(field.tag[1, y, z] == expected_tag(1, y, z));
        }
    }
}

// An offset says where the part begins along every dim, and no more.
void test_reports_an_offset_of_the_wrong_size() {
    const std::string path = write_test_file();
    H5::H5File file(path, H5F_ACC_RDONLY);
    GridHdf5Reader reader(file, "/sim/grid");

    Grid row(1, grid_cols);
    std::array<std::size_t, 1> offset = {0};
    const std::string error =
        error_of([&] { reader.read_partial_dataset(row, offset); });

    CHECK(contains(error, "offset must hold one index per dim of 'Grid'"));
}

// A part that reaches past the array is reported rather than cut down.
void test_reports_a_part_that_does_not_fit() {
    const std::string path = write_test_file();
    H5::H5File file(path, H5F_ACC_RDONLY);
    GridHdf5Reader reader(file, "/sim/grid");

    Grid row(1, grid_cols);
    std::array<std::size_t, 2> offset = {grid_rows, 0};
    const std::string error =
        error_of([&] { reader.read_partial_dataset(row, offset); });

    CHECK(contains(error, "'/sim/grid/temperature' has extent 2, "
                          "which does not hold 1 elements at offset 2 "
                          "along dimension 0"));
}

// A part is written into an array that is already there,
// which is what write_dataset creates.
void test_reports_a_part_written_into_a_group_without_the_array() {
    const std::string path = "partial_missing.h5";
    {
        H5::H5File file(path, H5F_ACC_TRUNC);
        H5::Group group = file.createGroup("/out");
    }

    H5::H5File file(path, H5F_ACC_RDWR);
    GridHdf5Writer writer(file, "/out");

    Grid row(1, grid_cols);
    fill_untouched(row);
    std::array<std::size_t, 2> offset = {0, 0};
    const std::string error =
        error_of([&] { writer.write_partial_dataset(row, offset); });

    CHECK(contains(error, "'/out/temperature' is not in the HDF5 file"));
}

void test_write_reports_a_file_that_is_open_for_reading() {
    const std::string path = write_test_file();
    H5::H5File file(path, H5F_ACC_RDONLY);

    Grid grid(grid_rows, grid_cols);
    fill_expected(grid);
    const std::string error =
        error_of([&] { write_from<GridHdf5Writer>(file, "/out", grid); });

    CHECK(contains(error, "failed to write '/out'"));
}

}  // namespace

int main(int argc, char** argv) {
    // The readers report their errors by throwing,
    // so the library does not have to print them as well.
    H5::Exception::dontPrint();

    // The run without the plugins reads the file that the run with them
    // leaves behind, and checks nothing that needs a filter of a plugin.
    if (argc > 1 && std::string(argv[1]) == "--without-plugins") {
        test_reports_a_filter_that_is_not_there();

        if (failures == 0) {
            std::printf("all checks passed\n");
            return 0;
        }
        std::printf("%d check(s) failed\n", failures);
        return 1;
    }

    test_reads_every_array();
    test_include_reads_only_the_arrays_it_lists();
    test_exclude_reads_every_other_array();
    test_reads_a_column_major_dataset();

    test_reports_a_missing_group();
    test_reports_a_missing_array();
    test_a_skipped_array_may_be_missing();
    test_reports_a_shape_that_does_not_match();
    test_reports_a_rank_that_does_not_match();
    test_reports_a_datatype_of_the_wrong_class();
    test_reports_a_datatype_of_the_wrong_size();
    test_reports_a_datatype_of_the_wrong_signedness();
    test_reports_a_datatype_of_the_wrong_byte_order();

    test_writes_a_row_major_dataset();
    test_writes_a_column_major_dataset();
    test_write_creates_the_groups_that_are_missing();
    test_write_replaces_the_arrays_that_are_there();
    test_write_replaces_an_array_of_another_shape_and_datatype();
    test_include_writes_only_the_arrays_it_lists();
    test_write_reports_a_file_that_is_open_for_reading();

    test_writes_a_chunked_dataset();
    test_writes_a_deflated_dataset();
    test_writes_a_dataset_through_a_filter_of_a_plugin();
    test_writes_a_dataset_through_a_filter_without_a_level();
    test_writes_a_compressed_column_major_dataset();

    test_reads_and_writes_a_part_of_a_dataset();
    test_reads_and_writes_a_part_of_a_column_major_dataset();
    test_reports_an_offset_of_the_wrong_size();
    test_reports_a_part_that_does_not_fit();
    test_reports_a_part_written_into_a_group_without_the_array();

    if (failures == 0) {
        std::printf("all checks passed\n");
        return 0;
    }
    std::printf("%d check(s) failed\n", failures);
    return 1;
}
