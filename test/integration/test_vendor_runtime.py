"""Tests for vendoring the runtime and ``--runtime-package`` / ``compile_modules``.

These are infrastructure tests and intentionally do not follow the four-tier
runtime / pyright (impl, wrapper, usage) layout used by scenario integration tests.
"""

import importlib
from pathlib import Path

from synchronicity.codegen.compile import compile_modules
from synchronicity.codegen.runtime_vendor import vendor_runtime
from synchronicity.module import Module


def test_vendor_runtime_writes_expected_files(tmp_path: Path) -> None:
    dest = vendor_runtime(target_package="vendored_test.sync_rt", output_base=tmp_path)
    assert dest == tmp_path / "vendored_test" / "sync_rt"
    assert (tmp_path / "vendored_test" / "__init__.py").is_file()
    for name in ("module.py", "types.py", "descriptor.py", "synchronizer.py", "__init__.py"):
        assert (dest / name).is_file()
    text = (dest / "__init__.py").read_text(encoding="utf-8")
    assert "FunctionWithAio" in text
    assert "Module" in text


def test_compile_modules_respects_runtime_package(generated_wrappers) -> None:
    impl = importlib.import_module("simple_function_impl")
    module_objs = [getattr(impl, n) for n in dir(impl)]
    module_objs = [m for m in module_objs if isinstance(m, Module)]
    assert module_objs

    custom = "my_library._vendored_synchronicity"
    out = compile_modules(module_objs, runtime_package=custom)
    code = "\n".join(out.values())

    assert f"import {custom}.types" in code
    assert f"from {custom}.descriptor import" in code
    assert f"from {custom}.synchronizer import get_synchronizer" in code
    assert "import synchronicity.types" not in code


def test_cli_vendor_invocation(tmp_path: Path) -> None:
    import subprocess
    import sys

    ok = subprocess.run(
        [
            sys.executable,
            "-m",
            "synchronicity.codegen",
            "vendor",
            "cli_vendor_test.sync_rt",
            "-o",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stderr
    assert (tmp_path / "cli_vendor_test" / "sync_rt" / "types.py").is_file()

    bad = subprocess.run(
        [
            sys.executable,
            "-m",
            "synchronicity.codegen",
            "vendor",
            "not-a-package!",
            "-o",
            str(tmp_path / "o2"),
        ],
        capture_output=True,
        text=True,
    )
    assert bad.returncode != 0
