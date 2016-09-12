#!/usr/bin/env python

# quick script to visualize waveform for BioPac MP150 to aid in setup

import os
import time
if os.name != 'posix': from msvcrt import kbhit, getch
else: raise OSError("Need Windows")
import numpy as np
import matplotlib.pyplot as plt
try: 
    from rtpeaks import MP150
except ImportError: 
    import sys
    sys.path.append(os.path.dirname(os.getcwd()))
    from rtpeaks import MP150

if __name__ == '__main__':
    plt.style.use('ggplot')

    r = MP150(channels = [1], samplerate = 500.)
    while not r.dic['connected']: pass

    sig = np.zeros(100)
    key = None

    fig, ax = plt.subplots()
    
    ax.set(ylim=[-10,10],xlim=[0,200],
            xticklabels=[],yticklabels=[],
            xlabel='Time (s)')
    li, = ax.plot(range(0,100),sig)
    fig.canvas.draw()

    plt.show(block=False)

    while True:
        i = r.sample()
        if kbhit(): key = ord(getch())
        if key == 27 or key == 32: break
            
        sig = np.append(sig,i)[-100:]

        li.set(ydata=sig)
        fig.canvas.draw()

    r.close()
    print "Done!"