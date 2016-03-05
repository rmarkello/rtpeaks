#!/usr/bin/env python

import os
import time
import copy
import numpy as np
import multiprocessing as mp
import logging
import time
from libmpdev_v2 import MP150

class RTP(MP150):
    
    def __init__(self, logfile='default', samplerate=200, channels=[1,2,3]):
        MP150.__init__(self, logfile, samplerate, channels)
        
        self._dict['peaklog'] = "%s_peak_data.csv" % (logfile)
        self._peak_queue = self._manager.Queue()
                
        self._peak_process = mp.Process(target=_peak_finder,args=(self._dict,self._out_queue,self._peak_queue))
        self._peak_process.daemon = True
        
        self._peak_log_process = mp.Process(target=_peak_log,args=(self._dict,self._peak_queue))
        self._peak_log_process.daemon = True
        
        
    def start(self):
        self.start_recording()
        self._start_pipe()
        
        self._peak_process.start()
        self._peak_log_process.start()
    
        
    def stop(self):
        self._stop_pipe()
        self.close()
        

def _peak_finder(dic,que_in,que_log):
    last_bunch = np.empty(1)
    peakind_log = np.empty(0)
    
    while True:
        i = que_in.get()
        if i == 'kill':
            break
        else:
            if i[1] != last_bunch[-1]:
                last_bunch = np.hstack((last_bunch,i[1]))
                peakind = scipy.signal.argrelmax(last_bunch,order=10)[0]
                
                if peakind.size > peakind_log.size:
                    peakind_log = peakind            
                    que_log.put(i[0:2])
                    print "Peak found!"
    
    que_log.put('kill')
    print "Receiver queue process killed at: "+str(time.time()-dic['starttime'])


def _peak_log(dic,que):
    f = open(dic['peaklog'],'a+')
    print "Peak file opened  at: "+str(time.time()-dic['starttime'])
    
    while True:
        i = que.get()
        if i == 'kill':
            break
        else:
            f.write(str(i)+'\n')
            f.flush()

    f.close()
    print "Peak file closed at: "+str(time.time()-dic['starttime'])
    

if __name__ == '__main__':
    mp.log_to_stderr(logging.DEBUG)
    r = RTP()
    print "Created RTP instance  at: "+str(r._dict['starttime'])
    r.start()
    time.sleep(10)
    for f in range(500):
        print "SAMPLING: " + str(r.sample())
    r.stop()
    print "Done at: "+str(time.time()-r._dict['starttime'])