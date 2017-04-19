import settings
import logging
from ingest import Ingest
import re
from appAux import loadFile

logger = logging.getLogger(__name__)
# Module to ingest appcompat data parsed by ShimCacheParser
# File name and format is what you get redirecting the output from ShimCacheParser to a file


class Appcompat_parsed(Ingest):
    ingest_type = "appcompat_parsed"
    file_name_filter = "(?:.*)(?:\/|\\\)(.*)-[A-Za-z0-9]{64}-\d{1,10}-\d{1,10}(?:_w32registry(\.xml){0,1}-shimcache.txt)$"

    def __init__(self):
        super(Appcompat_parsed, self).__init__()

    def checkMagic(self, file_name_fullpath):
        return True

    def processFile(self, file_fullpath, hostID, instanceID, rowsData):
        rowNumber = 0
        file_object = loadFile(file_fullpath)
        rows = file_object.read().splitlines()[1:]
        file_object.close()

        appCompatREGEX = re.compile(
            "((?:\d\d\d\d\-\d\d\-\d\d \d\d:\d\d:\d\d)|N\/A)[, ]((?:\d\d\d\d\-\d\d\-\d\d \d\d:\d\d:\d\d)|N\/A)[, ](.*)\\\([^\\\]*)[, ](N\/A|\d*)[, ](N\/A|True|False)")
        assert (rows is not None)
        for r in rows:
            if b'\x00' in r:
                logger.debug("NULL byte found, ignoring bad shimcache parse: %s" % r)
                continue
            m = appCompatREGEX.match(r)
            if m:
                namedrow = settings.EntriesFields(HostID=hostID, EntryType=settings.__APPCOMPAT__, RowNumber=rowNumber,
                                                  LastModified=unicode(m.group(1)), LastUpdate=unicode(m.group(2)),
                                                  FilePath=unicode(m.group(3)),
                                                  FileName=unicode(m.group(4)), Size=unicode(m.group(5)),
                                                  ExecFlag=str(m.group(6)), InstanceID=instanceID)
                rowsData.append(namedrow)
                rowNumber += 1
            else:
                logger.warning("Entry regex failed for: %s - %s" % (hostID, r))