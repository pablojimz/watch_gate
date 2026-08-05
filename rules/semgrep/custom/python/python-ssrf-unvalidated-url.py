import requests
import urllib.request


def bad1(user_url):
    # ruleid: python-ssrf-unvalidated-url
    requests.get(user_url)


def bad2(user_url):
    # ruleid: python-ssrf-unvalidated-url
    urllib.request.urlopen(user_url)


def ok1():
    # ok: python-ssrf-unvalidated-url
    requests.get("https://api.internal-trusted.example.com/health")


def ok2():
    # ok: python-ssrf-unvalidated-url
    urllib.request.urlopen("https://example.com")
