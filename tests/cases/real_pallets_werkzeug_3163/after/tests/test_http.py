        assert rv.date is None
        assert rv.to_header() == '"Test"'

        # weak etag is discarded
        rv = IfRange.from_header('W/"Test"')
        assert rv.etag is None
        assert rv.date is None
        assert rv.to_header() == ""

        # broken etags are supported too
        rv = IfRange.from_header("unquoted")
        assert rv.etag == "unquoted"
        assert rv.date is None
        assert rv.to_header() == '"unquoted"'

        rv = IfRange.from_header("Thu, 01 Jan 1970 00:00:00 GMT")
        assert rv.etag is None
