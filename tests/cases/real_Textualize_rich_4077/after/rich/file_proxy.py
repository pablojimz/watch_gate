
    def fileno(self) -> int:
        return self.__file.fileno()

    def isatty(self) -> bool:
        return self.__file.isatty()
