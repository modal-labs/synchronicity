import os
import traceback

synchronicity_dir = os.path.dirname(__file__)


def should_skip_tb_frame(tb):
    "Skip the frame if it's in the same directory as this module."

    frame_file = traceback.extract_tb(tb, 1)[0].filename
    return os.path.commonpath([synchronicity_dir, frame_file]) == synchronicity_dir


def get_filtered_tb(tb):
    while tb and should_skip_tb_frame(tb):
        tb = tb.tb_next

    if tb is not None:
        tb.tb_next = get_filtered_tb(tb.tb_next)

    return tb


def filter_traceback(f):
    def f_wrapped(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as exc:
            tb = exc.__traceback__
            raise exc.with_traceback(get_filtered_tb(tb))

    return f_wrapped
