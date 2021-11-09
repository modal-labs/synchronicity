import pytest
import traceback

from synchronicity import Synchronizer


class CustomException(Exception):
    pass


async def f_raises():
    raise CustomException("boom!")


def analyze_tb(exc):
    tb = exc.__traceback__
    file_summary = {}
    for frame in traceback.extract_tb(tb):
        # print(frame.filename, frame.lineno, frame.line)
        file_summary[frame.filename] = file_summary.get(frame.filename, 0) + 1
    return file_summary


def test_raises():
    s = Synchronizer()
    f_raises_s = s(f_raises)
    with pytest.raises(CustomException) as excinfo:
        f_raises_s()

    exc = excinfo.value
    summary = analyze_tb(exc)

    # Let's allow for at most 1 entry outside of this file
    assert sum(summary.values()) <= summary[__file__] + 1
