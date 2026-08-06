            "http://example.org</a>"
        )

    def test_urlize_mail_mastodon(self):
        fr = "nabijaczleweli@nabijaczleweli.xyz\n@eater@cijber.social\n"
        to = (
            '<a href="mailto:nabijaczleweli@nabijaczleweli.xyz">'
            "nabijaczleweli@nabijaczleweli.xyz</a>\n@eater@cijber.social\n"
        )
        assert urlize(fr) == to


class TestLoremIpsum:
    def test_lorem_ipsum_markup(self):
