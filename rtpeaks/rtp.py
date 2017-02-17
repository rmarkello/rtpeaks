#!/usr/bin/env python

from __future__ import print_function, division, absolute_import
import multiprocessing as mp
import numpy as np
from scipy.signal import argrelmax, argrelmin
import rtpeaks.keypress as keypress
from rtpeaks.libmpdev import MP150


class RTP(MP150):
    """
    Class for use in real-time detection of peaks and troughs

    Inherits from MP150 class (see: libmpdev.py). If you only want to record
    BioPac MP150 data, probably best to use that class instead.

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

    def __init__(self, logfile='default', samplerate=200,
                 channels=[1,2], debug=False):
        """
        Initializes class

        Parameters
        ----------
        logfile : str
            Name of logfile (prepended to "_MP150_data.csv")
        samplerate : float
            Samplerate to record from BioPac
        channels : int or list
            Channels to record from BioPac
        debug : bool
            Whether to run in debug mode. Will print statements rather than
            imitating keypress
        """

        # check inputs
        if not isinstance(samplerate,(float,int)):
            raise TypeError("Samplerate must be one of [int, float]")
        if not isinstance(channels,(list, np.ndarray)):
            if isinstance(channels,(int)): channels = [channels]
            else: raise TypeError("Channels must be one of [list, array, int]")

        super(RTP,self).__init__(logfile, samplerate, channels)

        self.dic['baseline'] = False
        self.dic['samplerate'] = samplerate
        self.dic['debug'] = debug
        self.dic['log'] = logfile

        self.peak_queue = self.manager.Queue()
        self.peak_process = mp.Process(target=rtp_finder,
                                       args=(self.dic,
                                             self.sample_queue,
                                             self.peak_queue))
        self.peak_process.daemon = True
        self.peak_process.start()

    def start_peak_finding(self, channel=None, samplerate=None, run=None):
        """
        Begin peak finding process and start logging data

        Parameters
        ----------
        channel : int
            Channel for peak finding
        samplerate : float
            Samplerate at which `channel` should be searched for peaks/troughs.
            Will appropriately downsample data, if desired.
        run : str
            To differentiate name of output file
        """

        if not self.dic['baseline']:
            print("RTP hasn't been baselined! Proceeding anyways, but note"+
                  "that peak finding quality will likely be erratic.")

        # set peak finding channel
        if isinstance(channel, (list, np.ndarray)): channel = channel[0]
        elif isinstance(channel, (int)): channel = channel
        else: channel = self.dic['channels'][0]

        # set peak finding sample rate
        if isinstance(samplerate, (int,float)):
            self.dic['samplerate'] = samplerate

        # turn off peak finding if it's currently happening
        if self.dic['pipe'] is not None: self.stop_peak_finding()

        # start recording and turn peak finding back on
        self.start_recording(run=run)
        self.dic['pipe'] = np.where(self.dic['channels'] == channel)[0][0]

        # start peak logging process
        fname = "{}_MP150_peaks.csv".format(self.logfile)
        if run is not None:
            fname = "{}-run{}_MP150_peaks.csv".format(self.logfile, str(run))

        self.peak_log_process = mp.Process(target=rtp_log,
                                           args=(fname,self.peak_queue))
        self.peak_log_process.daemon = True
        self.peak_log_process.start()

    def stop_peak_finding(self):
        """
        Stops peak finding process (and stops data recording)
        """

        # turn off pipe and stop recording
        self.dic['pipe'] = None
        self.stop_recording()

        # tell peak finder to not force peak after next start_peak_finding
        self.sample_queue.put('break')

        # ensure peak logging process quits successfully
        self.peak_queue.put('kill')
        self.peak_log_process.join()

    def start_baseline(self, channel=None):
        """
        Creates a baseline data file

        Baseline data file will be used by rtp_finder to generate starter
        thresholds for peak detection. The longer this is run the better the
        estimates will be for actual peak detection.

        Parameters
        ----------
        channel : int
            Channel that peak finding will occur on
        """

        self.start_recording(run='_baseline')
        self.base_chan = np.where(self.dic['channels'] == channel)[0][0]

    def stop_baseline(self):
        """
        Stops recording baseline.

        This causes rtp_finder() to progress and process baseline data file to
        "seed" peak detection.
        """

        self.stop_recording()
        self.dic['baseline'] = True
        self.sample_queue.put([self.timestamp(),self.base_chan])

    def close(self):
        """
        Stops peak finding (if ongoing) and cleanly disconnects from BioPac
        """

        self.stop_peak_finding()
        super(RTP,self).close()


def rtp_log(log,que):
    """
    Creates log file for detected peaks & troughs

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


