#!/usr/bin/env python

import os
import time
import numpy as np
import scipy.signal
from libmpdev import MP150
import keypress
import multiprocessing as mp

class RTP(MP150):
    """Detects physiological 'peaks' in real time from a BioPac MP150 device"""
    
    def __init__(self, logfile='test', samplerate=200, channels=[1], peakchan=1):
        """
        logfile:    string, file to which MP150 recorded data is output
        samplerate: float, sampling rate for MP150
        channels:   list of integers, BioPac channels from which to record data
        peakchan:   integer, 
        """
        
        if type(peakchan) != int:
            raise Exception("Can only detect peaks on one channel at a time!")
        
        if peakchan[0] not in channels:
            channels.append(peakchan[0])
            channels.sort()
        
        MP150.__init__(self,logfile,samplerate,channels,pipe=True)        
        
        self._manager = mp.Manager()
        self._dict = self._manager.dict()
        
        self._queue = self._manager.Queue()
        
        self._dict['DEBUGGING'] = True
        self._dict['recchan'] = peakchan[0]
        self._dict['logfile'] = logfile
                
        self._peakprocess = mp.Process(target=self._findpeaks, args=(self._dict,self._outpipe,self._queue))
        self._peakprocess.daemon = True

        self._logprocess = mp.Process(target=self._logdetected, args=(self._dict,self._queue))
        self._logprocess.daemon = True
            
    
    def start_peak_finding(self):
        """Starts sending signals to stdout"""
        
        self._dict['peakdet'] = True
        
        if not self._recording: self.start_recording()

        self._peakprocess.start()
        self._logprocess.start()
        
        print 'Finding peaks...'
    
    
    def stop_peak_finding(self):
        """Stops sending signals to stdout"""
        
        #stop output
        self._dict['peakdet'] = False
        
        #stop logging
        self._queue.put('kill')
                
        #stop recording
        if self._recording: self.stop_recording()
    
    
    ## INTERNAL USE
    def _logdetected(self, dic, queu):
    
        detfile = open("%s_MP150_peaks.csv" % dic['logfile'], 'w')
        
        detfile.write("timestamp,peak_signal\n")

        while True:
            sig = queu.get()
            
            if sig == 'kill':
                break
                
            detfile.write('%s\n' % str(sig).strip('()'))
            detfile.flush()
        
        detfile.close()
        
    def _findpeaks(self, dic, pip, queu):
        # instantiate variables for holding data
        peakind_log = np.empty(0)
        sig_log = np.empty(1)
        
        # run until told not to run
        while dic['peakdet']:
            try:
                sig = pip.recv()
            except EOFError:
                raise Exception("RTP Error: pipe was closed from the other side")
            
            if sig[1] != sig_log[-1]:
                sig_log = np.hstack((sig_log,sig[1]))
                peakind = scipy.signal.argrelmax(sig_log,order=10)[0]
                
                if peakind.size > peakind_log.size:
                    peakind_log = peakind
                    queu.put((sig[0:2]))
                    
                    #keypress.PressKey(0x50)
                    #keypress.ReleaseKey(0x50)
                        
                    if dic['DEBUGGING']: print 'Peak found!'
            
    
if __name__ == '__main__':
    realtimedet = RTP(logfile='test')
    print "Successfully connected to MP150."
    realtimedet.start_peak_finding()
    
    time.sleep(10)
    
    realtimedet.stop_peak_finding()