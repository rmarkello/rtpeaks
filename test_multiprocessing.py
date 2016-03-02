#!/usr/bin/env python

import os
import time
import numpy as np
import multiprocessing as mp
import threading as thr

class Counter(object):

    def __init__(self):
        self._outpipe, self._inpipe = mp.Pipe(False)
        
        self._pthread = thr.Thread(target=self._send_pipe)
        self._pthread.daemon = True
        self._pthread.start()
        
    def _send_pipe(self):
        for i in range(1,501):
            self._inpipe.send(i)

class Receiver(Counter):
    
    def __init__(self):
        Counter.__init__(self)
        
        self._manager = mp.Manager()
        self._dict = self._manager.dict()
        self._queue = self._manager.Queue()
        
        self._pproc = mp.Process(target=self._rec_pipe,args=(self._outpipe,self._dict,self._queue,))
        self._pproc.daemon = True
        
        self._qproc = mp.Process(target=self._rec_queue,args=(self._dict,self._queue,))
        self._qproc.daemon = True
        
        
    def start(self):
        self._dict['go'] = True
        self._dict['rec'] = True
        self._pproc.start()
        self._qproc.start()
        
    def stop(self):
        self._dict['go'] = False
        
        self._queue.put('kill')
            
    def _rec_queue(self,dic,que):
        f = open('test.csv','w')
        
        while True:
            i = que.get()
            
            if i == 'kill':
                break
            
            print "Queue:"+str(i)
            f.write('Queue received: %s\n' % str(i).strip('()'))
            f.flush()
            
        f.close()
        
    def _rec_pipe(self,pipe,dic,que):
        while dic['go']:
            i = pipe.recv()
            if i % 25 == 0:
                print "Pipe:" + str(i)
                que.put((i, i+5))
        
                
if __name__ == '__main__':
    c = Counter()
    r = Receiver()
    r.start()
    time.sleep(5)
    r.stop()