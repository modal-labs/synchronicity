import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from traceback import print_exc

import pytest

from synchronicity.type_stubs import write_stub

helpers_dir = Path(__file__).parent / "type_stub_helpers"
assertion_file = helpers_dir / "e2e_example_type_assertions.py"


class FailedMyPyCheck(Exception):
    def __init__(self, output):
        self.output = output


def run_mypy(input_file):
    p = subprocess.Popen(
        ["mypy", input_file], stderr=subprocess.STDOUT, stdout=subprocess.PIPE
    )
    result_code = p.wait()
    if result_code != 0:
        raise FailedMyPyCheck(p.stdout.read())


@contextmanager
def temp_assertion_file(new_assertion):
    template = assertion_file.read_text()
    setup_code, default_assertions = template.split("# assert start")
    assertion_code = setup_code + new_assertion
    with tempfile.NamedTemporaryFile(
        dir=assertion_file.parent, suffix=".py"
    ) as new_file:
        new_file.write(assertion_code.encode("utf8"))
        new_file.flush()
        try:
            yield new_file.name
        except:
            print(f"Exception when running type assertions on:\n{assertion_code}")
            print_exc()
            raise


@pytest.fixture(scope="session")
def interface_file():
    write_stub("test.type_stub_helpers.e2e_example_export")
    yield


def test_mypy_assertions(interface_file):
    run_mypy(assertion_file)


@pytest.mark.parametrize(
    "failing_assertion,error_matches",
    [
        (
            "e2e_example_export.BlockingFoo(1)",
            'incompatible type "int"; expected "str"',
        ),
        (
            "blocking_foo.some_static()",
            'Missing positional argument "arg" in call to "some_static"',
        ),  # missing argument
        (
            "blocking_foo.some_static(True)",
            'Argument 1 to "some_static" of "BlockingFoo" has incompatible type "bool"',
        ),  # bool instead of str
        (
            "e2e_example_export.listify(123)",
            'Value of type variable "_T_Blocking" of "listify" cannot be "int"',
        ),  #  int does not satisfy the type bound of the typevar (!)
    ],
)
def test_failing_assertion(interface_file, failing_assertion, error_matches):
    # since there appears to be no good way of asserting failing type checks (and skipping to the next assertion)
    # we use the assertion file as a template to insert statements that should fail type checking
    with temp_assertion_file(
        failing_assertion
    ) as custom_file:  # we pass int instead of str
        with pytest.raises(FailedMyPyCheck, match=error_matches):
            run_mypy(custom_file)
