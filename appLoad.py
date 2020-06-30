__author__ = 'matiasbevilacqua'

import logging
from mpEngineProdCons import MPEngineProdCons
from mpEngineWorker import MPEngineWorker
import Queue
import os
import re
import sqlite3
import ntpath
from contextlib import closing
import time
import struct
from appAux import update_progress, chunks, loadFile, psutil_phymem_usage, file_size
import appDB
import settings
from ShimCacheParser_ACP import read_mir, write_it
from AmCacheParser import _processAmCacheFile_StringIO
import zipfile
# import contextlib
from datetime import timedelta, datetime
import sys
import traceback
import gc
import cProfile
from Ingest import issues_document
from Ingest import appcompat_hxregistryaudit
from Ingest import appcompat_parsed
from Ingest import appcompat_mirregistryaudit
from Ingest import amcache_miracquisition
from Ingest import appcompat_mirlua_v1
from Ingest import appcompat_mirlua_v2
from Ingest import amcache_mirlua_v1
from Ingest import appcompat_csv
from Ingest import appcompat_redline
from Ingest import appcompat_raw_hive
from Ingest import appcompat_miracquisition
from Ingest import amcache_raw_hive
from Ingest import appcompat_mirShimShady_v1
import json

try:
    import pyregf
except ImportError:
    if settings.__PYREGF__:
        settings.__PYREGF__ = False
        print "Ooops seems you don't have pyregf!"
        print "AmCache loading support will be disabled"
else: settings.__PYREGF__ = True


logger = logging.getLogger(__name__)
_tasksPerJob = 10
supported_ingest_plugins = ['issues_document.Issues_document',
                            'appcompat_hxregistryaudit.Appcompat_hxregistryaudit',
                            'appcompat_mirShimShady_v1.Appcompat_mirShimShady_v1',
                            'appcompat_parsed.Appcompat_parsed', 'amcache_miracquisition.Amcache_miracquisition',
                            'appcompat_mirregistryaudit.Appcompat_mirregistryaudit', 'amcache_mirlua_v1.Amcache_mirlua_v1',
                            'appcompat_mirlua_v2.Appcompat_mirlua_v2', 'appcompat_csv.Appcompat_csv',
                            'appcompat_redline.Appcompat_redline', 'appcompat_raw_hive.Appcompat_Raw_hive',
                            'appcompat_miracquisition.Appcompat_miracquisition', 'amcache_raw_hive.Amcache_Raw_hive']

# Load IngestTypes
ingest_plugins = {}
ingest_plugins_types_stack = []
for plugin in supported_ingest_plugins:
    ingest_plugins[eval(plugin).ingest_type] = eval(plugin)()
    ingest_plugins_types_stack.append(eval(plugin).ingest_type)


def do_cprofile(func):
    def profiled_func(*args, **kwargs):
        profile = cProfile.Profile()
        try:
            profile.enable()
            result = func(*args, **kwargs)
            profile.disable()
            return result
        finally:
            profile.print_stats()
    return profiled_func


