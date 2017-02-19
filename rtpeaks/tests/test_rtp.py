#!/usr/bin/env python

from __future__ import print_function, division, absolute_import
import pytest
import os
import os.path as op
import numpy as np
from rtpeaks.rtp import get_baseline, peak_or_trough, get_extrema


def rtp_finder(dic,test_sig):
    """
    Simulates detection of peaks/troughs in real time

    Parameters
    ----------
    dic : dictionary

        Required input
        --------------
        dic['log'] : str, logfile name
        dic['samplerate'] : list, samplerates for each channel
        dic['baseline'] : bool, whether a baseline session was run
        dic['channelloc'] : int, location of test channel from baseline data

    test_sig : array (n x 2)

    Returns
    -------
    array (n x 3) : detected peaks and troughs
    """

    # this will block until an item is available (i.e., dic['pipe'] is set)
    last_found = np.array([[0,0,0],[1,0,0],[-1,0,0]]*2)

    if dic['baseline']:
        out = get_baseline(op.join(os.getcwd(),'data',dic['log']),
                           dic['channelloc'],
                           dic['samplerate'])
        last_found = out.copy()
        last_found = np.vstack((last_found,
                                [-1,test_sig[0,0],last_found[-1,2]]))

    sig = np.atleast_2d(test_sig[0])

    st = 1000./dic['samplerate']

    detected = []
    for i in test_sig[1:]:
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
            if ex == sig.shape[0]-2:
                print("Got {}".format('peak' if peak else 'trough'))
                detected.append(np.append(sig[-1], [int(peak)]))

            # reset sig
            sig = np.atleast_2d(sig[-1])

    return np.array(detected), sig


def test_RTP(channelloc=1):
    fname = op.join(op.dirname(os.getcwd()),'data','test-run1_MP150_data.csv')
    test_sig = np.loadtxt(fname,
                          skiprows=1,
                          usecols=[0,channelloc+1],
                          delimiter=',')

    dic = {'log'        : 'test',
           'samplerate' : 1000,
           'baseline'   : True,
           'channelloc'  : channelloc}

    detected, sig = rtp_finder(dic, test_sig)

    return detected
