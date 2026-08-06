    response = wrappers.Response("Hello World")
    assert response.get_etag() == (None, None)
    response.add_etag()
    assert response.get_etag() == ("0a4d55a8d778e5022fab701977c5d840bbc486d0", False)
    assert not response.cache_control
    response.cache_control.must_revalidate = True
    response.cache_control.max_age = 60
    response = wrappers.Response("Hello World")
    assert response.get_etag() == (None, None)
    response.add_etag()
    assert response.get_etag() == ("0a4d55a8d778e5022fab701977c5d840bbc486d0", False)
    assert not response.cache_control
    response.cache_control.must_revalidate = True
    response.cache_control.max_age = 60
