    assert not out
    assert '  0%' in err
    assert '100%' not in err


def test_write_stdout_none():
    """Test tqdm.write does not crash when sys.stdout is None"""
    orig_stdout = sys.stdout
    try:
        sys.stdout = None
        tqdm.write("test stdout none message")
    finally:
        sys.stdout = orig_stdout
