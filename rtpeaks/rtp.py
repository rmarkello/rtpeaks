#!/usr/bin/env python

from __future__ import print_function, division, absolute_import
import numpy as np
import rtpeaks.keypress as keypress
from rtpeaks.mpdev import MP150
import rtpeaks.process as rp


class RTP(MP150):
    """
    Class for use in real-time detection of peaks and troughs

    Inherits from MP150 class (see: `libmpdev.py`). If you only want to record
    BioPac MP150 data, probably best to use that class instead.

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
        imitating keypresses

    Methods
    -------
    start_baseline(), stop_baseline()
        Runs a baseline measurement -- highly recommended!!
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
                 channels=[1, 2], debug=False):
        # check inputs
        if not isinstance(samplerate, (float, int)):
            raise TypeError('Samplerate must be one of [int, float]'')
        if not isinstance(channels, (list, np.ndarray)):
            if isinstance(channels, (int)): channels = [channels]
            else: raise TypeError('Channels must be one of [list, array, int]')

        super(RTP, self).__init__(logfile, samplerate, channels)

        self.dic['baseline'] = False
        self.dic['samplerate'] = samplerate
        self.dic['debug'] = debug
        self.dic['log'] = logfile
        self.peak_log_process = None

        self.peak_queue = self.manager.Queue()
        self.peak_process = rp.Process(name='rtp_finder',
                                       target=rtp_finder,
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
            Channel for peak finding; must be one of channels set at
            instantiation.
        samplerate : float
            Samplerate at which `channel` should be searched for peaks/troughs.
            Will appropriately downsample data, if desired.
        run : str
            To differentiate name of output file
        """

        if not self.dic['baseline']:
            print('RTP hasn\'t been baselined! Proceeding anyways, but note' +
                  'that peak finding quality will likely be erratic.')

        # set peak finding channel
        if isinstance(channel, (list, np.ndarray)): channel = channel[0]
        elif isinstance(channel, int): pass
        else: channel = self.dic['channels'][0]

        # set peak finding sample rate
        if isinstance(samplerate, (int, float)):
            self.dic['samplerate'] = samplerate

        # turn off peak finding if it's currently happening
        if self.dic['pipe'] is not None: self.stop_peak_finding()

        # start recording and turn peak finding back on
        self.start_recording(run=run)
        self.dic['pipe'] = np.where(self.dic['channels'] == channel)[0][0]

        # start peak logging process
        if run is not None:
            fname = '{}-run{}_MP150_peaks.csv'.format(self.logfile, str(run))
        else:
            fname = '{}_MP150_peaks.csv'.format(self.logfile)

        self.peak_log_process = rp.Process(name='rtp_log',
                                           target=rtp_log,
                                           args=(fname, self.peak_queue))
        self.peak_log_process.daemon = True
        self.peak_log_process.start()

    def stop_peak_finding(self):
        """
        Stops peak finding process (and stops data recording)
        """

        # turn off pipe and stop recording
        self.dic['pipe'] = None
        self.stop_recording()

        # ensure peak logging process quits successfully
        if self.peak_log_process is not None:
            self.peak_queue.put('kill')
            self.peak_log_process.join()
            self.peak_log_process = None

    def start_baseline(self, channel, samplerate):
        """
        Creates a baseline data file

        Baseline data file will be used by rtp_finder to generate starter
        thresholds for peak detection. The longer this is run the better the
        estimates will be for actual peak detection.

        Parameters
        ----------
        channel : int
            Channel that peak finding will occur on
        samplerate : float
            Samplerate at which to search data for peaks/troughs
        """

        self.start_recording(run='_baseline')
        self.base_chan = np.where(self.dic['channels'] == channel)[0][0]
        self.base_rate = samplerate

    def stop_baseline(self):
        """
        Stops recording baseline.

        This causes rtp_finder() to progress and process baseline data file to
        "seed" peak detection.
        """

        self.stop_recording()
        self.dic['baseline'] = True
        self.sample_queue.put([self.base_chan, self.base_rate])

    def close(self):
        """
        Stops peak finding (if ongoing) and cleanly disconnects from BioPac
        """

        self.stop_peak_finding()
        self.sample_queue.put('kill')
        self.peak_process.join()

        super(RTP, self).close()


