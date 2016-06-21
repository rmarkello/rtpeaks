#!/usr/bin/env python

import time
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