class appLoadProd(MPEngineWorker):

    def _notInRange(self, start, end, x):
        """Return true if x is in the range [start, end]"""
        if start <= end:
            return not (start <= x <= end)
        else:
            return not (start <= x or x <= end)

    def do_work(self, next_task):
        self.logger.debug("do_work")
        rowsData = next_task()

        # Sanityzing entries
        for x in rowsData:
            # Check if we've been killed
            self.check_killed()
            sanityCheckOK = True
            try:
                # Sanity check dates:
                # We need to exclude these entries as the SQLite driver would die later when queried
                minSQLiteDTS = datetime(1, 1, 1, 0, 0, 0)
                maxSQLiteDTS = datetime(9999, 12, 31, 0, 0, 0)
                if x.EntryType == settings.__AMCACHE__:

                    if self._notInRange(minSQLiteDTS, maxSQLiteDTS, x.FirstRun):
                        sanityCheckOK = False
                        settings.logger.warning(
                            "Weird FirstRun date, ignoring as this will kill sqlite on query: %s - %s - %s" % (
                            x.HostID, x.FilePath, x.FirstRun))
                    if self._notInRange(minSQLiteDTS, maxSQLiteDTS, x.Modified1):
                        sanityCheckOK = False
                        settings.logger.warning(
                            "Weird Modified1 date, ignoring as this will kill sqlite on query: %s - %s - %s" % (
                            x.HostID, x.FilePath, x.Modified1))
                    if self._notInRange(minSQLiteDTS, maxSQLiteDTS, x.Modified2):
                        sanityCheckOK = False
                        settings.logger.warning(
                            "Weird Modified2 date, ignoring as this will kill sqlite on query: %s - %s - %s" % (
                            x.HostID, x.FilePath, x.Modified2))
                    if self._notInRange(minSQLiteDTS, maxSQLiteDTS, x.LinkerTS):
                        sanityCheckOK = False
                        settings.logger.warning(
                            "Weird LinkerTS date, ignoring as this will kill sqlite on query: %s - %s - %s" % (
                            x.HostID, x.FilePath, x.LinkerTS))

                if x.EntryType == settings.__APPCOMPAT__:
                    if x.FirstRun is not None:
                        if self._notInRange(minSQLiteDTS, maxSQLiteDTS, x.FirstRun):
                            sanityCheckOK = False
                            settings.logger.warning(
                                "Weird FirstRun date, ignoring as this will kill sqlite on query: %s - %s - %s" % (
                                x.HostID, x.FilePath, x.FirstRun))

                    if x.LastModified is not None:
                        if self._notInRange(minSQLiteDTS, maxSQLiteDTS, x.LastModified):
                            sanityCheckOK = False
                            settings.logger.warning(
                                "Weird LastModified date, ignoring as this will kill sqlite on query: %s - %s - %s" % (
                                x.HostID, x.FilePath, x.LastModified))

                    if x.LastUpdate is not None:
                        if self._notInRange(minSQLiteDTS, maxSQLiteDTS, x.LastUpdate):
                            sanityCheckOK = False
                            settings.logger.warning(
                                "Weird LastUpdate date, ignoring as this will kill sqlite on query: %s - %s - %s" % (
                                x.HostID, x.FilePath, x.LastUpdate))

                if sanityCheckOK:
                    # We use FirstRun as LastModified for AmCache entries
                    # We use Modified2 as LastUpdate for AmCache entries
                    if x.EntryType == settings.__AMCACHE__:
                        x.LastModified = x.FirstRun
                        x.LastUpdate = x.Modified2

                    # Should be able to remove this from here once all ingest plugins deliver datetimes consistently:
                    if type(x.LastModified) != datetime:
                        # todo: Maybe we don't need this after the ISO patch to ShimCacheParser?
                        if x.LastModified != "N/A" and x.LastModified != None:
                            if x.LastModified == '0000-00-00 00:00:00':
                                settings.logger.warning("LastModified TS set to 0000-00-00 00:00:00 (%s)" % x)
                                x.LastModified = datetime.min
                            else:
                                x.LastModified = datetime.strptime(x.LastModified, "%Y-%m-%d %H:%M:%S")
                        else:
                            x.LastModified = datetime.min

                    if type(x.LastUpdate) != datetime:
                        if x.LastUpdate != "N/A" and x.LastUpdate != None:
                            if x.LastUpdate == '0000-00-00 00:00:00':
                                settings.logger.warning("LastUpdate TS set to 0000-00-00 00:00:00 (%s)" % x)
                                x.LastUpdate = datetime.min
                            else:
                                x.LastUpdate = datetime.strptime(x.LastUpdate, "%Y-%m-%d %H:%M:%S")
                        else:
                            x.LastUpdate = datetime.min

                    # Sanitize things up (AmCache is full of these 'empty' entries which I don't have a clue what they are yet)
                    if x.FilePath is None:
                        x.FilePath = "None"
                    else:
                        x.FilePath = x.FilePath.replace("'", "''")
                        # Trim out UNC path prefix
                        x.FilePath = x.FilePath.replace("\\??\\", "")
                        # Trim out SYSVOL path prefix
                        x.FilePath = x.FilePath.replace("SYSVOL", "C:")
                    if x.FileName is None:
                        x.FileName = "None"
                    else:
                        x.FileName = x.FileName.replace("'", "''")

                if not sanityCheckOK:
                    rowsData.remove(x)
            except Exception as e:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                self.logger.warning("Exception processing row (%s): %s [%s / %s / %s]" % (e.message, x, exc_type, fname, exc_tb.tb_lineno))

                # Skip row:
                rowsData.remove(x)
                pass
        return rowsData


