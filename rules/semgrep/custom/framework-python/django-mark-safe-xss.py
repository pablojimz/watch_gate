from django.utils.safestring import mark_safe


def bad1(request):
    username = request.GET.get("name")
    # ruleid: django-mark-safe-xss
    return mark_safe(f"<div>Hello {username}</div>")


def bad2(request):
    comment = request.POST.get("comment")
    # ruleid: django-mark-safe-xss
    return mark_safe("<p>" + comment + "</p>")


def ok1():
    # ok: django-mark-safe-xss
    return mark_safe("<div>Static trusted content</div>")
