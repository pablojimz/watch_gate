from flask import render_template_string, request


def bad1():
    name = request.args.get("name")
    # ruleid: flask-render-template-string-ssti
    return render_template_string(f"<h1>Hello {name}</h1>")


def bad2():
    tpl = request.form.get("template")
    # ruleid: flask-render-template-string-ssti
    return render_template_string(tpl)


def ok1(name):
    # ok: flask-render-template-string-ssti
    return render_template_string("<h1>Hello {{ name }}</h1>", name=name)
