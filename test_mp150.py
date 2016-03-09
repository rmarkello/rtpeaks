#!/usr/bin/env python

from libmpdev_v2 import MP150
import time
from multiprocessing import Process, Queue, Manager, Pipe, log_to_stderr
import logging

def f():
    mp = MP150(channels=[1])
    while not mp._dict['connected']:
        pass
    mp.start_recording()
    print "Started recording"
    
    time.sleep(5)
        
    mp.stop_recording()
    print "Stopped recording"
    mp.close()
    print "Closed mp"

###############################################################

def f2():
    mp = MP150(channels=[1])
    mp.start_recording()
    mp._start_pipe()
    print "Started recording and pipe"
    
    fil1 = open('test_out_pipe.csv','w')
    
    for f in range(10):
        i = mp._sample_queue.get()
        print i
        fil1.write(str(i[0])+str(i[1])+'\n')
        fil1.flush()
    
    fil1.close()
    
    mp._stop_pipe()
    print "Stopped pipe"
    
    mp.stop_recording()
    print "Stopped recording"
    
    mp.close()
    print "Closed mp"
    
###############################################################

def rec_queue(queue):
    fil1 = open('test_out_queue.csv','w')
    print "opened file"
    print "attempting to read from queue..."
    for f in range(100):
        i = queue.get()
        print i
        fil1.write(str(i[0])+','+str(i[1][0])+'\n')
        fil1.flush()
    
    fil1.close()

def f3():
    mp = MP150(logfile='test',channels=[1])
    mp.start_recording()
    print "Started recording"

    p = Process(target=rec_queue,args=(mp._sample_queue,))
    p.start()
    mp._start_pipe()
    print "Started pipe process"
    while not mp._dict['pipe']:
        pass
    print "joining process"
    p.join()
    
    mp.stop_recording()
    print "Stopped recording"
    mp.close()
    print "Closed mp"

###############################################################
#
#def f4():
#    mp = MP150(channels=[1],pipe=True)
#    manager = Manager()
#    que = manager.Queue()
#    #p_pipe, c_pipe = Pipe(False)
#    mp.start_recording()
#    print "Started recording"
#
#    p = Process(target=rec_pipe_out_queue,args=(mp._outpipe,que,))
#    p.daemon = True
#    
#    q = Process(target=rec_queue,args=(que,))
#    q.daemon = True
#    
#    p.start()
#    print "Started pipe process"
#    
#    q.start()
#    print "Started queue process"
#            
#    que.put('kill')
#    print "Killed queue"
#    
#    p.join()
#    q.join()
#    
#    mp.stop_recording()
#    print "Stopped recording"
#    mp.close()
#    
#    que.close()
#
#def rec_pipe_out_queue(pipe1, que):    
#    for f in range(300):
#        i = pipe1.recv()
#        print "Pipe received:"+str(i)
#        que.put(i)
#
#
#def rec_queue(que):
#    fil1 = open('test_out_pipe.csv','w')
#    
#    while True:
#        i = que.get()
#        if i == 'kill':
#            break
#        fil1.write(str(i[0])+','+str(i[1][0])+'\n')
#        fil1.flush()
#    
#    fil1.close()
#
#    
    
#############################################################


if __name__ == '__main__':
    f3()