#!/usr/bin/env python

import os
import time
import multiprocessing as mp
import numpy as np
import scipy.signal
import matplotlib.pyplot as plt
import keypress
from libmpdev import MP150


class RTP(MP150):
    """
    Class for use in real-time detection of peaks and troughs.

    Inherits from MP150 class (see: libmpdev.py). If you only want to record
    BioPac MP150 data, use that class instead!

    Methods
    -------
    start_peak_finding()
        Begin detection and recording of peaks; will begin recording sampled 
        data, if not already
    stop_peak_finding()
        Stop detection of peaks

    Usage
    -----
    Instantiate class and call start_peak_finding() method. Upon peak/trough 
    detection, class will simulate 'p' or 't' keypress. 

    Notes
    -----
    Should NOT be used interactively.
    """
    
    def __init__(self, logfile='default', samplerate=300, channels=[1,2,3], debug=False):

        MP150.__init__(self, logfile, samplerate, channels)

        while not self.dic['connected']: pass

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
        """Begin peak finding process and start logging data, if necessary"""

        self.peak_process.start()
        self.peak_log_process.start()

        if not self.dic['record']: self.start_recording()
        self._start_pipe()


    def stop_peak_finding(self):
        """Stop peak finding process"""

        self._stop_pipe()
        # make sure peak logging finishes before closing the parent process...
        while not self.peak_queue.empty(): pass


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
    f.write('time_detected,time_received,amplitude,peak\n')
    f.flush()
    
    while True:
        i = que.get()
        if i == 'kill': break
        else: 
            f.write('%s,%s,%s,%s\n' % (i[0], i[1], str(i[2]).strip('[]'),i[3]))
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
            
            que_log.put((int((time.time()-pf_start)*1000),i[0],i[1],int(peak)))
            
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

    Determines if any peaks or troughs were detected in signal that 
    meet height threshold

    Parameters
    ----------
    signal : array
        Physio data since last peak/trough
    
    last_found : array (n x 3)
        Class, time, and height of previously detected peaks/troughs

    Returns
    -------
    bool, bool
        First boolean is whether a peak was detected, second is whether a 
        trough was detected. Maximum one True
    """

    peaks = scipy.signal.argrelmax(signal,order=10)[0]
    troughs = scipy.signal.argrelmin(signal,order=10)[0]
        
    peak_height, trough_height = gen_thresh(last_found)
    thresh = np.mean(np.abs(peak_height-trough_height))/3. #HC
    
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

    Returns
    -------
    array, array
        First array is heights of previous three peaks, second heights of
        previous three troughs
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
    time.sleep(60)
    r.stop_peak_finding()
    r.close()

    print "Done!"