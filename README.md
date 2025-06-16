![CI/CD badge](https://github.com/erikbern/synchronicity/actions/workflows/ci.yml/badge.svg)
[![pypi badge](https://img.shields.io/pypi/v/synchronicity.svg?style=flat)](https://pypi.python.org/pypi/synchronicity)

Python 3 has some amazing support for async programming but it's arguably made it a bit harder to develop libraries. Are you tired of implementing synchronous _and_ asynchronous methods doing basically the same thing? This might be a simple solution for you.

Installing
==========

```
pip install synchronicity
```


Background: why is anything like this needed
============================================

Let's say you have an asynchronous function

```python fixture:quicksleep
async def f(x):
    await asyncio.sleep(1.0)
    return x**2
```

And let's say (for whatever reason) you want to offer a synchronous API to users. For instance maybe you want to make it easy to run your code in a basic script, or a user is building something that's mostly CPU-bound, so they don't want to bother with asyncio.

A "simple" way to create a synchronous equivalent would be to implement a set of synchronous functions where all they do is call [asyncio.run](https://docs.python.org/3/library/asyncio-task.html#asyncio.run) on an asynchronous function. But this isn't a great solution for more complex code:

* It's kind of tedious grunt work to have to do this for every method/function
* [asyncio.run](https://docs.python.org/3/library/asyncio-task.html#asyncio.run) doesn't work with generators
* In many cases, you need to preserve an event loop running between calls

The last case is particularly challenging. For instance, let's say you are implementing a client to a database that needs to have a persistent connection, and you want to build it in asyncio:

```python
class DBConnection:
    def __init__(self, url):
        self._url = url

    async def connect(self):
        self._connection = await connect_to_database(self._url)

    async def query(self, q):
        return await self._connection.run_query(q)
```

How do you expose a synchronous interface to this code? The problem is that wrapping `connect` and `query` in [asyncio.run](https://docs.python.org/3/library/asyncio-task.html#asyncio.run) won't work since you need to _preserve the event loop across calls_. It's clear we need something slightly more advanced.

How to use this library
=======================

This library offers a simple `Synchronizer` class that creates an event loop on a separate thread, and wraps functions/generators/classes so that execution happens on that thread.

Wrapped functions expose two interfaces:
* For synchronous (non-async) use, the wrapper function itself will simply block until the result of the wrapped function is available (note that you can make it return a future as well, [see below](#returning-futures))
* For async use, you use a special `.aio` member *on the wrapper function itself* which works just like the usual business of calling asynchronous code (`await`, `async for` etc.) - except that async code is executed on the `Synchronizer`'s own event loop ([more on why this matters below](#using-synchronicity-with-other-asynchronous-code)).

```python fixture:quicksleep
import asyncio
from synchronicity import Synchronizer

synchronizer = Synchronizer()

@synchronizer.wrap
async def f(x):
    await asyncio.sleep(1.0)
    return x**2


# Running f in a synchronous context blocks until the result is available
ret = f(42)  # Blocks
assert isinstance(ret, int)
print('f(42) =', ret)
```

Async usage of the `f` wrapper, using the `f.aio` special coroutine function. This will execute `f` on `synchronizer`'s event loop - not the main event loop used by `asyncio.run()` here:
```python continuation fixture:quicksleep
async def g():
    # Running f in an asynchronous context works the normal way
    ret = await f.aio(42)  # f.aio is roughly equivalent to the original `f`
    print('f(42) =', ret)

asyncio.run(g())
```

More advanced examples
======================

Generators
----------

The decorator also works on async generators, wrapping them as a regular (non-async) generator:

```python fixture:quicksleep
@synchronizer.wrap
async def f(n):
    for i in range(n):
        await asyncio.sleep(1.0)
    yield i

# Note that the following runs in a synchronous context
# Each number will take 1s to print
for ret in f(3):
    print(ret)
```

The wrapped generators can also be called safely in an async context using the `.aio` property:

```py continuation fixture:quicksleep
async def async_iteration():
    async for ret in f.aio(3):
        pass
    
asyncio.run(async_iteration())
```

Synchronizing whole classes
---------------------------

The `Synchronizer` wrapper operates on classes by creating a new class that wraps every method on the class:


```python
@synchronizer.wrap
class DBConnection:
    def __init__(self, url):
        self._url = url

    async def connect(self):
        self._connection = await connect_to_database(self._url)

    async def query(self, q):
        return await self._connection.run_query(q)


# Now we can call it synchronously, if we want to
db_conn = DBConnection('tcp://localhost:1234')
db_conn.connect()
data = db_conn.query('select * from foo')
```
*Or*, we could opt to use the wrapped class in an async context if we want to:
```python continuation
async def async_main():
    db_conn = DBConnection('tcp://localhost:1234')
    await db_conn.connect.aio()
    await db_conn.query.aio('select * from foo')  # .aio works on methods too

asyncio.run(async_main())
```

Context managers
----------------

You can synchronize context manager classes just like any other class and the special methods will be handled properly.

```python fixture:quicksleep
@synchronizer.wrap
class CtxMgr:
    def __init__(self, exit_delay: float):
        self.exit_delay = exit_delay

    async def __aenter__(self):
        pass
    
    async def __aexit__(self, exc, exc_type, tb):
        await asyncio.sleep(self.exit_delay)

with CtxMgr(exit_delay=1):
    print("sleeping 1 second")
print("done")
```


Returning futures
-----------------

You can also make functions return a `concurrent.futures.Future` object by adding `_future=True` to any call. This can be useful if you want to dispatch many calls from a blocking context, but you want to resolve them roughly in parallel:

```python fixture:quicksleep
@synchronizer.wrap
async def f(x):
    await asyncio.sleep(1.0)
    return x**2

futures = [f(i, _future=True) for i in range(10)]  # This returns immediately, but starts running all calls in the background
rets = [fut.result() for fut in futures]  # This should take ~1s to run, resolving all futures in parallel
print('first ten squares:', rets)
```


Using synchronicity with other asynchronous code
------------------------------------------------

Why does synchronicity expose a separate async interface (`.aio`) when you could just use the original unwrapped function that is already async? It solves two issues:
* Intercompatibility with the non-async interface - you can pass wrapped class instances to the wrapper and those will be "unwrapped" so that the implementation code only needs to deal with unwrapped objects.
* Separate event loops of the library and the user of the library adds safeguards from event loop blockers for both

A common pitfall in asynchronous programming is to accidentally lock up an event loop by making non-async long-running calls within the event loop. If your async library shares an event loop with a user's own async code, a synchronous call (typically a bug) in either the library or the user code would prevent the other from running concurrent tasks. Using synchronicity wrappers on your library functions, you avoid this pitfall by isolating the library execution to its own event loop and thread automatically.


```python
import time

@synchronizer.wrap
async def buggy_library():
    time.sleep(0.1)  #non-async sleep, this locks the library's event loop for the duration
    
async def async_user_code():
    await buggy_library.aio()  # this will not lock the "user's" event loop
```

This library can also be useful in purely asynchronous settings, if you have multiple event loops, if you have some section that is CPU-bound, or some critical code that you want to run on a separate thread for safety. All calls to synchronized functions/generators are thread-safe by design. This makes it a useful alternative to [loop.run_in_executor](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.run_in_executor) for simple things. Note however that each synchronizer only runs one thread.


Static type support for wrappers
----------------------------------

One issue with the wrapper functions and classes is that they will have different argument and return value types than the wrapped originals (e.g. an AsyncGenerator becomes a Generator after being wrapped). This type transformation can't easily be expressed statically in Python's typing system.

For this reason, synchronicity includes a basic type stub (.pyi) generation tool (`python -m synchronicity.type_stubs`) that takes Python modules names as inputs and emits a `.pyi` file for each module with static types translating any synchronicity-wrapped classes or functions.

Since the `.pyi` file will sometimes "shadow" the original file, which you still might want to type check for issues in the implementation code, a good practice is to separate wrappers and wrapped implementation code into separate modules and only emit type stubs for the "wrapper modules".  

A recommended structure would be something like this:

#### _my_library.py (private library implementation)
```py
import typing

async def foo() -> typing.AsyncGenerator[int, None]:
    yield 1
```

#### my_library.py (public library interface)
```py notest
import _my_library
from synchronicity import Synchronizer

synchronizer = Synchronizer()

foo = synchronizer.wrap(_my_library.foo, name="MyClass", target_module=__name__)
```

You can then emit type stubs for the public module, as part of your build process:
```shell
python -m synchronicity.type_stubs my_module
```
The automatically generated type stub `my_library.pyi` would then look something like:
```py
import typing
import typing_extensions

class __foo_spec(typing_extensions.Protocol):
    def __call__(self) -> typing.Generator[int, None, None]:
        ...

    def aio(self) -> typing.AsyncGenerator[int, None]:
        ...

foo: __foo_spec
```

The special `*_spec` protocol types here make sure that both calling the wrapped `for x in foo()` method and `async for x in foo.aio()` will be statically valid operations, and their respective return values are typed correctly.


Gotchas
=======

* If you have a non-async function that *returns* an awaitable or other async entity, but isn't itself defined with the `async` keyword, you have to *type annotate* that function with the correct async return type - otherwise it will not get wrapped correctly by `synchronizer.wrap`:

    ```py
    @synchronizer.wrap
    def foo() -> typing.AsyncContextManager[str]:
        return make_context_manager() 
    ```
* If a class is "synchronized", any instance of that class will be a proxy for an instance of the original class. Methods on the class will delegate to methods of the underlying class, but *attributes* of the original class aren't directly reachable and would need getter methods or @properties to be reachable on the wrapper.
* Note that all synchronized code will run on a different thread, and a different event loop, so calling the code might have some minor extra overhead.
* Since all arguments and return values of wrapped functions are recursively run-time inspected to "translate" them, large data structures that are passed in and out can incur extra overhead. This can be disabled using a `@synchronizer.no_io_translation` decorator on the original function.


Future ideas
=====
* Use type annotations instead of runtime type inspection to determine the wrapping logic. This would prevent overly zealous argument/return value inspection when it isn't needed.
* Use (optional?) code generation (using type annotations) instead of runtime wrappers + type stub generation. This could make it easier to navigate exception tracebacks, and lead to simpler/better static types for wrappers. 
* Support the opposite case, i.e. you have a blocking function/generator/class/object, and you want to call it asynchronously (this is relatively simple to do for plain functions using [loop.run_in_executor](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.run_in_executor), but Python has no built-in support for generators, and it would be nice to transform a whole class.
* More/better documentation
* A cleaner way to return futures from sync code (instead of the `_future=True` argument)


Release process
===============
TODO: We should automate this in CI/CD

* Make a new branch `release-X.Y.Z` from main
* Bump version in pyproject.toml to `X.Y.Z`
* Commit that change and create a PR
* Merge the PR once green
* Checkout main
* `git tag -a vX.Y.Z -m "* release bullets"`
* git push --tags
* `UV_PUBLISH_TOKEN="$PYPI_TOKEN_SYNCHRONICITY" make publish`
