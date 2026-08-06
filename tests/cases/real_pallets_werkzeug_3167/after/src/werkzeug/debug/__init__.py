import os
import pkgutil
import re
import secrets
import subprocess
import sys
import time
from ..exceptions import SecurityError
from ..http import parse_cookie
from ..sansio.utils import host_is_trusted
from ..utils import send_file
from ..wrappers.request import Request
from ..wrappers.response import Response
        self.console_path = console_path
        self.console_init_func = console_init_func
        self.show_hidden_frames = show_hidden_frames
        self.secret = secrets.token_urlsafe(20)
        self._failed_pin_auth = Value("B")

        self.pin_logging = pin_logging
