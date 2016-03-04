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

try:
    mpdev = windll.LoadLibrary('mpdev.dll')
except:
    try:
        mpdev = windll.LoadLibrary(os.path.join(os.path.dirname(os.path.abspath(__file__)),'mpdev.dll'))
    except:
        raise Exception("Error in libmpdev: could not load mpdev.dll")


# error handling
def check_returncode(returncode):
    if returncode == 1:
        meaning = "MPSUCCESS"
    else:
        meaning = "UNKNOWN"

    return meaning

class MP150(object):

    def __init__(self, logfile='default', samplerate=200, channels=[1,2,3]):
        self._manager = mp.Manager()
        
        self._sample_queue = self._manager.Queue(2)
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
            chnls = np.zeros(12,dtype='int64')
            chnls[np.array(channels) - 1] = 1
            self._dict['channels'] = chnls
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
        
        self._sample_process = mp.Process(target=_mp_sample,args=(self._dict,self._sample_queue,self._log_queue))
        self._sample_process.daemon = True
        self._sample_process.start()
        print "Starting sample process"
        
        self._log_process = mp.Process(target=_mp_log,args=(self._dict,self._log_queue))
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
        if self._dict['record']: self._stop_record()
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
    
    
def _mp_sample(dic,pipe_que,log_que):    
    while dic['connected']:
        try:
            data = np.zeros(12)
            data = (c_double * len(data))(*data)
            result = mpdev.getMostRecentSample(byref(data))
            data = np.array(tuple(data))[dic['channels'] == 1]
        except:
            result = "failed to call getMPBuffer"
            if check_returncode(result) != "MPSUCCESS":
                raise Exception("Error in libmpdev: failed to obtain a sample from the MP150: %s" % result)
        
        if not np.all(data == dic['newestsample']):
            dic['newestsample'] = copy.deepcopy(data)
            currtime = int((time.time()-dic['start_time']) * 1000)
                            
        if dic['record']:
            log_que.put((currtime,data))
        
        if dic['pipe']:
            pipe_que.put((currtime,data))
    
    pipe_que.put('kill')
    print "Data acq process done  at: "+str(time.time()-dic['starttime'])
    

def _mp_log(dic,log_que):
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
   
         
class Receiver(Counter):
    
    def __init__(self):
        Counter.__init__(self)
        
        self._dict['peaklog'] = 'test_peaking.csv'
        self._peak_queue = self._manager.Queue()
                
        self._rprocess = mp.Process(target=_rec_queue,args=(self._dict,self._out_queue,self._peak_queue))
        self._rprocess.daemon = True
        
        self._kprocess = mp.Process(target=_log_peaks,args=(self._dict,self._peak_queue))
        self._kprocess.daemon = True
        
    def start(self):
        self._start_record()
        self._start_put()
        self._rprocess.start()
        self._kprocess.start()

        
    def stop(self):
        self._stop_put()
        print "Sleeping for two seconds..."
        time.sleep(2)
        self._log("this is a test")
        self._close()
            
    def log(self):
        pass


def _rec_queue(dic,que_in,que_log):
    while True:
        i = que_in.get()
        if i == 'kill':
            break
        if i % 500 == 0:
            print "Queue received: " + str(i) + " at: "+str(time.time()-dic['starttime'])
            que_log.put([i, time.time()-dic['starttime']])
    
    que_log.put('kill')
    print "Receiver queue process killed at: "+str(time.time()-dic['starttime'])


def _log_peaks(dic,que):
    f = open(dic['peaklog'],'w')
    print "Peak file opened  at: "+str(time.time()-dic['starttime'])
    
    while True:
        i = que.get()
        if i == 'kill':
            break
        else:
            f.write(str(i)+'\n')

    f.close()
    print "Peak file closed at: "+str(time.time()-dic['starttime'])
           
if __name__ == '__main__':
    #mp.log_to_stderr(logging.DEBUG)
    r = Receiver()
    print "Created Receiver instance  at: "+str(r._dict['starttime'])
    r.start()
    time.sleep(1)
    for f in range(500):
        print "SAMPLING: " + str(r._sample())
    r.stop()
    print "Done at: "+str(time.time()-r._dict['starttime'])