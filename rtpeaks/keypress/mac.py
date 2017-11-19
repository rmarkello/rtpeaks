from __future__ import print_function, division, absolute_import
import subprocess


def press_key(key):
    """
    Uses osascript to simulate a keypress of `key`

    Parameters
    ----------
    key : str
        String to type
    """

    cmd = 'osascript -e \'tell application "System Events" to keystroke'
    out = subprocess.call(cmd.split() + [key])
    if out != 0:
        raise Exception('Failed to call `osascript` to simulate keypress. ' +
                        'Ensure `osascript` is installed on system and try ' +
                        'again.')
