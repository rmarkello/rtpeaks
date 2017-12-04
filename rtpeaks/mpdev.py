"""
Credit to @esdalmaijer for initial basis for code at:
https://github.com/esdalmaijer/MPy150

All code has been significantly refactored to use multiprocessing instead of
threading and to play nicely with `rtp.py`, but the calls to mpdev.dll were
from their initial repo
"""

from __future__ import print_function, division, absolute_import
try:
    from ctypes import windll, c_int, c_double, byref
    from ctypes.wintypes import DWORD
except ImportError:
    pass
import multiprocessing as mp
import os
import Queue
import numpy as np
import rtpeaks.process as rp


def do_nothing():
    """Does absolutely nothing
    """
    pass


def get_returncode(returncode):
    """
    Checks return codes from BIOPAC device

    Parameters
    ----------
    returncode : int
        Code returned by call to BIOPAC

    Returns
    -------
    str
        Plain-text "translation" of `returncode`
    """

    errors = ['MPSUCCESS', 'MPDRVERR', 'MPDLLBUSY',
              'MPINVPARA', 'MPNOTCON', 'MPREADY',
              'MPWPRETRIG', 'MPWTRIG', 'MPBUSY',
              'MPNOACTCH', 'MPCOMERR', 'MPINVTYPE',
              'MPNOTINNET', 'MPSMPLDLERR', 'MPMEMALLOCERR',
              'MPSOCKERR', 'MPUNDRFLOW', 'MPPRESETERR',
              'MPPARSERERR']
    error_codes = dict(enumerate(errors, 1))
    try:
        e = error_codes[returncode]
    except:
        e = returncode

    return e


def setup_biopac(dic):
    """
    Does most of the set up for the BIOPAC

    Connects to BIOPAC MP device, sets sample rate, sets acquisition channels,
    and starts acquisiton daemon

    Parameters
    ----------
    dic : multiprocessing.manager.Dict
        sampletime : float
            Number of milliseconds per sample
        channels : list
            From which channels to record data
        connected : boolean
            Whether process was able to successfully connect to the BIOPAC and
            start relevant acquisition daemon
    """

    # load required library
    try: mpdev = windll.LoadLibrary('mpdev.dll')
    except:
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'mpdev.dll')
        try: mpdev = windll.LoadLibrary(f)
        except: raise Exception('Could not load mpdev.dll')

    # connect to BIOPAC
    try: result = mpdev.connectMPDev(c_int(103), c_int(11), b'auto')
    except: result = 0
    result = get_returncode(result)
    if result != "MPSUCCESS":
        try: result = mpdev.connectMPDev(c_int(101), c_int(11), b'auto')
        except: result = 0
        result = get_returncode(result)
        if result != "MPSUCCESS":
            raise Exception("Failed to connect to BIOPAC: {}".format(result))

    # set sampling rate
    try: result = mpdev.setSampleRate(c_double(dic['sampletime']))
    except: result = 0
    result = get_returncode(result)
    if result != 'MPSUCCESS':
        raise Exception('Failed to set samplerate: {}'.format(result))

    # set acquisition channels
    chnls = [0] * 16
    for x in dic['channels']: chnls[x - 1] = 1
    chnls = (c_int * len(chnls))(*chnls)

    try: result = mpdev.setAcqChannels(byref(chnls))
    except: result = 0
    result = get_returncode(result)
    if result != 'MPSUCCESS':
        raise Exception('Failed to set channels to acquire: {}'.format(result))

    # start acquisition daemon
    try: result = mpdev.startMPAcqDaemon()
    except: result = 0
    result = get_returncode(result)
    if result != 'MPSUCCESS':
        raise Exception('Failed to start acq daemon: {}'.format(result))

    # start acquisition
    try: result = mpdev.startAcquisition()
    except: result = 0
    result = get_returncode(result)
    if result != 'MPSUCCESS':
        raise Exception('Failed to start data acquisition: {}'.format(result))

    dic['connected'] = True

    return mpdev


