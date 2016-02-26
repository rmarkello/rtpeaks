from psychopy import visual, event
import keypress
from threading import Thread
import time

def pressp():
    time.sleep(10)
    keypress.PressKey(0x50)
    keypress.ReleaseKey(0x50)

rtpthread = Thread(target=pressp)
rtpthread.daemon = True
rtpthread.name = "peakfinder"

win = visual.Window(size=[800,800],units='norm')

rtpthread.start()

while len(event.getKeys(keyList='p')) == 0:
    win.flip

print "Pressed key!"