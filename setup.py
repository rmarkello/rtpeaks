#!/usr/bin/env python

from setuptools import setup, find_packages
from rtpeaks.version import __version__

setup(
    name='rtpeaks',
    version=__version__,
    description='Real-time peak detection with BioPac MP150',
    maintainer='Ross Markello',
    url='http://github.com/rmarkello/rtpeaks',
    install_requires=['numpy','scipy'],
    packages=find_packages(exclude=['setup','rtpeaks/tests']),
    license='GNU3')
