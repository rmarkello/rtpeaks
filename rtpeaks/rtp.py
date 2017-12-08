from __future__ import print_function, division, absolute_import
import itertools
import Queue
import time
import numpy as np
from rtpeaks.keypress import press_key
from rtpeaks.mpdev import BIOPAC
import rtpeaks.process as rp
from rtpeaks.utils import (peak_or_trough, gen_thresh)


def rtp_log(fname, que):
    """
    Creates log file to record detected peaks/troughs

    Parameters
    ----------
    fname : str
        Name of log file to record sampled data
    que : multiprocessing.manager.Queue
        Queue to receive detected peaks/troughs from `rtp_finder()` function
    """

    with open(fname, 'a+') as f:
        f.write('time,amplitude,peak\n')
        f.flush()

        while True:
            i = que.get()
            if isinstance(i, str) and i == 'kill': break
            out = '{0}\n'.format(','.join(str(y) for y in list(i)))
            f.write(out)
            f.flush()


def get_baseline(logfile, channel, samplerate):
    """
    Gets baseline estimates of physiological waveform

    Will only be run if `start_baseline()`/`stop_baseline()` have been used.
    This function will import the baseline data and attempt to do cursory peak
    detection on it. The data from the peak detection will be used to seed
    initial parameters for real-time detection, including vanishing thresholds
    and lookback values.

    Parameters
    ----------
    logfile : str
        RTP.logfile
    channel : int
        Channel for peak finding; must be channel used in call to
        `start_baseline()`
    samplerate : int
        Sampling rate at which `channel` data should be searched for peaks/
        troughs.

    Returns
    -------
    (N x 3) np.ndarray
        Class, time, and height of detected peaks & troughs
    """

    try:
        from peakdet import PeakFinder
    except ImportError:
        print('Can\'t load peakdet; ignoring baseline data.')
        return

    data = np.loadtxt('{0}-run_baseline_biopac_data.csv'.format(logfile),
                      skiprows=1,
                      delimiter=',',
                      usecols=[0, channel + 1])
    fs = 1000. / np.mean(np.diff(data[:, 0]))  # sampling rate of BIOPAC

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


def rtp_finder(dic, sample_queue, peak_queue, debug=False):
    """
    Detects peaks/troughs in real time from BIOPAC data

    Parameters
    ----------
    dic : multiprocessing.manager.Dict
        samplerate : list
            Sampling rate
        baseline : bool, optional
            Whether a baseline session was run. Default: False
        log : str,
            name of logfile (required if dic['baseline'])
    sample_queue : multiprocessing.manager.Queue
        Queue for receiving sampled data (i.e., from `biopac_sample()`)
    peak_queue : multiprocessing.manager.Queue
        Queue to send detected peaks/troughs from `rtp_log()` function
    debug : bool, optional
        Whether to run in debug mode. This will cause the function to print
        updates (e.g., 'Found peak/trough') rather than imitating keypresses.
        Default: False

    Returns
    -------
    Imitates `p` and `t` keypress for each detected peak and trough
    """

    # this will block until an item is available in sample_queue
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
        detected = peak_or_trough(sig, last_found, thresh, st)

        if np.any(detected):
            # get index of extrema
            extrema, peak = np.any(detected), int(bool(detected[0]))

            # add to last_found and reload thresholds
            last_found = np.vstack((last_found,
                                    np.append([peak], sig[extrema])))
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
            if extrema == len(sig) - 2:
                if debug:
                    print('Found {}'.format('peak' if peak else 'trough'))
                    peak_queue.put(np.append(sig[-1],
                                             [peak, dic['newesttime']]))
                else:
                    press_key('p' if peak else 't')
                    peak_queue.put(np.append(sig[-1], [peak]))

            # add detected peak time to dic['peaks'] for use in .rate
            if peak:
                dic['peaks'] = dic['peaks'].append(sig[extrema, 0])

            # reset sig
            sig = np.atleast_2d(sig[-1])

        # reset to baseline if it's been more than 10 seconds
        elif dic['baseline'] and (sig[-1, 0] - last_found[-1, 1]) > 10000:
            last_found = out.copy()
            t_thresh = gen_thresh(last_found[:-1])[0, 0]

            sig = np.atleast_2d(sig[-1])
            last_found[-1, 1] = sig[0, 0] - t_thresh

            thresh = gen_thresh(last_found[:-1])


def dummy_keypress(dic, sample_queue, debug=False):
    """
    Simulates peak/trough detection by making random keypresses

    Parameters
    ----------
    dic : multiprocessing.manager.Dict
        pipe : int
            Determines when to simulate keypresses (i.e., this is set by calls
            to `RTP.start_peak_finding()` and `RTP.stop_peak_finding()`)
    sample_queue : multiprocessing.manager.Queue
        Queue for receiving kill signal by call to `RTP.close()`
    debug : bool, optional
        Whether to run in debug mode. This will cause the function to print
        updates (e.g., 'Found peak/trough') rather than imitating keypresses.
        Default: False
    """

    cycle = itertools.cycle(['p', 't'])

    while True:
        try: i = sample_queue.get_nowait()
        except Queue.Empty: i = None
        if isinstance(i, str) and i == 'kill': return

        if dic['pipe'] is None: continue

        time.sleep(np.random.randint(5))
        key = cycle.next()
        if debug and dic['pipe'] is not None:
            print('Found {}'.format('peak' if key == 'p' else 'trough'))
        elif dic['pipe'] is not None:
            press_key(key)


