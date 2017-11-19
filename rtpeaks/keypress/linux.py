from __future__ import print_function, division, absolute_import
import subprocess


def press_key(key):
    """
    Uses xdotool to simulate a keypress of `key`

    Parameters
    ----------
    key : str
        String to type
    """

    out = subprocess.call(['xdotool', 'type', key])
    if out != 0:
        raise Exception('Failed to call `xdotool` to simulate keypress. ' +
                        'Ensure `xdotool` is installed on system using `apt`' +
                        '-get install -y xdotool` and try again.')
