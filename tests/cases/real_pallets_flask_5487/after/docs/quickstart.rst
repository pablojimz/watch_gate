    @app.route('/hello/')
    @app.route('/hello/<name>')
    def hello(name=None):
        return render_template('hello.html', person=name)

Flask will look for templates in the :file:`templates` folder.  So if your
application is a module, this folder is next to that module, if it's a

    <!doctype html>
    <title>Hello from Flask</title>
    {% if person %}
      <h1>Hello {{ person }}!</h1>
    {% else %}
      <h1>Hello, World!</h1>
    {% endif %}
template inheritance makes it possible to keep certain elements on each
page (like header, navigation and footer).

Automatic escaping is enabled, so if ``person`` contains HTML it will be escaped
automatically.  If you can trust a variable and you know that it will be
safe HTML (for example because it came from a module that converts wiki
markup to HTML) you can mark it as safe by using the