def shutdown_biopac(dll):
    """
    Stop acquisition daemon and disconnect from the BIOPAC

    Parameters
    ----------
    dll : WinDLL
        Loaded from `mpdev.dll`
    """

    # stop acquisition
    try: result = dll.stopAcquisition()
    except: result = 'failed to call stopAcquisition'
    result = get_returncode(result)
    if result != 'MPSUCCESS':
        raise Exception('Failed to stop data acquisition: {}'.format(result))

    # close connection
    try: result = dll.disconnectMPDev()
    except: result = 'failed to call disconnectMPDev'
    result = get_returncode(result)
    if result != 'MPSUCCESS':
        raise Exception('Failed to disconnect from BIOPAC: {}'.format(result))


def receive_data(dll, channels):
    """
    Receives a datapoint from the BIOPAC

    Parameters
    ----------
    dll : WinDLL
        Loaded from `mpdev.dll`
    channels : (1 x 16) array_like
        Specify whether to record from a given channel [on=1, off=0]
    """

    num_points, read = len(channels), DWORD(0)
    data = [0] * num_points
    data = (c_double * len(data))(*data)
    try:
        result = dll.receiveMPData(byref(data), DWORD(num_points), byref(read))
    except:
        result = 0
    result = get_returncode(result)
    if result != 'MPSUCCESS':
        raise Exception('Failed to obtain a sample: {}'.format(result))

    return np.array(tuple(data))


def biopac_log(fname, channels, log_queue):
    """
    Creates log file to record BIOPAC data

    Parameters
    ----------
    fname : str
        Name of log file to record sampled data
    channels : array_like
        From which channels data is being acquired
    log_queue : multiprocessing.manager.Queue
        Queue to receive data from `biopac_sample()` function
    """

    ch = 'channel' + ',channel'.join(str(y) for y in channels)
    with open(fname, 'a+') as f:
        f.write('time,{0}\n'.format(ch))
        f.flush()

        while True:
            i = log_queue.get()
            if isinstance(i, str) and i == 'kill': break
            sig = ','.join(str(y) for y in list(i[1]))
            f.write('{0},{1}\n'.format(i[0], sig))
            f.flush()


def biopac_sample(dic, sample_queue, log_queue):
    """
    Continuously samples data from the BIOPAC

    Parameters
    ----------
    dic : multiprocessing.manager.Dict
        sampletime : float
            Number of milliseconds per sample
        channels : list
            From which channels to record data
        newestsample : array_like
            Most recently sampled data
        newesttime : array_like
            Timestamp of most recently sampled data
        record : boolean, optional
            Whether to record sampled data (i.e., send through `log_queue`).
            Default: False
        pipe : int, optional
            Which data to send to `sample_queue`. Default: None
    sample_queue : multiprocessing.manager.Queue
        Queue to send sampled data for use by another process
    log_queue : multiprocessing.manager.Queue
        Queue to send data to `biopac_log()` function
    """

    # set up acquisition
    mpdev = setup_biopac(dic)

    # process samples
    while dic['connected']:
        data = receive_data(mpdev, dic['channels'])
        currtime = dic['newesttime'] + dic['sampletime']

        if not np.all(data == dic['newestsample']):
            dic['newestsample'], dic['newesttime'] = data.copy(), currtime

            if dic['record']: log_queue.put([currtime, data])

            pipe = dic['pipe']
            if pipe is not None:
                try: sample_queue.put_nowait([currtime, data[pipe]])
                except Queue.Full: pass

    shutdown_biopac(mpdev)


