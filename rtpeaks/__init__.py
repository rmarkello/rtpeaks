__all__ = ['keypress', 'mpdev', 'rtp', 'info']

import os
import warnings
from rtpeaks.rtp import RTP
from rtpeaks.mpdev import BIOPAC

if os.name == 'posix':
    warnings.warn(
        'Non-Windows system detected; most functionality will be inaccessible.'
    )
