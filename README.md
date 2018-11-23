# rtpeaks

A Python package for interfacing with BIOPAC's MP150/160 systems and performing real-time analysis of physiological waveforms.

## Table of contents

* [Software requirements](#software-requirements)
* [Hardware requirements](#hardware-requirements)
* [Usage](#usage)
  * [Real-time peak detection](#real-time-peak-detection)
  * [Recording physiological data](#recording-physiological-data)
* [Acknowledgments](#acknowledgments)
* [Copyright and disclaimers](#copyright-and-disclaimers)

## Software requirements

* Windows (tested up through Win7)
* Python &geq;2.7
* numpy
* scipy

Also, you'll need to purchase and install the [BIOPAC Hardware API (BHAPI)](http://www.biopac.com/product/api-biopac-hardware/).
The current version of the BHAPI should provide Win8 and Win10 compatibility, but that functionality has not yet been tested with `rtpeaks`.

## Hardware requirements

* BIOPAC MP150/MP160
* At least one module for recording physiological data (e.g., [RSPEC](http://www.biopac.com/product/bionomadix-rsp-with-ecg-amplifier/))

`rtpeaks` is designed to work with the MP150/160 but could be tweaked to work with other BIOPAC systems (e.g., MP36R, MP35, MP36).
Note that if you are using the MP160 you will need to ensure you are using &geq;v2.2.1 of the BIOPAC Hardware API!

## Usage

This section details a few use cases for `rtpeaks`.
All examples assume you have the BIOPAC system set up and plugged in to the computer.
As only one program can communicate with the BIOPAC at a time you should ensure that you are not concurrently running e.g., Acqknowledge while trying to use this code!
Even having Acqknowledge open in the background can prevent this code from being able to communicate with the BIOPAC system.

**WARNING**: Please note that while the code below is written as though the package is being run interactively, this is for demonstration purposes only.
This package utilizes Python's `multiprocessing` module; as such, you should ensure that all code that uses this package is called within an `if __name__ == '__main__':` codeblock.

### Real-time peak detection

First, import `rtpeaks` and create an instance of the `RTP` class.

```python
import rtpeaks

pf = rtpeaks.RTP(logfile='test', channels=[1, 2], samplerate=1000)
```

Here, `logfile` indicates the name of the output file where our recorded data will be saved, `channels` indicates what BIOPAC channels to record from (these channels are set on the actual hardware and will vary by set up), and `samplerate` indicates the sampling rate at which to acquire data.

Next, we'll collect some baseline data.
The program performs *much* better when we've given it some time to get used to the waveform that is being recorded and analyzed.

```python
pf.start_baseline(channel=1, samplerate=500)
time.sleep(60)  # or run some experimental code here
pf.stop_baseline()
```

Since we can only actively analyze one physiological waveform at a time, we must specify that we are interested in `channel=1`. Data from channel 2 will still be recorded, just not analyzed!
The `samplerate=500` argument specifies that we would like to downsample the data from channel 1 to 500 Hz for our real-time analysis (it is still recorded at the samplerate set during instantiation of the `RTP` object).

Now that we have baseline data, we can initiate real-time peak and trough detection.
Be careful not to start this too soon as the class imitates keypresses (`p` for peaks and `t` for troughs) when you call this method.

```python
pf.start_peak_finding(channel=1, samplerate=500, run=1)
time.sleep(100)  # or run some experimental code here
```

As with baselining, we specify what channel and samplerate at which to *analyze* our data (again, the raw data will be saved at the sampling rate set during instanation of the `RTP` object).
We can also provide the optional `run` argument which can be used to differentiate output files if you will be recording data from multiple experimental sessions.

When we're all done with peak finding, we can stop it and disconnect from the BIOPAC.

```python
pf.stop_peak_finding()
pf.close()
```

The call to `pf.close()` should only be done once you no longer need to communicate with the BIOPAC.
If you intend to call `pf.start_peak_finding()` again then you should hold off.

Now that we're done, the program will create two files (or more, depending on how many times you call `start_peak_finding()` with a different `run` argument).
Assuming you ran the code snippets above, you'll get the following two CSV files:

1. A `test_run1_biopac_data.csv` file, including
   * The timestamp of each acquired datapoint (relative to instantiation of the `RTP` class), and
   * The amplitude of data from all recorded channels

2. A `test_run1_biopac_peaks.csv` file, including
   * The time each detected peak/trough occurred,
   * The amplitude of the peak/trough, and
   * Whether it was a peak (1) or trough (0)

### Recording physiological data

You can also use `rtpeaks` to simply record from and interface with the BIOPAC, as opposed to doing real-time physiological analysis.
In order to do that you should use the `BIOPAC` class:

```python
import rtpeaks

physio = rtpeaks.BIOPAC(logfile='test', channels=[1, 2], samplerate=1000)
physio.start_recording(run=1)
```

The arguments are the same as described above; note that `physio.start_recording()` does not require a `channel` or `samplerate` argument as in `.start_peak_finding()`, as we are simply recording data (not analyzing it).

If you would like to access the physiological recordings during recording, the current timestamp of the internal clock and the most recently acquired data sample are accessible as attributes:

```python
current_time = physio.timestamp
current_sample = physio.sample
```

When you're done, stop recording and close the connection to the BIOPAC as before:

```python
physio.stop_recording()
physio.close()
```

The above code snippet wil result in only ONE output file: `test_run1_biopac_data.csv`.
Since we are not perform peak detection there will be no `_peaks.csv` file.

## Acknowledgments

The original idea for this package came from [Edwin Dalmaijer's](https://github.com/esdalmaijer) [MPy150](https://github.com/esdalmaijer/MPy150) package.
Several of the warnings and caveats scattered throughout this README about version compatability issues are thanks to the trials and tribulations of [Dennis Hernaus](https://mhens.mumc.maastrichtuniversity.nl/profile/dennis.hernaus).

## Copyright and disclaimers

`rtpeaks` is distributed under Version 3 of the GNU Public License.
For more details, see the [LICENSE](LICENSE) included in the `rtpeaks` distribution.

BIOPAC is a trademark of BIOPAC Systems, Inc.
The authors of this software have no affiliation with BIOPAC Systems, Inc, and that company neither supports nor endorses this software package.
