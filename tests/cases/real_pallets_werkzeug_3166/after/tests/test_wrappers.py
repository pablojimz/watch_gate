    response = wrappers.Response("Hello World")
    assert response.get_etag() == (None, None)
    response.add_etag()
    assert response.get_etag() == ("4Wf2jWVj11uyXzqknCnvYS1BNS3ABgbefL1jC7JmX1E", False)
    assert not response.cache_control
    response.cache_control.must_revalidate = True
    response.cache_control.max_age = 60
    response = wrappers.Response("Hello World")
    assert response.get_etag() == (None, None)
    response.add_etag()
    assert response.get_etag() == ("4Wf2jWVj11uyXzqknCnvYS1BNS3ABgbefL1jC7JmX1E", False)
    assert not response.cache_control
    response.cache_control.must_revalidate = True
    response.cache_control.max_age = 60
