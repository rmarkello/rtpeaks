#!/usr/bin/env python

import os
import time
import multiprocessing as mp
import numpy as np
import scipy.signal
import keypress
from libmpdev_v2 import MP150

class RTP(MP150):
    
    def __init__(self, logfile='default', samplerate=500, channels=[1,2,3], debug=False):

        MP150.__init__(self, logfile, samplerate, channels)
        
        peak_log_file = "%s_MP150_peaks.csv" % (logfile)

        self.peak_queue = self.manager.Queue()
        self.peak_process = mp.Process(target = peak_finder,
                                        args = (self.sample_queue,
                                                self.peak_queue,
                                                self.dic['starttime'],
                                                debug))
        self.peak_log_process = mp.Process(target = peak_log,
                                            args = (peak_log_file,
                                                    self.peak_queue))

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
    

def peak_log(log_file,que):
    """Creates log file for detected peaks/troughs

    Parameters
    ----------
    log_file : str
        Name for log file output
    que : multiprocessing.manager.Queue()
        To receive detected peaks/troughs from peak_finder() function
    """

    f = open(log_file,'a+')
    f.write('time_detected,time_received,amplitude\n')
    f.flush()
    
    while True:
        i = que.get()
        if i == 'kill': break
        else: 
            f.write('%s,%s,%s\n' % (i[0], i[1], str(i[2]).strip('[]')))
            f.flush()
    
    f.close()
    

def peak_finder(que_in,que_log,pf_start,debug=False):
    """Detects peaks in real time from BioPac MP150 data

    Parameters
    ----------
    que_in : multiprocessing.manager.Queue()
        Queue for receiving data from the BioPac MP150
    que_log : multiprocessing.manager.Queue()
        Queue to send detected peak information to peak_log() function
    pf_start : int
        Time at which data sampling began
    debug : bool
        Whether to print debugging statements

    Returns
    -------
    Imitates 'p' and 't' keypress for each detected peak and trough
    """

    sig = np.empty(0)
    last_found = np.array([[ 0,0,0],
                           [ 1,0,0],
                           [-1,0,0]]*3)
    
    P_KEY, T_KEY = 0x50, 0x54
    
    print "Ready to find peaks..."
    
    while True:
        i = que_in.get()
        if i == 'kill': break

        sig = np.append(sig,i[1])
        peak, trough = peak_or_trough(sig,last_found)
        
        pt, tt = gen_thresh(last_found,time=True)
        rr_thresh = np.mean(np.abs(pt-tt))/2.
                
        if (peak or trough) and (i[0]-last_found[-1,1] > rr_thresh):
            sig = np.empty(0)
            
            que_log.put((int((time.time()-dic['starttime'])*1000),i[0],i[1]))
            
            last_found = np.vstack((last_found,
                                    [peak,i[0],i[1]]))
            
            keypress.PressKey(P_KEY if peak else T_KEY)
            keypress.ReleaseKey(P_KEY if peak else T_KEY)
                
            if debug: print "Found %s" % ("peak" if peak else "trough")
            
        elif (peak or trough) and (i[0]-last_found[-1,1] < rr_thresh):
            sig = np.empty(0)
    
    que_log.put('kill')


def peak_or_trough(signal, last_found):
    """Helper function for peak_finder()

    Determines in any peaks or troughs were detected in signal that 
    meet height threshold

    Parameters
    ----------
    signal : array
        Physio data since last peak/trough
    last_found : array (n x 3)
        Class, time, and height of previously detected peaks/troughs
    """

    peaks = scipy.signal.argrelmax(signal,order=10)[0] #HC
    troughs = scipy.signal.argrelmin(signal,order=10)[0] #HC
        
    peak_height, trough_height = gen_height_thresh(last_found)
    thresh = np.mean(np.abs(peak_height-trough_height))/2.
    
    if peaks.size and (last_found[-1,0] != 1):
        if np.abs(signal[peaks[-1]]-trough_height[-1]) > thresh:
            return True, False
    if troughs.size and (last_found[-1,0] != 0):
        if np.abs(signal[troughs[-1]]-peak_height[-1]) > thresh:
            return False, True
    return False, False
    

def gen_thresh(last_found,time=False):
    """Helper function for peak_finder() and peak_or_trough()

    Determines relevant threshold for peak/trough detection based on last
    three previously detected peaks/troughs

    Parameters
    ----------
    last_found : array (n x 3)
        Class, time, and height of previously detected peaks/troughs
    time : bool
        Whether to generate time threshold (default: False, generates height)
    """
    
    col = 1 if time else 2

    peak_height = last_found[last_found[:,0]==1,col][-3:]
    trough_height = last_found[last_found[:,0]==0,col][-3:]
    
    if peak_height.size > trough_height.size:
        peak_height = peak_height[peak_height.size-trough_height.size:]
    elif trough_height.size > peak_height.size:
        trough_height = trough_height[trough_height.size-peak_height.size:]
    
    return peak_height, trough_height


if __name__ == '__main__':
    r = RTP(logfile = time.ctime().split(' ')[3].replace(':','_'),
            channels = [1],
            debug = True)

    r.start_peak_finding()
    time.sleep(600)
    r.stop_peak_finding()

    print "Done!"