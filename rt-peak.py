#!/usr/bin/env python

import os
import time
import numpy as np
import scipy.signal
import libmpdev
import keypress
from threading import Thread, Lock

# Overview
# Get baseline of ~one minute (depending on physio)
# Calculate avg half peak wave (from ~preceding trough until x samples after peak)
# Begin 'recording' real data
# Update baseline measure (use sliding window ??)
# If recorded data matches +/- x SDs within avg half peak wave, assume peak
#
# Mechanics:
# How to make peak detector program "output" that peak occurred?
# PPG or EKG or resp? (user options?)
# Filter recorded data for use in prediction? May cause temporal inaccuracies...


class RTP:
    """Detects physiological 'peaks' in real time from a BioPac MP150 device"""
    
    def __init__(self, mp=libmpdev.MP150(), physio='resp'):
        """Initalizes peak detection thread
        
        mp:     instance of MP150, needed for sampling BioPac
        physio: string, one of ['resp','ecg','ppg']
        """
        
        if os.name == 'posix':
            raise Exception("Error in RTP: you, unfortunately, can only use this on Windows computers...")
        
        if not isinstance(mp,MP150):
            raise Exception("Error in RTP: need to provide an MP150 instance.")
        
        if physio.lower() not in ['resp','ecg','ppg']:
            raise Exception("Error in RTP: physio must be one of ['resp','ecg','ppg'].")
        
        self._physio = physio
        self._mp = mp
        
        self._output = False
        self._detected = []
        
        self._mp.start_recording()
        
        self._rtpthread = Thread(target=self._findpeaks)
        self._rtpthread.daemon = True
        self._rtpthread.name = "peakfinder"
        self._rtpthread.start()
    
    
    def start_peak_finding(self):
        """Starts sending signals to stdout"""
        
        self._output = True
    
    
    def stop_peak_finding(self):
        """Stops sending signals to stdout"""
        
        self._output = False
        self._mp.stop_recording()
        self._mp.close()
    
    
    ## INTERNAL USE
    def _findpeaks(self):
        self._mp.start_recording_to_buffer()
        
        
        
        if self._ouput:
            keypress.PressKey(0x50)
            keypress.ReleaseKey(0x50)
            
        self._detected.append(peakind)

