    assert response.status_code == 400


def test_normal_environ_completes():
    app = flask.Flask(__name__)

