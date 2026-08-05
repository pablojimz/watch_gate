def bad1(request, user_id):
    # ruleid: django-extra-raw-sql-injection
    return User.objects.extra(where=[f"id = {user_id}"])


def bad2(request, user_id):
    # ruleid: django-extra-raw-sql-injection
    return User.objects.raw(f"SELECT * FROM auth_user WHERE id = {user_id}")


def ok1():
    # ok: django-extra-raw-sql-injection
    return User.objects.extra(where=["active = 1"])


def ok2():
    # ok: django-extra-raw-sql-injection
    return User.objects.raw("SELECT * FROM auth_user WHERE active = 1")
