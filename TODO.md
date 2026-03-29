## TODO

### High Priority

- [ ] **Add support for async context managers**
  - Implement `__aenter__` and `__aexit__` wrapper generation
  - Support both `with` (sync) and `async with` (async) usage
  - Test with real-world use cases (database connections, file handles)

- [ ] **Add tests that generated code is valid across Python 3.10+ versions**
  - The code generation process could require a newer Python version
  - Output types needs to still be backwards compatible with Python 3.10+ for now
  - Test generated code across Python versions

- [ ] Add support for classmethod and staticmethod
- [ ] Add support for explicit @property

### Medium Priority
- [ ] Transfer docstrings to generated wrappers
- [ ] Backport some of the traceback stripping (if needed?)
- [ ] **Improve error messages in code generation**
  - Better diagnostics when type annotations are missing
  - Clear error messages for unsupported type constructs
  - Helpful suggestions for common mistakes
- [ ] **Investigate translation of TypeVar bounds that reference wrapped classes**
  - Example: `T = typing.TypeVar("T", bound="SomeClass")` where `SomeClass` is a wrapped class
  - Current behavior partially supports this at TypeVar definition/codegen time: generated code recreates `TypeVar(..., bound="WrapperType")`
  - The missing piece is bound-aware translation in the annotation transformer: when a signature contains `T`, the compiler currently treats `T` as opaque rather than "translate according to the bound"
  - This means generic declaration and some ordinary generic container code paths work, but translation-sensitive paths still fail
  - Confirmed failing typed paths include `tuple[T, ...] -> list[T]` where `T` is bound to a wrapped class
  - Confirmed failing typed paths also include callback/callable forms like `Callable[P, T] -> Callable[P, list[T]]` when `T` is bound to a wrapped class
  - Evaluate whether TypeVar bounds should be lowered to wrapper-aware transformers, not just wrapper-aware emitted definitions
  - Evaluate edge cases and type checking compatibility
- [ ] **Add callback/callable translation for wrapped classes**
  - Plain callback forms like `Callable[[Node], Node]` and `Callable[[Node], int]` are not translated to public wrapper types today
  - This is a separate limitation from TypeVar-bound translation, though the two interact in callback-heavy generic APIs
  - Runtime and pyright coverage currently live in xfailed integration tests; use those as the target behavior
- [ ] Add inclusion/exclusion overrides for both properties and methods (default excludes _-prefixed)
- [ ] Add option for renaming the output entity itself, not just the module (function name or class name)
- [ ] Add Module.auto(__name__) for auto-inferring output modules as sibling of current (_-prefix or _impl suffix)

- [ ] **Clean up generated code**
  - Share common code between similar wrappers
  - Consider template-based generation

- [ ] **Add Python 3.14+ improvements**
  - Test with free-threaded Python

- [ ] **IDE support**
  - Verify PyCharm/VSCode jump-to-definition
  - Check compatibility with MyPy and ty

### Low Priority

- [ ] **Better CLI ergonomics**
  - Add `--watch` mode for development
  - Support glob patterns for module discovery

- [ ] **Performance profiling**
  - Benchmark thread overhead
  - Optimize hot paths in Synchronizer
  - Consider alternative execution strategies for high-performance use cases

## IDEAS

### Separate "pure" async wrapper
It might be nice to be able to generate a "pure" async interface too that doesn't have the sync methods, since this makes it harder to make the mistake of calling blocking code from within async code when objects have both types.
Then you could have a separate interface `my_library.aio` that mirrors your sync `my_library` library export, but with purely async types. This wrapper could either offload to the same Synchronizer, or entirely (optionally?) circumvent the Synchronizer altogether - reducing the thread overhead.


### "Vendor" library in generated code
If we make the code generator include the library code itself (the synchronizer etc.), the generated library wouldn't even depend on the synchronicity package anymore and be entirely self-contained.

This isn't trivial with the current structure where we use things like synchronicity.Module in library code
to mark what entities to generate code for (this import would fail), and would require some restructuring - for example pre-generation of the code that contains Module, or a separate set of manifest files that determine what
to emit in codegen.