#!/usr/bin/env python

# script to test real time peak detection functionality

import time
try: 
    from rtpeaks import RTP
except ImportError:
    import sys
    import os 
    sys.path.append(os.path.dirname(os.getcwd()))
    from rtpeaks import RTP

if __name__ == '__main__':
    r = RTP(logfile = time.ctime().split(' ')[3].replace(':','_'),
            samplerate=500.,
            channels = [1],
            debug = True)

    r.start_peak_finding()
    time.sleep(60)
    r.stop_peak_finding()
    r.close()

    print "Done!"