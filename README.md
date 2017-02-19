# rtpeaks
For use in the real-time detection of physiological "peaks" using BioPac MP150

## Software Requirements
* Windows (tested on XP and 7)
* Python >= 2.7
* numpy
* scipy

Also, unfortunately, you'll need to purchase the Biopac Hardware API from [BioPac Systems](http://www.biopac.com/product/api-biopac-hardware/)...

## Hardware Requirements
* BioPac MP150
* At least one add-on module (e.g., [RSPEC](http://www.biopac.com/product/bionomadix-rsp-with-ecg-amplifier/))

This is designed to work with the MP150 but could be customized to work with other BioPac systems (e.g., MP160, MP36R, MP35, MP36).

## Usage
Making sure you've got the BioPac system set up and plugged in to the computer.

First, import the relevant class and instantiate. Use the `logfile` kwarg to determine what the relevant outputs will be labelled as, `channels` to set the BioPac channels for recording, and `samplerate` to set the sampling rate.

```python
from rtpeaks import RTP

pf = RTP(logfile='test', channels=[1,2], samplerate=1000.)
```

Next, initiate peak and trough detection. Be careful not to start this too soon as the class will imitate keypress (`p` for peaks and `t` for troughs) when you call this method.

When calling `start_peak_finding()`, you should specify the channel that you want to use to detect peaks with the `channel` kwarg. Not all physiological signals are best sampled at high rates; for example, respiration is generally best sampled in the 50-100Hz range, while ECG is best sampled in the ~1000Hz range. If you want to detect peaks in respiration but simultaneously record ECG data at 1000Hz, you can provide the `samplerate` kwarg to this method, which will automatically downsample the incoming data. The optional kwarg `run` is used to differentiate output files (i.e., if you call this method multiple times in the same experiment, you can ensure that you have multiple output files rather than one large output file).

```python
pf.start_peak_finding(channel=1, samplerate=50, run=1)
```

When you're done peak finding, you can call `stop_peak_finding()` to stop emulating the keypresses and recording data.

Then calling `close()` will disconnect the program from the BioPac device. Only call that when you are totally done with your experiment!

```python
pf.stop_peak_finding()
pf.close()
```

This program will create two (or more) files (depending on how many times you call `start_peak_finding()`). Assuming you ran the code snippets above:

1. A data file ('*_MP150_data.csv'), detailing 

   * Timestamp of each datapoint (relative to instantiation of class)
   * Amplitude of recorded data channels

2. A peak file ('*_MP150_peaks.csv'), detailing 

   * The time each peak/trough occurred,
   * The amplitude of the peak/trough, and
   * Whether it was a trough (0) or peak (1)


## Copyright & Disclaimers

rtpeaks is distributed under Version 3 of the GNU Public License. For more details,
see LICENSE.

BIOPAC is a trademark of BIOPAC Systems, Inc. The authors of this software have no 
affiliation with BIOPAC Systems, Inc, and that company neither supports nor endorses 
this software package.
