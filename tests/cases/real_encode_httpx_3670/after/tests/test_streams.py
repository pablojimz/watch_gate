    path = tmp_path / "example.txt"
    path.write_bytes(b"hello world")

    with httpx.File(path).encode() as s:
        assert s.size == 11
        assert s.read() == b'hello world'

    with httpx.File(path).encode() as s:
        assert s.read(5) == b'hello'
        assert s.read(5) == b' worl'
        assert s.read(5) == b'd'
        assert s.read(5) == b''

    with httpx.File(path).encode() as s:
        assert s.read(5) == b'hello'


