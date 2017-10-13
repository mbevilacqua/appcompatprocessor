import settings
import logging
from ingest import Ingest
from appAux import loadFile
import ntpath
import csv

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
        file_object = loadFile(file_fullpath)
        csvdata = file_object.read().splitlines()[1:]
        file_object.close()

        data = csv.reader(csvdata, dialect='IngestDialect1')
        for row in data:
            for field in row:
                if b'\x00' in field:
                    settings.logger.warning("NULL byte found, ignoring bad shimcache parse: %s" % field)
                    rowValid = False
            if rowValid:
                path, filename = ntpath.split(row[2])
                namedrow = settings.EntriesFields(HostID=hostID, EntryType=settings.__APPCOMPAT__, RowNumber=rowNumber,
                                                  LastModified=unicode(row[0]), LastUpdate=unicode(row[1]),
                                                  FilePath=unicode(path),
                                                  FileName=unicode(filename), Size=unicode(row[3]),
                                                  ExecFlag=str(row[4]), InstanceID=instanceID)
                rowsData.append(namedrow)
                rowNumber += 1