class appLoadCons(MPEngineWorker):

    def run(self):
        # Note: __init__ runs on multiprocessing's main thread and as such we can't use that to init a sqlite connection
        assert(len(self.extra_arg_list) == 1)
        self.dbfilenameFullPath = self.extra_arg_list[0]
        self.DB = None
        self.conn = None

        # Init DB access to DB
        self.DB = appDB.DBClass(self.dbfilenameFullPath, True, settings.__version__)
        # self.DB.appInitDB()
        self.conn = self.DB.appConnectDB()

        # Call super run to continue with the natural worker flow
        super(appLoadCons, self).run()

        # Close DB connection
        self.logger.debug("%s - closing down DB" % self.proc_name)
        self.conn.close()
        del self.DB


    def do_work(self, entries_fields_list):
        self.logger.debug("do_work")
        number_of_grabbed_tasks = 1
        min_bucket = _tasksPerJob * 5
        max_bucket = _tasksPerJob * 10
        bucket_ready = False

        if entries_fields_list:
            numFields = len(entries_fields_list[0]._asdict().keys()) - 4
            valuesQuery = "(NULL," + "?," * numFields + "0, 0)"
            try:
                insertList = []
                with closing(self.conn.cursor()) as c:
                    # Grab a bunch of results to reduce # of DB commits
                    while not bucket_ready:
                        try:
                            self.logger.debug("%s - trying to grab additional task" % self.proc_name)
                            tmp = self.task_queue.get_nowait()
                            number_of_grabbed_tasks += 1
                            self.update_progress()
                            entries_fields_list.extend(tmp)
                        except Queue.Empty:
                            # If we're over min_bucket we can proceed
                            if number_of_grabbed_tasks > min_bucket:
                                logger.debug("%s - Over min_bucket" % self.proc_name)
                                bucket_ready = True
                            else:
                                # Grab tasks and progress
                                with self.available_task_num.get_lock():
                                    available_task_num = self.available_task_num.value
                                with self.progress_counter.get_lock():
                                    progress_counter = self.progress_counter.value
                                # If we just have to wait to get enough tasks to fill our bucket we wait
                                if self.total_task_num - progress_counter > min_bucket:
                                    self.logger.debug("%s - waiting for bucket to be filled (%d/%d), sleeping" %
                                                        (self.proc_name, number_of_grabbed_tasks, min_bucket))
                                    time.sleep(1)
                                else:
                                    self.logger.debug("%s - Going for the last bucket!" % self.proc_name)
                                    bucket_ready = True

                        #If we've reached max_bucket we move on to consume it
                        if number_of_grabbed_tasks > max_bucket:
                            bucket_ready = True

                    for x in entries_fields_list:
                        # Ugly hack as some versions of libregf seems to return utf16 for some odd reason
                        # Does not work as some stuff will decode correctly when it's not really UTF16, need to find root cause to decode when required only.
                        # if x.FilePath is not None:
                        #     try:
                        #         tmp_file_path = (x.FilePath).decode('utf-16')
                        #         # print "string is UTF-8, length %d bytes" % len(string)
                        #     except UnicodeError:
                        #         tmp_file_path = x.FilePath
                        #         # print "string is not UTF-8"

                        tmp_file_path = x.FilePath
                        # Add FilePath if not there yet
                        c.execute("INSERT OR IGNORE INTO FilePaths VALUES (NULL, '%s')" % tmp_file_path)
                        # Get assigned FilePathID
                        x.FilePathID = self.DB.QueryInt("SELECT FilePathID FROM FilePaths WHERE FilePath = '%s'" % tmp_file_path)

                        # Append the record to our insertList
                        # Note: Info from AmCache is already in datetime format
                        insertList.append((x.HostID, x.EntryType, x.RowNumber, x.LastModified, x.LastUpdate, x.FilePathID, \
                                           x.FileName, x.Size, x.ExecFlag, x.SHA1, x.FileDescription, x.FirstRun, x.Created, \
                                           x.Modified1, x.Modified2, x.LinkerTS, x.Product, x.Company, x.PE_sizeofimage, \
                                           x.Version_number, x.Version, x.Language, x.Header_hash, x.PE_checksum, str(x.SwitchBackContext), x.InstanceID))

                    # self.logger.debug("%s - Dumping result set into database %d rows / %d tasks" % (self.proc_name, len(insertList), number_of_grabbed_tasks))
                    c.executemany("INSERT INTO Entries VALUES " + valuesQuery, insertList)

                    # Clear insertList
                    insertList[:] = []
            except sqlite3.Error as er:
                print("%s - Sqlite error: %s" % (self.proc_name, er.message))
                self.logger.debug("%s - Sqlite error: %s" % (self.proc_name, er.message))
            self.conn.commit()


