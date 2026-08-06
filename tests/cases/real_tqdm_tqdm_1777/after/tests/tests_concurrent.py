"""
Tests for `tqdm.contrib.concurrent`.
"""
import sys

from pytest import warns

from tqdm.contrib.concurrent import interpreter_map, process_map, thread_map

from .tests_tqdm import StringIO, TqdmWarning, closing, importorskip, mark, skip

        assert thread_map(incr, a, file=our_file) == b


@mark.skipif(sys.version_info < (3, 14), reason="requires Python 3.14+")
def test_interpreter_map(capsys):
    """Test contrib.concurrent.interpreter_map"""
    a = range(9)
    b = [i + 1 for i in a]
    try:
        assert interpreter_map(incr, a) == b
    except ImportError as err:
        skip(str(err))
    out, err = capsys.readouterr()
    assert not out
    assert '9/9' in err


def test_process_map():
    """Test contrib.concurrent.process_map"""
    with closing(StringIO()) as our_file:
            skip(str(err))


def check_lock(args):
    """Check that another interpreter cannot acquire a held tqdm lock"""
    from os.path import exists
    from time import sleep

    from tqdm.auto import tqdm

    held, checked, result, role = args
    assert tqdm.monitor_interval == 0
    lock = tqdm.get_lock()
    if role == 'holder':
        with lock, lock:  # also check that the lock is reentrant
            with open(held, 'w'):
                pass
            while not exists(checked):
                sleep(0.01)
    else:
        while not exists(held):
            sleep(0.01)
        acquired = lock.acquire(False)
        if acquired:
            lock.release()
        with open(result, 'w') as result_file:
            result_file.write(str(acquired))
        with open(checked, 'w'):
            pass
    return role


@mark.skipif(sys.version_info < (3, 14), reason="requires Python 3.14+")
def test_interpreter_map_lock(tmp_path):
    """Test interpreter workers share tqdm's write lock"""
    held = str(tmp_path / 'held')
    checked = str(tmp_path / 'checked')
    result = tmp_path / 'result'
    roles = ['holder', 'contender']
    args = [(held, checked, str(result), role) for role in roles]
    try:
        assert interpreter_map(check_lock, args, max_workers=2, disable=True) == roles
    except ImportError as err:
        skip(str(err))
    assert result.read_text() == 'False'


@mark.parametrize("iterables,should_warn", [([], False), (['x'], False), ([()], False),
                                            (['x', ()], False), (['x' * 1001], True),
                                            (['x' * 100, ('x',) * 1001], False),
