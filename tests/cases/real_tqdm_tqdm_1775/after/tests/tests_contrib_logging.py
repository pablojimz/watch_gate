        with logging_redirect_tqdm(loggers=[logger]):
            assert logger.handlers[0].formatter == formatter

    def test_should_inherit_console_handler_filters(self):
        class SuffixFilter(logging.Filter):
            def filter(self, record):
                record.msg = f'{record.msg} -- filter'
                return True

        logger = logging.Logger('test')
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.addFilter(SuffixFilter())
        logger.handlers = [console_handler]
        CustomTqdm.messages = []
        with logging_redirect_tqdm(loggers=[logger], tqdm_class=CustomTqdm):
            logger.info('test')
        assert CustomTqdm.messages == ['test -- filter']

    def test_should_not_remove_stream_handlers_not_for_stdout_or_stderr(self):
        logger = logging.Logger('test')
        stream_handler = logging.StreamHandler(StringIO())
