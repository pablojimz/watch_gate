    _, err = capsys.readouterr()
    assert '30/30' in err
    assert res == list(range(0, 30 * 2, 2))
