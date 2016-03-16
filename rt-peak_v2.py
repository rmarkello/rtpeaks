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
    

def _peak_log(dic,que):
    f = open(dic['peaklog'],'a+')
    
    while True:
        i = que.get()
        if i == 'kill': break
        else:
            peakt, sigt, signal = i
            f.write('%s,%s,%s\n' % (peakt, sigt, str(signal).strip('[]')))
            f.flush()
    
    f.close()
    

def _peak_finder(dic,que_in,que_log):
    sig = np.empty(0)
    last_found = np.array([[0,-2000,0],[1,-2000,0],[0,-1000,0],[1,-1000,0]])
    
    P_KEY = 0x50
    T_KEY = 0x54
    
    print "Ready to find peaks..."
    
    while True:
        i = que_in.get()
        if i == 'kill': break
        else:
            sig = np.hstack((sig,i[1]))
            
            peak_height, trough_height = _gen_thresh(last_found)
            thresh = np.mean(np.abs(peak_height-trough_height))/2
            
            peak = _is_it_a_peak(sig,trough_height[-1],thresh)
            trough = _is_it_a_trough(sig,peak_height[-1],thresh)
            
            if (peak or trough) and (i[0]-last_found[-1][1] > 1000):
                sig = np.empty(0)
                currtime = int((time.time()-dic['starttime']) * 1000)
                que_log.put((currtime,i[0],i[1]))
                
                last_found = np.vstack((last_found,
                                        np.array([peak,i[0],i[1]])))
                
                keypress.PressKey(P_KEY if peak else T_KEY)
                keypress.ReleaseKey(P_KEY if peak else T_KEY)
                    
                if dic['DEBUGGING']: print "Found %s" % ("peak" if peak else "trough")
                
            elif (peak or trough) and (i[0]-last_found[-1][1] < 1000):
                sig = np.empty(0)
    
    que_log.put('kill')


def _peak_or_trough(signal):
    pass


def _gen_thresh(last_found):
    b_size = last_found.shape[0]
    t_size = 0 if (b_size-6 < 0) else b_size-6
    
    peak_height = last_found[t_size:b_size,2][last_found[t_size:b_size,0]==1]
    trough_height = last_found[t_size:b_size,2][last_found[t_size:b_size,0]==0]
    
    if peak_height.size>trough_height.size:
        peak_height = peak_height[peak_height.size-trough_height.size:]
    elif trough_height.size>peak_height.size:
        trough_height = trough_height[trough_height.size-peak_height.size:]
    
    return peak_height, trough_height


def _is_it_a_peak(sig, last_trough_height, thresh=0):
    peakind = scipy.signal.argrelmax(sig,order=10)[0]
    
    if not peakind.size: return False
    
    high_enough = np.abs(sig[peakind[-1]]-last_trough_height) > thresh
    
    if high_enough: return True
    else: return False


def _is_it_a_trough(sig, last_peak_height, thresh=0):
    peakind = scipy.signal.argrelmin(sig,order=10)[0]
    
    if not peakind.size: return False
    
    low_enough = np.abs(sig[peakind[-1]]-last_peak_height) > thresh
    
    if low_enough: return True
    else: return False


if __name__ == '__main__':
    #mp.log_to_stderr(logging.DEBUG)
    name = time.ctime().split(' ')
    r = RTP(logfile=name[3].replace(':','_'),channels=[1])
    r.start_peak_finding()
    time.sleep(25)
    r.stop_peak_finding()
    print "Done!"