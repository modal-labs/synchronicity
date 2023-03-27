import subprocess
from pathlib import Path
from synchronicity.genstub import StubEmitter


def test_mypy_assertions():
    helpers_dir = Path(__file__).parent / "genstub_helpers"
    assertion_file = helpers_dir / "e2e_example_type_assertions.py"

    import test.genstub_helpers.e2e_example_export as testmod

    emitter = StubEmitter.from_module(testmod)
    source = emitter.get_source()
    stub_path = Path(testmod.__file__).with_suffix(".pyi")
    stub_path.write_text(source)
    subprocess.check_call(["mypy", assertion_file])
