    response = wrappers.Response("Hello World")
    assert response.get_etag() == (None, None)
    response.add_etag()
    assert response.get_etag() == (
        "e167f68d6563d75bb25f3aa49c29ef612d41352dc00606de7cbd630bb2665f51",
        False,
    )
    assert not response.cache_control
    response.cache_control.must_revalidate = True
    response.cache_control.max_age = 60
    response = wrappers.Response("Hello World")
    assert response.get_etag() == (None, None)
    response.add_etag()
    assert response.get_etag() == (
        "e167f68d6563d75bb25f3aa49c29ef612d41352dc00606de7cbd630bb2665f51",
        False,
    )
    assert not response.cache_control
    response.cache_control.must_revalidate = True
    response.cache_control.max_age = 60
