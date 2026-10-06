# Fill an HDF5 file one window at a time

A table holds rows.
The other half of `codegen-cpp` holds n-dimensional arrays,
which it calls a dataset,
and reads and writes them through HDF5.
In this tutorial, we declare a dataset, write it into a file, and read it back.
Then we lay out an array far larger than the memory we give it.
We fill that array in one window at a time.
We finish by compressing what we write.

This tutorial stands on its own,
though [Convert a CSV file into a Parquet file](convert-a-csv-file-into-a-parquet-file.md)
sets the tools up at a slower pace.
We need `codegen-cpp` on the path,
a C++23 compiler, CMake 3.23 or later, and Conan 2.

## Set the project up

```bash
mkdir terrain
cd terrain
```

The generated code needs the HDF5 C++ API and `mdspan`.
Write `conanfile.txt`:

```toml
[requires]
hdf5/1.14.6
mdspan/0.6.0

[options]
hdf5/*:enable_cxx=True

[generators]
CMakeDeps
CMakeToolchain

[layout]
cmake_layout
```

```bash
conan install . --build=missing -of build -s compiler.cppstd=20
```

Write `CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.23)
project(terrain CXX)

find_package(HDF5 REQUIRED)
find_package(mdspan REQUIRED)

add_executable(terrain main.cpp)
target_include_directories(terrain PRIVATE "${CMAKE_SOURCE_DIR}")
target_compile_features(terrain PRIVATE cxx_std_23)
target_link_libraries(terrain PRIVATE hdf5::hdf5_cpp std::mdspan)
```

## Declare a dataset

A dataset is a group of arrays that share one shape.
Write `terrain.toml`:

```toml
[[dataset]]
name = "Raster"
dims = ["row", "col"]
arrays = [
    { name = "elevation", type = "f32" },
    { name = "land_class", type = "u8" },
]

[[hdf5_writer]]
name = "RasterHdf5Writer"
dataset = "Raster"

[[hdf5_reader]]
name = "RasterHdf5Reader"
dataset = "Raster"
```

`dims` names one dimension per axis,
so this dataset is rank two and both of its arrays are rank two.
The names are documentation and the names of the constructor parameters.
The program chooses the sizes at run time, not here.

Generate the header:

```bash
codegen-cpp generate terrain.toml
```

and read the struct that came out of the dataset:

```cpp
struct Raster {
    static constexpr std::size_t rank = 2;

    std::vector<std::size_t> dims;

    std::unique_ptr<float[]> _mem_elevation;
    span_type<float> elevation;

    std::unique_ptr<std::uint8_t[]> _mem_land_class;
    span_type<std::uint8_t> land_class;

    Raster(
        std::size_t row,
        std::size_t col)
    ...
};
```

Each array is two members: a `std::unique_ptr` that owns the memory,
and an `mdspan` of the dataset's rank that we read and write through.
The constructor takes one size per dimension.
Notice that it allocates without initializing the elements.
So we must write an element before we read it.

## Write the arrays into a file

Write `main.cpp`:

```cpp
#include <array>
#include <cstdio>

#include <H5Cpp.h>

#include "terrain.hpp"

int main() {
    Raster tile(4, 8);
    for (std::size_t r = 0; r < tile.dims[0]; ++r) {
        for (std::size_t c = 0; c < tile.dims[1]; ++c) {
            tile.elevation[r, c] = static_cast<float>(10 * r + c);
            tile.land_class[r, c] = static_cast<std::uint8_t>(r);
        }
    }

    H5::H5File file("terrain.h5", H5F_ACC_TRUNC);
    RasterHdf5Writer writer(file, "/survey/tile");
    writer.write_dataset(tile);

    std::printf("wrote %zu elements per array\n", tile.size());
    return 0;
}
```

We reach an element with the C++23 subscript, `tile.elevation[r, c]`,
one index per dimension.
The writer takes the open file and the path of a group inside it.
It creates that group and the group above it, because neither is there yet.

Build and run:

