"""rtpeaks
"""

__all__ = ['keypress','libmpdev','rtp','__version__']

import os

if os.name == 'posix': raise OSError("Need to be on a Windows OS (>=Win7)")

from .rtp import RTP
from .libmpdev import MP150
from .version import __version__