class RTP(BIOPAC):
    """
    Class for use in real-time peak/trough detection of BIOPAC data

    Inherits from `BIOPAC`. If you only want to record data from the BIOPAC
    it's probably best to use that class instead.

    Parameters
    ----------
    logfile : str
        Name of output file to which data is saved. This parameter will be
        prepended to '_biopac_data.csv'.
    channels : int or array_like
        List of channels on BIOPAC device from which to record data. There
        should be no more than sixteen (the limit set by BIOPAC), and they
        should correspond to the physical switches set on the BIOPAC device.
    samplerate : float, optional
        Sampling rate at which to record from BIOPAC in samples/second (Hz).
        Default: 500
    debug : bool, optional
        Whether to run in debug mode. If using peak-finding functionality this
        will cause the class to print updates (e.g., 'Found peak/trough')
        rather than imitating keypresses. Default: False
    dummy : bool, optional
        Whether to run in dummy mode. This is for testing purposes only. The
        program will not connect to the BIOPAC and no data will be recorded.
        All other functionality should be accessible. Default: False

    Methods
    -------
    start_baseline(), stop_baseline()
        Start/stop a baseline measurement -- *highly* recommended for accurate
        peak/trough detection
    start_peak_finding(), stop_peak_finding()
        Stop/start real-time peak/trough detection

    Attributes
    ----------
    rate : float
        Average rate of peaks detected over last 5 sec in units (peaks / sec)

    Usage
    -----
    Instantiate class and call `start_peak_finding()` method. Upon peak/trough
    detection, class will simulate `p` (peak) or `t` (trough) keypress. After
    calling `stop_peak_finding()` must call `close()` method to disconnect from
    BIOPAC.

    Notes
    -----
    Should not be used interactively.
    """

    def __init__(self, logfile, channels, samplerate=500,
                 debug=False, dummy=False):
        super(RTP, self).__init__(logfile, channels,
                                  samplerate=samplerate, dummy=dummy)
        self.debug = debug
        self.dic['baseline'] = False
        self.dic['peaks'] = np.empty(0, dtype='float')
        self.peak_log_process = None
        self.peak_queue = self.manager.Queue()

        if not self.dummy:
            self.peak_process = rp.Process(name='rtp_finder',
                                           target=rtp_finder,
                                           args=(self.dic,
                                                 self.sample_queue,
                                                 self.peak_queue,
                                                 self.debug))
        else:
            self.peak_process = rp.Process(name='rtp_finder',
                                           target=dummy_keypress,
                                           args=(self.dic,
                                                 self.sample_queue,
                                                 self.debug))

        self.peak_process.daemon = True
        self.peak_process.start()

    def start_peak_finding(self, channel=None, samplerate=None, run=None):
        """
        Begin peak finding process and start logging data

        Parameters
        ----------
        channel : int
            Channel for peak finding; must be one of channels set at
            self.channels.
        samplerate : float
            Samplerate at which `channel` should be searched for peaks/troughs.
            Will appropriately downsample data, if desired.
        run : str, optional
            Will add 'runX' to logfile name; useful for differentiating ouptuts
            of experimental sessions. Default: None
        """

        if not self.dic['baseline'] and not self.dummy:
            print('RTP hasn\'t been baselined! Proceeding anyways, but note' +
                  ' that peak finding quality will likely be erratic.')

        # set peak finding channel
        if isinstance(channel, (list, np.ndarray)):
            channel = channel[0]
        elif isinstance(channel, int):
            pass
        else:
            channel = self.dic['channels'][0]

        # set peak finding sample rate
        if isinstance(samplerate, (int, float)):
            self.dic['samplerate'] = samplerate

        # turn off peak finding if it's currently happening
        if self.dic['pipe'] is not None:
            self.stop_peak_finding()

        # start recording and turn peak finding back on
        self.start_recording(run=run)
        self.dic['pipe'] = np.argwhere(self.dic['channels'] ==
                                       channel).squeeze()

        # start peak logging process
        if run is not None:
            fname = '{0}-run{1}_biopac_peaks.csv'.format(self.logfile,
                                                         str(run))
        else:
            fname = '{0}_biopac_peaks.csv'.format(self.logfile)

        self.peak_log_process = rp.Process(name='rtp_log',
                                           target=rtp_log,
                                           args=(fname,
                                                 self.peak_queue))
        self.peak_log_process.daemon = True
        self.peak_log_process.start()

    def stop_peak_finding(self):
        """Stops peak finding process (and stops data recording)"""

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

        Baseline data file will be used by `rtp_finder()` to generate starter
        thresholds for peak detection. The longer this is run the better the
        estimates will be for actual peak detection.

        Parameters
        ----------
        channel : int
            Channel for peak finding; must be one of channels set at
            self.channels.
        samplerate : float
            Samplerate at which `channel` should be searched for peaks/troughs.
            Will appropriately downsample data, if desired.
        """

        self.start_recording(run='_baseline')
        self.base_chan = np.where(self.dic['channels'] == channel)[0][0]
        self.base_rate = samplerate

    def stop_baseline(self):
        """
        Stops recording baseline.

        This causes `rtp_finder()` to progress and process baseline data file
        to generate start thresholds for peak detection.
        """

        self.stop_recording()
        self.dic['baseline'] = True
        self.sample_queue.put([self.base_chan, self.base_rate])

    def close(self):
        """Stops peak finding (if ongoing) and disconnects from BIOPAC"""

        self.stop_peak_finding()
        self.sample_queue.put('kill')
        self.peak_process.join()

        super(RTP, self).close()

    @property
    def rate(self):
        """Returns average rate of peaks in last 5 sec (units: peaks / sec)"""

        curr_time = self.dic['newesttime']
        peaks = self.dic['peaks'][self.dic['peaks'] > (curr_time - 5000.)]
        rate = np.diff(peaks)
        if rate.size == 0: return
        return 60. / (np.diff(rate).mean() / 1000.)