def get_baseline(log, channel_loc, samplerate):
    """
    Gets baseline estimates of physiological waveform

    Will only be run if rtp.start_baseline()/stop_baseline() has been used;
    this function will import the baseline data and attempt to do a cursory
    peak finding on it. The data from the peak finding will be used to seed
    initial parameters of real-time detection, including vanishing thresholds
    and lookback values.

    Parameters
    ----------
    log : str
        RTP.logfile
    channel_loc : int
        dic['pipe']
    samplerate : int
        dic['samplerate']

    Returns
    -------
    array : (n x 3), class, time, and height of detected peaks & troughs
    """

    try:
        from peakdet import PeakFinder
    except ImportError:
        print("Can't load peakdet; ignoring baseline data.")
        return

    data = np.loadtxt("{0}-run_baseline_MP150_data.csv".format(log),
                      skiprows=1,
                      delimiter=',',
                      usecols=[0,channel_loc+1])
    fs = 1000./np.mean(np.diff(data[:,0]))  # sampling rate of MP150

    pf = PeakFinder(data[:,1],fs=fs)
    if fs != 1000: pf.interpolate(np.floor(1000/fs))  # interpolate to 1000 Hz
    pf.get_peaks(thresh=0.2)

    size = np.min([pf.troughinds.size,pf.peakinds.size])
    p = np.floor(pf.peakinds[-size:]/np.floor(1000/fs)).astype('int64')
    t = np.floor(pf.troughinds[-size:]/np.floor(1000/fs)).astype('int64')

    pi = np.hstack((np.ones([p.size,1]),
                    np.atleast_2d(data[p,0]).T,
                    np.atleast_2d(data[p,channel_loc+1]).T))
    ti = np.hstack((np.zeros([t.size,1]),
                    np.atleast_2d(data[t,0]).T,
                    np.atleast_2d(data[t,channel_loc+1]).T))

    out = np.vstack((pi,ti))
    out = out[np.argsort(out[:,1])]

    return out


