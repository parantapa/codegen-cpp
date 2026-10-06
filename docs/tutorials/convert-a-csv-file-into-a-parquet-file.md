# Convert a CSV file into a Parquet file

In this tutorial, we write a specification
and generate a C++ header from it.
We build a program that reads a CSV file
and writes the rows back out as Parquet.
Then we read the Parquet file back and write a CSV file from it.
As a result, each of the four table classes of `codegen-cpp` runs once.

We need `codegen-cpp` on the path,
a C++23 compiler, CMake 3.23 or later, and Conan 2.
The [README](../../README.md) says how to install the generator.

## Set the project up

Everything we write lives in one directory:

```bash
mkdir weather
cd weather
```

The generated code reads and writes its files through Apache Arrow,
which we install with Conan.
Write `conanfile.txt`:

```toml
[requires]
arrow/25.0.1

[options]
arrow/*:parquet=True
arrow/*:with_csv=True
arrow/*:with_thrift=True
arrow/*:with_snappy=True
arrow/*:with_zlib=True
arrow/*:with_zstd=True

[generators]
CMakeDeps
CMakeToolchain

[layout]
cmake_layout
```

Now install it.
Arrow needs C++20 or later, which the default Conan profile does not ask for,
so we ask for it here:

```bash
conan install . --build=missing -of build -s compiler.cppstd=20
```

The first run builds what it cannot download, and takes a while.
Later runs find the packages already built.

## Make a CSV file to read

Write `measurements.csv`:

```csv
station_id,temperature,humidity,note
101,12.5,0.41,clear
101,13.125,0.44,clear
204,-3.25,0.8,snow
204,-4.0,0.82,drifting
307,21.75,0.15,calm
```

The file has five rows, four columns, and a header line that names them.

## Write the specification

A specification is a TOML file
that declares the data we hold and the classes that move it in and out.
Write `weather.toml`:

```toml
[[table]]
name = "Measurement"
columns = [
    { name = "station_id", type = "i64" },
    { name = "temperature", type = "f64" },
    { name = "humidity", type = "f32" },
    { name = "note", type = "str" },
]

[[csv_reader]]
name = "MeasurementCsvReader"
table = "Measurement"
```

The `table` section is the data.
It names the table `Measurement`.
It gives the table one column for each column of our file.
Each column has a name and a type.
The `csv_reader` section is a class that fills that table from a CSV file.

Check that the generator reads it the way we meant:

```bash
codegen-cpp debug parse-spec weather.toml
```

It prints the specification as the generator understands it:

```
Spec(
    tables=[
        Table(
            name='Measurement',
            columns=[
                Column(name='station_id', type=<ScalarType.i64: 'i64'>),
                Column(name='temperature', type=<ScalarType.f64: 'f64'>),
                Column(name='humidity', type=<ScalarType.f32: 'f32'>),
                Column(name='note', type=<ScalarType.str: 'str'>)
            ]
        )
    ],
    datasets=[],
...
```

Notice that the sections we did not write are there and empty.
This command generates nothing.
It reads the specification and stops,
which is the quickest way to find a typo.

## Generate the header

```bash
codegen-cpp generate weather.toml
```

```
Generated weather.hpp
```

The whole specification becomes that one header, and nothing else.
Open it and find the struct that the table became:

```cpp
struct Measurement {
    struct row_type {
        std::int64_t station_id;
        double temperature;
        float humidity;
        std::string note;
    };

    std::vector<std::int64_t> station_id;
    std::vector<double> temperature;
    std::vector<float> humidity;
    std::vector<std::string> note;
    ...
};
```

Notice that the table holds a `std::vector` per column
rather than a vector of rows.
The names we wrote in the specification are the member names,
and `row_type` is a single row by value, for the times we want one.

Below the struct is the class `MeasurementCsvReader`.
The generator writes every name we declare in the specification
into the header under that name.
So a name we choose is the name our program spells.

## Read the file

Write `main.cpp`:

