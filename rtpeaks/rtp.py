#!/usr/bin/env python

from __future__ import print_function, division, absolute_import
import time
import multiprocessing as mp
import numpy as np
import scipy.signal
from scipy.interpolate import InterpolatedUnivariateSpline
import rtpeaks.keypress as keypress
from rtpeaks.libmpdev import MP150

class RTP(MP150):
    """Class for use in real-time detection of peaks and troughs

    Inherits from MP150 class (see: libmpdev.py). If you only want to record
    BioPac MP150 data, probably best to use that class instead

    Methods
    -------
    start_baseline(), stop_baseline()
        Runs a baseline measurement and generates some approximated thresholds
        for use in future peak detection
    start_peak_finding(), stop_peak_finding()
        Detects peaks/troughs in specified physiological data

    Usage
    -----
    Instantiate class and call `start_peak_finding()` method. Upon peak/trough 
    detection, class will simulate `p` or `t` keypress. After calling 
    `stop_peak_finding()` must call `close()` method to disconnect from BioPac.

    Notes
    -----
    Should _NOT_ be used interactively.
    """

    def __init__(self, logfile='default', samplerate=500, channels=[1,2], debug=False):
        """You damn well know what __init__ does"""

        if isinstance(samplerate,(np.ndarray,list)): 
            maxsr, samplerate = max(samplerate), list(samplerate)
        elif isinstance(samplerate, (float,int)): 
            maxsr, samplerate = samplerate, [samplerate]*len(channels)
        else: raise TypeError("Check samplerate input for correct type.")

        if len(samplerate) != len(channels):
            raise ValueError("Samplerate must be length 1 or equal to len(channels).")

        super(RTP,self).__init__(logfile, maxsr, channels)

        self.dic['baseline'] = False
        self.dic['samplerate'] = samplerate
        self.dic['debug'] = debug

        self.peak_queue = self.manager.Queue()
        self.peak_process = mp.Process(target = rtp_finder,
                                       args   = (self.dic,
                                                 self.sample_queue,
                                                 self.peak_queue))
        self.peak_process.daemon = True
        self.peak_process.start()
        

    def start_peak_finding(self, channel=[], run=None):
        """Begin peak finding process and start logging data"""
        
        # start recording and turn on pipe
        if not channel: channel = self.dic['channels'][0]
        if isinstance(channel, (list, np.ndarray)): channel = channel[0] 

        if self.dic['pipe'] is not None: self.stop_peak_finding()

        self.start_recording(run=run)
        self.dic['pipe'] = np.where(self.dic['channels'] == channel)[0][0]

        # start peak logging process
        if run: fname = "{}-run{}_MP150_peaks.csv".format(self.logfile, str(run))
        else: fname = "{}_MP150_peaks.csv".format(self.logfile)

        self.peak_log_process = mp.Process(target = rtp_log,
                                           args   = (fname,
                                                     self.peak_queue))
        self.peak_log_process.daemon = True
        self.peak_log_process.start()


    def stop_peak_finding(self):
        """Stop peak finding process"""

        # turn off pipe and stop recording
        self.dic['pipe'] = None
        self.stop_recording()
                
        # ensure peak logging process quits successfully
        self.peak_queue.put('kill')
        self.peak_log_process.join()


    def start_baseline(self):
        """Creates a baseline data file to generate "guess" thresholds"""
        self.start_recording(run='baseline')


    def stop_baseline(self):
        """Reads in baseline data file and generates thresholds"""
        # or, it will once I've set this up
        # for now, baseline does nothing
        self.stop_recording()
        self.dic['baseline'] = True


    def close(self):
        self.stop_peak_finding()
        super(RTP,self).close()



def rtp_log(log,que):
    """Creates log file for detected peaks/troughs

    Parameters
    ----------
    log : str
        Name for log file output
    que : multiprocessing.manager.Queue()
        To receive detected peaks/troughs from peak_finder() function
    """

    f = open(log,'a+')
    f.write('time,amplitude,peak\n')
    f.flush()
    
    while True:
        i = que.get()
        if i == 'kill': break
        f.write("{0}\n".format(','.join(str(y) for y in list(i))))
        f.flush()
    
    f.close()


