# Store nested columns in a Parquet file

A column of a table does not have to hold one number or one string.
In this tutorial, we declare a vector, a map and a struct,
and nest one inside another.
We write a table of them into a Parquet file and read it back.
Then we read a file that came from somewhere else,
which names its columns differently and leaves holes in them.

This tutorial follows
[Convert a CSV file into a Parquet file](convert-a-csv-file-into-a-parquet-file.md),
and we set the project up the same way.

## Set the project up

```bash
mkdir library
cd library
```

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

Now install it:

```bash
conan install . --build=missing -of build -s compiler.cppstd=20
```

Write `CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.23)
project(library CXX)

find_package(Arrow REQUIRED)

add_executable(library main.cpp)
target_include_directories(library PRIVATE "${CMAKE_SOURCE_DIR}")
target_compile_features(library PRIVATE cxx_std_23)
target_link_libraries(
    library PRIVATE Arrow::arrow_static Parquet::parquet_static
)
```

## Declare a vector

We store papers.
A paper has an id and a title, which we already know how to declare,
and a list of keywords, which we do not.
Write `works.toml`:

```toml
[[vector]]
name = "Keywords"
element = "str"

[[table]]
name = "Work"
columns = [
    { name = "work_id", type = "i64" },
    { name = "title", type = "str" },
    { name = "keywords", type = "Keywords" },
]

[[parquet_writer]]
name = "WorkParquetWriter"
table = "Work"

[[parquet_reader]]
name = "WorkParquetReader"
table = "Work"
```

A `vector` section declares a type rather than a class.
It has a name and the type of one `element`,
and the name is what a column asks for.
Generate the header and look for that name:

```bash
codegen-cpp generate works.toml
```

```cpp
using Keywords = std::vector<std::string>;
```

Notice that the type we declared is a name for a `std::vector`.
The column that named it is a `std::vector<Keywords>`,
one list of keywords per row.

## Write a row and read it back

Write `main.cpp`:

```cpp
#include <cstdio>

#include "works.hpp"

int main() {
    Work works;
    works.push_back({
        .work_id = 1,
        .title = "Rainfall over the plateau",
        .keywords = {"rainfall", "monsoon"},
    });
    works.push_back({
        .work_id = 2,
        .title = "Ice cores of the last century",
        .keywords = {},
    });

    WorkParquetWriter writer("works.parquet");
    writer.write_batch(works);
    writer.close();

    WorkParquetReader reader("works.parquet", 1000);
    Work back;
    reader.read_all(back);

    for (std::size_t i = 0; i < back.size(); ++i) {
        const auto row = back[i];
        std::printf("%ld %s\n", row.work_id, row.title.c_str());
        for (const auto& keyword : row.keywords) {
            std::printf("    keyword %s\n", keyword.c_str());
        }
    }

    return 0;
}
```

`row_type` is a plain struct, so we can write a row out field by field.
Build and run:

```bash
cmake -S . -B build/cpp \
    -DCMAKE_TOOLCHAIN_FILE="$PWD/build/build/Release/generators/conan_toolchain.cmake" \
    -DCMAKE_BUILD_TYPE=Release
cmake --build build/cpp
./build/cpp/library
```

```
1 Rainfall over the plateau
    keyword rainfall
    keyword monsoon
2 Ice cores of the last century
```

The second row kept its empty list.
A vector holds as many elements as the row holds, including none.

## Declare a struct and a map

Two more shapes go on the same table.
A struct is a fixed set of named fields.
A map is a variable number of keys, each with one value.
Add both to `works.toml`, above the table:

```toml
[[struct]]
name = "Biblio"
fields = [
    { name = "volume", type = "str" },
    { name = "first_page", type = "i32" },
    { name = "last_page", type = "i32" },
]

[[map]]
name = "CitationsByYear"
key = "i64"
value = "u32"
```

and two columns to the table:

```toml
    { name = "biblio", type = "Biblio" },
    { name = "citations", type = "CitationsByYear" },
```

Generate the header again and read what the two became:

```cpp
struct Biblio {
    std::string volume;
    std::int32_t first_page;
    std::int32_t last_page;

    bool operator==(const Biblio&) const = default;
};

using CitationsByYear = std::map<std::int64_t, std::uint32_t>;
```