class Task(object):
    def __init__(self, pathToLoad, data):
        self.pathToLoad = pathToLoad
        # Task format is (fileFullPath, hostName, HostID)
        self.data = data

    def __call__(self):
        rowsData = []
        last_number_of_rows = 0
        for item in self.data:
            file_fullpath = item[0]
            assert (file_fullpath)
            instanceID = item[1]
            assert (instanceID)
            hostName = item[2]
            assert (hostName)
            hostID = item[3]
            ingest_class_instance = item[4]
            assert(ingest_class_instance)
            try:
                logger.debug("Processing file %s" % file_fullpath)
                ingest_class_instance.processFile(file_fullpath, hostID, instanceID, rowsData)
                if last_number_of_rows == len(rowsData):
                    logger.warning("No data was extracted from: %s" % file_fullpath)
            except Exception as e:
                logger.error("Error processing: %s (%s)" % (file_fullpath, str(e)))

        return rowsData


def CalculateInstanceID(file_fullpath, ingest_plugin):
    instanceID = ingest_plugin.calculateID(file_fullpath)
    assert(instanceID is not None)

    return instanceID


def GetIDForHosts(files_to_process, DB):
    # todo: With the improved magic_checks this now takes quite a while
    # todo: multiprocess, merge into host ID generation or at least add some GUI feedback.
    # Returns: (filePath, instanceID, hostname, hostID, ingest_type)
    hostsTest = {}
    hostsProcess = []
    progress_total = 0
    progress_current = 0

    # Determine plugin_type and hostname
    for (file_name_fullpath, file_name_original) in files_to_process:
        hostName = None
        ingest_type = None
        loop_counter = 0
        magic_check_res = False
        logger.info("Calculating ID for: %s" % file_name_fullpath)
        while True:
            if loop_counter > len(ingest_plugins_types_stack):
                # Ignore small files with no real data in them (manifest files) from looping through ingestion plugins for no purpose
                # todo: Omit suppression on verbose mode
                tmp_file_size = file_size(file_name_fullpath)
                if tmp_file_size > 500:
                    logger.warning("No ingest plugin could process: %s (skipping file) [size: %d]" %
                                   (file_name_fullpath, tmp_file_size))
                break
            ingest_type = ingest_plugins_types_stack[0]
            if file_name_original is None:
                if ingest_plugins[ingest_type].matchFileNameFilter(file_name_fullpath):
                    # Check magic:
                    try:
                        magic_check = ingest_plugins[ingest_type].checkMagic(file_name_fullpath)
                        if isinstance(magic_check, tuple):
                            logger.error("Report bug")
                        else: magic_check_res = magic_check
                        if magic_check_res:
                            # Magic OK, go with this plugin
                            hostName = ingest_plugins[ingest_type].getHostName(file_name_fullpath)
                            break
                    except Exception as e:
                        logger.exception("Error processing: %s (%s)" % (file_name_fullpath, str(e)))
            else:
                if ingest_plugins[ingest_type].matchFileNameFilter(file_name_original):
                    # Check magic:
                    try:
                        magic_check = ingest_plugins[ingest_type].checkMagic(file_name_fullpath)
                        if isinstance(magic_check, tuple):
                            logger.error("Report bug")
                        else:
                            magic_check_res = magic_check
                        if magic_check_res:
                            # Magic OK, go with this plugin
                            hostName = ingest_plugins[ingest_type].getHostName(file_name_original)
                            break
                    except Exception as e:
                        logger.exception("Error processing: %s (%s)" % (file_name_fullpath, str(e)))

            # Emulate stack with list to minimize internal looping (place last used plugin at the top)
            ingest_plugins_types_stack.remove(ingest_type)
            ingest_plugins_types_stack.insert(len(ingest_plugins_types_stack), ingest_type)
            loop_counter += 1

        if not magic_check_res:
            if file_size(file_name_fullpath) > 500:
                logger.error("Magic check failed (or audit returned no results), can't process: %s [%d bytes] (skipping file)" % (
                ntpath.basename(file_name_fullpath), file_size(file_name_fullpath)))
            else:
                logger.debug("Magic check failed (or audit returned no results), can't process: %s [%d bytes] (skipping file)" % (
                ntpath.basename(file_name_fullpath), file_size(file_name_fullpath)))

        else:
            if hostName is not None and len(hostName) != 0:
                if hostName in hostsTest:
                    hostsTest[hostName].append((file_name_fullpath, ingest_plugins[ingest_type]))
                else:
                    hostsTest[hostName] = []
                    hostsTest[hostName].append((file_name_fullpath, ingest_plugins[ingest_type]))
            else:
                logger.warning("Something went very wrong, can't process: %s [%d bytes] (skipping file)" % (ntpath.basename(file_name_fullpath), file_size(file_name_fullpath)))

    progress_total = len(hostsTest.keys())
    # Iterate over hosts. If host exists in DB grab rowID else create and grab rowID.
    conn = DB.appGetConn()
    with closing(conn.cursor()) as c:
        for hostName in hostsTest.keys():
            assert(hostName)
            # logger.debug("Processing host: %s" % hostName)
            # Check if Host exists
            c.execute("SELECT count(*) FROM Hosts WHERE HostName = '%s'" % hostName)
            data = c.fetchone()[0]
            if (data != 0):
                # Host already has at least one instance in the DB
                c.execute("SELECT HostID, Instances FROM Hosts WHERE HostName = '%s'" % hostName)
                data = c.fetchone()
                tmpHostID = data[0]
                tmpInstances = eval(data[1])
                for (file_fullpath, ingest_plugin) in hostsTest[hostName]:
                    try:
                        logger.debug("[%s] Grabbing instanceID from file: %s" % (ingest_plugin, file_fullpath))
                        instance_ID = CalculateInstanceID(file_fullpath, ingest_plugin)
                    except Exception:
                        logger.error("Error parsing: %s (skipping)" % file_fullpath)
                        traceback.print_exc(file=sys.stdout)
                    else:
                        if str(instance_ID) not in tmpInstances:
                            tmpInstances.append(str(instance_ID))
                            hostsProcess.append((file_fullpath, instance_ID, hostName, tmpHostID, ingest_plugin))
                        else:
                            logger.debug("Duplicate host and instance found: %s" %hostName)
                            continue
                # Save updated Instances list
                c.execute("UPDATE Hosts SET Instances = %s, InstancesCounter = %d WHERE HostName = '%s'" % ('"' + str(repr(tmpInstances)) + '"', len(tmpInstances), hostName))
            else:
                # Host does not exist. Add instance and grab the host ID.
                tmpInstances = []
                newInstances = []
                for (file_fullpath, ingest_plugin) in hostsTest[hostName]:
                    try:
                        logger.debug("[%s] Grabbing instanceID from file: %s" % (ingest_plugin, file_fullpath))
                        instance_ID = CalculateInstanceID(file_fullpath, ingest_plugin)
                    except Exception:
                        logger.error("Error parsing: %s (skipping)" % file_fullpath)
                        traceback.print_exc(file=sys.stdout)
                    else:
                        if str(instance_ID) not in tmpInstances:
                            tmpInstances.append(str(instance_ID))
                            newInstances.append((file_fullpath, instance_ID, ingest_plugin))

                c.execute("INSERT INTO Hosts VALUES (NULL,%s,%s,%d,%d,%d)" % ('"' + hostName + '"', '"' + str(repr(tmpInstances)) + '"', len(tmpInstances), 0, 0))
                tmpHostID = c.lastrowid
                for (file_fullpath, instance_ID, ingest_plugin) in newInstances:
                    # todo: Do we want/need each row to track from what instance it came?
                    hostsProcess.append((file_fullpath, instance_ID, hostName, tmpHostID, ingest_plugin))
            # Update progress
            progress_current += 1
            if settings.logger_getDebugMode():
                status_extra_data = " [RAM: %d%%]" % psutil_phymem_usage()
            else: status_extra_data = ""
            logger.info(update_progress(min(1, float(progress_current) / float(progress_total)), "Calculate ID's for new hosts/instances%s" % status_extra_data, True))
        conn.commit()

    # Return hosts to be processed
    return hostsProcess