def rtp_log(log, que):
    """
    Creates log file for detected peaks & troughs

    Parameters
    ----------
    log : str
        Name for log file output
    que : multiprocessing.manager.Queue
        To receive detected peaks/troughs from peak_finder() function
    """

    f = open(log, 'a+')
    f.write('time,amplitude,peak\n')
    f.flush()

    while True:
        i = que.get()
        if isinstance(i, str) and i == 'kill': break
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
        Channel that peak finding is supposed to occur on
    samplerate : int
        dic['samplerate']

    Returns
    -------
    (N x 3) np.ndarray
        Class, time, and height of detected peaks & troughs
    """

    try:
        from peakdet import PeakFinder
    except ImportError:
        print('Can\'t load peakdet; ignoring baseline data.'')
        return

    data = np.loadtxt('{0}-run_baseline_MP150_data.csv'.format(log),
                      skiprows=1,
                      delimiter=',',
                      usecols=[0, channel_loc + 1])
    fs = 1000. / np.mean(np.diff(data[:, 0]))  # sampling rate of MP150

    # downsample data if necessary
    if samplerate < fs:
        indata = data[np.arange(0, data.shape[0], 1000 / samplerate,
                                dtype='int64')]
    else:
        indata = data.copy()

    pf = PeakFinder(indata[:, 1], fs=samplerate)
    if pf.fs != 1000: pf.interpolate(np.floor(1000 / pf.fs))
    pf.get_peaks(thresh=0.2)

    size = np.min([pf.troughinds.size, pf.peakinds.size])
    p = np.floor(pf.peakinds[-size:] / np.floor(1000 / fs)).astype('int64')
    t = np.floor(pf.troughinds[-size:] / np.floor(1000 / fs)).astype('int64')

    pi = np.column_stack((np.ones([p.size, 1]), data[p, 0], data[p, 1]))
    ti = np.column_stack((np.zeros([t.size, 1]), data[t, 0], data[t, 1]))

    out = np.vstack((pi, ti))
    out = out[np.argsort(out[:, 1])]

    return out


def rtp_finder(dic, sample_queue, peak_queue):
    """
    Detects peaks/troughs in real time from BioPac MP150 data

    Parameters
    ----------
    dic : multiprocessing.manager.Dict
        dic['samplerate'] : list, samplerates for each channel
        dic['debug'] : bool, whether to print debug statements
        dic['baseline'] : bool, whether a baseline session was run
        dic['log'] : str, name of logfile (required if dic['baseline'])
    sample_queue : multiprocessing.manager.Queue
        Queue for receiving data from the BioPac MP150
    peak_queue : multiprocessing.manager.Queue
        Queue to send detected peak information to peak_log() function

    Returns
    -------
    Imitates `p` and `t` keypress for each detected peak and trough
    """

    # this will block until an item is available in sample_queue
    # i.e., dic['pipe'] is set
    # or, if we've gotten baseline, this will be that!
    sig = sample_queue.get()
    if isinstance(sig, str) and sig == 'kill': return
    else: sig = np.atleast_2d(np.array(sig))
    last_found = np.array([[0, 0, 0],
                           [1, 0, 0],
                           [-1, 0, 0]] * 2)

    if dic['baseline']:
        out = get_baseline(dic['log'], int(sig[-1, 0]), int(sig[-1, 1]))
        last_found = out.copy()
        t_thresh = gen_thresh(last_found[:-1])[0, 0]

        # now wait for the real signal!
        sig = sample_queue.get()
        if isinstance(sig, str) and sig == 'kill': return
        else: sig = np.atleast_2d(np.array(sig))
        last_found[-1, 1] = sig[0, 0] - t_thresh

    thresh = gen_thresh(last_found[:-1])  # generate thresholds
    st = np.ceil(1000. / dic['samplerate'])  # sampling time

    while True:
        i = sample_queue.get()
        if isinstance(i, str) and i == 'kill': return
        if i[0] < sig[-1, 0] + st: continue

        sig = np.vstack((sig, i))
        peak, trough = peak_or_trough(sig, last_found, thresh, st)

        if peak is not None or trough is not None:
            # get index of extrema
            ex, l = peak or trough, int(bool(peak))

            # add to last_found and reload thresholds
            last_found = np.vstack((last_found, np.append([l], sig[ex])))
            # if we didn't baseline and have gotten some peaks/troughs
            # fix the last_found array so as not to have starter datapoints
            if (not dic['baseline'] and len(last_found) > 7 and
                    np.any(last_found[:, 1] == 0)):
                last_found = last_found[np.where(last_found[:, 1] != 0)[0]]
                last_found = np.vstack((last_found, last_found))

            # regenerate thresholds
            thresh = gen_thresh(last_found[:-1])

            # if extrema was detected "immediately" (i.e., within 2 datapoints
            # of real-time) then log detection.
            if ex == len(sig) - 2:
                if dic['debug']:
                    print('Found {}'.format('peak' if l else 'trough'))
                    peak_queue.put(np.append(sig[-1], [l, dic['newesttime']]))
                else:
                    keypress.PressKey(0x50 if l else 0x54)
                    peak_queue.put(np.append(sig[-1], [l]))

            # reset sig
            sig = np.atleast_2d(sig[-1])

        # reset to baseline if it's been more than 10 seconds
        elif dic['baseline'] and (sig[-1, 0] - last_found[-1, 1]) > 10000:
            last_found = out.copy()
            t_thresh = gen_thresh(last_found[:-1])[0, 0]

            sig = np.atleast_2d(sig[-1])
            last_found[-1, 1] = sig[0, 0] - t_thresh

            thresh = gen_thresh(last_found[:-1])


def peak_or_trough(signal, last_found, thresh, fs):
    """
    Helper function for rtp_finder()

    Determines if any peaks or troughs are detected in `signal` that
    meet threshold generated via `gen_thresh()`

    Parameters
    ----------
    signal : (N x 2) array_like
        Time, physio data since last detection
    last_found : (N x 3) array_like
        Class, time, and height of previously detected peaks/troughs
    thresholds : (2 x 2) array_like
        Average (c1) and std (c2) thresholds for time (r1) and height (r2)
    fs : float
        Sampling rate

    Returns
    -------
    bool
        Whether a peak was detected
    bool
        Whether a trough was detected
    """

    # if time since last det > upper bound of normal time interval
    # shrink height threshold by relative factor
    divide = ((signal[-1, 0] - last_found[-1, 1]) /
              (thresh[0, 0] + thresh[0, 1]))
    divide = divide if divide > 1 else 1

    tdiff = thresh[0, 0] - thresh[0, 1]
    hdiff = (thresh[1, 0] - thresh[1, 1]) / divide

    # approximate # of samples between detections
    avgrate = int(np.floor(tdiff / fs))
    if avgrate < 0: avgrate = 5  # if negative, let's just look 5 back

    if last_found[-1, 0] != 1:  # if we're looking for a peak
        peaks = get_extrema(signal[:, 1])
        if len(peaks) > 0:
            p = peaks[-1]
            # ensure peak is higher than previous `avgrate` datapoints
            max_ = np.all(signal[p, 1] >= signal[p - avgrate:p, 1])
            sh = signal[p, 1] - last_found[-1, 2]
            rh = signal[p, 0] - last_found[-1, 1]

            if sh > hdiff and rh > tdiff and max_:
                return p, None

    if last_found[-1, 0] != 0:  # if we're looking for a trough
        troughs = get_extrema(signal[:, 1], peaks=False)
        if len(troughs) > 0:
            t = troughs[-1]
            # ensure trough is lower than previous `avgrate` datapoints
            min_ = np.all(signal[t, 1] <= signal[t - avgrate:t, 1])
            sh = signal[t, 1] - last_found[-1, 2]
            rh = signal[t, 0] - last_found[-1, 1]

            if sh < -hdiff and rh > tdiff and min_:
                return None, t

    return None, None


def gen_thresh(last_found):
    """
    Helper function for peak_or_trough()

    Determines relevant threshold for peak/trough detection based on previously
    detected peaks/troughs

    Parameters
    ----------
    last_found : (N x 3) array_like
        Class, time, and height of previously detected peaks/troughs

    Returns
    -------
    (2 x 2) np.ndarray
        [[avg time, std time], [avg height, std height]]
    """

    output = np.zeros((2, 2))
    for col in [1, 2]:
        peaks = last_found[last_found[:, 0] == 1, col]
        troughs = last_found[last_found[:, 0] == 0, col]

        if peaks.size != troughs.size:
            size = np.min([peaks.size, troughs.size])
            dist = peaks[-size:] - troughs[-size:]
        else:
            dist = peaks - troughs

        # get rid of gross outliers (likely caused by pauses in peak finding)
        inds = np.where(np.logical_and(dist <= dist.mean() + dist.std() * 3,
                                       dist >= dist.mean() - dist.std() * 3))
        dist = dist[inds[0]]

        weights = np.linspace(1, 10, dist.size)  # weighting

        thresh = np.average(dist, weights=weights)  # weighted avg
        if last_found.shape[0] > 20:
            variance = np.average((dist - thresh)**2,
                                  weights=weights) * dist.size
            stdev = np.sqrt(variance / (dist.size - 1)) * 2.5  # unbiased std
        else:
            stdev = thresh / 2
        output[col - 1] = [np.abs(thresh), stdev]

    return output


def get_extrema(data, peaks=True, thresh=0):
    """
    Find extrema in `data` by changes in sign of first derivative

    Parameters
    ----------
    data : array_like
    peaks : bool
        Whether to look for peaks (True) or troughs (False)
    thresh : float [0,1]

    Returns
    -------
    np.ndarray
        Indices of extrema from `data`
    """

    if thresh < 0 or thresh > 1: raise ValueError('Thresh must be in (0,1).')

    data = normalize(data)

    if peaks: Indx = np.where(data > data.max() * thresh)[0]
    else: Indx = np.where(data < data.min() * thresh)[0]

    trend = np.sign(np.diff(data))
    idx = np.where(trend == 0)[0]

    # get only peaks, and fix flat peaks
    for i in range(idx.size - 1, -1, -1):
        if trend[min(idx[i] + 1, trend.size) - 1] >= 0: trend[idx[i]] = 1
        else: trend[idx[i]] = -1

    if peaks: idx = np.where(np.diff(trend) == -2)[0] + 1
    else: idx = np.where(np.diff(trend) == 2)[0] + 1

    return np.intersect1d(Indx, idx)


def normalize(data):
    """
    Normalizes `data` (subtracts mean and divides by std)

    Parameters
    ----------
    data : array_like

    Returns
    -------
    np.ndarray
        Normalized data
    """

    if data.size == 1 or data.std() == 0: return data - data.mean(0)
    else: return (data - data.mean(0)) / data.std(0)