A struct is the one shape with members of its own,
so the generator writes it out as a struct.
A map is another name for a container.
Its keys are data rather than specification,
so nothing in our file says which years a row holds.

Fill both in for the two rows of `main.cpp`:

```cpp
    works.push_back({
        .work_id = 1,
        .title = "Rainfall over the plateau",
        .keywords = {"rainfall", "monsoon"},
        .biblio = {.volume = "12", .first_page = 31, .last_page = 44},
        .citations = {{2021, 4}, {2022, 11}},
    });
    works.push_back({
        .work_id = 2,
        .title = "Ice cores of the last century",
        .keywords = {},
        .biblio = {.volume = "3", .first_page = 5, .last_page = 19},
        .citations = {},
    });
```

and print them inside the `for` loop, below the keyword loop:

```cpp
        std::printf("    volume %s, pages %d to %d\n", row.biblio.volume.c_str(),
                    row.biblio.first_page, row.biblio.last_page);
        for (const auto& [year, count] : row.citations) {
            std::printf("    cited %u times in %ld\n", count, year);
        }
```

Generate, build, and run:

```bash
codegen-cpp generate works.toml
cmake --build build/cpp
./build/cpp/library
```

```
1 Rainfall over the plateau
    keyword rainfall
    keyword monsoon
    volume 12, pages 31 to 44
    cited 4 times in 2021
    cited 11 times in 2022
2 Ice cores of the last century
    volume 3, pages 5 to 19
```

We reach a field of a struct as `row.biblio.first_page`.
The pairs of the map come back in the order of their keys,
whatever order they went in.

## Nest one type inside another

A type can name another type of the same file.
That is how we write the deeper shapes.
A paper has a list of topics, and a topic has a name and a score,
so a struct goes inside a vector.
Add both to `works.toml`, above the table:

```toml
[[struct]]
name = "TopicScore"
fields = [
    { name = "name", type = "str" },
    { name = "score", type = "f64" },
]

[[vector]]
name = "Topics"
element = "TopicScore"
```

and the column:

```toml
    { name = "topics", type = "Topics" },
```

Fill the column in for the first row, below `.citations`:

```cpp
        .topics = {{.name = "hydrology", .score = 0.81},
                   {.name = "climate", .score = 0.44}},
```

and print it inside the `for` loop, below the citations loop:

```cpp
        for (const auto& topic : row.topics) {
            std::printf("    topic %s at %g\n", topic.name.c_str(), topic.score);
        }
```

Generate, build, and run:

```bash
codegen-cpp generate works.toml
cmake --build build/cpp
./build/cpp/library
```

```
1 Rainfall over the plateau
    keyword rainfall
    keyword monsoon
    volume 12, pages 31 to 44
    cited 4 times in 2021
    cited 11 times in 2022
    topic hydrology at 0.81
    topic climate at 0.44
2 Ice cores of the last century
    volume 3, pages 5 to 19
```

There is no limit on how deep this goes.
We write a vector of vectors, or a struct of vectors of structs,
the same way, one section per level.

## Read a file that came from somewhere else

So far we wrote the file we read,
so every name lined up and no field was missing.
Now take a file that somebody else wrote.
Write `make_incoming.py`:

```python
import pyarrow as pa
import pyarrow.parquet as pq

topic = pa.struct([("display_name", pa.string()), ("score", pa.float64())])
biblio = pa.struct(
    [("volume", pa.string()), ("first_page", pa.int32()), ("last_page", pa.int32())]
)

table = pa.table(
    {
        "id": pa.array([7, 8], pa.int64()),
        "title": pa.array(["Ice shelf retreat", None], pa.string()),
        "keywords": pa.array([["ice", None], []], pa.list_(pa.string())),
        "biblio": pa.array(
            [{"volume": None, "first_page": 3, "last_page": 9}, None], biblio
        ),
        "counts": pa.array([[(2020, 2)], []], pa.map_(pa.int64(), pa.uint32())),
        "topics": pa.array(
            [[{"display_name": "glaciology", "score": None}], []], pa.list_(topic)
        ),
    }
)
pq.write_table(table, "incoming.parquet")
```

