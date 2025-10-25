import asyncio
import sys
import time
from contextlib import asynccontextmanager

from synchronicity import Synchronizer


@asynccontextmanager
async def ctx_mgr():
    try:
        if sys.argv[1] == "enter":
            while True:
                print("enter")
                await asyncio.sleep(0.3)
        elif sys.argv[1] == "yield":
            yield
        else:
            print("this should not happen")
    finally:
        print("exit")


s = Synchronizer()
blocking_ctx_mgr = s.create_blocking(ctx_mgr)
try:
    with blocking_ctx_mgr():
        while True:
            print("in ctx")
            time.sleep(0.3)
except KeyboardInterrupt:
    print("keyboard interrupt")
