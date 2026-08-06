def test_itms_services() -> None:
    url = "itms-services://?action=download-manifest&url=https://test.example/path"
    assert urls.iri_to_uri(url) == url


@pytest.mark.parametrize(
    "value",
    ["http://:p@d.test", "http://u:@d.test", "http://:@d.test", "http://u@d.test"],
)
def test_uri_empty_auth(value: str) -> None:
    assert urls.uri_to_iri(value) == value
    assert urls.iri_to_uri(value) == value


def test_uri_port_0() -> None:
    assert urls.uri_to_iri("http://d.test:0") == "http://d.test:0"
    assert urls.iri_to_uri("http://d.test:0") == "http://d.test:0"
