"""
rtpeaks
"""

__all__ = ['keypress', 'mpdev', 'rtp', '__version__']

import os
import warnings
from .version import __version__

if os.name == 'posix':
    warnings.warn('Not on Windows operating system; most functionality will ' +
                  'be inaccessible.')

from .rtp import RTP
from .mpdev import MP150
