import settings
import logging
from ingest import Ingest
import xml.etree.ElementTree as ET
from appAux import loadFile
import hashlib
import ntpath
from datetime import datetime
import sys, traceback
import os

try:
    import xml.etree.cElementTree as etree
except ImportError:
    print "No cElementTree available falling back to python implementation!"
    settings.__CELEMENTREE__ = False
    import xml.etree.ElementTree as etree
else: settings.__CELEMENTREE__ = True

logger = logging.getLogger(__name__)
# Module to ingest AmCache data
# File name and format is what you get from a customized Mir AmCache LUA audit


class Amcache_mirlua_v1(Ingest):
    ingest_type = "amcache_mirlua_v1"
    file_name_filter = "(?:.*)(?:\/|\\\)(.*)-[A-Za-z0-9]{64}-\d{1,10}-\d{1,10}(?:_w32scripting-persistence.xml)$"

    def __init__(self):
        super(Amcache_mirlua_v1, self).__init__()

    def calculateID(self, file_name_fullpath):
        # Get the creation date for the first PersistenceItem in the audit (they will all be the same)
        instanceID = datetime.min
        tmp_instanceID = None

        # Parsing these huge xml files to grab the last modified data as an instance ID is slower than just hashing the whole thing:
        # try:
        #     file_object = loadFile(file_name_fullpath)
        #     root = ET.parse(file_object).getroot()
        #     file_object.close()
        #     reg_key = root.find('AmCacheItem')
        #     reg_modified = reg_key.get('created')
        #     try:
        #         tmp_instanceID = datetime.strptime(reg_modified, "%Y-%m-%dT%H:%M:%SZ")
        #     except ValueError as e:
        #         tmp_instanceID = datetime.max
        #         logger.warning("Invalid reg_modified date found!: %s (%s)" % (reg_modified, file_name_fullpath))
        #     instanceID = tmp_instanceID
        # except Exception:
        #     traceback.print_exc(file=sys.stdout)

        # If we found no AmCacheItem date we go with plan B and just hash the whole file
        if instanceID is None:
            file_object = loadFile(file_name_fullpath)
            content = file_object.read()
            instanceID = hashlib.md5(content).hexdigest()
            file_object.close()

        return instanceID

    def checkMagic(self, file_name_fullpath):
        # As long as we find one AmCacheItem PersistenceType we're declaring it good for us
        # Check magic
        magic_id = self.id_filename(file_name_fullpath)
        if 'XML' in magic_id:
            if 'Mir AmCache Lua_v1 file' in magic_id: return True
            else:
                file_object = loadFile(file_name_fullpath)
                try:
                    root = etree.parse(file_object).getroot()
                    if root.find('AmCacheItem'):
                        return True
                except Exception:
                    logger.warning("[%s] Failed to parse XML for: %s" % (self.ingest_type, file_name_fullpath))

        return False


    def _processElement(self, element, tag_dict, tag_prefix = ""):
        # Recursively process all tags and add them to a tag dictionary
        # We ignore tags that are duplicated in the FileAudit
        ignore_tags = ['FileOwner','FileCreated','FileModified','FileAccessed','FileChanged','md5sum','MagicHeader','SignatureExists','SignatureVerified','SignatureDescription','CertificateSubject','CertificateIssuer']
        for e in element:
            if e.tag not in ignore_tags:
                if len(e) > 0:
                    self._processElement(e, tag_dict, tag_prefix + e.tag + '_')
                else:
                    if tag_prefix + e.tag not in tag_dict:
                        if tag_prefix + e.tag == "ExecutionFlag":
                            tag_dict[tag_prefix + e.tag] = "True" if e.text == "1" else "False" if e.text == "0" else e.text
                        else:
                            tag_dict[tag_prefix + e.tag] = e.text
                    else:
                        # Aggregate some tags when required
                        tag_dict[tag_prefix + e.tag] = tag_dict[tag_prefix + e.tag] + ", " + e.text

    def processFile(self, file_fullpath, hostID, instanceID, rowsData):
        minSQLiteDTS = datetime(1, 1, 1, 0, 0, 0)
        maxSQLiteDTS = datetime(9999, 12, 31, 0, 0, 0)
        # alltags = set()
        tag_mapping = [
            ('AmCacheCompanyName', 'N/A'),
            ('AmCacheCompileTime', 'N/A'),
            ('AmCacheCreated', 'N/A'),
            ('AmCacheFileDescription', 'N/A'),
            ('AmCacheFilePath', 'N/A'),
            ('AmCacheFileSize', 'N/A'),
            ('AmCacheFileVersionNumber', 'N/A'),
            ('AmCacheFileVersionString', 'N/A'),
            ('AmCacheLanguageCode', 'N/A'),
            ('AmCacheLastModified', 'N/A'),
            ('AmCacheLastModified2', 'N/A'),
            ('AmCachePEHeaderChecksum', 'N/A'),
            ('AmCachePEHeaderHash', 'N/A'),
            ('AmCachePEHeaderSize', 'N/A'),
            ('AmCacheProductName', 'N/A'),
            ('AmCacheProgramID', 'N/A'),
            ('AmCacheSha1', 'SHA1'),
            ('FileItem_Accessed', 'N/A'),
            ('FileItem_Changed', 'N/A'),
            ('FileItem_Created', 'N/A'),
            ('FileItem_DevicePath', 'N/A'),
            ('FileItem_Drive', 'N/A'),
            ('FileItem_FileAttributes', 'N/A'),
            ('FileItem_FileExtension', 'N/A'),
            ('FileItem_FileName', 'N/A'),
            ('FileItem_FilePath', 'N/A'),
            ('FileItem_FullPath', 'N/A'),
            ('FileItem_Md5sum', 'N/A'),
            ('FileItem_Modified', 'N/A'),
            ('FileItem_PEInfo_BaseAddress', 'N/A'),
            ('FileItem_PEInfo_DigitalSignature_Description', 'N/A'),
            ('FileItem_PEInfo_ExtraneousBytes', 'N/A'),
            ('FileItem_PEInfo_PEChecksum_PEComputedAPI', 'N/A'),
            ('FileItem_PEInfo_PEChecksum_PEFileAPI', 'N/A'),
            ('FileItem_PEInfo_PEChecksum_PEFileRaw', 'N/A'),
            ('FileItem_PEInfo_PETimeStamp', 'N/A'),
            ('FileItem_PEInfo_Subsystem', 'N/A'),
            ('FileItem_PEInfo_Type', 'N/A'),
            ('FileItem_SecurityID', 'N/A'),
            ('FileItem_SecurityType', 'N/A'),
            ('FileItem_SizeInBytes', 'N/A'),
            ('FileItem_Username', 'N/A'),
            ('ProgramEntryPresent', 'N/A'),
            ('ProgramInstallDate', 'N/A'),
            ('ProgramInstallSource', 'N/A'),
            ('ProgramLocaleID', 'N/A'),
            ('ProgramName', 'N/A'),
            ('ProgramPackageCode', 'N/A'),
            ('ProgramPackageCode2', 'N/A'),
            ('ProgramUninstallKey', 'N/A'),
            ('ProgramUnknownTimestamp', 'N/A'),
            ('ProgramVendorName', 'N/A'),
            ('ProgramVersion', 'N/A')]

        rowNumber = 0
        check_tags = ['AmCacheLastModified2']
        try:
            xml_data = loadFile(file_fullpath)
            for event, element in etree.iterparse(xml_data, events=("end",)):
                skip_entry = False
                tag_dict = {}
                if element.tag == "AmCacheItem":
                    self._processElement(element, tag_dict)

                    # Check we have everything we need and ignore entries with critical XML errors on them
                    for tag in check_tags:
                        if tag not in tag_dict:
                                if 'AmCacheFilePath' in tag_dict:
                                    logger.warning("Missing tag [%s] in %s, entry: %s (skipping entry)" % (tag, tag_dict['AmCacheFilePath'], file_fullpath))
                                else:
                                    logger.warning("Malformed tag [%s] in %s, entry: Unknown (skipping entry)" % (tag, file_fullpath))
                                skip_entry = True
                                break
                        if tag_dict[tag] is None:
                                if 'AmCacheFilePath' in tag_dict:
                                    logger.warning("Malformed tag [%s: %s] in %s, entry: %s (skipping entry)" % (tag, tag_dict[tag], tag_dict['AmCacheFilePath'], file_fullpath))
                                else:
                                    logger.warning("Malformed tag [%s: %s] in %s, entry: Unknown (skipping entry)" % (tag, tag_dict[tag], file_fullpath))
                                skip_entry = True
                                break

                    # Some entries in AmCache do not refer to files per se (like installed program entries)
                    # We don't have much use for them right now but let's keep the data there until I figure what to do with them
                    if 'AmCacheFilePath' not in tag_dict:
                        if 'ProgramName' in tag_dict:
                            tag_dict['AmCacheFilePath'] = tag_dict['ProgramName']
                        else:
                            # If we have no thing we can use here we skip the entry for now
                            # todo: pretty-print the tag_dict to the log file
                            logger.warning("AmCache entry with no AppCompatPath or ProgramName. (skipping entry)")
                            break

                    # If the entry is valid do some housekeeping:
                    if not skip_entry:
                        if 'ExecutionFlag' in tag_dict:
                            if tag_dict['ExecutionFlag'] == '1':
                                tmpExecFlag = True
                            elif tag_dict['ExecutionFlag'] == '0':
                                tmpExecFlag = False
                            else: tmpExecFlag = tag_dict['ExecutionFlag']
                        else:
                            # todo: Not all OS's have exec flag. Need to change the schema to reflect those cases!
                            tmpExecFlag = False

                        try:
                            # Convert TS to datetime format
                            if 'LastModified' in tag_dict:
                                tmp_LastModified = tag_dict['LastModified'].replace("T", " ").replace("Z", "")
                                if type(tmp_LastModified) is not datetime:
                                    tmp_LastModified = datetime.strptime(tmp_LastModified, "%Y-%m-%d %H:%M:%S")
                            else: tmp_LastModified = minSQLiteDTS

                            if 'LastUpdate' in tag_dict:
                                tmp_LastUpdate = tag_dict['LastUpdate'].replace("T", " ").replace("Z", "")
                                if type(tmp_LastUpdate) is not datetime:
                                    tmp_LastUpdate = datetime.strptime(tmp_LastUpdate, "%Y-%m-%d %H:%M:%S")
                            else: tmp_LastUpdate = minSQLiteDTS


                            row_dict = {}
                            row_dict['HostID'] = hostID
                            row_dict['EntryType'] = settings.__APPCOMPAT__
                            row_dict['RowNumber'] = rowNumber
                            row_dict['InstanceID'] = instanceID
                            row_dict['LastModified'] = tmp_LastModified
                            row_dict['LastUpdate'] = tmp_LastUpdate
                            row_dict['FileName'] = ntpath.basename(tag_dict['AmCacheFilePath'])
                            row_dict['FilePath'] = ntpath.dirname(tag_dict['AmCacheFilePath'])
                            row_dict['Size'] = (tag_dict['Size'] if 'Size' in tag_dict else 'N/A')
                            row_dict['ExecFlag'] = tmpExecFlag

                            # for tag in tag_dict.keys():
                            #     alltags.add(tag)

                            # Add all tags available with mappings to our database schema
                            for src_tag, dest_tag in tag_mapping:
                                if dest_tag <> 'N/A':
                                    if src_tag in tag_dict:
                                        row_dict[dest_tag] = tag_dict[src_tag]

                            namedrow = settings.EntriesFields(**row_dict)
                            rowsData.append(namedrow)
                            rowNumber += 1
                        except Exception as e:
                            print("crap")
                            exc_type, exc_obj, exc_tb = sys.exc_info()
                            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                            logger.info("Exception processing row (%s): %s [%s / %s / %s]" % (
                            e.message, element, exc_type, fname, exc_tb.tb_lineno))
            else:
                pass
                element.clear()
            xml_data.close()
        except Exception as e:
            print e.message
            print traceback.format_exc()
            pass

        print alltags