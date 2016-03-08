#!/usr/bin/env python

import os
import time
import copy
import numpy as np
import multiprocessing as mp
import logging
import time

if os.name != 'posix':
    from ctypes import windll, c_int, c_double, byref
else:
    raise Exception("Sorry Mac/Linux/POSIX user: you have to use Windows to work with the BioPac!")

# error handling
def check_returncode(returncode):
    if returncode == 1:
        meaning = "MPSUCCESS"
    else:
        meaning = "UNKNOWN"

    return meaning


class MP150(object):
    
    def __init__(self, logfile='default', samplerate=200, channels=[1,2,3]):
        
        try:
            mpdev = windll.LoadLibrary('mpdev.dll')
        except:
            try:
                mpdev = windll.LoadLibrary(os.path.join(os.path.dirname(os.path.abspath(__file__)),'mpdev.dll'))
            except:
                raise Exception("Error in libmpdev: could not load mpdev.dll")
            
        self._manager = mp.Manager()
        
        self._sample_queue = self._manager.Queue(5)
        self._log_queue = self._manager.Queue()
        self._dict = self._manager.dict()
        
        self._samplerate = samplerate
        self._sampletime = 1000.0 / self._samplerate
        self._sampletimesec = self._sampletime / 1000.0
        
        self._dict['logname'] = "%s_MP150_data.csv" % (logfile)
        self._dict['newestsample'] = [0]*len(channels)
        self._dict['pipe'] = False
        self._dict['record'] = False
        
        # connect to the MP150
        # (101 is the code for the MP150, 103 for the MP36R)
        # (11 is a code for the communication method)
        # ('auto' is for automatically connecting to the first responding device)
        try:
            result = mpdev.connectMPDev(c_int(101), c_int(11), b'auto')
        except:
            result = "failed to call connectMPDev"
        if check_returncode(result) != "MPSUCCESS":
            raise Exception("Error in libmpdev: failed to connect to the MP150: %s" % result)
            
        self._dict['starttime'] = time.time()
        
        # set sampling rate
        try:
            result = mpdev.setSampleRate(c_double(self._sampletime))
        except:
            result = "failed to call setSampleRate"
        if check_returncode(result) != "MPSUCCESS":
            raise Exception("Error in libmpdev: failed to set samplerate: %s" % result)
        
        # set acquisition channels
        try:
            chnls = [0]*12
            for x in channels: chnls[x-1] = 1
            self._dict['channels'] = np.array(chnls)
            chnls = (c_int * len(chnls))(*chnls)
            result = mpdev.setAcqChannels(byref(chnls))
        except:
            result = "failed to call setAcqChannels"
        if check_returncode(result) != "MPSUCCESS":
            raise Exception("Error in libmpdev: failed to set channels to acquire: %s" % result)
        
        # start acquisition
        try:
            result = mpdev.startAcquisition()
        except:
            result = "failed to call startAcquisition"
        if check_returncode(result) != "MPSUCCESS":
            raise Exception("Error in libmpdev: failed to start acquisition: %s" % result)
        
        self._dict['connected'] = True
        
        self._sample_process = mp.Process(target=_mp150_sample,args=(self._dict,self._sample_queue,self._log_queue))
        self._sample_process.daemon = True
        self._sample_process.start()
        print "Starting sample process"
        
        self._log_process = mp.Process(target=_mp150_log,args=(self._dict,self._log_queue))
        self._log_process.daemon = True
        
    
    def start_recording(self):
        print "Starting logging process at: "+str(time.time()-self._dict['starttime'])
        self._dict['record'] = True
        self._log_process.start()
    
    
    def stop_recording(self):
        print "Stopping logging process at: "+str(time.time()-self._dict['starttime'])
        self._dict['record'] = False
        self._log_queue.put('kill')
    
    
    def log(self, msg):
        self._log_queue.put((get_timestamp(),'MSG',msg))
        print "Logged message at: "+str(time.time()-self._dict['starttime'])
    
    
    def sample(self):
        return self._dict['newestsample']
    
    
    def get_timestamp(self):
        return int((time.time()-self._dict['start_time']) * 1000)
        
    
    def close(self):
        if self._dict['record']: self.stop_recording()
        self._dict['connected'] = False
        print "Killing counter process at: "+str(time.time()-self._dict['starttime'])
        
        # close connection
        try:
            result = mpdev.disconnectMPDev()
        except:
            result = "failed to call disconnectMPDev"
        if check_returncode(result) != "MPSUCCESS":
            raise Exception("Error in libmpdev: failed to close the connection to the MP150: %s" % result)
    
    
    # ONLY USE THESE IF YOU KNOW WHAT YOU'RE DOING; QUEUE WILL BLOCK
    def _start_pipe(self):
        print "Starting queue put at: "+str(time.time()-self._dict['starttime'])
        self._dict['pipe'] = True
    
    
    def _stop_pipe(self):
        print "Stopping queue put at: "+str(time.time()-self._dict['starttime'])
        self._dict['pipe'] = False
        try:
            self._sample_queue.put('kill',timeout=0.5)
        except:
            i = self._sample_queue.get()
            self._sample_queue.put('kill')
    
    
def _mp150_sample(dic,pipe_que,log_que):
    currtime = 0
    data = 0
    
    try:
        mpdev = windll.LoadLibrary('mpdev.dll')
    except:
        try:
            mpdev = windll.LoadLibrary(os.path.join(os.path.dirname(os.path.abspath(__file__)),'mpdev.dll'))
        except:
            raise Exception("Error in libmpdev: could not load mpdev.dll")
    
    while dic['connected']:
        try:
            data = [0,0,0]
            data = (c_double * len(data))(*data)
            result = mpdev.getMostRecentSample(byref(data))
            data = tuple(data)
        except:
            result = "failed to call getMPBuffer"
            if check_returncode(result) != "MPSUCCESS":
                raise Exception("Error in libmpdev: failed to obtain a sample from the MP150: %s" % result)
        
        if not np.all(data == dic['newestsample']):
            dic['newestsample'] = copy.deepcopy(data)
            currtime = int((time.time()-dic['starttime']) * 1000)
                            
            if dic['record']:
                log_que.put((currtime,data))
            
            if dic['pipe']:
                try:
                    pipe_que.put((currtime,data),timeout=0.5)
                except:
                    pass
    
    print "Data acq process done  at: "+str(time.time()-dic['starttime'])
    
    
def _mp150_log(dic,log_que):
    f = open(dic['logname'],'a+')
    print "Logging file opened  at: "+str(time.time()-dic['starttime'])
    
    while True:
        i = log_que.get()
        if i == 'kill':
            break
        else:
            f.write(str(i).strip("()")+'\n')
            f.flush()

    f.close()
    print "Logging file closed at: "+str(time.time()-dic['starttime'])