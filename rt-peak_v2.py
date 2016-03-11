#!/usr/bin/env python

import os
import time
import numpy as np
import multiprocessing as mp
import keypress
from libmpdev_v2 import MP150
import scipy.signal

class RTP(MP150):
    
    def __init__(self, logfile='default', samplerate=200, channels=[1,2,3]):
        MP150.__init__(self, logfile, samplerate, channels)
        
        self._dict['DEBUGGING'] = True
        
        self._dict['peaklog'] = "%s_MP150_peaks.csv" % (logfile)
        self._peak_queue = self._manager.Queue()
        
        self._peak_process = mp.Process(target=_peak_finder,args=(self._dict,self._sample_queue,self._peak_queue))
        self._peak_process.daemon = True
        
        self._peak_log_process = mp.Process(target=_peak_log,args=(self._dict,self._peak_queue))
        self._peak_log_process.daemon = True
        
        
    def start_peak_finding(self):
        self.start_recording()
        self._start_pipe()
        
        self._peak_process.start()
        self._peak_log_process.start()
    
        
    def stop_peak_finding(self):
        self._stop_pipe()
        self.close()
        

def _peak_finder(dic,que_in,que_log):
    last_bunch = np.empty(0)
    peakind_log = np.empty(0)
    
    print "Ready to find peaks..."
    
    while True:
        i = que_in.get()
        if i == 'kill': break
        else:
            last_bunch = np.hstack((last_bunch,i[1]))
            
            peak = _is_it_a_peak(last_bunch)
            trough = _is_it_a_trough(last_bunch)
            
            if peak or trough:
                last_bunch = np.empty(0)
                
                que_log.put(i[0:2])
                
                if peak:
                    keyPress.PressKey(0x50)
                    keypress.ReleaseKey(0x50)
                    
                    if dic['DEBUGGING']: print "Found peak"
                
                if trough:
                    keypress.PressKey(0x54)
                    keypress.ReleaseKey(0x54)
                    
                    if dic['DEBUGGING']: print "Found trough"
            
                
                
    que_log.put('kill')


def _peak_log(dic,que):
    f = open(dic['peaklog'],'a+')
    
    while True:
        i = que.get()
        if i == 'kill': break
        else:
            logt, signal = i
            f.write('%s,%s\n' % (logt, str(signal).strip('[]')))
            f.flush()
    
    f.close()


def _is_it_a_peak(sig):
    peakind = scipy.signal.argrelmax(sig,order=10)[0]
    
    return peakind.size


def _is_it_a_trough(sig):
    peakind = scipy.signal.argrelmin(sig,order=10)[0]
    
    return peakind.size


if __name__ == '__main__':
    #mp.log_to_stderr(logging.DEBUG)
    name = time.ctime().split(' ')
    r = RTP(logfile=name[3].replace(':','_'),channels=[1,2,3])
    r.start_peak_finding()
    time.sleep(25)
    r.stop_peak_finding()
    print "Done!"