    def test_match_ignore_subdomain(self) -> None:
        assert self._match(base_url="static.app.test") == ("index", {})

    def test_build_relative(self) -> None:
        assert self._build("index") == "/"

    def test_build_external(self) -> None:
        """server_name is used over host"""
        assert (
            self._build("index", base_url="untrusted.test", external=True)
            == "http://app.test/"
        )


def test_server_name_casing():
    m = r.Map([r.Rule("/", endpoint="index", subdomain="foo")])
