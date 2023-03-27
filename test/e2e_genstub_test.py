import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from traceback import print_exc

import pytest

from synchronicity.genstub import StubEmitter


helpers_dir = Path(__file__).parent / "genstub_helpers"
assertion_file = helpers_dir / "e2e_example_type_assertions.py"

class FailedMyPyCheck(Exception):
    def __init__(self, output):
        self.output = output
def run_mypy(input_file):
    p = subprocess.Popen(["mypy", input_file], stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
    result_code = p.wait()
    if result_code != 0:
        raise FailedMyPyCheck(p.stdout.read())

@contextmanager
def temp_assertion_file(new_assertion):
    template = assertion_file.read_text()
    setup_code, default_assertions = template.split("# assert start")
    assertion_code = setup_code + new_assertion
    with tempfile.NamedTemporaryFile(dir=assertion_file.parent, suffix=".py") as new_file:
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
    import test.genstub_helpers.e2e_example_export as testmod

    emitter = StubEmitter.from_module(testmod)
    source = emitter.get_source()
    stub_path = Path(testmod.__file__).with_suffix(".pyi")
    stub_path.write_text(source)
    yield

def test_mypy_assertions(interface_file):
    run_mypy(assertion_file)

def test_failing_assertion(interface_file):
    # since there appears to be no good way of asserting failing type checks (and skipping to the next assertion)
    # we do some mangling of the assertion file to do one-by-one tests
    with temp_assertion_file("e2e_example_export.BlockingFoo(1)") as custom_file:  # we pass int instead of str
        with pytest.raises(FailedMyPyCheck):
            run_mypy(custom_file)
