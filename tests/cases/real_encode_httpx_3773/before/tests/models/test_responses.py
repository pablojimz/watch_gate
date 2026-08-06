
    assert response.status_code == 200
    assert response.reason_phrase == "OK"
    assert response.encoding == "ISO-8859-1"
    assert response.text == text


