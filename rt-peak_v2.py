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
    sig = np.empty(0)
    last_found = np.array([[0,-1000,10],[1,-1000,-10]])
    
    print "Ready to find peaks..."
    
    while True:
        i = que_in.get()
        if i == 'kill': break
        else:
            sig = np.hstack((sig,i[1]))
            b_size = last_found.shape[0]
            
            if b_size-6 < 0: t_size = 0
            else: t_size = b_size-6
            
            p_thresh = np.mean(last_found[last_found[t_size:b_size,0]==1,2])
            t_thresh = np.mean(last_found[last_found[t_size:b_size,0]==0,2])
            
            peak = _is_it_a_peak(sig,p_thresh)
            trough = _is_it_a_trough(sig,t_thresh)
            
            if (peak or trough) and (i[0]-last_found[-1][1] > 1000):
                sig = np.empty(0)
                
                que_log.put(i[0:2])
                
                last_found = np.vstack((last_found,np.array([peak,i[0],i[1]])))
                
                if peak:
                    keypress.PressKey(0x50)
                    keypress.ReleaseKey(0x50)
                    
                    if dic['DEBUGGING']: print "Found peak"
                    
                else:
                    keypress.PressKey(0x54)
                    keypress.ReleaseKey(0x54)
                    
                    if dic['DEBUGGING']: print "Found trough"
                
            elif (peak or trough) and (i[0]-last_found[-1][1] < 1000):
                sig = np.empty(0)
    
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


def _is_it_a_peak(sig, thresh):
    peakind = scipy.signal.argrelmax(sig,order=10)[0]
    
    if peakind.size > 0 and sig[peakind[-1]] > thresh:
        return True
    else:
        return False


def _is_it_a_trough(sig, thresh):
    peakind = scipy.signal.argrelmin(sig,order=10)[0]
    
    if peakind.size > 0 and sig[peakind[-1]] < thresh:
        return True
    else:
        return False


if __name__ == '__main__':
    #mp.log_to_stderr(logging.DEBUG)
    name = time.ctime().split(' ')
    r = RTP(logfile=name[3].replace(':','_'),channels=[1,2,3])
    r.start_peak_finding()
    time.sleep(25)
    r.stop_peak_finding()
    print "Done!"