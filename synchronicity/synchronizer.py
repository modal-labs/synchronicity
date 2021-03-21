import asyncio
import concurrent.futures
import functools
import inspect
import queue
import threading
import time
import traceback


class Synchronizer:
    '''Helps you offer a blocking (synchronous) interface to asynchronous code.
    '''

    def __init__(self, return_futures=False):
        self._return_futures = return_futures
        self._loop = None

    def _get_loop(self):
        if self._loop is not None:
            return self._loop

        is_ready = threading.Event()

        def run_forever():
            self._loop = asyncio.new_event_loop()
            is_ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=lambda: run_forever(), daemon=True)
        self._thread.start()  # TODO: we should join the thread at some point
        is_ready.wait()  # TODO: this might block for a very short time
        return self._loop

    def _is_async_context(self):
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False

    def _run_function_sync(self, coro, return_future):
        loop = self._get_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        if return_future is None:
            return_future = self._return_futures
        if return_future:
            return fut
        else:
            return fut.result()

    async def _run_function_async(self, coro):
        current_loop = asyncio.get_running_loop()
        loop = self._get_loop()
        if loop == current_loop:
            return await coro

        c_fut = asyncio.run_coroutine_threadsafe(coro, loop)
        a_fut = asyncio.wrap_future(c_fut)
        return await a_fut

    def _create_generator_queue(self, coro):
        loop = self._get_loop()
        q = queue.Queue()
        async def pump():
            try:
                async for result in coro:
                    q.put_nowait(('gen', result))
            except Exception as exc:
                traceback.print_exc()  # TODO: is this really needed?
                q.put_nowait(('exc', exc))
            # TODO: we should catch StopIteration and make sure the value is returned
            # TODO: should we catch KeyboardInterrupt and CancelledError?
            q.put_nowait(('val', None))

        future = asyncio.run_coroutine_threadsafe(pump(), loop)
        return q

    def _run_generator_sync(self, coro):
        q = self._create_generator_queue(coro)
        while True:
            tag, res = q.get()
            if tag == 'val':
                return res
            elif tag == 'exc':
                raise res
            else:
                yield res

    async def _run_generator_async(self, coro):
        current_loop = asyncio.get_running_loop()
        loop = self._get_loop()
        if loop == current_loop:
            async for val in coro:
                yield val
            return

        q = self._create_generator_queue(coro)
        while True:
            tag, res = await current_loop.run_in_executor(None, q.get)
            if tag == 'val':
                return
            elif tag == 'exc':
                raise res
            else:
                yield res

    def _wrap_callable(self, f, return_future=None):
        @functools.wraps(f)
        def f_wrapped(*args, **kwargs):
            res = f(*args, **kwargs)
            is_async_context = self._is_async_context()
            is_coroutine = inspect.iscoroutine(res)
            is_asyncgen = inspect.isasyncgen(res)
            if is_coroutine:
                if is_async_context:
                    return self._run_function_async(res)
                else:
                    return self._run_function_sync(res, return_future)
            elif is_asyncgen:
                if is_async_context:
                    return self._run_generator_async(res)
                else:
                    return self._run_generator_sync(res)
            else:
                return res

        return f_wrapped

    def _wrap_class(self, cls):
        new_dict = {}
        cls_name = cls.__name__
        cls_new_name = cls_name + 'Synchronized'
        for k, v in cls.__dict__.items():
            if k == '__aenter__':
                new_dict[k] = v
                new_dict['__enter__'] = self._wrap_callable(v, return_future=False)
            elif k == '__aexit__':
                new_dict[k] = v
                new_dict['__exit__'] = self._wrap_callable(v, return_future=False)
            elif callable(v):
                new_dict[k] = self._wrap_callable(v)
            else:
                new_dict[k] = v
        cls_new = type(cls_new_name, (cls,), new_dict)
        return cls_new

    def __call__(self, object):
        if inspect.isclass(object):
            return self._wrap_class(object)
        elif callable(object):
            return self._wrap_callable(object)
        else:
            raise Exception('Argument %s is not a class or a callable' % object)