```cpp
#include <cstdio>

#include "weather.hpp"

int main() {
    MeasurementCsvReader reader("measurements.csv", 2);

    Measurement batch;
    while (reader.has_more_batches()) {
        batch.clear();
        reader.read_batch(batch);

        std::printf("batch of %zu rows\n", batch.size());
        for (std::size_t i = 0; i < batch.size(); ++i) {
            const auto row = batch[i];
            std::printf("  %ld %g %g %s\n", row.station_id, row.temperature,
                        row.humidity, row.note.c_str());
        }
    }

    return 0;
}
```

The reader takes the path of the file
and the number of rows we want per batch.
Here the number is two, so that we can watch the loop go around.
A reader appends to the table we give it.
It does not replace what is in the table.
For this reason, we call `clear()` at the top of each turn.

Write `CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.23)
project(weather CXX)

find_package(Arrow REQUIRED)

add_executable(weather main.cpp)
target_include_directories(weather PRIVATE "${CMAKE_SOURCE_DIR}")
target_compile_features(weather PRIVATE cxx_std_23)
target_link_libraries(
    weather PRIVATE Arrow::arrow_static Parquet::parquet_static
)
```

The generated classes are header only,
so the header goes on the include path and nothing goes into the build.
Configure and build:

```bash
cmake -S . -B build/cpp \
    -DCMAKE_TOOLCHAIN_FILE="$PWD/build/build/Release/generators/conan_toolchain.cmake" \
    -DCMAKE_BUILD_TYPE=Release
cmake --build build/cpp
```

Run it:

```bash
./build/cpp/weather
```

```
batch of 2 rows
  101 12.5 0.41 clear
  101 13.125 0.44 clear
batch of 2 rows
  204 -3.25 0.8 snow
  204 -4 0.82 drifting
batch of 1 rows
  307 21.75 0.15 calm
```

The program reads five rows in batches of two.
The last batch is short.
A file of any size reads this way,
because only one batch is in memory at a time.

## Write the rows out as Parquet

Add a writer to `weather.toml`:

```toml
[[parquet_writer]]
name = "MeasurementParquetWriter"
table = "Measurement"
```

A writer names the same table that the reader fills,
which is what makes the two halves fit.
Now put it in the loop in `main.cpp`:

```cpp
#include <cstdio>

#include "weather.hpp"

int main() {
    MeasurementCsvReader reader("measurements.csv", 2);
    MeasurementParquetWriter writer("measurements.parquet");

    Measurement batch;
    while (reader.has_more_batches()) {
        batch.clear();
        reader.read_batch(batch);
        writer.write_batch(batch);
    }

    writer.close();

    std::printf("wrote measurements.parquet\n");
    return 0;
}
```

Generate the header again, and build and run:

```bash
codegen-cpp generate weather.toml
cmake --build build/cpp
./build/cpp/weather
```

```
wrote measurements.parquet
```

Remember to call `close()`.
The destructor closes the file as well.
But only `close()` reports a failure to write.
A failure we never hear about is the one that costs us the afternoon.

That is the whole conversion.
The batch we read is the batch we write,
so the program holds one batch of rows and never the file.

## Accept a field that is not there

Real files have holes in them.
Add a row that carries no humidity:

```bash
echo '307,22.0,,clear' >> measurements.csv
```

Run the program again:

```bash
./build/cpp/weather
```

```
terminate called after throwing an instance of 'std::runtime_error'
  what():  column 'humidity' contains null values
```

Notice that the reader refuses the row rather than guessing at it.
To accept the hole, we must say what to put in it.
Give the reader a default in `weather.toml`:

```toml
[[csv_reader]]
name = "MeasurementCsvReader"
table = "Measurement"
default = { humidity = 0.0 }
```

Generate, build, and run again:

```bash
codegen-cpp generate weather.toml
cmake --build build/cpp
./build/cpp/weather
```

```
wrote measurements.parquet
```

The key of a default is the column it fills in.
The value of the default must fit the type of that column.

