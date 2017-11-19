import sys

if sys.platform == 'darwin':
    from rtpeaks.keypress.mac import press_key
elif sys.platform in ['win32', 'cygwin']:
    from rtpeaks.keypress.windows import press_key
else:
    from rtpeaks.keypress.linux import press_key