def parseManifestAuditFileName(jsondata, zip_archive_filename):
    # Parse manifest.json data and return files which will need to be processed
    file_list = []
    m = re.match(r'^.*(?:\\|\/)(.*)[-_].{22}(-[0-9]+-[0-9]+){0,1}\..{3}$', zip_archive_filename)
    if m:
        hostname = m.group(1)
        data = json.load(jsondata)
        if 'audits' in data:
            for audit in data['audits']:
                if 'sysinfo' in audit['generator']: continue
                if 'install' not in audit['generator']:

                    if 'registry-api' in audit['generator'] or 'w32registryapi' in audit['generator']:
                        for result in audit['results']:
                            if 'application/xml' in result['type']:
                                file_list.append((os.path.join(zip_archive_filename, result['payload']), os.path.join(zip_archive_filename, hostname + "_" + result['payload'] + ".xml")))
                            else: continue
                    elif 'plugin-execute' in audit['generator']:
                        for result in audit['results']:
                            if 'application/vnd.mandiant.issues+xml' not in result['type']:
                                file_list.append((os.path.join(zip_archive_filename, result['payload']), os.path.join(zip_archive_filename, hostname + "_" + result['payload'] + ".xml")))
                            else: continue
                    elif 'w32scripting-persistence' in audit['generator'] or 'persistence' in audit['generator']:
                        for result in audit['results']:
                            if 'application/vnd.mandiant.issues+xml' not in result['type']:
                                file_list.append((os.path.join(zip_archive_filename, result['payload']), os.path.join(zip_archive_filename, hostname + "_" + result['payload'] + ".xml")))
                            else: continue
                    elif 'file-acquisition' in audit['generator']:
                        for result in audit['results']:
                            if 'application/vnd.mandiant.issues+xml' not in result['type']:
                                file_list.append((os.path.join(zip_archive_filename, result['payload']), os.path.join(zip_archive_filename, hostname + "_" + result['payload'] + ".xml")))
                            else: continue
                    elif 'AppCompatCache' in audit['generator']:
                        for result in audit['results']:
                            if 'application/vnd.mandiant.issues+xml' not in result['type']:
                                file_list.append((os.path.join(zip_archive_filename, result['payload']), os.path.join(zip_archive_filename, hostname + "_" + result['payload'] + ".xml")))
                            else: continue
        else:
            logger.warning("HX script execution failed for host: %s, ignoring" % hostname)
    else:
        logger.error("Unable to extract hostname on parseManifestAuditFileName: %s" % zip_archive_filename)

    if len(file_list) == 0:
        logger.warning("No file that could be processed found on manifest.json (likely to be a failed script run) for: %s [%d bytes]" % (zip_archive_filename, file_size(zip_archive_filename)))
    return file_list

