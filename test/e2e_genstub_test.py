import subprocess
from pathlib import Path


def test_mypy_assertions():
    helpers_dir = Path(__file__).parent / "genstub_helpers"
    assertion_file = helpers_dir / "e2e_example_type_assertions.py"

    from synchronicity.genstub import StubEmitter

    # TODO: nicer interface to generate stub for module
    import test.genstub_helpers.e2e_example_export as testmod
    exported_module = StubEmitter(testmod.__name__)
    exported_module.add_class(testmod.BlockingFoo)
    source = exported_module.get_source()
    stub_path = Path(testmod.__file__).with_suffix(".pyi")
    stub_path.write_text(source)
    subprocess.check_call(["mypy", assertion_file])
