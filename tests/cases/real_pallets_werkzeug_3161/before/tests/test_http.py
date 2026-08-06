        assert a.best_match(["text/html; version=1", "text/html"]) == "text/html"
        assert a.best_match(["text/html", "text/html; level=1"]) == "text/html; level=1"

    def test_charset_accept(self):
        a = http.parse_accept_header(
            "ISO-8859-1,utf-8;q=0.7,*;q=0.7", datastructures.CharsetAccept
        )
        assert a["iso-8859-1"] == a["iso8859-1"]
        assert a["iso-8859-1"] == 1
        assert a["UTF8"] == 0.7
        assert a["ebcdic"] == 0.7

    def test_language_accept(self):
        a = http.parse_accept_header(
            "de-AT,de;q=0.8,en;q=0.5", datastructures.LanguageAccept