class BIOPAC(object):
    """
    Class to sample and record data from BIOPAC MP device

    Parameters
    ----------
    logfile : str
        Name of output file to which data will be saved. This parameter will be
        prepended to '_biopac_data.csv'. File will only be created if
        `start_recording()` is called at least once.
    channels : int or array_like
        List of channels on BIOPAC device from which to record data. There
        should be no more than sixteen (the limit set by BIOPAC), and they
        should correspond to the physical switches set on the BIOPAC device.
    samplerate : float, optional
        Sampling rate at which to record from BIOPAC in samples/second (Hz).
        Default: 500
    dummy : bool, optional
        Whether to run in dummy mode. This is for testing purposes only. The
        program will not connect to the BIOPAC and no data will be recorded.
        All other functionality should be accessible. Default: False

    Methods
    -------
    start_recording(), stop_recording()
        Starts/stops recording data from BIOPAC. Can be called multiple times.
    close()
        Disconnects from BIOPAC. Can only be called once.

    Attributes
    ----------
    sample : np.ndarray
        Most recently acquired data from BIOPAC device. Length of array will
        depend on how many channels are set at instantiation.
    timestamp : int
        Timestamp of most recently acquired data from BIOPAC device. Timestamp
        is relative to instantiation of class (i.e., it is NOT analagous to
        time.time()).
    """

    def __init__(self, logfile, channels, samplerate=500., dummy=False):
        # check inputs
        if not isinstance(samplerate, (float, int)):
            raise TypeError('Samplerate must be one of [int, float]')
        if not isinstance(channels, (list, np.ndarray)):
            if isinstance(channels, (int)): channels = [channels]
            else: raise TypeError('Channels must be one of [list, array, int]')
        f = dict(
            samplerate=samplerate,
            sampletime=(1000. / samplerate),
            newestsample=np.zeros(len(channels)),
            newesttime=0,
            pipe=None,
            record=False,
            connected=False,
            channels=np.array(channels),
            log=logfile
        )
        self.logfile = logfile
        self.dummy = dummy
        self.manager = mp.Manager()
        self.dic = self.manager.dict(**f)
        self.sample_queue = self.manager.Queue()
        self.log_queue = self.manager.Queue()
        self.log_process = None

        if not self.dummy:
            self.sample_process = rp.Process(name='biopac_sample',
                                             target=biopac_sample,
                                             args=(self.dic,
                                                   self.sample_queue,
                                                   self.log_queue))
        else:
            self.sample_process = rp.Process(name='biopac_sample',
                                             target=do_nothing)
            self.dic['connected'] = True

        self.sample_process.daemon = True
        self.sample_process.start()
        while not self.dic['connected']: pass

    def start_recording(self, run=None):
        """
        Begins logging/recording of sampled data

        Parameters
        ----------
        run : str, optional
            Will add 'runX' to logfile name; useful for differentiating ouptuts
            of experimental sessions. Default: None
        """

        if self.dic['record']:
            self.stop_recording()
        self.dic['record'] = True

        if run is not None:
            fname = "{0}-run{1}_biopac_data.csv".format(self.logfile, str(run))
        else:
            fname = "{0}_biopac_data.csv".format(self.logfile)

        self.log_process = rp.Process(name='biopac_log',
                                      target=biopac_log,
                                      args=(fname,
                                            self.dic['channels'],
                                            self.log_queue))
        self.log_process.daemon = True
        self.log_process.start()

    def stop_recording(self):
        """Halts logging/recording of sampled data"""

        self.dic['record'] = False
        if self.log_process is not None:
            self.log_queue.put('kill')
            self.log_process.join()
            self.log_process = None

    @property
    def sample(self):
        """Most recently sampled data"""

        return self.dic['newestsample']

    @property
    def timestamp(self):
        """Timestamp of most recently sampled data"""

        return self.dic['newesttime']

    def close(self):
        """Closes connection with BIOPAC. Should only be called once."""

        self.dic['connected'] = False
        if self.dic['pipe'] is not None:
            self.dic['pipe'] = None
        if self.dic['record']:
            self.stop_recording()
        self.sample_process.join()
