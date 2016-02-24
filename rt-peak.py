#!/usr/bin/env python

import numpy as np
import scipy.signal

def extrap_signal(x_new, xp, yp):
    """Extrapolates signal (xp, yp) to x_new
    
    x:  array, desired x-values
    xp: array, current x-values
    yp: array, current y-values
    """
    
    #thanks to @sastanin on stack
    y_new = np.interp(x_new, xp, yp)
    y_new[x_new < xp[0]] = yp[0] + (x_new[x_new<xp[0]]-xp[0]) * (yp[0]-yp[1]) / (xp[0]-xp[1])
    y_new[x_new > xp[-1]]= yp[-1] + (x_new[x_new>xp[-1]]-xp[-1]) * (yp[-1]-yp[-2]) / (xp[-1]-xp[-2])
    
    return y_new


def bandpass_filt(signal,fs,flims):
    """Runs bandpass filter and returns filtered signal
    
    signal: array-like, signal of interest
    fs:     float, sampling rate of signal (samples / unit time)
    flims:  list-of-two, limits of bandpass filter
    """
    
    nyq_freq = fs*0.5
    nyq_cutoff = np.array(flims)/nyq_freq
    b, a = scipy.signal.butter(3,nyq_cutoff,btype='bandpass')
    filtSig = scipy.signal.filtfilt(b,a,signal)
    
    return filtSig


def run_avg_filt(signal, winsize):
    """Runs running-average filter and returns filtered signal
    
    signal:  array-like, signal of interest
    winsize: int, window size for filter
    """
    
    filtSig = np.zeros(signal.size)
    bottom = lambda x: 0 if x < winsize else x
    
    halfWin = int(((winsize-winsize%2)/2)+1)
    
    for x in np.arange(signal.size):
        filtSig[x] = np.mean(signal[bottom(x-halfWin-winsize%2):x+halfWin])
    
    return filtSig


def avg_peak_wave(signal, fs, order):
    """Returns an array of waveforms around peaks in signal and indices of peaks
    
    signal: array-like, signal of interest
    fs:     float, sampling rate of signal (samples / unit time)
    order:  int, number of datapoints to determine peaks
    """
    
    peakind = (scipy.signal.argrelmax(signal,order=order))[0]
    rrAvg = int(np.mean(peakind[1:peakind.size]-
                        peakind[0:peakind.size-1])/2)
    averageSig = np.zeros((peakind.size,rrAvg*2))
    time = np.arange(0,signal.size/float(fs),1./fs)
    
    bottomOut = lambda x: 0 if x<0 else x
    topOut = lambda x: -1 if x>signal.size else x

    for x in np.arange(peakind.size):
        high = topOut(peakind[x]+rrAvg)
        low = bottomOut(peakind[x]-rrAvg)
        
        tempSig = signal[low:high]
        
        if tempSig.size != rrAvg*2 and low == 0:
            x_new = np.arange(time[high]-(rrAvg*2.*(1./fs)),
                                time[high],
                                1./fs)[0:rrAvg*2]
            tempSig = extrap_signal(x_new,time[low:high],signal[low:high])
        
        elif tempSig.size != rrAvg*2 and high == -1:
            x_new = np.arange(time[low],
                                time[low]+(rrAvg*2.*(1./fs)),
                                1./fs)[0:rrAvg*2]
            tempSig = extrap_signal(x_new,time[low:high],signal[low:high])
            
        averageSig[x] = tempSig
    
    return averageSig, peakind


def thresh_peaks(averageSig,sd=2.5):
    """Returns % overlap of each row of averageSig with mean(averageSig)+-sd
    
    averageSig: array,
    sd:         float, stdevs away from mean waveform to consider peak waveforms
    """
    meanSig = np.mean(averageSig,0)
    ci = sd*np.std(averageSig,0)
    
    low = meanSig-ci
    high = meanSig+ci
    
    goodInd = []
    
    for samp in np.arange(averageSig.shape[0]):
        currSigWin = averageSig[samp]
        logInd = np.logical_and(currSigWin >= low, currSigWin <= high)
        numOverlap = float(logInd[logInd].size)
        percOverlap = numOverlap/averageSig.shape[1]
        
        goodInd.append(round(percOverlap,3))
    
    return np.array(goodInd)