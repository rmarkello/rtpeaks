#!/usr/bin/env python
"""
Thanks to @esdalmaijer: https://github.com/esdalmaijer/MPy150
"""

from __future__ import print_function, division, absolute_import
import os
import time
import numpy as np
import multiprocessing as mp
from ctypes import windll, c_int, c_double, byref
from ctypes.wintypes import DWORD


def get_returncode(returncode):
    """
    Checks return codes from BioPac MP150 device

    Parameters
    ----------
    returncode : int
        Code returned by call to BioPac mpdev.dll

    Returns
    -------
    str : plain-text translation of returncode`
    """

    errors = ['MPSUCCESS',  'MPDRVERR',   'MPDLLBUSY',
              'MPINVPARA',  'MPNOTCON',   'MPREADY',
              'MPWPRETRIG', 'MPWTRIG',    'MPBUSY',
              'MPNOACTCH',  'MPCOMERR',   'MPINVTYPE',
              'MPNOTINNET', 'MPSMPLDLERR','MPMEMALLOCERR',
              'MPSOCKERR',  'MPUNDRFLOW', 'MPPRESETERR',
              'MPPARSERERR']

    error_codes = dict(enumerate(errors,1))

    try: e = error_codes[returncode]
    except: e = 'n/a'

    return e


class MP150(object):
    """
    Class to sample and record data from BioPac MP device
    """

    def __init__(self, logfile='default', samplerate=500., channels=[1,2]):

        self.logfile = logfile
        self.manager = mp.Manager()
        if not isinstance(channels,(list,np.ndarray)): channels = [channels]

        f = {'sampletime'   : 1000. / samplerate,
             'newestsample' : np.zeros(len(channels)),
             'newesttime'   : 0,
             'pipe'         : None,
             'record'       : False,
             'connected'    : False,
             'channels'     : np.array(channels)}

        self.dic = self.manager.dict(f)

        self.sample_queue = self.manager.Queue()
        self.log_queue = self.manager.Queue()

        self.sample_process = mp.Process(target=mp150_sample,
                                         args=(self.dic,
                                               self.sample_queue,
                                               self.log_queue))
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

        if self.dic['record']: self.stop_recording()
        self.dic['record'] = True

        if run:
            fname = "{0}-run{1}_MP150_data.csv".format(self.logfile,str(run))
        else:
            fname = "{0}_MP150_data.csv".format(self.logfile)

        self.log_process = mp.Process(target=mp150_log,
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

        self.log_queue.put('kill')
        self.log_process.join()

    def sample(self):
        """
        Returns most recently sampled datapoint
        """

        return self.dic['newestsample']

    def timestamp(self):
        """
        Returns timestamp of most recently sampled datapoint
        """

        return self.dic['newesttime']

    def close(self):
        """
        Closes connection with BioPac MP150
        """

        self.dic['connected'] = False
        if self.dic['pipe'] is not None: self.dic['pipe'] = None
        if self.dic['record']: self.stop_recording()

        self.sample_process.join()


def mp150_log(fname,channels,log_queue):
    """
    Creates log file for physio data

    Parameters
    ----------
    fname : str
        Name of log file to record sampled data to
    channels : array-like
        What channels data is being acquired for
    log_queue : multiprocessing.manager.Queue()
        To receive detected peaks/troughs from peak_finder() function
    """

    ch = ',channel'.join(str(y) for y in channels)
    f = open(fname,'a+')
    f.write('time,channel{0}\n'.format(ch))
    f.flush()

    while True:
        i = log_queue.get()
        if i == 'kill': break
        sig = ','.join(str(y) for y in list(i[1]))
        f.write('{0},{1}\n'.format(i[0],sig))
        f.flush()

    f.close()


def mp150_sample(dic,sample_queue,log_queue):
    """
    Continuously samples data from the BioPac MP150

    Parameters
    ----------
    dic : multiprocessing.manager.Dict()

        Required input
        --------------
        dic['sampletime']: float, msec / sample
        dic['channels']: list , specify recording channels (e.g., [1,5,7])

        Set by mp150_sample()
        ---------------------
        dic['newestsample']: array, most recently sampled data
        dic['newesttime']: array, time of most recently sampled data

        Optionally set
        --------------
        dic['record']: boolean, save sampled data to log file
        dic['pipe']: list-of-int, send specified data channels to queue

    sample_queue : multiprocessing.manager.Queue()
        Queue to send sampled data for use by another process
    log_queue : multiprocessing.manager.Queue()
        Queue to send sampled data to mp150_log() function

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

            if dic['record']: log_queue.put([currtime,data])

            if dic['pipe'] is not None:
                try: sample_queue.put([currtime,data[dic['pipe']]])
                except: pass

    shutdown_mp150(mpdev)
    sample_queue.put('kill')


def receive_data(dll, channels):
    """
    Receives a datapoint from the mpdev

    Parameters
    ----------
    dll : from ctypes.windll.LoadLibrary()
    channels : array-like (1 x 16)
        Specify recording channels [on=1, off=0]
    """

    num_points, read = len(channels), DWORD(0)
    data = [0]*num_points
    data = (c_double * len(data))(*data)
    try: result = dll.receiveMPData(byref(data),DWORD(num_points),byref(read))
    except: result = 0
    result = get_returncode(result)
    if result != "MPSUCCESS":
        raise Exception("Failed to obtain a sample: {}".format(result))

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
    except: result = "failed to call stopAcquisition"
    result = get_returncode(result)
    if result != "MPSUCCESS":
        raise Exception("Failed to close the connection: {}".format(result))

    # close connection
    try: result = dll.disconnectMPDev()
    except: result = "failed to call disconnectMPDev"
    result = get_returncode(result)
    if result != "MPSUCCESS":
        raise Exception("Failed to close the connection: {}".format(result))


def setup_mp150(dic):
    """
    Does most of the set up for the MP150

    Connects to MP150, sets sample rate, sets acquisition channels, and starts
    acquisiton daemon

    Parameters
    ----------
    dic : multiprocessing.manager.Dict()

        Required input
        --------------
        dic['sampletime']: specify sampling rate (in ms)
        dic['channels']: specify recording channels

        Set by mp150_sample()
        ---------------------
        dic['starttime']: int, time at which sampling begins
        dic['connected']: boolean, continue sampling or not
    """

    # load required library
    try: mpdev = windll.LoadLibrary('mpdev.dll')
    except:
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)),'mpdev.dll')
        try: mpdev = windll.LoadLibrary(f)
        except: raise Exception("Could not load mpdev.dll")

    # connect to MP150
    try: result = mpdev.connectMPDev(c_int(101), c_int(11), b'auto')
    except: result = 0
    result = get_returncode(result)
    if result != "MPSUCCESS":
        raise Exception("Failed to connect: {}".format(result))

    # set sampling rate
    try: result = mpdev.setSampleRate(c_double(dic['sampletime']))
    except: result = 0
    result = get_returncode(result)
    if result != "MPSUCCESS":
        raise Exception("Failed to set samplerate: {}".format(result))

    # set acquisition channels
    chnls = [0]*16
    for x in dic['channels']: chnls[x-1] = 1
    chnls = (c_int * len(chnls))(*chnls)

    try: result = mpdev.setAcqChannels(byref(chnls))
    except: result = 0
    result = get_returncode(result)
    if result != "MPSUCCESS":
        raise Exception("Failed to set channels to acquire: {}".format(result))

    # start acquisition daemon
    try: result = mpdev.startMPAcqDaemon()
    except: result = 0
    result = get_returncode(result)
    if result != "MPSUCCESS":
        raise Exception("Failed to start acquisition: {}".format(result))

    # start acquisition
    try: result = mpdev.startAcquisition()
    except: result = 0
    result = get_returncode(result)
    if result != "MPSUCCESS":
        raise Exception("Failed to start acquisition: {}".format(result))

    dic['starttime'] = time.time()
    dic['connected'] = True

    return mpdev
