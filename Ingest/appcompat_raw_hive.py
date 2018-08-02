import settings
import logging
import struct
from ingest import Ingest
from appAux import loadFile
import pyregf
import settings
import re
from datetime import datetime
from ShimCacheParser_ACP import read_from_hive, write_it

logger = logging.getLogger(__name__)
# Module to ingest AppCompat data
# File name must start with "SYSTEM"
# Host name is extracted from the actual hive

class Appcompat_Raw_hive(Ingest):
    ingest_type = "appcompat_raw_hive"
    file_name_filter = "(?:.*)(?:\/|\\\)SYSTEM.*$"

    def __init__(self):
        super(Appcompat_Raw_hive, self).__init__()

    def getHostName(self, file_name_fullpath):
        file_object = loadFile(file_name_fullpath)
        regf_file = pyregf.file()
        regf_file.open_file_object(file_object, "r")
        # Get control set number
        tmp_key = regf_file.get_key_by_path(r'Select')
        if tmp_key is not None:
            controlset_number = tmp_key.get_value_by_name('Current').get_data_as_integer()
            # Get host name
            tmp_key = regf_file.get_key_by_path(r'ControlSet00' + str(controlset_number) + '\Control\ComputerName\ComputerName')
            host_name = tmp_key.get_value_by_name('ComputerName').get_data_as_string()
        else:
            # todo: Close everything down elegantly
            logger.error("Attempting to process non-SYSTEM hive with appcompat_raw_hive plugin: %s" % file_name_fullpath)
            raise(Exception('Attempting to process non-SYSTEM hive with appcompat_raw_hive plugin'))

        # Need to close these or the memory will never get freed:
        regf_file.close()
        del regf_file
        file_object.close()
        del file_object
        return host_name

    def checkMagic(self, file_name_fullpath):
        magic_ok = False
        # Check magic
        magic_id = self.id_filename(file_name_fullpath)
        if 'registry' in magic_id:
            file_object = loadFile(file_name_fullpath)
            regf_file = pyregf.file()
            regf_file.open_file_object(file_object, "r")
            magic_key = regf_file.get_key_by_path(r'Select')
            regf_file.close()
            del regf_file
            if magic_key is not None:
                magic_ok = True

            # Need to close these or the memory will never get freed:
            file_object.close()
            del file_object

        return magic_ok

    def calculateID(self, file_name_fullpath):
        instanceID = 0
        file_object = loadFile(file_name_fullpath)
        regf_file = pyregf.file()
        regf_file.open_file_object(file_object, "r")

        # Search for key containing ShimCache entries on all control sets
        # Use last modification time of the last modified one as instanceID
        root = regf_file.get_root_key()
        num_keys = root.get_number_of_sub_keys()
        for i in xrange(0,num_keys):
            tmp_key = root.get_sub_key(i)
            if "controlset" in tmp_key.get_name().lower():
                session_man_key = regf_file.get_key_by_path("%s\Control\Session Manager" % tmp_key.get_name())
                num_keys = session_man_key.get_number_of_sub_keys()
                for i in xrange(0, num_keys):
                    tmp_key = session_man_key.get_sub_key(i)
                    if "appcompatibility" in tmp_key.get_name().lower() or "appcompatcache" in tmp_key.get_name().lower():
                        last_write_time = tmp_key.get_last_written_time_as_integer()
                        if last_write_time > instanceID: instanceID = last_write_time
                        break

        # Need to close these or the memory will never get freed:
        regf_file.close()
        del regf_file
        file_object.close()
        del file_object
        return instanceID

    def processFile(self, file_fullpath, hostID, instanceID, rowsData):
        rowNumber = 0
        entries = None
        minSQLiteDTS = datetime(1, 1, 1, 0, 0, 0)
        maxSQLiteDTS = datetime(9999, 12, 31, 0, 0, 0)

        # Process file using ShimCacheParser
        try:
            entries = read_from_hive(file_fullpath, True)
            if not entries:
                logger.warning("[ShimCacheParser] found no entries for %s" % file_fullpath)
                return False
            else:
                rows = write_it(entries, "StringIO")[1:]
        except IOError, err:
            logger.error("[ShimCacheParser] Error opening binary file: %s" % str(err))

        # Process records
        appCompatREGEX = re.compile(
            "((?:\d\d\d\d\-\d\d\-\d\d \d\d:\d\d:\d\d)|N\/A)[, ]((?:\d\d\d\d\-\d\d\-\d\d \d\d:\d\d:\d\d)|N\/A)[, ](.*)\\\([^\\\]*)[, ](N\/A|\d*)[, ](N\/A|True|False)")
        assert (rows is not None)
        for r in rows:
            if b'\x00' in r:
                logger.debug("NULL byte found, skipping bad shimcache parse: %s" % r)
                continue
            m = appCompatREGEX.match(r)
            if m:
                try:
                    # Convert to timestamps:
                    if m.group(1) != 'N/A':
                        tmp_LastModified = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                    else: tmp_LastModified = minSQLiteDTS
                    if m.group(2) != 'N/A':
                        tmp_LastUpdate = datetime.strptime(m.group(2), "%Y-%m-%d %H:%M:%S")
                    else: tmp_LastUpdate = minSQLiteDTS

                except Exception as e:
                    print("crap")
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    logger.info("Exception processing row (%s): %s [%s / %s / %s]" % (
                    e.message, unicode(ntpath.split(row[2])[0]), exc_type, fname, exc_tb.tb_lineno))

                namedrow = settings.EntriesFields(HostID=hostID, EntryType=settings.__APPCOMPAT__,
                                                  RowNumber=rowNumber,
                                                  LastModified=tmp_LastModified,
                                                  LastUpdate=tmp_LastUpdate,
                                                  FilePath=unicode(m.group(3)),
                                                  FileName=unicode(m.group(4)),
                                                  Size=unicode(m.group(5)),
                                                  ExecFlag=str(m.group(6)),
                                                  InstanceID=instanceID)
                rowsData.append(namedrow)
                rowNumber += 1
            else:
                logger.warning("Entry regex failed for: %s - %s" % (hostID, r))
