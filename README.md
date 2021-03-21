Python 3 has some amazing support for async programming but it's arguably made it a bit harder to develop libraries. Are you tired of implementing synchronous _and_ asynchronous methods doing basically the same thing? This might be a simple solution for you.

Background: why is anything like this needed
--------------------------------------------

Let's say you have an asynchronous function

```python
async def f(x):
   await asyncio.sleep(1.0)
   return x**2
```

A "simple" way to create a synchronous equivalent would be to wrap it in `asyncio.run(...)`. But this isn't a great solution for more complex code that requires keeping the same event loop. For instance, let's say you are implementing a client to a database that needs to have a persistent connection, and you want to built it in asyncio:

```python
class DBConnection:
    def __init__(self, url):
        self._url = url

    async def connect(self):
        # ...

    async def query(self, q):
        return await self._connection.run_query(q)
```

How to use
----------

This library offers a simpler `Synchronizer` class that creates an event loop on a separate thread, and wraps functions/generators/classes so that synchronous execution happens on that thread.

```python
from synchronicity import Synchronizer

synchronizer = Synchronizer()

@synchronizer
async def f(x):
   await asyncio.sleep(1.0)
   return x**2


# Running f in a synchronous context returns a Future object, with a blocking method .result()
fut = f(42)  # Returns immediately
print('f(42) =', fut.result())  # Blocks until result is available


async def g():
    print('f(42) =', (await f(42)))  # Running f in an asynchronous context runs it on the same event loop as expected
```

More advanced examples
----------------------

The decorator also works on generators:

```python
@synchronizer
async def f(n):
    for i in range(n):
        await asyncio.sleep(1.0)
	yield i


# Note that the following runs in a synchronous context
# Each number will take 1s to print
for ret in f(10):
    print(ret)
```

It also operates on classes by wrapping every method on the class:


```python
@synchronizer
class DBConnection:
    def __init__(self, url):
        self._url = url

    async def connect(self):
        # ...

    async def query(self, q):
        return await self._connection.run_query(q)


# Now we can call it synchronously, if we want to
db_conn = DBConnection('tcp://localhost:1234')
db_conn.connect().result()  # remember to wait for the future to finish
fut = db_conn.query('select * from foo')
data = fut.result()
```
