
    assert response.status_code == 200
    assert response.reason_phrase == "OK"
    # The encoded byte string is consistent with either ISO-8859-1 or
    # WINDOWS-1252. Versions <6.0 of chardet claim the former, while chardet
    # 6.0 detects the latter.
    assert response.encoding in ("ISO-8859-1", "WINDOWS-1252")
    assert response.text == text


