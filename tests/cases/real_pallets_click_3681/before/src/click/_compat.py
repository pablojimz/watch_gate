
CYGWIN = sys.platform.startswith("cygwin")
WIN = sys.platform.startswith("win")
_ansi_re = re.compile(r"\033\[[;?0-9]*[a-zA-Z]")


def _make_text_stream(
