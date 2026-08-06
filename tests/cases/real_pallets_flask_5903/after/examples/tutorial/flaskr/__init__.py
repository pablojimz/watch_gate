        app.config.update(test_config)

    # ensure the instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)

    @app.route("/hello")
    def hello():
