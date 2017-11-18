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
import numpy as np
import rtpeaks.process as rp


def get_returncode(returncode):
    """
    Checks return codes from BIOPAC device

    Parameters
    ----------
    returncode : int
        Code returned by call to BIOPAC mpdev.dll

    Returns
    -------
    str
        Plain-text translation of returncode
    """

    errors = ['MPSUCCESS', 'MPDRVERR', 'MPDLLBUSY',
              'MPINVPARA', 'MPNOTCON', 'MPREADY',
              'MPWPRETRIG', 'MPWTRIG', 'MPBUSY',
              'MPNOACTCH', 'MPCOMERR', 'MPINVTYPE',
              'MPNOTINNET', 'MPSMPLDLERR', 'MPMEMALLOCERR',
              'MPSOCKERR', 'MPUNDRFLOW', 'MPPRESETERR',
              'MPPARSERERR']
    error_codes = dict(enumerate(errors, 1))
    try: e = error_codes[returncode]
    except: e = returncode

    return e


class MP150(object):
    """
    Class to sample and record data from BIOPAC MP device

    Parameters
    ----------
    logfile : str
        Name of output file
    samplerate : float, optional
        Set sampling rate for physiological data from BIOPAC. Default: 500Hz
    channels : int or array_like, optional
        List of channels on BIOPAC device from which to record data. There
        should be a maximum of 16 (this is the BIOPAC limit). Default: [1,2]
    dummy : bool, optional
        Whether to run in dummy mode (i.e., don't try to connect to BIOPAC).
        Default: False
    """

    def __init__(self, logfile='default', samplerate=500.,
                 channels=[1, 2], dummy=False):

        self.logfile = logfile
        if not isinstance(channels, (list, np.ndarray)):
            channels = [channels]
        f = dict(
            sampletime=(1000. / samplerate),
            newestsample=np.zeros(len(channels)),
            newesttime=0,
            pipe=None,
            record=False,
            connected=False,
            channels=np.array(channels)
        )

        self.manager = mp.Manager()
        self.dic = self.manager.dict(**f)
        self.sample_queue = self.manager.Queue()
        self.log_queue = self.manager.Queue()
        self.log_process = None

        if not dummy:
            self.sample_process = rp.Process(name='mp150_sample',
                                             target=mp150_sample,
                                             args=(self.dic,
                                                   self.sample_queue,
                                                   self.log_queue))
        else:
            self.sample_process = rp.Process(name='mp150_sample',
                                             target=do_nothing)
            self.dic['connected'] = True

        self.sample_process.daemon = True
        self.sample_process.start()
        while not self.dic['connected']: pass

    def start_recording(self, run=None):
        """
        Begins logging sampled data

        Parameters
        ----------
        run : str
            To differentiate name of output file
        """

        if self.dic['record']:
            self.stop_recording()
        self.dic['record'] = True

        if run is not None:
            fname = "{0}-run{1}_MP150_data.csv".format(self.logfile, str(run))
        else:
            fname = "{0}_MP150_data.csv".format(self.logfile)

        self.log_process = rp.Process(name='mp150_log',
                                      target=mp150_log,
                                      args=(fname,
                                            self.dic['channels'],
                                            self.log_queue))
        self.log_process.daemon = True
        self.log_process.start()

    def stop_recording(self):
        """
        Halts logging of sampled data and sends kill signal
        """

        self.dic['record'] = False

        if self.log_process is not None:
            self.log_queue.put('kill')
            self.log_process.join()
            self.log_process = None

    @property
    def sample(self):
        """
        Most recently sampled datapoint
        """

        return self.dic['newestsample']

    @property
    def timestamp(self):
        """
        Timestamp of most recently sampled datapoint
        """

        return self.dic['newesttime']

    def close(self):
        """
        Closes connection with BIOPAC MP150
        """

        self.dic['connected'] = False
        if self.dic['pipe'] is not None:
            self.dic['pipe'] = None
        if self.dic['record']:
            self.stop_recording()

        self.sample_process.join()


def mp150_log(fname, channels, log_queue):
    """
    Creates log file for physio data

    Parameters
    ----------
    fname : str
        Name of log file to record sampled data to
    channels : array_like
        What channels data is being acquired for
    log_queue : multiprocessing.manager.Queue
        To receive detected peaks/troughs from `peak_finder()` function
    """

    ch = ',channel'.join(str(y) for y in channels)
    with open(fname, 'a+') as f:
        f.write('time,channel{0}\n'.format(ch))
        f.flush()

        while True:
            i = log_queue.get()
            if isinstance(i, str) and i == 'kill': break
            sig = ','.join(str(y) for y in list(i[1]))
            f.write('{0},{1}\n'.format(i[0], sig))
            f.flush()


def do_nothing():
    """
    Does nothing
    """

    pass


def mp150_sample(dic, sample_queue, log_queue):
    """
    Continuously samples data from the BIOPAC MP150

    Parameters
    ----------
    dic : multiprocessing.manager.Dict
        dic['sampletime']: float, msec / sample
        dic['channels']: list , specify recording channels (e.g., [1,5,7])
        dic['newestsample']: array_like, most recently sampled data
        dic['newesttime']: array_like, time of most recently sampled data
        dic['record']: boolean, save sampled data to log file
        dic['pipe']: list-of-int, send specified data channels to queue
    sample_queue : multiprocessing.manager.Queue
        Queue to send sampled data for use by another process
    log_queue : multiprocessing.manager.Queue
        Queue to send sampled data to `mp150_log()` function

    Methods
    -------
    Can pipe data; set dic['record'] and/or dic['pipe']

    Notes
    -----
    Probably best not to use dic['pipe'] if you aren't actively pulling from
    it, but it _shouldn't_ hurt anything if you do.
    """

    # set up MP150 acquisition
    mpdev = setup_mp150(dic)

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
                except mp.queues.Full: pass

    shutdown_mp150(mpdev)


def receive_data(dll, channels):
    """
    Receives a datapoint from the mpdev

    Parameters
    ----------
    dll : from ctypes.windll.LoadLibrary
    channels : (1 x 16) array_like
        Specify recording channels [on=1, off=0]
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


def shutdown_mp150(dll):
    """
    Attempts to disconnect from the mpdev cleanly

    Parameters
    ----------
    dll : from ctypes.windll.LoadLibrary()
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


def setup_mp150(dic):
    """
    Does most of the set up for the MP150

    Connects to MP150, sets sample rate, sets acquisition channels, and starts
    acquisiton daemon

    Parameters
    ----------
    dic : multiprocessing.manager.Dict
        dic['sampletime']: float, specify sampling rate (in ms)
        dic['channels']: list-of-int, specify recording channels
        dic['connected']: boolean, continue sampling or not
    """

    # load required library
    try: mpdev = windll.LoadLibrary('mpdev.dll')
    except:
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'mpdev.dll')
        try: mpdev = windll.LoadLibrary(f)
        except: raise Exception('Could not load mpdev.dll')

    # connect to MP150
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
