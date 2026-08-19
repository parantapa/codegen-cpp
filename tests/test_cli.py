"""Tests for the codegen-cpp command line interface."""

from click.testing import CliRunner

from codegen_cpp import __version__
from codegen_cpp.cli import cli


def test_version() -> None:
    """The --version flag reports the package version."""
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
