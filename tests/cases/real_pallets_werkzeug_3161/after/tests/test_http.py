        assert a.best_match(["text/html; version=1", "text/html"]) == "text/html"
        assert a.best_match(["text/html", "text/html; level=1"]) == "text/html; level=1"

    def test_language_accept(self):
        a = http.parse_accept_header(
            "de-AT,de;q=0.8,en;q=0.5", datastructures.LanguageAccept
