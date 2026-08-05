import pickle
from flask import request, session


def bad1():
    # ruleid: flask-pickle-session-deserialization
    data = pickle.loads(request.cookies.get("session_data"))


def bad2():
    # ruleid: flask-pickle-session-deserialization
    data = pickle.loads(session["blob"])


def bad3():
    # ruleid: flask-pickle-session-deserialization
    data = pickle.loads(request.get_data())


def ok1():
    import json
    # ok: flask-pickle-session-deserialization
    data = json.loads(request.cookies.get("session_data"))
