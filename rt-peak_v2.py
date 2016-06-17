#!/usr/bin/env python

import os
import time
import multiprocessing as mp
import numpy as np
import scipy.signal
import keypress
from libmpdev_v2 import MP150

class RTP(MP150):
    
    def __init__(self, logfile='default', samplerate=500, channels=[1,2,3]):
        MP150.__init__(self, logfile, samplerate, channels)
        
        self.dic['DEBUGGING'] = True
        
        self.dic['peaklog'] = "%s_MP150_peaks.csv" % (logfile)
        self.peak_queue = self.manager.Queue()
        
        self.peak_process = mp.Process(target=peak_finder,
                                        args=(self.dic,self.sample_queue,self.peak_queue))
        self.peak_log_process = mp.Process(target=peak_log,
                                            args=(self.dic,self.peak_queue))

        self.peak_process.daemon = True
        self.peak_log_process.daemon = True
    
    
    def start_peak_finding(self):
        self.start_recording()
        self.__start_pipe()
        
        self.peak_process.start()
        self.peak_log_process.start()
    
    
    def stop_peak_finding(self):
        self.__stop_pipe()
        self.close()
    

def peak_log(dic,que):
    f = open(dic['peaklog'],'a+')
    f.write('time_detected,time_received,amplitude\n')
    f.flush()
    
    while True:
        i = que.get()
        if i == 'kill': break
        else:
            peakt, sigt, signal = i
            f.write('%s,%s,%s\n' % (peakt, sigt, str(signal).strip('[]')))
            f.flush()
    
    f.close()
    

def peak_finder(dic,que_in,que_log):
    sig = np.empty(0)
    last_found = np.array([[0,-2000,0],[1,-2000,0],[0,-1000,0],[1,-1000,0],[-1,0,0]])
    
    P_KEY, T_KEY = 0x50, 0x54
    
    print "Ready to find peaks..."
    
    while True:
        i = que_in.get()
        if i == 'kill': break

        sig = np.hstack((sig,i[1]))
        peak, trough = peak_or_trough(sig,last_found)
        
        if (peak or trough) and (i[0]-last_found[-1][1] > 800):
            sig = np.empty(0)
            
            currtime = int((time.time()-dic['starttime']) * 1000)
            que_log.put((currtime,i[0],i[1]))
            
            last_found = np.vstack((last_found,
                                    np.array([peak,i[0],i[1]])))
            
            keypress.PressKey(P_KEY if peak else T_KEY)
            keypress.ReleaseKey(P_KEY if peak else T_KEY)
                
            if dic['DEBUGGING']: print "Found %s" % ("peak" if peak else "trough")
            
        elif (peak or trough) and (i[0]-last_found[-1][1] < 800):
            sig = np.empty(0)
    
    que_log.put('kill')


def peak_or_trough(signal, last_found):    
    peaks = scipy.signal.argrelmax(signal,order=10)[0]
    troughs = scipy.signal.argrelmin(signal,order=10)[0]
        
    peak_height, trough_height = gen_thresh(last_found)
    thresh = np.mean(np.abs(peak_height-trough_height))/2
    
    if peaks.size and (last_found[-1][0] != 1):
        if np.abs(signal[peaks[-1]]-trough_height[-1]) > thresh:
            return True, False
    if troughs.size and (last_found[-1][0] != 0):
        if np.abs(signal[troughs[-1]]-peak_height[-1]) > thresh:
            return False, True
    return False, False
    

def gen_thresh(last_found):
    peak_heights = last_found[:,2][last_found[:,0]==1]
    trough_heights = last_found[:,2][last_found[:,0]==0]
    
    peak_height = peak_heights[-3 if peak_heights.shape[0]-3 > 0 else 0:]
    trough_height = trough_heights[-3 if trough_heights.shape[0]-3 > 0 else 0:]
    
    if peak_height.size > trough_height.size:
        peak_height = peak_height[peak_height.size-trough_height.size:]
    elif trough_height.size > peak_height.size:
        trough_height = trough_height[trough_height.size-peak_height.size:]
    
    return peak_height, trough_height


if __name__ == '__main__':
    r = RTP(logfile=time.ctime().split(' ')[3].replace(':','_'),
            channels=[1])

    r.start_peak_finding()
    time.sleep(600)
    r.stop_peak_finding()

    print "Done!"