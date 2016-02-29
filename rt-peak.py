#!/usr/bin/env python

import os
import time
import numpy as np
import scipy.signal
from libmpdev import MP150
import keypress
from threading import Thread, Lock

class RTP(MP150):
    """Detects physiological 'peaks' in real time from a BioPac MP150 device"""
    
    def __init__(self, logfile='test', samplerate=200, channels=[1], physio='resp'):
        """Initalizes peak detection thread
         
        mp:     instance of MP150, needed for sampling BioPac
        physio: string, one of ['resp','ecg','ppg']
        """
        
        MP150.__init__(self,logfile,samplerate,channels)
        
        self.DEBUGGING = True
        
        if physio.lower() not in ['resp','ecg','ppg']:
            raise Exception("Error in RTP: physio must be one of ['resp','ecg','ppg'].")
        
        self._physio = physio
        
        # assume first "on" channel is the one to record from
        self._recchan = channels[0]
        
        #set up for peak storing peak detection
        self._detected = []
        self._peakind = np.empty(0)
        
        self._output = False
        
        self._rtpthread = Thread(target=self._findpeaks)
        self._rtpthread.daemon = True
        self._rtpthread.name = "peakfinder"
        self._rtpthread.start()
    
    
    def start_peak_finding(self):
        """Starts sending signals to stdout"""
        
        self._output = True
    
    
    def stop_peak_finding(self):
        """Stops sending signals to stdout"""
        
        #stop output
        self._output = False
        #stop recording
        self.stop_recording()
        #close connection to MP150
        self.close()
    
    
    ## INTERNAL USE
    def _findpeaks(self):
        self.start_recording()
        print 'Finding peaks...'
        self._last = self.sample()
        
        while self._connected:
            sig = self.sample()
            
            if sig == self._last[-1]:
                pass
            else:
                self._last = np.hstack((self._last,sig))
                peakind = scipy.signal.argrelmax(np.array(self._last),order=10)[0]
                
                if peakind.size > self._peakind.size:
                    self._peakind = peakind
                    self._detected.append((self.get_timestamp(),sig))
                    
                    if self._output:
                        keypress.PressKey(0x50)
                        keypress.ReleaseKey(0x50)
                        
                    if self.DEBUGGING: print 'Peak found!'
            
    
if __name__ == '__main__':
    realtimedet = RTP(logfile='test')
    print "Successfully connected to MP150."
    realtimedet.start_peak_finding()
    
    time.sleep(10)
    
    realtimedet.stop_peak_finding()
    print "Saving detected peak file"
    np.savetxt('test_detected.csv',np.array(realtimedet._detected),fmt='%.3f')
    np.savetxt('test_sampled.csv',realtimedet._sig,fmt='%.3f') 