and run it with the Python where we installed `codegen-cpp`,
which already has pyarrow:

```bash
python make_incoming.py
```

This file disagrees with our specification twice.
It calls two columns and one field of a struct something else.
It also holds a null in five places where we expect a value.
A reader answers for both, one part of the table at a time.

Add a second reader to `works.toml`:

```toml
[[parquet_reader]]
name = "IncomingParquetReader"
table = "Work"

[parquet_reader.name_in_file]
work_id = "id"
citations = "counts"
"topics.element.name" = "display_name"

[parquet_reader.default]
title = "untitled"
"keywords.element" = ""
"biblio.volume" = ""
"biblio.first_page" = -1
"biblio.last_page" = -1
"topics.element.score" = 0.0
```

Every key here names one part of the table.
A key is the name of a column,
followed by one step for each level below it.
The step for each level is one of these:

- the name of a field, for a struct
- `element`, for the element of a vector
- `value`, for the value of a map

So `topics.element.name` is the name of one topic
of the vector of topics, three levels down.

Read that file at the end of `main`, before the `return`:

```cpp
    IncomingParquetReader incoming("incoming.parquet", 1000);
    Work more;
    incoming.read_all(more);

    for (std::size_t i = 0; i < more.size(); ++i) {
        const auto row = more[i];
        std::printf("%ld %s (%zu keywords, %zu topics)\n", row.work_id,
                    row.title.c_str(), row.keywords.size(), row.topics.size());
        std::printf("    volume '%s', pages %d to %d\n", row.biblio.volume.c_str(),
                    row.biblio.first_page, row.biblio.last_page);
    }
```

Generate, build, and run:

```bash
codegen-cpp generate works.toml
cmake --build build/cpp
./build/cpp/library
```

The last four lines of the output are the new file:

```
7 Ice shelf retreat (2 keywords, 1 topics)
    volume '', pages 3 to 9
8 untitled (0 keywords, 0 topics)
    volume '', pages -1 to -1
```

Notice what happened to the second row.
Its title was null, so it took the default we gave the column.
Its whole `biblio` was null.
The reader turns a null struct into a struct
whose fields each take their own default.
So its pages are the -1 we asked for,
not a number that looks like a page.
Its `counts` and `topics` were empty rather than null,
and an empty vector or map needs no default at all.

Remember that `name_in_file` and `default` belong to the reader
and not to the type.
`Topics` is one type.
Two readers of it can disagree
about what a file calls it and what a null in it means.

## Leave a column out

CSV has no way to hold a vector, a map or a struct.
A `csv_writer` over this table is an error rather than a guess at an encoding.
The one exception is a writer that writes only the columns a CSV can hold.
Add one that does:

```toml
[[csv_writer]]
name = "WorkTitleCsvWriter"
table = "Work"
include = ["work_id", "title"]
```

`include` names the columns that the writer writes.
The writer does not write a column that `include` leaves out.
Write the summary out at the end of `main`:

```cpp
    WorkTitleCsvWriter titles("titles.csv");
    titles.write_batch(works);
    titles.write_batch(more);
    titles.close();
```

Generate, build, and run:

```bash
codegen-cpp generate works.toml
cmake --build build/cpp
./build/cpp/library
cat titles.csv
```

```
"work_id","title"
1,"Rainfall over the plateau"
2,"Ice cores of the last century"
7,"Ice shelf retreat"
8,"untitled"
```

The two nested tables went out as a flat file
because the writer never asked for the columns that could not go.

## What we have built

We declared the three aggregate types,
nested a struct inside a vector,
and moved a table of them in and out of a Parquet file.
We read a file that named three of its parts differently
and left nulls at four levels.
We answered for each of those with one key on one reader.

From here:

- [Fill an HDF5 file one window at a time](fill-an-hdf5-file-one-window-at-a-time.md)
  is the other half of the tool: n-dimensional arrays rather than rows.
- [The specification](../reference/specification.md)
  gives the rules that the aggregate types, the flattened keys,
  `include` and `exclude` follow.
- [The generated code](../reference/generated-code.md)
  gives the Parquet shape
  that each of the three types is read from and written to.