```bash
cmake -S . -B build/cpp \
    -DCMAKE_TOOLCHAIN_FILE="$PWD/build/build/Release/generators/conan_toolchain.cmake" \
    -DCMAKE_BUILD_TYPE=Release
cmake --build build/cpp
./build/cpp/terrain
```

```
wrote 32 elements per array
```

The file holds one HDF5 dataset per array of ours,
named after the array, at `/survey/tile/elevation`
and `/survey/tile/land_class`.

## Read them back

A reader is the mirror image of the writer.
Add one at the end of `main`, before the `return`:

```cpp
    Raster back(4, 8);
    RasterHdf5Reader reader(file, "/survey/tile");
    reader.read_dataset(back);

    std::printf("elevation[3, 7] is %g, land_class[3, 7] is %d\n",
                back.elevation[3, 7], static_cast<int>(back.land_class[3, 7]));
```

Build and run:

```bash
cmake --build build/cpp
./build/cpp/terrain
```

```
wrote 32 elements per array
elevation[3, 7] is 37, land_class[3, 7] is 3
```

Notice that we allocated `back` ourselves, with the shape we expect.
A reader fills arrays in rather than sizing them.
It checks the file against the shape we gave it.
If we ask for a shape that the file does not hold,
the reader does not quietly resize the arrays.
Add these two lines below the ones we just added:

```cpp
    Raster wrong(4, 9);
    reader.read_dataset(wrong);
```

Run the program again.
The run ends where the reader gives up:

```
terminate called after throwing an instance of 'std::runtime_error'
  what():  '/survey/tile/elevation' has extent 8 instead of 9 along dimension 1
```

Take those two lines out again before going on.

## Read one array and leave the other alone

A reader does not have to read every array of its dataset.
In `terrain.toml`, add a reader that reads a single array:

```toml
[[hdf5_reader]]
name = "ElevationHdf5Reader"
dataset = "Raster"
include = ["elevation"]
```

`include` names the arrays that the reader reads.
Use it at the end of `main`:

```cpp
    Raster partial(4, 8);
    partial.land_class[3, 7] = 99;

    ElevationHdf5Reader elevation_reader(file, "/survey/tile");
    elevation_reader.read_dataset(partial);

    std::printf("elevation[3, 7] is %g, land_class[3, 7] is %d\n",
                partial.elevation[3, 7],
                static_cast<int>(partial.land_class[3, 7]));
```

Generate, build, and run:

```bash
codegen-cpp generate terrain.toml
cmake --build build/cpp
./build/cpp/terrain
```

```
wrote 32 elements per array
elevation[3, 7] is 37, land_class[3, 7] is 3
elevation[3, 7] is 37, land_class[3, 7] is 99
```

The array we left out kept the 99 we put there.
That is how a program reads one group in more than one pass.
It is also how a program reads the one array it needs
out of a group that holds twenty.

## Lay out an array larger than memory

`write_dataset` writes a dataset that we hold in memory,
so the file can never be larger than what we allocated.
Two other methods split that in half.
`create_dataset` lays the arrays out at whatever shape we name,
and writes nothing into them.
`write_partial_dataset` fills in a block of that shape.

Write a raster of a million rows, a window of four thousand rows at a time.
Replace the body of `main` with this:

```cpp
int main() {
    const std::size_t rows = 1048576;
    const std::size_t cols = 64;
    const std::size_t window_rows = 4096;

    H5::H5File file("big.h5", H5F_ACC_TRUNC);
    RasterHdf5Writer writer(file, "/survey/big");

    std::array<std::size_t, 2> shape = {rows, cols};
    writer.create_dataset(shape);

    Raster window(window_rows, cols);
    for (std::size_t base = 0; base < rows; base += window_rows) {
        for (std::size_t r = 0; r < window_rows; ++r) {
            for (std::size_t c = 0; c < cols; ++c) {
                window.elevation[r, c] = static_cast<float>((base + r) % 512);
                window.land_class[r, c] = static_cast<std::uint8_t>(c % 8);
            }
        }

        std::array<std::size_t, 2> offset = {base, 0};
        writer.write_partial_dataset(window, offset);
    }

    std::printf("laid out %zu by %zu and filled it\n", rows, cols);
    return 0;
}
```

