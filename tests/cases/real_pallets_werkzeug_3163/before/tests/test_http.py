        assert rv.date is None
        assert rv.to_header() == '"Test"'

        # weak information is dropped
        rv = IfRange.from_header('W/"Test"')
        assert rv.etag == "Test"
        assert rv.date is None
        assert rv.to_header() == '"Test"'

        # broken etags are supported too
        rv = IfRange.from_header("bullshit")
        assert rv.etag == "bullshit"
        assert rv.date is None
        assert rv.to_header() == '"bullshit"'

        rv = IfRange.from_header("Thu, 01 Jan 1970 00:00:00 GMT")
        assert rv.etag is None
