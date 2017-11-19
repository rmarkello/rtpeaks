import numpy as np


def peak_or_trough(data, last_found, thresh, fs):
    """
    Helper function for rtp_finder()

    Determines if any peaks or troughs are detected in `data` that meet
    threshold generated via `gen_thresh()`

    Parameters
    ----------
    data : (N x 2) array_like
        Array containing [time, data] since last peak/trough detection
    last_found : (N x 3) array_like
        Array containing [type, time, amplitude] of previously detected
        peaks/troughs
    thresholds : (2 x 2) array_like
        Array containing average (col 1) and standard deviation (col 2) of
        time (row 1) and amplitude (row 2) thresholds for peak/trough detection
    fs : float
        Sampling rate

    Returns
    -------
    bool
        Whether a peak was detected
    bool
        Whether a trough was detected
    """

    # if time since last detection > upper bound of normal time interval
    # shrink height threshold by relative factor
    divide = ((data[-1, 0] - last_found[-1, 1]) /
              (thresh[0, 0] + thresh[0, 1]))
    divide = divide if divide > 1 else 1

    tdiff = thresh[0, 0] - thresh[0, 1]
    hdiff = (thresh[1, 0] - thresh[1, 1]) / divide

    # approximate # of samples between detections
    lookback = int(np.floor(tdiff / fs))
    if lookback < 0: lookback = 5  # if negative, let's lookback 5 samples

    if last_found[-1, 0] != 1:  # if we're looking for a peak
        peaks = get_extrema(data[:, 1])
        if len(peaks) > 0:
            p = peaks[-1]
            # ensure peak is higher than previous `lookback` datapoints
            max_ = np.all(data[p, 1] >= data[p - lookback:p, 1])
            sh = data[p, 1] - last_found[-1, 2]
            rh = data[p, 0] - last_found[-1, 1]

            if sh > hdiff and rh > tdiff and max_:
                return p, None

    if last_found[-1, 0] != 0:  # if we're looking for a trough
        troughs = get_extrema(data[:, 1], peaks=False)
        if len(troughs) > 0:
            t = troughs[-1]
            # ensure trough is lower than previous `lookback` datapoints
            min_ = np.all(data[t, 1] <= data[t - lookback:t, 1])
            sh = data[t, 1] - last_found[-1, 2]
            rh = data[t, 0] - last_found[-1, 1]

            if sh < -hdiff and rh > tdiff and min_:
                return None, t

    return None, None


def gen_thresh(last_found):
    """
    Helper function for peak_or_trough()

    Determines relevant threshold for peak/trough detection based on previously
    detected peaks/troughs

    Parameters
    ----------
    last_found : (N x 3) array_like
        Array containing [type, time, amplitude] of previously detected
        peaks/troughs

    Returns
    -------
    (2 x 2) np.ndarray
        [[avg time, std time], [avg height, std height]]
    """

    output = np.zeros((2, 2))
    for col in [1, 2]:
        peaks = last_found[last_found[:, 0] == 1, col]
        troughs = last_found[last_found[:, 0] == 0, col]

        if peaks.size != troughs.size:
            size = np.min([peaks.size, troughs.size])
            dist = peaks[-size:] - troughs[-size:]
        else:
            dist = peaks - troughs

        # get rid of gross outliers (likely caused by pauses in peak finding)
        inds = np.logical_and(dist <= dist.mean() + dist.std() * 3,
                              dist >= dist.mean() - dist.std() * 3)
        dist = dist[inds]

        # get weighted average and unbiased standard deviation
        weights = np.linspace(1, 10, dist.size)
        thresh = np.average(dist, weights=weights)
        if last_found.shape[0] > 20:
            variance = np.average((dist - thresh)**2,
                                  weights=weights) * dist.size
            stdev = np.sqrt(variance / (dist.size - 1)) * 2.5
        else:
            stdev = thresh / 2
        output[col - 1] = [np.abs(thresh), stdev]

    return output


def get_extrema(data, peaks=True, thresh=0):
    """
    Find extrema in `data` by examining changes in sign of first derivative

    Parameters
    ----------
    data : (N,) array_like
        Data sampled from BIOPAC
    peaks : bool, optional
        Whether to look for peaks (True) or troughs (False). Default: True
    thresh : (0,1) float, optional
        Height threshold for peak/trough detection. Default: 0

    Returns
    -------
    np.ndarray
        Indices of extrema from `data`
    """

    if thresh < 0 or thresh > 1:
        raise ValueError('Thresh must be in (0,1).')

    data = normalize(data)

    if peaks:
        above_threshold_ind = np.where(data > data.max() * thresh)[0]
    else:
        above_threshold_ind = np.where(data < data.min() * thresh)[0]

    trend = np.sign(np.diff(data))
    extrema_ind = np.where(trend == 0)[0]

    # get only peaks, and fix flat peaks
    for i in range(extrema_ind.size - 1, -1, -1):
        if trend[min(extrema_ind[i] + 1, trend.size) - 1] >= 0:
            trend[extrema_ind[i]] = 1
        else:
            trend[extrema_ind[i]] = -1

    if peaks:
        extrema_ind = np.where(np.diff(trend) == -2)[0] + 1
    else:
        extrema_ind = np.where(np.diff(trend) == 2)[0] + 1

    return np.intersect1d(above_threshold_ind, extrema_ind)


def normalize(data):
    """
    Normalizes `data` (subtract mean and divide by std)

    Parameters
    ----------
    data : array_like

    Returns
    -------
    np.ndarray
        Normalized data
    """

    if data.size == 1 or data.std(0).all() == 0:
        return data - data.mean(0)
    else:
        return (data - data.mean(0)) / data.std(0)
