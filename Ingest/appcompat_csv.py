import settings
import logging
from ingest import Ingest
from appAux import loadFile
import ntpath
import csv
from datetime import datetime
import sys, os

logger = logging.getLogger(__name__)
# Module to ingest csv AppCompat data
# File extension must be .csv
# Hostname = File name
# First line must contain the following headers: Last Modified,Last Update,Path,File Size,Exec Flag
# Format is what you get from running ShimCacheParser.py with flags -t (ISO timestamps) and -o (CSV output)

csv.register_dialect(
    'IngestDialect1',
    delimiter = ',',
    quotechar = '"',
    doublequote = True,
    skipinitialspace = True,
    lineterminator = '\r\n',
    quoting = csv.QUOTE_MINIMAL)

class Appcompat_csv(Ingest):
    ingest_type = "appcompat_csv"
    file_name_filter = "(?:.*)(?:\/|\\\)(.*)\.csv$"

    def __init__(self):
        super(Appcompat_csv, self).__init__()

    def checkMagic(self, file_name_fullpath):
        # Check magic
        magic_id = self.id_filename(file_name_fullpath)
        if 'ShimCacheParser CSV' in magic_id:
            file_object = loadFile(file_name_fullpath)
            header = file_object.readline().strip()
            if header == "Last Modified,Last Update,Path,File Size,Exec Flag":
                return True
        return False

    def processFile(self, file_fullpath, hostID, instanceID, rowsData):
        rowNumber = 0
        rowValid = True
        minSQLiteDTS = datetime(1, 1, 1, 0, 0, 0)
        maxSQLiteDTS = datetime(9999, 12, 31, 0, 0, 0)

        file_object = loadFile(file_fullpath)
        csvdata = file_object.read().splitlines()[1:]
        file_object.close()

        data = csv.reader(csvdata, dialect='IngestDialect1')
        for row in data:
            for field in row:
                if b'\x00' in field:
                    settings.logger.warning("NULL byte found, ignoring bad shimcache parse: %s" % field)
                    rowValid = False

                try:
                    # Convert to timestamps:
                    if row[0] != 'N/A':
                        tmp_LastModified = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                    else: tmp_LastModified = minSQLiteDTS
                    if row[1] != 'N/A':
                        tmp_LastUpdate = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
                    else: tmp_LastUpdate = minSQLiteDTS

                except Exception as e:
                    print("crap")
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    logger.info("Exception processing row (%s): %s [%s / %s / %s]" % (
                    e.message, unicode(ntpath.split(row[2])[0]), exc_type, fname, exc_tb.tb_lineno))

            if rowValid:
                path, filename = ntpath.split(row[2])
                namedrow = settings.EntriesFields(HostID=hostID,
                    EntryType=settings.__APPCOMPAT__,
                    RowNumber=rowNumber,
                    LastModified=tmp_LastModified,
                    LastUpdate=tmp_LastUpdate,
                    FilePath=unicode(path),
                    FileName=unicode(filename),
                    Size=unicode(row[3]),
                    ExecFlag=str(row[4]),
                    InstanceID=instanceID)
                rowsData.append(namedrow)
                rowNumber += 1
