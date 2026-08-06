    assert out == '  0%|          | 0/10 [00:00<?, ?it/s]\n'


def test_reset(capsys):
    """Test resetting a bar for re-use"""
    with tqdm(total=10, miniters=1, mininterval=0, maxinterval=0) as t:
        t.update(9)
        t.reset()
        t.update()
        t.reset(total=12)
        t.update(10)
    out, err = capsys.readouterr()
    assert not out
    assert '| 1/10' in err
    assert '| 10/12' in err


def test_reset_inf(capsys):
    """Test resetting a bar to an infinite total"""
    with tqdm(total=10, miniters=1, mininterval=0, maxinterval=0) as t:
        t.update(5)
        t.reset(total=float("inf"))
        t.update()
        # same as tqdm(total=float("inf")): treated as unknown
        assert t.total is None
    out, err = capsys.readouterr()
    assert not out
    assert '1it' in err


def test_disabled_reset(capsys):
