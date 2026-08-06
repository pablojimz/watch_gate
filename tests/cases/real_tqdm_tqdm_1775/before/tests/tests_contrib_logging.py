        with logging_redirect_tqdm(loggers=[logger]):
            assert logger.handlers[0].formatter == formatter

    def test_should_not_remove_stream_handlers_not_for_stdout_or_stderr(self):
        logger = logging.Logger('test')
        stream_handler = logging.StreamHandler(StringIO())
