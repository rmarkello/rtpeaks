#!/usr/bin/env python

import os
import time
import numpy as np
import multiprocessing as mp
import threading as thr
import logging
import time
import scipy.signal

class Counter(object):

    def __init__(self):
        self._manager = mp.Manager()
        self._out_queue = self._manager.Queue(2)
        self._record_queue = self._manager.Queue()
        self._dict = self._manager.dict()
        self._dict['thread'] = True
        self._dict['logname'] = 'test_logging.csv'
        self._dict['starttime'] = time.time()
        self._dict['newestsample'] = [0]
        self._dict['put'] = False
        self._dict['record'] = False
                
        self._pprocess = mp.Process(target=_send_queue,args=(self._dict,self._out_queue,self._record_queue))
        self._pprocess.daemon = True
        self._pprocess.start()
        print "Starting counter process"
        
        self._lprocess = mp.Process(target=_write_log,args=(self._dict,self._record_queue))
        self._lprocess.daemon = True
        
    def _start_record(self):
        print "Starting recording process at: "+str(time.time()-self._dict['starttime'])
        self._dict['record'] = True
        self._lprocess.start()
    
    def _stop_record(self):
        print "Stopping recording process at: "+str(time.time()-self._dict['starttime'])
        self._dict['record'] = False
        self._record_queue.put('kill')

    def _start_put(self):
        print "Starting queue put at: "+str(time.time()-self._dict['starttime'])
        self._dict['put'] = True
        
    def _stop_put(self):
        print "Stopping queue put at: "+str(time.time()-self._dict['starttime'])
        self._dict['put'] = False
        
    def _close(self):
        if self._dict['record']: self._stop_record()
        self._dict['thread'] = False
        print "Killing counter process at: "+str(time.time()-self._dict['starttime'])
        
    def _log(self, msg):
        self._record_queue.put(msg)
        print "Logged message at: "+str(time.time()-self._dict['starttime'])
    
    def _sample(self):
        return self._dict['newestsample']

        
def _send_queue(dic,que_out,que_record):
    t_range = np.arange(0,10000*np.pi,np.pi/20)
    t = 0
    
    while dic['thread']:
        i = np.sin(t_range[t])
        t = t+1
        
        dic['newestsample'] = i
        currtime = time.time()-dic['starttime']

        if dic['put']:
            que_out.put([currtime,i])
        if dic['record']:
            que_record.put([currtime, i])
            
    que_out.put('kill')
    print "Counter process done  at: "+str(time.time()-dic['starttime'])


def _write_log(dic,que):
    f = open(dic['logname'],'w')
    print "Logging file opened  at: "+str(time.time()-dic['starttime'])
    
    while True:
        i = que.get()
        if i == 'kill':
            break
        else:
            f.write(str(i).strip("[]")+'\n')
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
        self._close()
            
    def log(self):
        pass


def _rec_queue(dic,que_in,que_log):
    last_bunch = np.empty(1)
    peakind_log = np.empty(0)
    while True:
        i = que_in.get()
        if i == 'kill':
            break
        else:
            if i[1] > 0.95:
                print "Queue received sample "+str(time.time()-dic['starttime']-i[0])+" seconds late."
            if i[1] != last_bunch[-1]:
                last_bunch = np.hstack((last_bunch,i[1]))
                peakind = scipy.signal.argrelmax(last_bunch,order=10)[0]
                
                if peakind.size > peakind_log.size:
                    peakind_log = peakind            
                    que_log.put(i[0:2])
                    print 'Queue peak found!'
    
    que_log.put('kill')


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
    time.sleep(2)
    r.stop()
    print "Done at: "+str(time.time()-r._dict['starttime'])