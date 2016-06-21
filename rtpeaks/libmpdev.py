#!/usr/bin/env python

import os
import time
import numpy as np
import multiprocessing as mp
from ctypes import windll, c_int, c_double, byref

def check_returncode(returncode):
    """Checks return codes from BioPac MP150 device"""
    if returncode == 1: return "MPSUCCESS"
    else: return "UNKNOWN"


class MP150(object):
    """Class to sample and record data from BioPac MP device"""
    
    def __init__(self, logfile='default', samplerate=500., channels=[1,2,3]):
        
        self.manager = mp.Manager()
        self.sample_queue = self.manager.Queue()
        self.log_queue = self.manager.Queue()
        self.dic = self.manager.dict()
        
        self.dic['sampletime'] = 1000.0 / samplerate
        
        self.dic['logname'] = "%s_MP150_data.csv" % (logfile)
        self.dic['newestsample'] = [0]*16
        self.dic['pipe'] = False
        self.dic['record'] = False
        self.dic['connected'] = False
        self.dic['channels'] = channels
        
        self.sample_process = mp.Process(target = mp150_sample,
                                            args = (self.dic,
                                                    self.sample_queue,
                                                    self.log_queue)) 
        self.log_process = mp.Process(target = mp150_log,
                                        args = (self.dic,
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
    

    def log(self, msg):
        """Logs user-specified message in line with recorded data
        
        Parameters
        ----------
        msg : str
            Message to be logged
        """

        self.log_queue.put((get_timestamp(),'MSG',msg))    
    
    
    def sample(self):
        """Returns most recently sampled datapoint"""

        return self.dic['newestsample']
    
    
    def get_timestamp(self):
        """Returns current timestamp"""

        return int((time.time()-self.dic['start_time']) * 1000)
        
    
    def close(self):
        """Closes connection with BioPac MP150"""

        self.dic['connected'] = False
        if self.dic['pipe']: self.__stop_pipe()
        if self.dic['record']: self.stop_recording()
        while not self.log_queue.empty(): pass
    

    def _start_pipe(self):
        """Begin sending sampled data to queue

        Notes
        -----
        Queue will block, so only do this if you have concurrently set up
        process to pull from queue.
        """

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
        dic['starttime']: int, time at which sampling begins
        dic['connected']: boolean, continue sampling or not
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
    Can pipe data via dic['record'] and dic['pipe'] set True

    Notes
    -----
    Probably best not to use dic['pipe'] if you aren't actively pulling
    from it!
    """

    # load required library
    try: mpdev = windll.LoadLibrary('mpdev.dll')
    except:
        try: mpdev = windll.LoadLibrary(os.path.join(os.path.dirname(os.path.abspath(__file__)),'mpdev.dll'))
        except: raise Exception("Error in libmpdev: could not load mpdev.dll")
    
    # connect to the MP150
    # (101 is the code for the MP150; use 103 for the MP36R)
    try: result = mpdev.connectMPDev(c_int(101), c_int(11), b'auto')
    except: result = "failed to call connectMPDev"
    if check_returncode(result) != "MPSUCCESS":
        raise Exception("Error in libmpdev: failed to connect to the MP150: %s" % result)

    # set sampling rate
    try: result = mpdev.setSampleRate(c_double(dic['sampletime']))
    except: result = "failed to call setSampleRate"
    if check_returncode(result) != "MPSUCCESS":
        raise Exception("Error in libmpdev: failed to set samplerate: %s" % result)
    
    # set acquisition channels
    try:
        chnls = [0]*16
        for x in dic['channels']: chnls[x-1] = 1
        dic['channels'] = np.array(chnls)
        chnls = (c_int * len(chnls))(*chnls)
        result = mpdev.setAcqChannels(byref(chnls))
    except:
        result = "failed to call setAcqChannels"
    if check_returncode(result) != "MPSUCCESS":
        raise Exception("Error in libmpdev: failed to set channels to acquire: %s" % result)
    
    # start acquisition
    try: result = mpdev.startAcquisition()
    except: result = "failed to call startAcquisition"
    if check_returncode(result) != "MPSUCCESS":
        raise Exception("Error in libmpdev: failed to start acquisition: %s" % result)   

    dic['starttime'] = time.time()
    dic['connected'] = True
        
    # process samples    
    while dic['connected']:
        try:
            data = [0]*16
            data = (c_double * len(data))(*data)
            result = mpdev.getMostRecentSample(byref(data))
            data = np.array(tuple(data))[dic['channels']==1]
        except:
            result = "failed to call getMostRecentSample"
            if check_returncode(result) != "MPSUCCESS":
                raise Exception("Error in libmpdev: failed to obtain a sample from the MP150: %s" % result)
        
        if not np.all(data == dic['newestsample']):
            dic['newestsample'] = data.copy()
            currtime = int((time.time()-dic['starttime']) * 1000)
                            
            if dic['record']: log_que.put((currtime,data))
            
            if dic['pipe']:
                try: pipe_que.put((currtime,data[0]),timeout=dic['sampletime']/1000)
                except: pass
    
    # close connection
    try: result = mpdev.disconnectMPDev()
    except: result = "failed to call disconnectMPDev"
    if check_returncode(result) != "MPSUCCESS":
        raise Exception("Error in libmpdev: failed to close the connection to the MP150: %s" % result)

    
def mp150_log(dic,log_que):
    """Creates log file for physio data

    Parameters
    ----------
    dic : multiprocessing.manager.Dict()

        Required input
        --------------
        dic['logname']: name for logfile
        dic['channels']: specify recording channels
   
    que : multiprocessing.manager.Queue()
        To receive detected peaks/troughs from peak_finder() function
    """

    f = open(dic['logname'],'a+')
    f.write('time,')
    for ch in np.where(dic['channels'])[0]: f.write('channel_%s,' % ch)
    f.seek(f.tell()-1)
    f.write('\n')
    
    while True:
        i = log_que.get()
        if i == 'kill': break
        else:
            logt, signal = i
            f.write('%s,' % (logt))
            signal.tofile(f,sep=',',format='%.10f')
            f.write('\n')
            f.flush()

    f.close()