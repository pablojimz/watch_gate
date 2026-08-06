from werkzeug.test import create_environ
from werkzeug.wrappers import Request
from werkzeug.wrappers import Response
    response = Response(["Hällo Wörld".encode()])
    headers = response.get_wsgi_headers(create_environ())
    assert "Content-Length" in headers
