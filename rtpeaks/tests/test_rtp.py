#!/usr/bin/env python

from __future__ import print_function, division, absolute_import
import os
import os.path as op
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import savgol_filter as savgol
if os.name != 'posix':
    from rtpeaks.rtp import get_baseline, peak_or_trough, gen_thresh


def test_rtp_finder(signal, dic, plot=False):
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
    last_found = np.array([[0, 0, 0],
                           [1, 0, 0],
                           [-1, 0, 0]] * 2)

    if plot:
        fig, ax = plt.subplots(1)
        plt.show(block=False)
        ax.set(ylim=[signal[:, 1].min() - 2, signal[:, 1].max() + 2],
               xlim=[signal[0, 0], signal[-1, 0]])
        inds = np.arange(0, signal.shape[0],
                         np.ceil(1000. / dic['samplerate']),
                         dtype='int64')
        whole_sig, part_sig, all_peaks, all_troughs, hline, vline = ax.plot(
            signal[inds, 0], signal[inds, 1], 'blue',
            np.array([0]), np.array([0]), 'oc',
            np.array([0]), np.array([0]), 'or',
            np.array([0]), np.array([0]), 'og',
            np.array([0]), np.array([0]), 'r',
            np.array([0]), np.array([0]), 'black')
        fig.canvas.draw()

    if dic['baseline']:
        out = get_baseline(op.join(os.getcwd(), 'data', dic['log']),
                           dic['channelloc'],
                           dic['samplerate'])
        last_found = out.copy()
        t_thresh = gen_thresh(last_found[:-1])[0, 0]

        last_found[-1, 1] = signal[0, 0] - t_thresh

    thresh = gen_thresh(last_found[:-1])
    if plot: tdiff = thresh[0, 0] - thresh[0, 1]
    sig = np.atleast_2d(signal[0])

    st = np.ceil(1000. / dic['samplerate'])
    if plot: x = np.arange(signal[0, 0], signal[-1, 0], st)

    for i in signal[1:]:
        if i[0] < sig[-1, 0] + st: continue

        sig = np.vstack((sig, i))
        if len(sig) > 3: sig[:, 1] = savgol(sig[:, 1], 3, 1)
        peak, trough = peak_or_trough(sig, last_found, thresh, st)

        if plot:
            # if time since last det > upper bound of normal time interval
            # shrink height threshold by relative factor
            divide = ((sig[-1, 0] - last_found[-1, 1]) /
                      (thresh[0, 0] + thresh[0, 1]))
            divide = divide if divide > 1 else 1

            hdiff = (thresh[1, 0] - thresh[1, 1]) / divide

            # draw previously detected peaks and troughs
            m = last_found[last_found[:, 1] > signal[0, 0]]
            p, t = m[m[:, 0] == 1], m[m[:, 0] == 0]
            if len(t) > 0: all_troughs.set(xdata=t[:, 1], ydata=t[:, 2])
            if len(p) > 0: all_peaks.set(xdata=p[:, 1], ydata=p[:, 2])

            # set the moving blue dot denoting signal
            part_sig.set(xdata=np.array([sig[-1, 0]]),
                         ydata=np.array([sig[-1, 1]]))

            if last_found[-1, 0] != 1:  # if we're looking for a peak
                mult = last_found[-1, 2] + hdiff
                hline.set(color='r', xdata=x,
                          ydata=np.ones(x.size) * mult)
            if last_found[-1, 0] != 0:  # if we're looking for a trpugh
                mult = last_found[-1, 2] - hdiff
                hline.set(color='g', xdata=x,
                          ydata=np.ones(x.size) * mult)
            vline.set(xdata=np.array([last_found[-1, 1] + tdiff]),
                      ydata=np.arange(*ax.get_ylim()))

            ax.draw_artist(ax.patch)
            ax.draw_artist(whole_sig)
            ax.draw_artist(hline)
            ax.draw_artist(vline)
            if len(t) > 0: ax.draw_artist(all_troughs)
            if len(p) > 0: ax.draw_artist(all_peaks)
            ax.draw_artist(part_sig)
            fig.canvas.update()
            fig.canvas.flush_events()

        if peak is not None or trough is not None:
            # get index of extrema
            ex, l = peak or trough, int(bool(peak))

            # add to last_found
            last_found = np.vstack((last_found, np.append([l], sig[ex])))
            if (not dic['baseline'] and len(last_found) > 7 and
                    np.any(last_found[:, 1] == 0)):
                last_found = last_found[np.where(last_found[:, 1] != 0)[0]]
                last_found = np.vstack((last_found, last_found))
            thresh = gen_thresh(last_found[:-1])
            if plot: tdiff = thresh[0, 0] - thresh[0, 1]

            # if extrema was detected "immediately" then log detection
            if len(sig) - ex <= 3:
                detected.append(np.append(sig[-1], [l]))
            else:
                detected.append(np.append(sig[ex], [2]))

            # reset sig
            sig = np.atleast_2d(sig[-1])

    return np.array(detected)


def test_RTP(f, channelloc=0, samplerate=1000, plot=False, rtplot=False):
    fname = op.join(os.getcwd(), 'data', '{}-run1_MP150_data.csv'.format(f))
    signal = np.loadtxt(fname,
                        skiprows=1,
                        usecols=[0, channelloc + 1],
                        delimiter=',')

    dic = {'log': f,
           'samplerate': samplerate,
           'baseline': True,
           'channelloc': channelloc}

    detected = test_rtp_finder(signal, dic, plot=rtplot)

    if plot:
        import matplotlib.pyplot as plt
        pi, ti = detected[detected[:, 2] == 1], detected[detected[:, 2] == 0]
        fi = detected[detected[:, 2] == 2]
        inds = np.arange(0, signal.shape[0], 1000 / samplerate, dtype='int64')
        plt.plot(signal[inds, 0], signal[inds, 1],
                 pi[:, 0], pi[:, 1], 'or',
                 ti[:, 0], ti[:, 1], 'og',
                 fi[:, 0], fi[:, 1], 'oc')
        str(input("Press <enter> to continue"))
        plt.close()

    return detected
