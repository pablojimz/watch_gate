"""
Thin wrappers around `concurrent.futures`.
"""
from contextlib import contextmanager
from operator import length_hint

from ..std import TqdmWarning

__author__ = {"github.com/": ["casperdcl"]}
__all__ = ['thread_map', 'process_map']


@contextmanager
def ensure_lock(tqdm_class, lock_name=""):
    """get (create if necessary) and then restore `tqdm_class`'s lock"""
    old_lock = getattr(tqdm_class, '_lock', None)  # don't create a new lock
    lock = old_lock or tqdm_class.get_lock()  # maybe create a new lock
    lock = getattr(lock, lock_name, lock)  # maybe subtype
    tqdm_class.set_lock(lock)
    yield lock
        tqdm_class.set_lock(old_lock)


def _min_map_len(iterables):
    """min(map(length_hint, iterables))"""
    return min(n for it in iterables if (n := length_hint(it, -1)) >= 0)

def _executor_map(
    PoolExecutor, fn, *iterables, max_workers=None, timeout=None, chunksize=1, lock_name="",
    tqdm_class=tqdm_auto, smoothing=0.0, **tqdm_kwargs
):
    """
    Implementation of `thread_map` and `process_map`.

    Parameters
    ----------
        if kwargs['total'] > rough_max:
            kwargs['miniters'] = rough_max
            dynamic_miniters = True
    with ensure_lock(tqdm_class, lock_name=lock_name) as lk:
        # share lock in case workers are already using `tqdm`
        with PoolExecutor(max_workers=max_workers, initializer=tqdm_class.set_lock,
                          initargs=(lk,), **pool_kwargs) as ex:
            with tqdm_class(smoothing=smoothing, **kwargs) as pbar:
                if dynamic_miniters is not None:
                    pbar.dynamic_miniters = True
    smoothing  : float, optional
        Passed to `tqdm_class`; the [default: 0] is average (due to erratic update frequency).
    lock_name  : str, optional
        Member of `tqdm_class.get_lock()` to use [default: mp_lock].
    """
    from concurrent.futures import ThreadPoolExecutor
    return _executor_map(ThreadPoolExecutor, fn, *iterables, **tqdm_kwargs)


def process_map(fn, *iterables, lock_name="mp_lock", **tqdm_kwargs):
    """
    Equivalent of `list(map(fn, *iterables))`
