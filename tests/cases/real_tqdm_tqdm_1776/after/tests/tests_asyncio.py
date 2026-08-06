    _, err = capsys.readouterr()
    assert '30/30' in err
    assert res == list(range(0, 30 * 2, 2))


async def raise_exc(i):
    if i == 1:
        raise ValueError("test")
    return i * 2


@mark.asyncio
async def test_gather_exceptions(capsys):
    """Test asyncio gather return_exceptions"""
    res = await gather(*map(raise_exc, range(3)), return_exceptions=True)
    _, err = capsys.readouterr()
    assert '3/3' in err
    assert isinstance(res[1], ValueError)
    assert res[0] == 0
    assert res[2] == 4
