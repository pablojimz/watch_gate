# ruleid: django-debug-true-production
DEBUG = True

# ok: django-debug-true-production
DEBUG = os.environ.get("DEBUG", "False") == "True"
