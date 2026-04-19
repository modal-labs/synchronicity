"""Tests for vendoring the runtime and ``--runtime-package`` / ``compile_modules``.

These are infrastructure tests and intentionally do not follow the four-tier
runtime / pyright (impl, wrapper, usage) layout used by scenario integration tests.
"""

import importlib
import os
import subprocess
import sys
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
    assert "FunctionWithAio" not in text
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


def test_cli_wrappers_reports_unsupported_default_expr(tmp_path: Path) -> None:
    module_file = tmp_path / "bad_defaults_impl.py"
    module_file.write_text(
        """
import time

from synchronicity import Module

wrapper_module = Module("bad_defaults")

@wrapper_module.wrap_function()
async def bad_default(value: float = time.time()) -> float:
    return value
""".strip()
        + "\n"
    )

    project_root = Path(__file__).parent.parent.parent
    env = os.environ.copy()
    pythonpath_parts = [str(tmp_path), str(project_root)]
    if "PYTHONPATH" in env:
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "synchronicity.codegen",
            "wrappers",
            "-m",
            "bad_defaults_impl",
            "--stdout",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project_root),
    )

    assert result.returncode != 0
    assert "Error:" in result.stderr
    assert "parameter 'value'" in result.stderr
    assert "unsupported default expression" in result.stderr