Notice that the field we emptied was a number.
The reader turns an empty field of a `str` column
into an empty string, not into a null.
So that field needs no default at all.
A column that has no default still refuses a null.
So we say which holes we expect one at a time,
rather than turn the checking off.

## Read a file that names its columns differently

The next file to arrive spells its headers for a person rather than for us.
Write `import.csv`:

```csv
Station ID,Temperature (C),Humidity,Note
811,7.5,0.93,fog
811,6.25,0.95,fog
```

We do not want to spell `Temperature (C)` in our C++.
Add a second reader over the same table.
The new reader says what the file calls each column:

```toml
[[csv_reader]]
name = "MeasurementImportCsvReader"
table = "Measurement"
name_in_file = { station_id = "Station ID", temperature = "Temperature (C)", humidity = "Humidity", note = "Note" }
default = { humidity = 0.0 }
```

Two readers over one table is the point of keeping them apart.
The table says what the data is,
and each reader says what one file calls it.

To read both files into one Parquet file,
add the second reader to `main.cpp` above `writer.close()`:

```cpp
    MeasurementImportCsvReader import_reader("import.csv", 2);
    while (import_reader.has_more_batches()) {
        batch.clear();
        import_reader.read_batch(batch);
        writer.write_batch(batch);
    }
```

Generate, build, and run:

```bash
codegen-cpp generate weather.toml
cmake --build build/cpp
./build/cpp/weather
```

```
wrote measurements.parquet
```

Both files are in there now, under the names our table uses.

## Read the Parquet file back

The readers and the writers of a table all have the same shape,
so the last step needs nothing new.
Add a Parquet reader and a CSV writer to `weather.toml`:

```toml
[[parquet_reader]]
name = "MeasurementParquetReader"
table = "Measurement"

[[csv_writer]]
name = "MeasurementCsvWriter"
table = "Measurement"
```

Then add a second pass over the file we just wrote,
below the line that prints `wrote measurements.parquet`:

```cpp
    MeasurementParquetReader parquet_reader("measurements.parquet", 1000);
    MeasurementCsvWriter csv_writer("round-trip.csv.gz");

    Measurement all;
    parquet_reader.read_all(all);
    csv_writer.write_batch(all);
    csv_writer.close();

    std::printf("round tripped %zu rows\n", all.size());
```

Generate, build, and run:

```bash
codegen-cpp generate weather.toml
cmake --build build/cpp
./build/cpp/weather
```

```
wrote measurements.parquet
round tripped 8 rows
```

Notice two things.
First, `read_all()` reads every row that is left, not one batch.
When the whole file fits in memory, we want this behavior.
Second, the CSV writer compressed its output without a request from us.
It did so because the name we gave it ends in `.gz`:

```bash
zcat round-trip.csv.gz
```

```
"station_id","temperature","humidity","note"
101,12.5,0.41,"clear"
101,13.125,0.44,"clear"
204,-3.25,0.8,"snow"
204,-4,0.82,"drifting"
307,21.75,0.15,"calm"
307,22,0,"clear"
811,7.5,0.93,"fog"
811,6.25,0.95,"fog"
```

The output has eight rows.
Six come from the first file,
including the one whose humidity took the default.
Two come from the second file.

## What we have built

We wrote one specification that holds a table and four classes over it.
We also wrote a program that moves rows
between a CSV file and a Parquet file in batches.
We gave a reader a default for the fields a file leaves empty.
We gave a second reader the names that another file uses for the same columns.

From here:

- [Store nested columns in a Parquet file](store-nested-columns-in-a-parquet-file.md)
  builds vectors, maps and structs out of the columns we used in this tutorial.
- [Fill an HDF5 file one window at a time](fill-an-hdf5-file-one-window-at-a-time.md)
  is the other half of the tool: n-dimensional arrays rather than rows.
- [The specification](../reference/specification.md) lists every section
  a specification holds.
- [The generated code](../reference/generated-code.md) lists every class
  the generator writes, and the arguments each one takes.
