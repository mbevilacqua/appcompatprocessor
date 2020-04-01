import settings
import logging
from ingest import Ingest
from datetime import datetime
import xml.etree.ElementTree as ET
from appAux import loadFile
import hashlib
import re
from ShimCacheParser_ACP import read_mir, write_it
import traceback

logger = logging.getLogger(__name__)
# Module to ingest AppCompat data in XML format
# File name and format is what you get from a Mir RegistryAudit


class Appcompat_mirregistryaudit(Ingest):
    ingest_type = "appcompat_mirregistryaudit"
    file_name_filter = "(?:.*)(?:\/|\\\)(.*)(?:-[A-Za-z0-9]{64}-\d{1,10}-\d{1,10}_w32registry.xml|_[A-Za-z0-9]{22}\.xml)$"

    def __init__(self):
        super(Appcompat_mirregistryaudit, self).__init__()

    def calculateID(self, file_name_fullpath):
        instanceID = datetime.min
        tmp_instanceID = None

        try:
            file_object = loadFile(file_name_fullpath)
            root = ET.parse(file_object).getroot()
            file_object.close()
            for reg_key in root.findall('RegistryItem'):
                tmp_reg_key = reg_key.find('Modified')
                if tmp_reg_key is not None:
                    reg_modified = tmp_reg_key.text
                    try:
                        tmp_instanceID = datetime.strptime(reg_modified, "%Y-%m-%dT%H:%M:%SZ")
                    except ValueError as e:
                        tmp_instanceID = datetime.max
                        logger.warning("Invalid reg_modified date found!: %s (%s)" % (reg_modified, file_name_fullpath))
                    if instanceID < tmp_instanceID:
                        instanceID = tmp_instanceID
                else:
                    logger.warning("Found RegistryItem with no Modified date (Mir bug?): %s" % file_name_fullpath)
        except Exception:
            logger.exception("Error on calculateID for: %s" % file_name_fullpath)

        # If we found no Modified date in any of the RegistryItems we go with plan B (but most probably ShimCacheParser will fail to parse anyway)
        if instanceID is None:
            file_object = loadFile(file_name_fullpath)
            content = file_object.read()
            instanceID = hashlib.md5(content).hexdigest()
            file_object.close()

        return instanceID


    def checkMagic(self, file_name_fullpath):
        # As long as we find one AppcompatCache key we're declaring it good for us
        # Check magic
        magic_id = self.id_filename(file_name_fullpath)
        if 'XML' in magic_id:
            file_object = loadFile(file_name_fullpath)
            try:
                root = ET.parse(file_object).getroot()
                # todo: relpace findall with find:
                for reg_key in root.findall('RegistryItem'):
                    if reg_key.find('ValueName').text == "AppCompatCache":
                        return True
            except Exception:
                logger.warning("[%s] Failed to parse XML for: %s" % (self.ingest_type, file_name_fullpath))
            finally:
                file_object.close()

        return False


    def processFile(self, file_fullpath, hostID, instanceID, rowsData):
        # Returns data in rowsData
        minSQLiteDTS = datetime(1, 1, 1, 0, 0, 0)
        maxSQLiteDTS = datetime(9999, 12, 31, 0, 0, 0)
        rowNumber = 0

        check_tags = ['LastModified', 'AppCompatPath']
        try:
            # Process file using ShimCacheParser
            try:
                xml_data = loadFile(file_fullpath)
                (error, entries) = read_mir(xml_data, True)
                xml_data.close()

                assert(not error)
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
                        else:
                            tmp_LastModified = minSQLiteDTS
                        if m.group(2) != 'N/A':
                            tmp_LastUpdate = datetime.strptime(m.group(2), "%Y-%m-%d %H:%M:%S")
                        else:
                            tmp_LastUpdate = minSQLiteDTS

                    except Exception as e:
                        print("crap")
                        exc_type, exc_obj, exc_tb = sys.exc_info()
                        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                        logger.info("Exception processing row (%s): %s [%s / %s / %s]" % (
                            e.message, file_fullpath, exc_type, fname, exc_tb.tb_lineno))

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
        except Exception as e:
            print e.message
            print traceback.format_exc()
            pass