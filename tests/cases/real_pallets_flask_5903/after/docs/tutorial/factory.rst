            app.config.from_mapping(test_config)

        # ensure the instance folder exists
        os.makedirs(app.instance_path, exist_ok=True)

        # a simple page that says hello
        @app.route('/hello')
