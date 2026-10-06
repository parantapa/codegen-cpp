# Developer notes

Install the package and its development dependencies in a virtual environment.
Then run the tests:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/codegen-cpp --help
.venv/bin/pytest
```

To run one test, give its file and its name:

```bash
.venv/bin/pytest tests/test_spec.py::<test name>
```

`black` formats the project,
and `pycodestyle` and `pyright` check it.
`pyproject.toml` holds the configuration of `black` and `pyright`.
`setup.cfg` holds the configuration of `pycodestyle`,
because `pycodestyle` does not read `pyproject.toml`.
It sets the line length that `black` uses,
and turns off the checks that disagree with how `black` formats
a slice and a broken line.
Before a change goes in, run the three tools in this order:

```bash
.venv/bin/black src tests
.venv/bin/pycodestyle src tests
.venv/bin/pyright
```

## The source

- `src/codegen_cpp/cli.py` holds the click commands,
  and the `write_config` helper that the `make-config` commands share.
  Each command parses, delegates, and prints where a file was written,
  except `debug parse-spec`, which prints the parsed specification.
  Its `cli` group is the `codegen-cpp` command,
  which `pyproject.toml` declares under `[project.scripts]`.
- `src/codegen_cpp/spec.py` holds the pydantic models of a specification,
  together with every check made on one.
  A specification that parses is a specification the generator can trust.
- `src/codegen_cpp/codegen.py` holds the spelling of every scalar type
  in C++, in Arrow and in HDF5,
  together with the headers that each generated construct needs.
  It also builds the node tree that a reader and a writer are rendered from,
  and assembles the single header.
- `src/codegen_cpp/templates/` holds one Jinja template
  per generated construct.
- `src/codegen_cpp/make_config.py` reads a CSV or a Parquet file
  and writes the first draft of a specification for it.
- `tests/` holds the pytest suite over the Python package,
  and `tests/cpp/` holds the CMake project
  that compiles and runs the generated code.
- `docs/` holds the user documentation,
  as tutorials, how-to guides and reference pages,
  and these developer notes.
- `examples/` holds the specifications
  that the documentation points a reader at.
  Each one exercises a part of the tool end to end.

## Tools and libraries

The package is built with setuptools.
It uses click for the command line, and rich for what it prints.
It uses pydantic for the specification models and their checks,
jinja2 for the templates, and pyarrow for reading a data file.
A specification is read with `tomllib` from the standard library.

The generated code depends on Apache Arrow,
on the HDF5 C++ API, and on `mdspan`.
This package does not build or ship any of them.
The C++ tests install them with Conan.

## Design decisions

A specification is validated once, in `spec.py`.
Every rule about names, types, defaults and selections is a pydantic validator.
`Spec.check_references` holds the rules
that need more than one section to decide.
The generator therefore indexes tables and datasets by name,
without checking that they are there.
A missing name is a bug in the validation,
rather than something the generator has to answer for.

The templates of the readers and the writers of a table walk a node tree,
rather than the specification.
`codegen.py` builds one `TypeNode` per part of a table
before it renders anything.
A template then asks a node what it holds,
rather than reading the specification a second time.
The tree is what makes nesting cheap.
A Parquet reader reaches an arbitrary depth,
and the recursion that reaches it stays in Python.
A template only has to loop over what it is handed.

The flattened key is the name that every part of the code shares.
A column, a field of a struct, the element of a vector
and the value of a map are each reached by one dotted key.
The specification keys `default` and `name_in_file` by it,
`spec.py` validates against it,
`codegen.py` turns it into a C++ identifier,
and `make_config.py` writes it out.
A change to the spelling of a key reaches all four.

Everything is generated into one header, and nothing into a source file.
The generated classes are header-only,
so a project adds the header to its include path and nothing to its build.
The cost lands in `spec_parts`.
It merges the includes of every construct,
and orders the definitions so that each one follows what it names.

## Testing the generated C++ code

The tests under `tests/cpp` generate a header per specification.
They write each format in two ways:

- CSV files as plain text, and with the generated writers.
- Parquet files with Arrow, and with the generated writers.
- HDF5 files with the HDF5 C++ API, and with the generated writers.

Then they read all of them back with the generated readers.
Conan installs Arrow, HDF5, `hdf5_plugins` and `mdspan`.
`conanfile.txt` says which features they are built with.
Note that Arrow needs C++20 or later,
which the default Conan profile does not ask for.

```bash
conan install . --build=missing -of build -s compiler.cppstd=20
cmake -S tests/cpp -B build/cpp \
    -DCMAKE_TOOLCHAIN_FILE="$PWD/build/build/Release/generators/conan_toolchain.cmake" \
    -DCMAKE_BUILD_TYPE=Release
cmake --build build/cpp
ctest --test-dir build/cpp --output-on-failure
```

`hdf5_plugins` comes
from the [`pb-conan-index`](https://github.com/parantapa/pb-conan-index) remote,
and holds the compression filters that HDF5 loads at run time.
The CMake project points the HDF5 tests
at the directory it packages them in,
so `ctest` finds them without any environment of its own.
A program of your own finds them
through the `HDF5_PLUGIN_PATH` environment variable.
The Conan run environment sets that variable for you.

The `hdf5_without_plugins` test runs the same binary with that path cleared,
and checks what a writer and a reader report when a filter is missing.
Only the filters that the tests use are built.
`conanfile.txt` says which, and turns the rest off.

A filter is loaded into the running program,
so it has to reach the HDF5 it was built against.
Against a shared HDF5 it links to the library like anything else.
Against a static one it is built with its HDF5 symbols left undefined,
and looks them up in the program that loaded it.
The tests therefore link `hdf5_plugins::hdf5_plugins`,
because the package puts `-rdynamic` on the executables that use it.
The generated code is the same either way.
Both are tested:

```bash
conan install . --build=missing -of build-shared -s compiler.cppstd=20 \
    -o "hdf5/*:shared=True"
cmake -S tests/cpp -B build-shared/cpp \
    -DCMAKE_TOOLCHAIN_FILE="$PWD/build-shared/build/Release/generators/conan_toolchain.cmake" \
    -DCMAKE_BUILD_TYPE=Release
cmake --build build-shared/cpp
ctest --test-dir build-shared/cpp --output-on-failure
```
