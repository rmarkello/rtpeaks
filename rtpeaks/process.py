#!/usr/bin/env python

from future.utils import raise_
import multiprocessing as mp


class Process(mp.Process):
    """
    Multiprocessing process designed to catch exceptions.

    Works the same as multiprocessing.Process class, but will catch Exception
    in child process and re-raise in calling thread with traceback info.
    """

    def __init__(self, *args, **kwargs):
        super(Process, self).__init__(*args, **kwargs)

    def saferun(self):
        if self._target is not None:
            self._target(*self._args, **self._kwargs)

    def run(self):
        try: self.saferun()
        except Exception as e:
            import sys
            _, exception, tb = sys.exc_info()
            raise_(exception, None, tb)
