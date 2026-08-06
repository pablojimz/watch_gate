"""
Tests for `tqdm.contrib.concurrent`.
"""
from pytest import warns

from tqdm.contrib.concurrent import process_map, thread_map

from .tests_tqdm import StringIO, TqdmWarning, closing, importorskip, mark, skip

        assert thread_map(incr, a, file=our_file) == b


def test_process_map():
    """Test contrib.concurrent.process_map"""
    with closing(StringIO()) as our_file:
            skip(str(err))


@mark.parametrize("iterables,should_warn", [([], False), (['x'], False), ([()], False),
                                            (['x', ()], False), (['x' * 1001], True),
                                            (['x' * 100, ('x',) * 1001], False),
