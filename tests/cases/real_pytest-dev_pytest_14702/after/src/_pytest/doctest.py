from _pytest.config import Config
from _pytest.config.argparsing import Parser
from _pytest.fixtures import fixture
from _pytest.fixtures import FixtureFunctionDefinition
from _pytest.fixtures import TopRequest
from _pytest.nodes import Collector
from _pytest.nodes import Item
                        obj,
                        source_lines,
                    )
            elif py_ver_info_minor == (3, 12):

                def _find_lineno(self, obj, source_lines):
                    if isinstance(obj, FixtureFunctionDefinition):
                        obj = inspect.unwrap(obj)

                    # Type ignored because this is a private function.
                    return super()._find_lineno(  # type:ignore[misc]
                        obj,
                        source_lines,
                    )

            if sys.version_info < (3, 13):

