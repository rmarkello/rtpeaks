#!/usr/bin/env python
"""
Thanks in large part to @esdalmaijer: https://github.com/esdalmaijer/MPy150
"""

from __future__ import print_function, division, absolute_import
import os
import time
import numpy as np
import multiprocessing as mp
from ctypes import windll, c_int, c_double, byref

def get_returncode(returncode):
    """Checks return codes from BioPac MP150 device"""

    errors = [  'MPSUCCESS',  'MPDRVERR',    'MPDLLBUSY',
                'MPINVPARA',  'MPNOTCON',    'MPREADY',
                'MPWPRETRIG', 'MPWTRIG',     'MPBUSY',
                'MPNOACTCH',  'MPCOMERR',    'MPINVTYPE',
                'MPNOTINNET', 'MPSMPLDLERR', 'MPMEMALLOCERR',
                'MPSOCKERR',  'MPUNDRFLOW',  'MPPRESETERR',
                'MPPARSERERR']
    
    error_codes = dict(enumerate(errors,1))
    
    try: e = error_codes[returncode]
    except: e = 'n/a'

    return e


class MP150(object):
    """Class to sample and record data from BioPac MP device"""
    
    def __init__(self, logfile='default', samplerate=500., channels=[1,2]):
        
        self.manager = mp.Manager()
        self.sample_queue = self.manager.Queue()
        self.log_queue = self.manager.Queue()
        self.dic = self.manager.dict()
        
        self.dic['sampletime'] = 1000.0 / samplerate
        
        self.dic['newestsample'] = [0]*16
        self.dic['pipe'] = False
        self.dic['record'] = False
        self.dic['connected'] = False
        self.dic['channels'] = channels
        
        self.sample_process = mp.Process(   target = mp150_sample,
                                            args = (self.dic,
                                                    self.sample_queue,
                                                    self.log_queue)) 
        self.log_process = mp.Process(  target = mp150_log,
                                        args = ("{}_MP150_data.csv".format(logfile),
                                                self.dic['channels'],
                                                self.log_queue))
        
        self.log_process.daemon = True
        self.sample_process.daemon = True
        self.sample_process.start()
        
    
    def start_recording(self):
        """Begins logging sampled data"""

        self.dic['record'] = True
        self.log_process.start()
    
    
    def stop_recording(self):
        """Halts logging of sampled data and sends kill signal"""

        self.dic['record'] = False
        self.log_queue.put('kill')    
    
    
    def sample(self):
        """Returns most recently sampled datapoint"""

        return self.dic['newestsample']
    
    
    def close(self):
        """Closes connection with BioPac MP150"""

        self.dic['connected'] = False
        if self.dic['pipe']: self.__stop_pipe()
        if self.dic['record']: self.stop_recording()
        while not self.log_queue.empty(): pass
    

    def _start_pipe(self):
        """Begin sending sampled data to queue"""
        
        if not self.dic['record']: self.start_recording()
        self.dic['pipe'] = True
    
    
    def _stop_pipe(self):
        """Halts sending sampled data to queue and sends kill signal"""

        self.dic['pipe'] = False
        
        try:
            self.sample_queue.put('kill',timeout=0.5)
        except:
            i = self.sample_queue.get()
            self.sample_queue.put('kill')
    
    
