# realtime-peaks
For use in the (mostly) real-time detection of physiological peaks using BioPac MP150

## Software Requirements
* Windows (only tested on 7)
* Python >= 2.7
* numpy
* scipy
* matplotlib

Also, unfortunately, you'll need to purchase the Biopac Hardware API from [BioPac Systems](http://www.biopac.com/product/api-biopac-hardware/)...

## Hardware Requirements
* BioPac MP150
* At least one add-on module (e.g., [RSPEC](http://www.biopac.com/product/bionomadix-rsp-with-ecg-amplifier/))

This is designed to work with the MP150 but could be customized to work with other BioPac systems (e.g., MP36R, MP35, MP36).

## Usage
Making sure you've got the BioPac system set up and plugged in first.

```python
# Import the module
import rtpeaks

# Next, create an instance of RTP
pf = rtpeaks.RTP(logfile = 'test', channels = [1,9], samplerate=200.)

# Initiate peak/trough detection whenever you're ready. But be careful to not
# start too soon. Once begun, the class will imitate keypresses ('p' for peaks 
# and 't' for troughs).

pf.start_peak_finding()

##############################################################
# Do all your other shenanigans / experimental procedures here
##############################################################

# Stop active peak/trough detection (keypresses will cease)
pf.stop_peak_finding()

# Stop recording data and disconnect from the BioPac
pf.close()

# Note: you can stop peak finding and still continue recording. The RTP class
# is built on top of the MP150 class from libmpdev.py, which has a few functions
# for recording / sampling data from the BioPac. If you want to get some post-
# experiment physio recordings without the real-time peak detection, just wait a
# few seconds before calling pf.close() after using pf.stop_peak_finding().
```

This small chunk of code will create two files:

1. A data file ('*_MP150_data.csv'), detailing 

   1. All the recorded data, and 
   2. A timestamp for each datapoint

2. A peak file ('*_MP150_peaks.csv'), detailing 

   1. The time each peak/trough was detected by the RTP instance,
   2. The time it occurred in the original datastream, 
   3. The amplitude of the peak/trough, and
   4. Whether it was a peak (1) or trough (0)

## Copyright & Disclaimers

rtpeaks is distributed under Version 3 of the GNU Public License. For more details,
see LICENSE.

BIOPAC is a trademark of BIOPAC Systems, Inc. The authors of this software have no 
affiliation with BIOPAC Systems, Inc, and that company neither supports nor endorses 
this software package.
