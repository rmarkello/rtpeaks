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
        
        self.logfile = logfile
        self.manager = mp.Manager()

        f = {   'sampletime'    : 1000. / samplerate,
                'newestsample'  : [0]*16,
                'pipe'          : None,
                'record'        : False,
                'connected'     : False,
                'channels'      : channels      }
                
        self.dic = self.manager.dict(f)
        
        self.sample_queue = self.manager.Queue()
        self.log_queue = self.manager.Queue()
        self.sample_process = mp.Process(target = mp150_sample,
                                         args   = (self.dic,
                                                   self.sample_queue,
                                                   self.log_queue)) 
        self.sample_process.daemon = True

        self.sample_process.start()

        while not self.dic['connected']: pass
        
    
    def start_recording(self, run=None):
        """Begins logging sampled data"""
        
        if self.dic['record']: self.stop_recording()
        
        self.dic['record'] = True

        if run: fname = "{}-{}_MP150_data.csv".format(self.logfile, str(run))
        else: fname = "{}_MP150_data.csv".format(self.logfile)

        self.log_process = mp.Process(target = mp150_log,
                                      args   = (fname,
                                                self.dic['channels'],
                                                self.log_queue))
        self.log_process.daemon = True
        self.log_process.start()

    
    def stop_recording(self):
        """Halts logging of sampled data and sends kill signal"""

        self.dic['record'] = False
        
        self.log_queue.put('kill')
        self.log_process.join()
        

    def sample(self):
        """Returns most recently sampled datapoint"""

        return self.dic['newestsample']
    
    
    def close(self):
        """Closes connection with BioPac MP150"""

        self.dic['connected'] = False
        if self.dic['pipe']: self.dic['pipe'] = []
        if self.dic['record']: self.stop_recording()

        self.sample_process.join()
   

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

    ch = ',channel'.join(str(y+1) for y in list(np.where(channels)[0]))
    f = open(log,'a+')
    f.write('time,channel{0}\n'.format(ch))
    f.flush()
    
    while True:
        i = que.get()
        if i == 'kill': break
        else:
            sig = ','.join(str(y) for y in list(i[1]))
            f.write('{0:.3f},{1}\n'.format(i[0],sig))
            f.flush()

    f.close()

     
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
        dic['pipe']: list-of-int, send specified data channels to queue

    pipe_que : multiprocessing.manager.Queue()
        Queue to send sampled data for use by another process
    log_que : multiprocessing.manager.Queue()
        Queue to send sampled data to mp150_log() function

    Methods
    -------
    Can pipe data; set dic['record'] and/or dic['pipe'] True

    Notes
    -----
    Probably best not to use dic['pipe'] if you aren't actively pulling from it
    """

    # set up MP150 acquisition
    mpdev = setup_mp150(dic)

    # process samples
    while dic['connected']:
        data = sample_data(mpdev, dic['channels'])
        currtime = int((time.time()-dic['starttime']) * 1000)

        if not np.all(data == dic['newestsample']):
            dic['newestsample'] = data.copy()
                            
            if dic['record']: 
                log_que.put([currtime,data])
            
            if dic['pipe'] is not None:
                try: pipe_que.put([currtime,data[dic['pipe']][0]])
                except: pass
    
    # close connection
    try: result = mpdev.disconnectMPDev()
    except: result = "failed to call disconnectMPDev"
    result = get_returncode(result)
    if result != "MPSUCCESS":
        raise Exception("Failed to close the connection: {}".format(result))

    pipe_que.put('kill') # just for good measure


def sample_data(dll,channels):
    """Attempts to sample data from MP150

    Parameters
    ----------
    dll : from ctypes.windll.LoadLibrary()
    channels : numpy.ndarray (1x16, boolean)
        True where acquiring channel data

    Returns
    -------
    array (1xn) : sampled data
    """
    try: 
        data = [0]*16
        data = (c_double * len(data))(*data)
        result = dll.getMostRecentSample(byref(data))
        data = np.array(tuple(data))[channels==1]
    except: result = 0
    result = get_returncode(result)
    if result != "MPSUCCESS":
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
    dic['channels'] = np.array(chnls)
    chnls = (c_int * len(chnls))(*chnls)

    try: result = mpdev.setAcqChannels(byref(chnls))
    except: result = 0
    result = get_returncode(result)
    if result != "MPSUCCESS":
        raise Exception("Failed to set channels to acquire: {}".format(result))
    
    # start acquisition
    try: result = mpdev.startAcquisition()
    except: result = 0
    result = get_returncode(result)
    if result != "MPSUCCESS":
        raise Exception("Failed to start acquisition: {}".format(result))

    dic['starttime'] = time.time()
    dic['connected'] = True
    
    return mpdev