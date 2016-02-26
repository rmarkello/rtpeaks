#!/usr/bin/env python

import os
import time
import numpy as np
import scipy.signal
from libmpdev import MP150
import keypress
from threading import Thread, Lock

# Overview
# Calculate avg half peak wave (from ~preceding trough until x samples after peak)
# Begin 'recording' real data
# Update baseline measure (use sliding window ??)
# If recorded data matches +/- x SDs within avg half peak wave, assume peak
#
# Mechanics:
# Filter recorded data for use in prediction? May cause temporal inaccuracies...

class RTP:
    """Detects physiological 'peaks' in real time from a BioPac MP150 device"""
    
    def __init__(self, mp, physio='resp'):
        """Initalizes peak detection thread
         
        mp:     instance of MP150, needed for sampling BioPac
        physio: string, one of ['resp','ecg','ppg']
        """
        
        self.DEBUGGING = True
        
        if os.name == 'posix':
            raise Exception("Error in RTP: you can, unfortunately, only use this on Windows computers...")
        
        if not isinstance(mp,MP150):
            raise Exception("Error in RTP: need to provide an MP150 instance.")
        
        if physio.lower() not in ['resp','ecg','ppg']:
            raise Exception("Error in RTP: physio must be one of ['resp','ecg','ppg'].")
        
        self._physio = physio
        self._mp = mp
        
        # assume first "on" channel is the one to record from
        self._recchan = np.where(self._mp._channels)[0]
        if self._recchan.size > 1: self._recchan = self._recchan[0]
        
        self._ready = True
        self._base = []
        self._last = np.empty(0)
        self._sig = np.empty(0)
        self._output = False
        self._detected = []
        self._peakind = np.empty(0)
        
        self._rtpthread = Thread(target=self._findpeaks)
        self._rtpthread.daemon = True
        self._rtpthread.name = "peakfinder"
        
        # create baseline measurement
        self._mp.start_recording()
        
        # start peakfinder program in background
        self._mp.start_recording_to_buffer()
        self._rtpthread.start()
    
    
    def start_peak_finding(self):
        """Starts sending signals to stdout"""
        
        self._output = True
    
    
    def stop_peak_finding(self):
        """Stops sending signals to stdout"""
        
        self._output = False
        self._ready = False
        self._mp.stop_recording_to_buffer()
        self._mp.stop_recording()
        self._mp.close()
    
    
    ## INTERNAL USE
    def _baseline(self):
        """Creates baseline measurement to ground initial peak detection"""
        
        self._mp.start_recording_to_buffer(self._recchan)
        
        if self._physio in ['ecg','ppg']: time.sleep(15)
        else: time.sleep(30)
        
        self._mp.stop_recording_to_buffer()
        
        base = self._mp.get_buffer()
        peakind = scipy.signal.argrelmax(base,order=10)[0]
        
        
        self._ready = True
    
    
    def _findpeaks(self):
        print 'Finding peaks...'
        
        while self._ready:
            try:
                self._sig = self._mp.get_buffer()
            except:
                raise Exception("Failed to get buffer from MP150")
            
            if np.all(self._last == self._sig):
                pass
            else:
                peakind = scipy.signal.argrelmax(np.array(self._sig),order=10)[0]
                
                if peakind.size > self._peakind.size:
                    self._peakind = peakind
                    self._detected.append((self._mp.get_timestamp(),self._mp.sample()))
                    
                    if self._output:
                        #keypress.PressKey(0x50)
                        #keypress.ReleaseKey(0x50)
                        if self.DEBUGGING: print 'Peak found!'
            
            self._last = self._sig
    

if __name__ == '__main__':
    mp = MP150(logfile='test',samplerate=100,channels=[1])
    print "Successfully connected to MP150"
    realtimedet = RTP(mp=mp)
    realtimedet.start_peak_finding()
    
    time.sleep(10)
    
    realtimedet.stop_peak_finding()
    print "Saving detected peak file"
    np.savetxt('test_detected.csv',np.array(realtimedet._detected),fmt='%.3f')
    np.savetxt('test_sampled.csv',realtimedet._sig,fmt='%.3f') 