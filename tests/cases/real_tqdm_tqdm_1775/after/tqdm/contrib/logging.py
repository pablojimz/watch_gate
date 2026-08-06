            if orig_handler is not None:
                tqdm_handler.setFormatter(orig_handler.formatter)
                tqdm_handler.stream = orig_handler.stream
                for log_filter in orig_handler.filters:
                    tqdm_handler.addFilter(log_filter)
            logger.handlers = [
                handler for handler in logger.handlers
                if not _is_console_logging_handler(handler)] + [tqdm_handler]
