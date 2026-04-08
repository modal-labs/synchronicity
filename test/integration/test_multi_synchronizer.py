"""Two named synchronizers use distinct worker threads and event loops."""


def test_distinct_synchronizers_separate_threads_and_loops(generated_wrappers):
    """Wrappers tied to different ``Module(..., synchronizer_name)`` values do not share a loop."""
    import multi_sync.a
    import multi_sync.b

    from synchronicity.synchronizer import get_synchronizer

    tid_a, lid_a = multi_sync.a.thread_and_loop_a()
    tid_b, lid_b = multi_sync.b.thread_and_loop_b()

    assert tid_a != tid_b, "implementation threads for the two synchronizers should differ"
    assert lid_a != lid_b, "asyncio loops for the two synchronizers should differ"

    sync_a = get_synchronizer("synchronizer_alpha")
    sync_b = get_synchronizer("synchronizer_beta")
    assert sync_a._thread is not None and sync_b._thread is not None
    assert sync_a._thread.ident == tid_a
    assert sync_b._thread.ident == tid_b
    assert sync_a._loop is not None and sync_b._loop is not None
    assert sync_a._loop is not sync_b._loop
