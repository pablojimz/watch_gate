
CYGWIN = sys.platform.startswith("cygwin")
WIN = sys.platform.startswith("win")
# One CSI escape sequence per the ECMA-48 grammar: parameter bytes (0x30-0x3F),
# intermediate bytes (0x20-0x2F), then a final byte (0x40-0x7E). Broader than the
# SGR codes Click emits, so foreign sequences (colon-delimited true-color, mouse
# reporting) are stripped too.
_ansi_re = re.compile(r"\033\[[0-?]*[ -/]*[@-~]")


def _make_text_stream(
