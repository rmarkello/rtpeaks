#!/usr/bin/env python

from __future__ import print_function, division, absolute_import
import pytest
import os.path as op
import multiprocessing as mp
import numpy as np
from scipy.signal import argrelmax, argrelmin
from rtpeaks.rtp import get_baseline, peak_or_trough, gen_thresh


def rtp_finder(dic,pipe_que):
    """
    Detects peaks/troughs in real time from BioPac MP150 data

    Parameters
    ----------
    dic : multiprocessing.manager.Dict()

        Required input
        --------------
        dic['log'] : str, logfile name
        dic['samplerate'] : list, samplerates for each channel
        dic['baseline'] : bool, whether a baseline session was run

    pipe_que : multiprocessing.manager.Queue()
        Queue for receiving data from the BioPac MP150

    Returns
    -------
    array (n x 3) : detected peaks and troughs
    """

    # this will block until an item is available (i.e., dic['pipe'] is set)
    sig = np.atleast_2d(np.array(pipe_que.get()))
    sig_temp = sig.copy()

    last_found = np.array([[ 0,0,0],[ 1,0,0],[-1,0,0]]*2)

    if dic['baseline']:
        out = get_baseline(op.join(op.dirname(__file__),'data',dic['log']),
                           sig[-1,1],
                           dic['samplerate'])
        last_found = out.copy()

        sig = np.atleast_2d(np.array(pipe_que.get()))
        sig_temp = sig.copy()

    st = 1000./dic['samplerate']

    detected = []

    while True:
        i = pipe_que.get()
        if i == 'kill': break
        if i == 'break': pass  # somehow make this ensure forced peaks real
        if i[0] < sig_temp[-1,0] + st: continue

        sig, sig_temp = np.vstack((sig,i)), np.vstack((sig_temp,i))
        peak, trough = peak_or_trough(sig_temp, last_found)
        if sig.shape[0]%1000 == 0: print("{}".format(str(sig.shape[0])))
        # too long since a detected peak/trough!
        avgrate, stdrate = gen_thresh(last_found,time=True)
        lasttime = sig_temp[-1,0]-last_found[-1,1]
        if not (peak or trough) and (lasttime > avgrate+stdrate):
            # reset everything
            sig_temp = np.atleast_2d(sig[-1])
            if dic['baseline']: last_found = out.copy()
            else: last_found = np.array([[ 0,sig_temp[0,0],0],
                                         [ 1,sig_temp[0,0],0],
                                         [-1,sig_temp[0,0],0]]*2)

            detected.append(i + [2])

        # a real peak or trough
        elif peak or trough:
            print("Got something")
            # reset sig_temp and add to last_found
            sig_temp = np.atleast_2d(sig[-1])
            last_found = np.vstack((last_found,
                                    [int(peak)] + i))

            detected.append(i + [int(peak)])

    return detected


def test_RTP():
    fname = op.join(op.dirname(__file__),'data','test-run1_MP150_data.csv')
    test_sig = np.loadtxt(fname,skiprows=1,usecols=[0,2],delimiter=',')

    pipe_que = mp.Queue()
    pipe_que.put([0,1])  # imitate baseline
    for f in test_sig: pipe_que.put(f)  # imitate data
    pipe_que.put('kill')

    dic = {'log'        : 'test',
           'samplerate' : 1000,
           'baseline'   : True}

    detected = rtp_finder(dic,pipe_que)

    return detected
