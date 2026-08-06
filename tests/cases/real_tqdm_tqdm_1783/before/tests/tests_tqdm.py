    assert out == '  0%|          | 0/10 [00:00<?, ?it/s]\n'


def test_reset():
    """Test resetting a bar for re-use"""
    with closing(StringIO()) as our_file:
        with tqdm(total=10, file=our_file,
                  miniters=1, mininterval=0, maxinterval=0) as t:
            t.update(9)
            t.reset()
            t.update()
            t.reset(total=12)
            t.update(10)
        assert '| 1/10' in our_file.getvalue()
        assert '| 10/12' in our_file.getvalue()


def test_disabled_reset(capsys):
