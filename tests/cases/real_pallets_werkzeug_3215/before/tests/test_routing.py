    def test_match_ignore_subdomain(self) -> None:
        assert self._match(base_url="static.app.test") == ("index", {})


def test_server_name_casing():
    m = r.Map([r.Rule("/", endpoint="index", subdomain="foo")])