def rtp_finder(dic,pipe_que,log_que):
    """
    Detects peaks/troughs in real time from BioPac MP150 data

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

    # this will block until an item is available (i.e., dic['pipe'] is set)
    sig = np.atleast_2d(np.array(pipe_que.get()))
    sig_temp = sig.copy()

    last_found = np.array([[ 0,0,0],[ 1,0,0],[-1,0,0]]*2)

    if dic['baseline']:
        out = get_baseline(dic['log'],
                           sig[-1,1],
                           dic['samplerate'])
        last_found = out.copy()

        sig = np.atleast_2d(np.array(pipe_que.get()))
        sig_temp = sig.copy()

    st = 1000./dic['samplerate']

    while True:
        i = pipe_que.get()
        if i == 'kill': break
        if i == 'break': pass  # somehow make this ensure forced peaks real
        if not (i[0] >= sig_temp[-1,0] + st): continue

        sig, sig_temp = np.vstack((sig,i)), np.vstack((sig_temp,i))
        peak, trough = peak_or_trough(sig_temp, last_found)

        # too long since a detected peak/trough!
        avgrate, stdrate = gen_thresh(last_found,time=True)
        lasttime = sig_temp[-1,0]-last_found[-1,1]
        if not (peak or trough) and (lasttime > avgrate+stdrate):
            if dic['debug']: print("Forcing peak due to time.")
            if not dic['debug']: keypress.PressKey(0x50)  # always force a peak

            # reset everything
            sig_temp = np.atleast_2d(sig[-1])
            if dic['baseline']: last_found = out.copy()
            else: last_found = np.array([[ 0,sig_temp[0,0],0],
                                         [ 1,sig_temp[0,0],0],
                                         [-1,sig_temp[0,0],0]]*2)

            log_que.put(i + [2])

        # a real peak or trough
        elif peak or trough:
            # press the required key (whatever it is)
            if dic['debug']: print("Found {}".format(['trough','peak'][peak]))
            if not dic['debug']: keypress.PressKey(0x50 if peak else 0x54)

            # reset sig_temp and add to last_found
            sig_temp = np.atleast_2d(sig[-1])
            last_found = np.vstack((last_found,
                                    [int(peak)] + i))

            log_que.put(i + [int(peak)])


def peak_or_trough(signal, last_found):
    """
    Helper function for rtp_finder()

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
    bool, bool : peak detected, trough detected
    """

    peaks = argrelmax(signal[:,1],order=2)[0]
    troughs = argrelmin(signal[:,1],order=2)[0]

    # generate thresholds
    h_thresh, h_ci = gen_thresh(last_found)
    t_thresh, t_ci = gen_thresh(last_found,time=True)

    # only accept CI if at least 20 samples
    if last_found.shape[0] < 20: h_ci, t_ci = h_thresh/2, t_thresh/2

    # how many samples between detections
    fs = np.mean(np.diff(signal[:,0]))
    avgrate = int(np.floor(t_thresh/fs - t_ci/fs))
    if avgrate < 0: avgrate = 1

    if peaks.size and (last_found[-1,0] != 1):
        p = peaks[-1]
        # ensure peak is higher than previous `avgrate` datapoints
        max_ = np.all(signal[p,1] >= signal[p-avgrate:p,1])
        sh = signal[p,1]-last_found[-1,2]
        rh = signal[p,0]-last_found[-1,1]

        if sh > h_thresh-h_ci and rh > t_thresh-t_ci and max_:
            return True, False

    if troughs.size and (last_found[-1,0] != 0):
        t = troughs[-1]
        # ensure trough is lower than previous `avgrate` datapoints
        min_ = np.all(signal[t,1] <= signal[t-avgrate:t,1])
        sh = signal[t,1]-last_found[-1,2]
        rh = signal[t,0]-last_found[-1,1]

        if sh < h_thresh+h_ci and rh > t_thresh-t_ci and min_:
            return False, True

    return False, False


def gen_thresh(last_found,time=False):
    """
    Helper function for peak_or_trough()

    Determines relevant threshold for peak/trough detection based on previously
    detected peaks/troughs

    Parameters
    ----------
    last_found : array (n x 3)
        Class, time, and height of previously detected peaks/troughs
    time : bool
        Whether to generate time threshold (default: False, generates height)

    Returns
    -------
    float : threshold
    """

    col = 1 if time else 2

    peaks = last_found[last_found[:,0]==1,col]
    troughs = last_found[last_found[:,0]==0,col]

    size = np.min([peaks.size,troughs.size])
    dist = peaks[-size:]-troughs[-size:]
    weights = np.power(range(1,size+1),5)  # exponential weighting

    thresh = np.average(dist, weights=weights)
    variance = np.average((dist-thresh)**2, weights=weights)
    variance = (variance*dist.size)/(dist.size-1)  # unbiased variance

    if not time: return thresh, np.sqrt(variance)*2.5
    else: return np.abs(thresh), np.sqrt(variance)*2.5
