#!/usr/bin/env python

from __future__ import print_function, division, absolute_import
import pytest
import os
import os.path as op
import numpy as np
from rtpeaks.rtp import get_baseline, peak_or_trough, get_extrema


def rtp_finder(signal,dic):
    """
    Simulates detection of peaks/troughs in real time

    Parameters
    ----------
    signal : array (n x 2)
    dic : dictionary

        Required input
        --------------
        dic['log'] : str, logfile name
        dic['samplerate'] : list, samplerates for each channel
        dic['baseline'] : bool, whether a baseline session was run
        dic['channelloc'] : int, location of test channel from baseline data

    Returns
    -------
    array (n x 3) : detected peaks and troughs
    """

    detected = []
    last_found = np.array([[0,0,0],[1,0,0],[-1,0,0]]*2)

    if dic['baseline']:
        out = get_baseline(op.join(os.getcwd(),'data',dic['log']),
                           dic['channelloc'],
                           dic['samplerate'])
        last_found = out.copy()
        last_found = np.vstack((last_found,
                                [-1,signal[0,0],last_found[-1,2]]))

    sig = np.atleast_2d(signal[0])

    st = 1000./dic['samplerate']

    for i in signal[1:]:
        if i[0] < sig[-1,0] + st: continue

        sig = np.vstack((sig,i))
        peak, trough = peak_or_trough(sig, last_found)

        if peak or trough:
            # get index of extrema
            if peak: ex = get_extrema(sig[:,1])[-1]
            else: ex = get_extrema(sig[:,1],peaks=False)[-1]

            # add to last_found
            last_found = np.vstack((last_found,
                                    np.append([int(peak)], sig[ex])))

            # if extrema was detected "immediately" then log detection
            if ex == len(sig)-2:
                print("Got {}".format('peak' if peak else 'trough'))
                detected.append(np.append(sig[-1], [int(peak)]))

            # reset sig
            sig = np.atleast_2d(sig[-1])

    return np.array(detected)


def test_RTP(f,channelloc=0,samplerate=1000,plot=False):
    fname = op.join(os.getcwd(),'data','{}-run1_MP150_data.csv'.format(f))
    signal = np.loadtxt(fname,
                        skiprows=1,
                        usecols=[0,channelloc+1],
                        delimiter=',')

    dic = {'log'        : f,
           'samplerate' : samplerate,
           'baseline'   : True,
           'channelloc'  : channelloc}

    detected = rtp_finder(signal,dic)

    if plot:
        import matplotlib.pyplot as plt
        pi, ti = detected[detected[:,2]==1], detected[detected[:,2]==0]
        plt.plot(signal[:,0],signal[:,1],
                 pi[:,0],pi[:,1],'or',
                 ti[:,0],ti[:,1],'og')
        _ = str(input("Enter to continue"))
        plt.close()

    return detected
