import settings
import logging
from ingest import Ingest
import xml.etree.ElementTree as ET
from appAux import loadFile
import hashlib
import ntpath
from datetime import datetime
import sys, traceback

try:
    import xml.etree.cElementTree as etree
except ImportError:
    print "No cElementTree available falling back to python implementation!"
    settings.__CELEMENTREE__ = False
    import xml.etree.ElementTree as etree
else: settings.__CELEMENTREE__ = True


logger = logging.getLogger(__name__)
# Module to ingest AppCompat data
# File name and format is what you get from a customized Mir AppCompat LUA audit
# Note: Enrichment file data is not currently pulled for this format
# Note: Deprecated format

class Appcompat_mirlua_v1(Ingest):
    ingest_type = "appcompat_mirlua_v1"
    file_name_filter = "(?:.*)(?:\/|\\\)(.*)-[A-Za-z0-9]{64}-\d{1,10}-\d{1,10}(?:_w32scripting-persistence.xml)$"

    def __init__(self):
        super(Appcompat_mirlua_v1, self).__init__()

    def calculateID(self, file_name_fullpath):
        # Get the creation date for the first PersistenceItem in the audit (they will all be the same)
        instanceID = datetime.min
        tmp_instanceID = None

        try:
            file_object = loadFile(file_name_fullpath)
            root = ET.parse(file_object).getroot()
            file_object.close()
            reg_key = root.find('PersistenceItem')
            reg_modified = reg_key.get('created')
            try:
                tmp_instanceID = datetime.strptime(reg_modified, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError as e:
                tmp_instanceID = datetime.max
                logger.warning("Invalid reg_modified date found!: %s (%s)" % (reg_modified, file_name_fullpath))
            instanceID = tmp_instanceID
        except Exception:
            traceback.print_exc(file=sys.stdout)

        # If we found no PersistenceItem date we go with plan B (but most probably this is corrupt and will fail later)
        if instanceID is None:
            file_object = loadFile(file_name_fullpath)
            content = file_object.read()
            instanceID = hashlib.md5(content).hexdigest()
            file_object.close()

        return instanceID

    def checkMagic(self, file_name_fullpath):
        # As long as we find one Appcompat PersistenceType we're declaring it good for us
        # Check magic
        magic_id = self.id_filename(file_name_fullpath)
        if 'XML' in magic_id:
            file_object = loadFile(file_name_fullpath)
            try:
                root = etree.parse(file_object).getroot()
                # todo: replace findall with find
                for reg_key in root.findall('PersistenceItem'):
                    if reg_key.find('PersistenceType').text.lower() == "Appcompat".lower():
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
        rowNumber = 0
        check_tags = ['LastModified', 'FilePath', 'ExecutionFlag']
        # the 'end' event signifies when the end of the XML node has been reached,
        # and therefore when all values can be parsed
        try:
            xml_data = loadFile(file_fullpath)
            for event, element in etree.iterparse(xml_data, events=("end",)):
                skip_entry = False
                tag_dict = {}
                if element.tag == "PersistenceItem":
                    self._processElement(element, tag_dict)

                    # Check we have everything we need and ignore entries with critical XML errors on them
                    for tag in check_tags:
                        if tag in tag_dict:
                            if tag_dict[tag] is None:
                                if 'AppCompatPath' in tag_dict:
                                    logger.warning("Malformed tag [%s: %s] in %s, entry: %s (skipping entry)" % (tag, tag_dict[tag], tag_dict['AppCompatPath'], file_fullpath))
                                else:
                                    logger.warning(
                                        "Malformed tag [%s: %s] in %s, entry: Unknown (skipping entry)" % (tag, tag_dict[tag], file_fullpath))
                                skip_entry = True
                                break
                    # If the entry is valid do some housekeeping:
                    if not skip_entry:
                        if tag_dict['ExecutionFlag'] == '1':
                            tmpExexFlag = True
                        elif tag_dict['ExecutionFlag'] == '0':
                            tmpExexFlag = False
                        else: tmpExexFlag = tag_dict['ExecutionFlag']
                        namedrow = settings.EntriesFields(HostID=hostID, EntryType=settings.__APPCOMPAT__,
                              RowNumber=rowNumber,
                              InstanceID=instanceID,
                              LastModified=(tag_dict['LastModified'].replace("T"," ").replace("Z","") if 'LastModified' in tag_dict else '0001-01-01 00:00:00'),
                              LastUpdate=(tag_dict['LastUpdate'].replace("T"," ").replace("Z","") if 'LastUpdate' in tag_dict else '0001-01-01 00:00:00'),
                              FileName=ntpath.basename(tag_dict['FilePath']),
                              FilePath=ntpath.dirname(tag_dict['FilePath']),
                              Size=(tag_dict['Size'] if 'Size' in tag_dict else 'N/A'),
                              ExecFlag=tmpExexFlag)
                        rowsData.append(namedrow)
                        rowNumber += 1
            else:
                pass
                element.clear()
            xml_data.close()
        except Exception as e:
            print e.message
            print traceback.format_exc()
            pass