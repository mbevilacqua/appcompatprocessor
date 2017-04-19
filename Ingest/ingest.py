import logging
import re
import hashlib
from appAux import loadFile

logger = logging.getLogger(__name__)

class Ingest(object):
    # Base class used to encapsulate the logic required to ingest entries in different formats
    # ingest_type: Iternal ID for the ingest plugin
    ingest_type = ""
    # file_name_filter: Filter that must match on fullpath on files to be processed by the ingest module
    file_name_filter = ""

    def __init__(self):
        pass

    def getIngestType(self):
        return self.ingest_type

    def getFileNameFilter(self):
        return self.file_name_filter

    def matchFileNameFilter(self, file_name_fullpath):
        # Check if our file_name_filter would match on the file we're looking at
        m = re.match(self.file_name_filter, file_name_fullpath)
        if m: return True
        else: return False

    def getHostName(self, file_name_fullpath):
        # We assume the hostname is the first capture group from the file_name_filter, override if not the case
        m = re.match(self.file_name_filter, file_name_fullpath)
        if m: return m.group(1)

    def checkMagic(self, file_name_fullpath):
        # Validate the file is actually a file the ingect pulgin can work with
        # Ingest plugins _must_ override this
        return True

    def calculateID(self, file_name_fullpath):
        # Lazy instanceID calculation, overwrite to make it faster if possible for the ingest format
        instanceID = None
        content_file = loadFile(file_name_fullpath)
        content = content_file.read()
        content_file.close()
        instanceID = hashlib.md5(content).hexdigest()
        return instanceID

    def processFile(self, file_fullpath, hostID, instanceID, rowsData):
        # Extract entries from file and return in rowsData
        # Ingest plugins _must_ override this
        raise NotImplementedError