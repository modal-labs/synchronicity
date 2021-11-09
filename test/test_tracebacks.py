import pytest
import traceback

from synchronicity import Synchronizer


class CustomException(Exception):
    pass


async def f_raises():
    raise CustomException("boom!")


def check_traceback(exc):
    tb = exc.__traceback__
    file_summary = {}
    for frame in traceback.extract_tb(tb):
        # print(frame.filename, frame.lineno, frame.line)
        file_summary[frame.filename] = file_summary.get(frame.filename, 0) + 1

    # Let's allow for at most 1 entry outside of this file
    assert sum(file_summary.values()) <= file_summary[__file__] + 1


def test_sync_to_async():
    s = Synchronizer()
    f_raises_s = s(f_raises)
    with pytest.raises(CustomException) as excinfo:
        f_raises_s()
    check_traceback(excinfo.value)


@pytest.mark.asyncio
async def test_async_to_async():
    s = Synchronizer()
    f_raises_s = s(f_raises)
    with pytest.raises(CustomException) as excinfo:
        await f_raises_s()
    check_traceback(excinfo.value)