def mp150_sample(dic,pipe_que,log_que):
    """Continuously samples data from the BioPac MP150

    Parameters
    ----------
    dic : multiprocessing.manager.Dict()

        Required input
        --------------
        dic['sampletime']: float, 1000 / desired sampling rate
        dic['channels']: list , specify recording channels (e.g., [1,5,7])

        Set by mp150_sample()
        ---------------------
        dic['newestsample']: array, sampled data each timepoint

        Optionally set
        --------------
        dic['record']: boolean, save sampled data to log file
        dic['pipe']: boolean, send sampled data to queue

    pipe_que : multiprocessing.manager.Queue()
        Queue to send sampled data for use by another process
    que_log : multiprocessing.manager.Queue()
        Queue to send sampled data to mp150_log() function

    Methods
    -------
    Can pipe data; set dic['record'] and/or dic['pipe'] True

    Notes
    -----
    Probably best not to use dic['pipe'] if you aren't actively pulling from it
    """

    mpdev = setup_mp150(mpdev,dic)
    
    # process samples    
    while dic['connected']:
        data = sample_data(mpdev,dic['channels'])
        
        if not np.all(data == dic['newestsample']):
            dic['newestsample'] = data.copy()
            currtime = (time.time()-dic['starttime']) * 1000
                            
            if dic['record']: log_que.put([currtime,data])
            
            if dic['pipe']:
                try: pipe_que.put([currtime,data[0]],timeout=dic['sampletime']/1000)
                except: pass
    
    # close connection
    try: result = mpdev.disconnectMPDev()
    except: result = "failed to call disconnectMPDev"
    if get_returncode(result) != "MPSUCCESS":
        raise Exception("Failed to close the connection: {}".format(result))


def sample_data(dll,channels):
    """Attempts to sample data from MP150

    Parameters
    ----------
    dll : from ctypes.windll.LoadLibrary()
    channels : numpy.ndarray (1x16)
        True where acquiring channel data

    Returns
    -------
    array (1xn) : sampled data
    """

    try:
        data = [0]*16
        data = (c_double * len(data))(*data)
        result = mpdev.getMostRecentSample(byref(data))
        data = np.array(tuple(data))[channels==1]
    except: 
        result = 0
    if get_returncode(result) != "MPSUCCESS":
        raise Exception("Failed to obtain a sample: {}".format(result))

    return data


def setup_mp150(dic):
    """Does most of the set up for the MP150

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
    try: 
        mpdev = windll.LoadLibrary('mpdev.dll')
    except:
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)),'mpdev.dll')
        try: mpdev = windll.LoadLibrary(f)
        except: raise Exception("Could not load mpdev.dll")

    # connect to MP150
    try: result = mpdev.connectMPDev(c_int(101), c_int(11), b'auto')
    except: result = 0
    if get_returncode(result) != "MPSUCCESS":
        raise Exception("Failed to connect: {}".format(result))

    # set sampling rate
    try: result = mpdev.setSampleRate(c_double(dic['sampletime']))
    except: result = 0
    if get_returncode(result) != "MPSUCCESS":
        raise Exception("Failed to set samplerate: {}".format(result))
    
    # set acquisition channels
    chnls = [0]*16
    for x in dic['channels']: chnls[x-1] = 1
    dic['channels'] = np.array(chnls)
    chnls = (c_int * len(chnls))(*chnls)

    try: result = mpdev.setAcqChannels(byref(chnls))
    except: result = 0
    if get_returncode(result) != "MPSUCCESS":
        raise Exception("Failed to set channels to acquire: {}".format(result))
    
    # start acquisition
    try: result = mpdev.startAcquisition()
    except: result = 0
    if get_returncode(result) != "MPSUCCESS":
        raise Exception("Failed to start acquisition: {}".format(result))

    dic['starttime'] = time.time()
    dic['connected'] = True
    
    return mpdev


def mp150_log(log,channels,que):
    """Creates log file for physio data

    Parameters
    ----------
    log : str
        Name of log file to record sampled data to
    channels : array-like
        What channels data is being acquired for
    que : multiprocessing.manager.Queue()
        To receive detected peaks/troughs from peak_finder() function
    """

    ch = ',channel'.join(str(y) for y in channels.tolist())
    f = open(log,'a+')
    f.write('time,channel{0}\n'.format(ch))
    f.flush()
    
    while True:
        i = que.get()
        if i == 'kill': break
        else:
            sig = ','.join(str(y) for y in i[1].tolist())
            f.write('{:0.3f},{1}\n'.format(i[0],sig))
            f.flush()

    f.close()