def processArchives(filename, file_filter):
    # Process zip file if required and return a list of files to process
    files_to_process = []

    if filename.endswith('.zip'):
        try:
            zip_archive_filename = filename
            # Open the zip archive:
            zip_archive = zipfile.ZipFile(loadFile(zip_archive_filename), "r")
            zipFileList = zip_archive.namelist()
            countTotalFiles = len(zipFileList)
            logger.info("Total files in %s: %d" % (zip_archive_filename, countTotalFiles))
            logger.info("Hold on while we check the zipped files...")

            # Check if it's an HX audit zip file:
            if 'manifest.json' in zipFileList:
                jsondata = loadFile(os.path.join(zip_archive_filename, 'manifest.json'))
                audit_result_filenames = parseManifestAuditFileName(jsondata, zip_archive_filename)
                for (file_name_fullpath, file_name_original) in audit_result_filenames:
                    logger.debug("Adding file to process %s from manifest.json %s" % (file_name_fullpath, zip_archive_filename))
                    files_to_process.append((file_name_fullpath, file_name_original))

            else:
                # Process normal zip file:
                for zipped_filename in zipFileList:
                    if re.match(file_filter, '\\' + zipped_filename):
                        if filename.endswith('.zip'):
                            files_to_process.extend(processArchives(os.path.join(zip_archive_filename, zipped_filename), file_filter))
                        else:
                            logger.debug("Adding file to process %s from zip archive" % (os.path.join(zip_archive_filename, zipped_filename), zip_archive_filename))
                            files_to_process.append((os.path.join(zip_archive_filename, zipped_filename), None))
                    else: logger.debug("Ignoring file: %s" % os.path.join(zip_archive_filename, zipped_filename))
                # if len(files_to_process) == 0:
                #     logger.error("No valid files found!")
            zip_archive.close()
        except (IOError, zipfile.BadZipfile, struct.error), err:
            logger.error("Error reading zip archive: %s" % zip_archive_filename)
            exit(-1)
    else:
        files_to_process.append((filename, None))
    return files_to_process

