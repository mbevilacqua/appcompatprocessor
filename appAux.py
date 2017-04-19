__author__ = 'matiasbevilacqua'

import logging
import os
import itertools
import sys
import settings
import zipfile
import re
try:
    import psutil
except ImportError:
    if settings.__PSUTIL__:
        settings.__PSUTIL__ = False
        print("Python psutil module required for memory governor (we can live without it unless we run out of memory)")
else: settings.__PSUTIL__ = True

try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO

try:
    from termcolor import colored
except ImportError:
    def colored(s1, s2):
        return s1


logger = logging.getLogger(__name__)
# ZipFile cache
zipCache = {}
spinner = itertools.cycle(['-', '\\', '|', '/'])


def getFileSize(fileobject):
    fileobject.seek(0,2) # move the cursor to the end of the file
    size = fileobject.tell()
    fileobject.seek(0, 0)
    return size


def toHex(data):
    return ':'.join(x.encode('hex') for x in data)


def checkLock(filefullpath):
    try:
        file = open(filefullpath, 'wb')
    except IOError:
        print "File locked"
    print "File not locked"


def loadFile(fileFullPath):
    """Abstracts loading a regular file and a file from within a zip archive.
    Note that this is convenient but extremely inefficient as we're parsing the zip header for each file we pull from the zip!

    Args:
        fileFullPath (str): Full path to file to load

    Returns:
        data (StringIO): Data read from fileFullPath
    """
    logger.debug("Loading file %s" % fileFullPath)
    if ".zip" in fileFullPath:
        m = re.match(r'^((?:.*)\.zip)[\\/](.*)$', fileFullPath)
        if m:
            zip_container = m.group(1)
            file_relative_path = m.group(2)
            # If not in the zipCache we add it
            if zip_container not in zipCache:
                if zipfile.is_zipfile(zip_container):
                    zipCache[zip_container] = zipfile.ZipFile(zip_container)
                else:
                    logger.error("Invalid ZIP file found: %s" % fileFullPath)
                    return None
            # Extract data using the zipCache:
            data = StringIO(zipCache[zip_container].read(file_relative_path))
        else:
            logger.error("Issue extracting container and relative path from ZIP file: %s" % fileFullPath)
    else:
            input_file = open(fileFullPath, 'rb')
            data = StringIO(input_file.read())
    assert(data is not None)

    #Extract RAW header
    logger.debug("Read %d bytes [%s]" % (getFileSize(data), toHex(data.read(20))))
    # Return file pointer to pos 0
    data.seek(0, 0)

    return data


def getTerminalWidth():
    tmp = os.popen('stty size', 'r').read().split()
    if len(tmp) == 0:
        return 40
    else: (rows, columns) = os.popen('stty size', 'r').read().split()
    return int(columns)


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in xrange(0, len(l), n):
        yield l[i:i + n]


def outputcolum(data):
    # Req. list of lists of fields per row
    maxStrLength = getTerminalWidth()
    if settings.rawOutput or stdout_redirect(): maxStrLength = 1000

    # Truncate fields
    # todo: There has to be a better approach to this
    for ii in xrange(0, len(data)):
        tmpList = []
        for i in xrange(0, len(data[ii][1])):
            tmpList.append(str(data[ii][1][i])[:maxStrLength] + (str(data[ii][1][i])[maxStrLength:] and '...'))
        t1 = []
        t1.append(data[ii][0])
        t1.append(tuple(tmpList))
        data[ii] = t1
        data[ii][1] = tuple(tmpList)
    widths = [max(map(len,map(str, col))) for col in zip(*[x[1] for x in data])]
    for row in data:
        if settings.rawOutput or stdout_redirect():
            print ("  ".join((str(val).ljust(width) for val, width in zip(row[1], widths))))
        else: print colored("  ".join((str(val).ljust(width) for val, width in zip(row[1], widths))), row[0])
    return data


def update_progress(progress, text="Progress", logmessage=False):
    if not stdout_redirect():
        oh = sys.stdout
    else:
        oh = sys.stderr

    barLength = 25  # Modify this to change the length of the progress bar
    status = ""
    if isinstance(progress, int):
        progress = float(progress)
    if not isinstance(progress, float):
        progress = 0
        status = "error: progress var must be float\r\n"
    if progress < 0:
        progress = 0
        status = "Halt...\r\n"
    if progress > 1:
        status = "Progress out of bounds...\r\n"
    if progress == 1:
        progress = 1
        oh.write('\x1b[2K\r')
        oh.flush()
        return ""
    block = int(round(barLength * progress))
    if logmessage:
        text = "{0}: [{1}] {2}% {3}\033[K".format(text, "#" * block + "-" * (barLength - block), round(progress * 100, 2), status)
        return text
    else:
        text = "\r{0}: [{1}] {2}% {3}\033[K".format(text, "#" * block + "-" * (barLength - block), round(progress * 100, 2), status)
        oh.write(text)
        oh.flush()


def update_spinner(text="Working "):
    if not stdout_redirect():
        oh = sys.stdout
    else:
        oh = sys.stderr

    oh.write(text + spinner.next())
    oh.flush()

    # Clear spinner:
    oh.write('\r')
    oh.write(' ' * (len(text) + 3))
    oh.write('\r')


def stdout_redirect():
    return (os.fstat(0) != os.fstat(1))


def psutil_phymem_usage():
    """
    Return physical memory usage (float)
    Requires the cross-platform psutil (>=v0.3) library
    (http://code.google.com/p/psutil/)
    """
    # This is needed to avoid a deprecation warning error with
    # newer psutil versions

    if settings.__PSUTIL__ == False:
        return 0.0

    try:
        percent = psutil.virtual_memory().percent
    except:
        percent = psutil.phymem_usage().percent
    return percent


def file_len(fname):
    with open(fname) as f:
        i = 0
        for i, l in enumerate(f):
            pass
    return i + 1


def file_size(file_name_fullpath):
    if ".zip/" in file_name_fullpath:
        file_object = loadFile(file_name_fullpath)
        file_object.seek(0, os.SEEK_END)
        return file_object.tell()
    else: return os.path.getsize(file_name_fullpath)