def rtp_finder(dic,pipe_que,log_que):
    """Detects peaks/troughs in real time from BioPac MP150 data

    Parameters
    ----------
    dic : multiprocessing.manager.Dict()

        Required input
        --------------
        dic['samplerate'] : list, samplerates for each channel
        dic['connected'] : bool, continue sampling or not
        dic['pipe'] : int, which channel is being piped
        dic['debug'] : bool, whether to print debug statements

        Optional input
        --------------
        dic['baseline'] : bool, whether a baseline session was run

    pipe_que : multiprocessing.manager.Queue()
        Queue for receiving data from the BioPac MP150
    log_que : multiprocessing.manager.Queue()
        Queue to send detected peak information to peak_log() function

    Returns
    -------
    Imitates `p` and `t` keypress for each detected peak and trough
    """

    st = 1000./dic['samplerate'][dic['pipe']]

    # this will block until an item is available (i.e., dic['pipe'] is set)
    sig = np.atleast_2d(np.array(pipe_que.get()))
    sig_temp = sig.copy()
    last_found = np.array([ [ 0,0,0],
                            [ 1,0,0],
                            [-1,0,0] ]*3)

    if dic['baseline']: pass #get baseline estimates here

    while dic['connected']:
        i = pipe_que.get()
        if i == 'kill': break
        
        if not (i[0] >= sig_temp[-1,0] + st): continue 

        sig, sig_temp = np.vstack((sig,i)), np.vstack((sig_temp,i))
        peak, trough = peak_or_trough(sig_temp, last_found)

        # too long since a detected peak/trough!
        if not (peak or trough) and (sig_temp[-1,0]-last_found[-1,1]) > 7000.: #HC
            # press the required key (whatever it is)
            last = last_found[-1,0]
            if dic['debug']: print("Forcing peak due to time.")
            if not dic['debug']:
                keypress.PressKey(0x54 if last else 0x50)
                keypress.ReleaseKey(0x54 if last else 0x50)

            # reset everything
            sig_temp = np.atleast_2d(sig[-1])
            last_found = np.array([ [ 0, sig_temp[0,0], 0],
                                    [ 1, sig_temp[0,0], 0],
                                    [-1, sig_temp[0,0], 0] ]*3)

            # tell the log file that this was forced (i.e, [x, x, x, 2])
            log_que.put(i + [2])

        # a real peak or trough
        elif (peak or trough):
            # press the required key (whatever it is)
            if dic['debug']: print("Found {}".format("peak" if peak else "trough"))
            if not dic['debug']:
                keypress.PressKey(0x50 if peak else 0x54)
                keypress.ReleaseKey(0x50 if peak else 0x54)

            # reset sig_temp and add to last_found
            sig_temp = np.atleast_2d(sig[-1])
            last_found = np.vstack( (last_found,
                                     [peak] + i) )

            # log it
            log_que.put(i + [peak])


def peak_or_trough(signal, last_found):
    """Helper function for peak_finder()

    Determines if any peaks or troughs are detected in `signal` that 
    meet threshold generated via `gen_thresh()`

    Parameters
    ----------
    signal : array (n x 2)
        Time, physio data since last detection
    last_found : array (n x 3)
        Class, time, and height of previously detected peaks/troughs

    Returns
    -------
    bool * 2 : peak, trough
    """

    # let's INTERPOLATE!
    peaks = scipy.signal.argrelmax(signal[:,1],order=2)[0]
    troughs = scipy.signal.argrelmin(signal[:,1],order=2)[0]
    
    # time since last detection
    last_det = signal[-1,0] - last_found[-1,1] 

    h_thresh = gen_thresh(last_found)/3             #HC
    t_thresh = gen_thresh(last_found,time=True)/3   #HC

    # how can I functionize this?
    if peaks.size and (last_found[-1,0] != 1):
        p = peaks[-1]
        max_ = np.all(signal[p,1] >= signal[p-30:p,1]) #HC
        sh = signal[p,1]-last_found[-1,2]
        rh = signal[p,0]-last_found[-1,1]

        if sh > h_thresh and rh > t_thresh and max_:
            return 1, 0

    if troughs.size and (last_found[-1,0] != 0):
        t = troughs[-1]
        min_ = np.all(signal[t,1] <= signal[t-30:t,1]) #HC
        sh = signal[t,1]-last_found[-1,2]
        rh = signal[t,0]-last_found[-1,1]
        
        if sh < h_thresh and rh > t_thresh and min_:
            return 0, 1

    return 0, 0


def gen_thresh(last_found,time=False):
    """Helper function for peak_or_trough()

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
    array * 2
        First array is heights of previous three peaks
        Second array is heights of previous three troughs
    """
    
    col = 1 if time else 2

    peak_height = last_found[last_found[:,0]==1,col][-3:]
    trough_height = last_found[last_found[:,0]==0,col][-3:]
    
    thresh = np.mean(peak_height-trough_height)

    return thresh