def searchFolders(pathToLoad, file_filter):
    # Walk folder recursively and build and return a list of files
    files_to_process = []

    # Process
    for root, directories, filenames in os.walk(pathToLoad):
        for dir in directories:
            files_to_process.extend(searchFolders(os.path.join(pathToLoad, dir), file_filter))
        for filename in filenames:
            if re.match(file_filter, os.path.join(pathToLoad, filename), re.IGNORECASE):
                logger.debug("Adding file to process: %s" % os.path.join(pathToLoad, filename))
                files_to_process.extend(processArchives(os.path.join(pathToLoad, filename), file_filter))
            else: logger.warning("Skipping file, no ingest plugin found to process: %s" % filename)
        break
    return files_to_process


def searchRedLineAudits(pathToLoad):
    # Walk folder recursively and build the list of Redline registry audits to process
    files_to_process = []

    # Process
    for root, directories, filenames in os.walk(pathToLoad):
        for dir in directories:
            files_to_process.extend(searchRedLineAudits(os.path.join(pathToLoad, dir)))
        for filename in filenames:
            if re.match('w32registryapi\..{22}$', filename):
                files_to_process.append(os.path.join(pathToLoad, filename))
        break
    return files_to_process


def appLoadMP(pathToLoad, dbfilenameFullPath, maxCores, governorOffFlag):
    global _tasksPerJob

    # Adding original filename to the tuple stored in files_to_process: (filename to load data from, original filename)
    files_to_process = []
    conn = None

    # Start timer
    t0 = datetime.now()

    logger.debug("Starting appLoadMP")
    # Calculate aggreagate file_filter for all ingest types supported:
    file_filter = '|'.join([v.getFileNameFilter() for k,v in ingest_plugins.iteritems()])
    # Add zip extension
    file_filter += "|.*\.zip$"

    # Check if we're loading Redline data
    if os.path.isdir(pathToLoad) and os.path.basename(pathToLoad).lower() == 'RedlineAudits'.lower():
        files_to_process = searchRedLineAudits(pathToLoad)
    else:
        # Search for all files to be processed
        if os.path.isdir(pathToLoad):
            files_to_process = searchFolders(pathToLoad, file_filter)
        else:
            files_to_process = processArchives(pathToLoad, file_filter)

    if files_to_process:
        # Init DB if required
        DB = appDB.DBClass(dbfilenameFullPath, True, settings.__version__)
        conn = DB.appConnectDB()

        # Extract hostnames, grab existing host IDs from DB and calculate instance ID for new IDs to be ingested:
        instancesToProcess = []
        instancesToProcess += GetIDForHosts(files_to_process, DB)
        countInstancesToProcess = len(instancesToProcess)
        logger.info("Found %d new instances" % (countInstancesToProcess))

        # Setup producers/consumers initial counts
        num_consumers = 1
        num_producers = 1

        # Setup MPEngine
        mpe = MPEngineProdCons(maxCores, appLoadProd, appLoadCons, governorOffFlag)

        # Reduce _tasksPerJob for small jobs
        if countInstancesToProcess < _tasksPerJob: _tasksPerJob = 1

        # Create task list
        task_list = []
        instancesPerJob = _tasksPerJob
        num_tasks = 0
        for chunk in chunks(instancesToProcess, instancesPerJob):
            # todo: We no longer need pathToLoad as tasks include the fullpath now
            task_list.append(Task(pathToLoad, chunk))
            num_tasks += 1

        if num_tasks > 0:
            # Check if we have to drop indexes to speedup insertions
            # todo: Research ratio of existing hosts to new hosts were this makes sense
            if countInstancesToProcess > 1000 or DB.CountHosts() < 1000:
                DB.appDropIndexesDB()

            # Queue tasks for Producers
            mpe.addTaskList(task_list)

            # Start procs
            mpe.startProducers(num_producers)
            mpe.startConsumers(num_consumers, [dbfilenameFullPath])
            # mpe.addProducer()

            # Control loop
            while mpe.working():
                time.sleep(1.0)
                (num_producers,num_consumers,num_tasks,progress_producers,progress_consumers) = mpe.getProgress()
                elapsed_time = datetime.now() - t0
                mean_loadtime_per_host = (elapsed_time) / max(1, _tasksPerJob * progress_consumers)
                pending_hosts = ((num_tasks * _tasksPerJob) - (_tasksPerJob * progress_consumers))
                etr = (mean_loadtime_per_host * pending_hosts)
                eta = t0 + elapsed_time + etr
                ett = (eta - t0)
                if settings.logger_getDebugMode(): status_extra_data = " Prod: %s Cons: %s (%d -> %d -> %d: %d) [RAM: %d%% / Obj: %d / ETH: %s / ETA: %s / ETT: %s]" % \
                                                                       (num_producers, num_consumers, num_tasks, progress_producers, progress_consumers, progress_producers - progress_consumers,
                     psutil_phymem_usage(), len(gc.get_objects()),
                     mean_loadtime_per_host if progress_consumers * _tasksPerJob > 100 else "N/A",
                     str(eta.time()).split(".")[0] if progress_consumers * _tasksPerJob > 100 else "N/A",
                     str(ett).split(".")[0] if progress_consumers * _tasksPerJob > 100 else "N/A")
                else: status_extra_data = ""
                # logger.info("Parsing files%s" % status_extra_data)

                logger.info(update_progress(min(1,float(progress_consumers) / float(num_tasks)), "Parsing files%s" % status_extra_data, True))
                mpe.rebalance()

            del mpe

        # Stop timer
        elapsed_time = datetime.now() - t0
        mean_loadtime_per_host = (elapsed_time) / max(1, countInstancesToProcess)
        logger.info("Load speed: %s seconds / file" % (mean_loadtime_per_host))
        logger.info("Load time: %s" % (str(elapsed_time).split(".")[0]))
    else:
        logger.info("Found no files to process!")