`create_dataset` takes one extent per dimension and allocates nothing of ours.
`offset` says where the window begins, again one index per dimension,
and the shape we allocated the window with says how large it is.
Together, the two name the block that the writer writes the window into.
So the loop walks the file 4096 rows at a time,
in a window that holds 4096 rows.

Build and run:

```bash
cmake --build build/cpp
./build/cpp/terrain
```

```
laid out 1048576 by 64 and filled it
```

```bash
ls -lh big.h5
```

```
-rw-r--r-- 1 you you 321M ... big.h5
```

The file holds 320 MB of arrays,
and the program never allocated more than 1.25 MB of them at once.

Read one row back the same way.
Add this before the `return`:

```cpp
    Raster strip(1, cols);
    std::array<std::size_t, 2> read_offset = {500000, 0};

    RasterHdf5Reader reader(file, "/survey/big");
    reader.read_partial_dataset(strip, read_offset);

    std::printf("row 500000 starts at %g\n", strip.elevation[0, 0]);
```

Build and run:

```bash
cmake --build build/cpp
./build/cpp/terrain
```

```
laid out 1048576 by 64 and filled it
row 500000 starts at 288
```

Notice that the window we read with is one row,
where the window we wrote with was four thousand.
Nothing ties the two together.
Remember the rule that the two partial methods share.
A whole read asks the file to have exactly the shape we allocated.
A partial read asks only for room beyond the offset.
So the file can be larger than the window we take out of it.

## Compress what we write

A writer can also say how HDF5 lays out the arrays in the file.
Add one that stores them in chunks and compresses each chunk:

```toml
[[hdf5_writer]]
name = "RasterCompressedHdf5Writer"
dataset = "Raster"
chunk = [4096, 64]
compression = "deflate"
compression_level = 6
shuffle = true
```

`chunk` is the shape of one chunk, one extent per dimension.
It turns the contiguous layout that a writer uses by default
into the chunked layout that a filter needs.
For this reason, the other three keys all ask for it.
`shuffle` sorts the bytes of the elements by position
before HDF5 compresses them.
On an array of numbers, the shuffle usually improves the compression ratio.

Notice that the chunk is the shape of the window we write.
HDF5 compresses each chunk as a unit.
So HDF5 compresses a window that covers whole chunks once.
A window that covers a part of a chunk
makes HDF5 read that chunk back, unpack it, and pack it again.
When a program fills a file this way, line the two up.

Change the one line of `main` that names the writer:

```cpp
    RasterCompressedHdf5Writer writer(file, "/survey/big");
```

Generate, build, and run:

```bash
codegen-cpp generate terrain.toml
cmake --build build/cpp
./build/cpp/terrain
ls -lh big.h5
```

```
laid out 1048576 by 64 and filled it
row 500000 starts at 288
-rw-r--r-- 1 you you 2.5M ... big.h5
```

The same 320 MB of arrays now take under 3 MB.
The program that reads them did not change at all.
A reader is unaware of compression,
because HDF5 decompresses an array as it reads it.

We used `deflate` here, which is built into HDF5 itself.
[The specification](../reference/specification.md) lists the other codecs
and what each one needs.

## What we have built

We declared a dataset of two arrays.
We wrote it into a group of an HDF5 file and read it back.
We also read one of its arrays without disturbing the other.
Then we laid out a 320 MB raster and filled it from a window of 1.25 MB.
We read one row back out of the middle of it.
Last, we asked for a chunk and a codec,
which compressed the whole thing down to 2.5 MB.

From here:

- [Store nested columns in a Parquet file](store-nested-columns-in-a-parquet-file.md)
  is the row-oriented half of the tool.
- [The specification](../reference/specification.md) lists every option
  a dataset, a reader and a writer take.
- [The generated code](../reference/generated-code.md)
  describes what each method checks,
  and what it reports when a file does not match.
