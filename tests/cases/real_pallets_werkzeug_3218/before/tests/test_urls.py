def test_itms_services() -> None:
    url = "itms-services://?action=download-manifest&url=https://test.example/path"
    assert urls.iri_to_uri(url) == url
