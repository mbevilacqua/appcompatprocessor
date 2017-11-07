#!/usr/bin/env python

from setuptools import setup
from settings import __version__

setup(name='AppCompatProcessor',
    version=__version__,
    description='Enterprise-wide AppCompat/AmCache processor',
    keywords = "appcompat shimcache amcache",
    author='Matias Bevilacqua',
    author_email='mbevilacqua@gmail.com',
    url='https://github.com/mbevilacqua/appcompatprocessor',
    license='Apache License (2.0)',
    classifiers = ["Programming Language :: Python",
                 "License :: OSI Approved :: Apache Software License"],
    packages=['Ingest'],
    scripts=['AppCompatProcessor.py'],
    py_modules=['AmCacheParser', 'appAux', 'appDB', 'appLoad', 'appSearch', 'mpEngineProdCons', 'mpEngineWorker', 'namedlist', 'settings', 'ShimCacheParser_ACP'],
    data_files=[('/etc/AppCompatProcessor', ['README.md', 'AppCompatSearch.txt', 'reconFiles.txt', 'LICENSE'])],
    install_requires=['pip>=1.5.4', 'setuptools>=3.3', 'argparse>=1.2.1', 'libregf-python>=20160109', 'future>=0.15.2', 'psutil>=4.3.1', 'python_Levenshtein>=0.10.0', 'termcolor>=1.1.0'],
    dependency_links=['git://github.com/williballenthin/python-registry@1a669eada6f7933798751e0cf482a9eb654c739b#egg=python-registry']
    )
