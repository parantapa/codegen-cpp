cmake_minimum_required(VERSION 3.23)
project(codegen_cpp_tests CXX)

find_package(Arrow REQUIRED)
find_package(HDF5 REQUIRED)
find_package(hdf5_plugins REQUIRED)
find_package(mdspan REQUIRED)

find_program(
    CODEGEN_CPP codegen-cpp
    HINTS "${CMAKE_CURRENT_SOURCE_DIR}/../../.venv/bin"
    REQUIRED
)

set(GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")

# Regenerate whenever a specification or one of the templates changes.
file(GLOB TEMPLATES
     "${CMAKE_CURRENT_SOURCE_DIR}/../../src/codegen_cpp/templates/*.jinja")

# Each specification becomes a single header named after it.
# The tables and the datasets are kept apart
# so that each test only pulls in the library it is linked against.
function(add_generated_header name)
    set(spec "${CMAKE_CURRENT_SOURCE_DIR}/${name}.toml")
    set(header "${GENERATED_DIR}/${name}.hpp")

    add_custom_command(
        OUTPUT "${header}"
        COMMAND "${CODEGEN_CPP}" generate "${spec}" --output-file "${header}"
        DEPENDS "${spec}" ${TEMPLATES}
        COMMENT "Generating ${header} from ${spec}"
        VERBATIM
    )

    add_custom_target(${name}_header DEPENDS "${header}")
    set(${name}_HEADER "${header}" PARENT_SCOPE)
endfunction()

add_generated_header(tables)
add_generated_header(datasets)
add_generated_header(nested)

add_executable(test_readers test_readers.cpp "${tables_HEADER}")
add_dependencies(test_readers tables_header)

target_include_directories(test_readers PRIVATE "${GENERATED_DIR}")
target_compile_features(test_readers PRIVATE cxx_std_23)
target_compile_options(test_readers PRIVATE -Wall -Wextra -Wshadow -Werror)
target_link_libraries(
    test_readers PRIVATE Arrow::arrow_static Parquet::parquet_static
)

add_executable(test_hdf5 test_hdf5.cpp "${datasets_HEADER}")
add_dependencies(test_hdf5 datasets_header)

target_include_directories(test_hdf5 PRIVATE "${GENERATED_DIR}")
target_compile_features(test_hdf5 PRIVATE cxx_std_23)
target_compile_options(test_hdf5 PRIVATE -Wall -Wextra -Wshadow -Werror)
# The plugin package holds the filters that hdf5 loads at run time.
# Linking it adds nothing to the program against a shared hdf5,
# and against a static one it exports the hdf5 symbols of the program,
# which is where a filter loaded into it looks them up.
target_link_libraries(
    test_hdf5 PRIVATE hdf5::hdf5_cpp std::mdspan hdf5_plugins::hdf5_plugins
)

add_executable(test_nested test_nested.cpp "${nested_HEADER}")
add_dependencies(test_nested nested_header)

target_include_directories(test_nested PRIVATE "${GENERATED_DIR}")
target_compile_features(test_nested PRIVATE cxx_std_23)
target_compile_options(test_nested PRIVATE -Wall -Wextra -Wshadow -Werror)
target_link_libraries(
    test_nested PRIVATE Arrow::arrow_static Parquet::parquet_static
)

enable_testing()

# Conan names the plugin directory after the build type it packaged.
string(TOUPPER "${CMAKE_BUILD_TYPE}" HDF5_PLUGINS_CONFIG)
set(HDF5_PLUGIN_PATH
    "${hdf5_plugins_PACKAGE_FOLDER_${HDF5_PLUGINS_CONFIG}}/lib/plugin")

add_test(NAME readers COMMAND test_readers)
add_test(NAME hdf5 COMMAND test_hdf5)
add_test(NAME nested COMMAND test_nested)

# The filters that hdf5 loads at run time are found through this path.
set_tests_properties(
    hdf5 PROPERTIES ENVIRONMENT "HDF5_PLUGIN_PATH=${HDF5_PLUGIN_PATH}"
)

# The same test binary without the plugins, which checks what is reported
# then; it reads the file that the run above leaves behind.
add_test(NAME hdf5_without_plugins COMMAND test_hdf5 --without-plugins)
set_tests_properties(
    hdf5_without_plugins PROPERTIES ENVIRONMENT "HDF5_PLUGIN_PATH=" DEPENDS hdf5
)
