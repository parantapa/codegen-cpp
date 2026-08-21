cmake_minimum_required(VERSION 3.23)
project(codegen_cpp_tests CXX)

find_package(Arrow REQUIRED)
find_package(HDF5 REQUIRED)
find_package(mdspan REQUIRED)

find_program(
    CODEGEN_CPP codegen-cpp
    HINTS "${CMAKE_CURRENT_SOURCE_DIR}/../../.venv/bin"
    REQUIRED
)

set(SPEC "${CMAKE_CURRENT_SOURCE_DIR}/spec.toml")
set(GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
set(GENERATED_HEADERS
    "${GENERATED_DIR}/Point.hpp"
    "${GENERATED_DIR}/PointCsvReader.hpp"
    "${GENERATED_DIR}/PointParquetReader.hpp"
    "${GENERATED_DIR}/PointCsvWriter.hpp"
    "${GENERATED_DIR}/PointParquetWriter.hpp"
    "${GENERATED_DIR}/Grid.hpp"
    "${GENERATED_DIR}/Field.hpp"
    "${GENERATED_DIR}/read_grid.hpp"
    "${GENERATED_DIR}/read_grid_temperature.hpp"
    "${GENERATED_DIR}/read_grid_labels.hpp"
    "${GENERATED_DIR}/read_field.hpp"
    "${GENERATED_DIR}/write_grid.hpp"
    "${GENERATED_DIR}/write_grid_temperature.hpp"
    "${GENERATED_DIR}/write_field.hpp"
)

# Regenerate whenever the specification or one of the templates changes.
file(GLOB TEMPLATES
     "${CMAKE_CURRENT_SOURCE_DIR}/../../src/codegen_cpp/templates/*.jinja")

add_custom_command(
    OUTPUT ${GENERATED_HEADERS}
    COMMAND "${CODEGEN_CPP}" generate "${SPEC}" --output-dir "${GENERATED_DIR}"
    DEPENDS "${SPEC}" ${TEMPLATES}
    COMMENT "Generating C++ headers from ${SPEC}"
    VERBATIM
)

add_custom_target(generated_headers DEPENDS ${GENERATED_HEADERS})

add_executable(test_readers test_readers.cpp ${GENERATED_HEADERS})
add_dependencies(test_readers generated_headers)

target_include_directories(test_readers PRIVATE "${GENERATED_DIR}")
target_compile_features(test_readers PRIVATE cxx_std_23)
target_compile_options(test_readers PRIVATE -Wall -Wextra -Wshadow -Werror)
target_link_libraries(
    test_readers PRIVATE Arrow::arrow_static Parquet::parquet_static
)

add_executable(test_hdf5 test_hdf5.cpp ${GENERATED_HEADERS})
add_dependencies(test_hdf5 generated_headers)

target_include_directories(test_hdf5 PRIVATE "${GENERATED_DIR}")
target_compile_features(test_hdf5 PRIVATE cxx_std_23)
target_compile_options(test_hdf5 PRIVATE -Wall -Wextra -Wshadow -Werror)
target_link_libraries(test_hdf5 PRIVATE hdf5::hdf5_cpp std::mdspan)

enable_testing()
add_test(NAME readers COMMAND test_readers)
add_test(NAME hdf5 COMMAND test_hdf5)
