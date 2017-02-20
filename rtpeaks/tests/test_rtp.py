#!/usr/bin/env python

from __future__ import print_function, division, absolute_import
import os
import os.path as op
import numpy as np
import matplotlib.pyplot as plt
from rtpeaks.rtp import get_baseline, peak_or_trough, get_extrema, gen_thresh


def rtp_finder(signal,dic,plot=False):
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

    plot : bool
        Whether to plot in real time w/threshold visualizations (WICKED SLOW)

    Returns
    -------
    array (n x 3) : detected peaks and troughs
    """

    detected = []
    if plot: fig, ax = plt.subplots(1)
    last_found = np.array([[0,0,0],[1,0,0],[-1,0,0]]*2)

    if dic['baseline']:
        out = get_baseline(op.join(os.getcwd(),'data',dic['log']),
                           dic['channelloc'],
                           dic['samplerate'])
        last_found = out.copy()
        t_thresh, t_ci = gen_thresh(last_found[:-1],time=True)
        last_found[-1,1] = signal[0,0]-t_thresh

    sig = np.atleast_2d(signal[0])
    sig_plot = sig.copy()
    st = 1000./dic['samplerate']

    for i in signal[1:]:
        if i[0] < sig[-1,0] + st: continue

        sig, sig_plot = np.vstack((sig,i)), np.vstack((sig_plot,i))
        peak, trough = peak_or_trough(sig, last_found)

        if plot:
            # for plotting
            h_thresh, h_ci = gen_thresh(last_found[:-1])
            t_thresh, t_ci = gen_thresh(last_found[:-1],time=True)

            # only accept CI if at least 20 samples
            if last_found.shape[0] < 20: h_ci, t_ci = h_thresh/2, t_thresh/2

            # if time since last det > upper bound of normal time interval
            # shrink height threshold by relative factor
            divide = (sig[-1,0]-last_found[-1,1])/(t_thresh+t_ci)
            if divide > 1: h_thresh /= divide

            # approximate # of samples between detections
            fs = np.diff(sig[:,0]).mean()
            avgrate = int(np.floor(t_thresh/fs - t_ci/fs))
            if avgrate < 0: avgrate = 5  # if negative, let's just look 5 back

            plt.hold(True)
            ax.clear()
            ax.set(ylim=[signal[:,1].min()-2,signal[:,1].max()+2],
                   xlim=[signal[0,0]-10000,signal[-1,0]+10000])
            m = last_found[last_found[:,1]>sig_plot[0,0]]
            ax.plot(sig_plot[:,0],sig_plot[:,1],
                    m[m[:,0]==1][:,1],m[m[:,0]==1][:,2],'or',
                    m[m[:,0]==0][:,1],m[m[:,0]==0][:,2],'og')
            if last_found[-1,0] != 1: ax.hlines(last_found[-1,2]+h_thresh-h_ci,
                                                sig_plot[0,0],
                                                sig_plot[-1,0]+10,
                                                'r')
            if last_found[-1,0] != 0: ax.hlines(last_found[-1,2]-h_thresh+h_ci,
                                                sig_plot[0,0],
                                                sig_plot[-1,0]+10,
                                                'g')
            ax.vlines(last_found[-1,1]+t_thresh-t_ci,*ax.get_ylim())

        if peak or trough:
            # get index of extrema
            ex = get_extrema(sig[:,1],peaks=peak)[-1]

            # add to last_found
            last_found = np.vstack((last_found,
                                    np.append([int(peak)], sig[ex])))

            # if extrema was detected "immediately" then log detection
            if ex == len(sig)-2:
                if not plot:
                    print("Found {}".format('peak' if peak else 'trough'))
                detected.append(np.append(sig[-1], [int(peak)]))
            else:
                if not plot:
                    print("Missed {}".format('peak' if peak else 'trough'))
                detected.append(np.append(sig[ex], [2]))

            # reset sig
            sig = np.atleast_2d(sig[-1])

        if plot: plt.pause(1e-9)

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
           'channelloc' : channelloc}

    detected = rtp_finder(signal,dic,plot=True)

    if plot:
        import matplotlib.pyplot as plt
        pi, ti = detected[detected[:,2]==1], detected[detected[:,2]==0]
        fi = detected[detected[:,2]==2]
        inds = np.arange(0,signal.shape[0],1000/samplerate,dtype='int64')
        plt.plot(signal[inds,0],signal[inds,1],
                 pi[:,0],pi[:,1],'or',
                 ti[:,0],ti[:,1],'og',
                 fi[:,0],fi[:,1],'oc')
        _ = str(input("Press <enter> to continue"))
        plt.close()

    return detected
