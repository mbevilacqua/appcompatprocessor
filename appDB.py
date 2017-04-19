__author__ = 'matiasbevilacqua'

import settings
import logging
import sqlite3
import os
from appAux import outputcolum, update_progress, update_spinner
from contextlib import closing
import re
import sys, traceback


logger = logging.getLogger(__name__)

def re_fn(expr, item):
    reg = re.compile(expr, re.IGNORECASE)
    return reg.search(item) is not None


class DBClass(object):
    def __init__(self, dbfilenameFullPath, createDB, version="0.0"):
        self.dbfilenameFullPath = dbfilenameFullPath
        self.createDB = createDB
        self.versionCode = version
        self.versionDB = '0.0.0'
        self.conn = None
        self.connRAW = None
        self.reindex = False
        self.indexList = []

        # If file exists, check it's our DB schema
        if os.path.isfile(self.dbfilenameFullPath):
            tmpconn = sqlite3.connect(self.dbfilenameFullPath, timeout=10)
            with closing(tmpconn.cursor()) as c:
                try:
                    c.execute("SELECT Value FROM Internal WHERE Property = 'version'")
                    return
                except sqlite3.OperationalError as error:
                    logger.debug("DB is not an AppCompatProcessor DB: %s" % self.dbfilenameFullPath)
                    # todo exit, not our db schema don't touch it.
                    return

                # todo: Detect empty leftover DB's and handle them gracefully
                # # Check if its a valid DB or leftover from failed load attempt
                # # Count entries
                # c.execute("SELECT count(*) FROM Entries")
                # entries_count = c.fetchone()[0]
                # if entries_count == 0:
                #     os.remove(self.dbfilenameFullPath)

    def __del__(self):
        if self.conn is not None: self.conn.close()
        if self.connRAW is not None: self.connRAW.close()
        if self.reindex:
            self.appAddIndexesDB()

    def close(self, *err):
        if self.conn is not None: self.conn.close()
        if self.connRAW is not None: self.connRAW.close()
        if self.reindex:
            self.appAddIndexesDB()

    def __enter__(self, *err):
        return self

    def __exit__(self, *err):
        self.close()

    def __call__(self):
        return 0

    def appDBDebugInfo(self):
        logger.debug("Sqlite database adapter version: %s" % sqlite3.sqlite_version)

    def appDBGetVersion(self):
        return self.versionDB

    def appGetConn(self):
        if self.conn is not None:
            return self.conn
        else:
            logger.error("No active connection exsits!")
            raise ValueError('No active connection exsits!')

    def appConnectDB(self, dbfilenameFullPath=None):
        # Check if optional DB filename was passed
        if dbfilenameFullPath is not None:
            self.dbfilenameFullPath = dbfilenameFullPath
        # Open connection to database
        if os.path.isfile(self.dbfilenameFullPath):
            # print "Loading %s sqlite DB" % self.dbfilenameFullPath
            try:
                self.conn = sqlite3.connect(self.dbfilenameFullPath, timeout=10, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
                self.conn.execute("PRAGMA synchronous=OFF")
                self.conn.execute("PRAGMA journal_mode=OFF")

                # todo: Remove, obsolete we don't use this approach anymore as it's slower :
                self.conn.create_function("REGEXP", 2, re_fn)

                # Create RAW connection
                self.connRAW = sqlite3.connect(self.dbfilenameFullPath, timeout=10, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
                self.conn.execute("PRAGMA synchronous=OFF")
                self.conn.execute("PRAGMA journal_mode=OFF")

            except sqlite3.Error as er:
                logger.exception("Error loading DB %s [%s]" % (self.dbfilenameFullPath, er.message))
                exit()
            self.appLoadIndexesDB()
        else:
            logger.error("Sqlite DB not found!")
            raise ValueError('Sqlite DB not found!')
        return self.conn


    def appInitDB(self):
        if os.path.isfile(self.dbfilenameFullPath):
            tmpconn = sqlite3.connect(self.dbfilenameFullPath, timeout=10)
            with closing(tmpconn.cursor()) as c:
                try:
                    c.execute("SELECT Value FROM Internal WHERE Property = 'version'")
                    self.versionDB = c.fetchone()
                    if self.versionCode > self.versionDB:
                        logger.warning("Warning: DB was generated with a previous version (%s) of AppCompatProcessor, watch out!" % self.versionDB)
                except sqlite3.OperationalError as error:
                    self.versionDB = 0.0
                    logger.warning("Warning: DB was generated with a previous version (%s) of AppCompatProcessor, watch out!" % self.versionDB)
        else:
            if self.createDB:
                # Create DB if it does not exists
                tmpconn = sqlite3.connect(self.dbfilenameFullPath, timeout=10)
                with closing(tmpconn.cursor()) as c:
                    logger.info("Initializing %s sqlite DB" % self.dbfilenameFullPath)
                    c.execute('''CREATE TABLE Internal(
                        PropertyID INTEGER PRIMARY KEY,
                        Property text UNIQUE collate nocase,
                        Value text collate nocase)''')
                    c.execute('''CREATE TABLE Hosts(
                        HostID INTEGER PRIMARY KEY,
                        HostName text UNIQUE collate nocase,
                        Instances text,
                        InstancesCounter integer,
                        Recon integer,
                        ReconScoring integer)''')
                    c.execute('''CREATE TABLE FilePaths(
                        FilePathID INTEGER PRIMARY KEY,
                        FilePath text UNIQUE collate nocase)''')
                    c.execute('''CREATE TABLE Entries(
                        RowID INTEGER PRIMARY KEY,
                        HostID integer,
                        EntryType integer,
                        RowNumber integer,
                        LastModified timestamp,
                        LastUpdate timestamp,
                        FilePathID integer,
                        FileName text collate nocase,
                        Size integer,
                        ExecFlag text collate nocase,
                        SHA1 text collate nocase,
                        FileDescription text collate nocase,
                        FirstRun timestamp,
                        Created timestamp,
                        Modified1 timestamp,
                        Modified2 timestamp,
                        LinkerTS timestamp,
                        Product text collate nocase,
                        Company text collate nocase,
                        PE_sizeofimage integer,
                        Version_number text collate nocase,
                        Version text collate nocase,
                        Language text collate nocase,
                        Header_hash text collate nocase,
                        PE_checksum text collate nocase,
                        SwitchBackContext text collate nocase,
                        InstanceID text collate nocase,
                        Recon integer,
                        ReconSession integer,
                        FOREIGN KEY(HostID) REFERENCES Hosts(HostID),
                        FOREIGN KEY(FilePathID) REFERENCES Hosts(FilePathID))''')
                    c.execute('''CREATE TABLE TemporalCollateral(
                        TempID INTEGER PRIMARY KEY,
                        RowID integer,
                        Before integer,
                        After integer,
                        Weight integer,
                        InvBond integer,
                        FOREIGN KEY(RowID) REFERENCES Entries(RowID))''')
                    c.execute('''CREATE VIEW Entries_FilePaths AS
                        SELECT * FROM Entries INNER JOIN FilePaths ON Entries.FilePathID = FilePaths.FilePathID''')
                    c.execute('''CREATE VIEW Csv_Dump AS
                        SELECT Entries.EntryType, Hosts.HostName, (CASE WHEN Entries.EntryType = 0 then 'AppCompat' else 'AmCache' END),
                        Entries.LastModified,
                        Entries.LastUpdate,
                        FilePaths.FilePath, Entries.FileName, Entries.Size, Entries.ExecFlag FROM Entries
                        INNER JOIN FilePaths ON Entries.FilePathID = FilePaths.FilePathID
                        INNER JOIN Hosts ON Entries.HostID = Hosts.HostID''')
                    c.execute('''CREATE VIEW Full_Dump AS
                        SELECT *
                        FROM Entries
                        INNER JOIN FilePaths ON Entries.FilePathID = FilePaths.FilePathID
                        INNER JOIN Hosts ON Entries.HostID = Hosts.HostID''')

                    # Set version info
                    c.execute("INSERT INTO Internal (Property, Value) VALUES ('version', '%s')" % str(self.versionCode))
                    self.versionDB = self.versionCode
                    tmpconn.commit()

            else:
                logger.critical("Database file expected but none found: %s" % self.dbfilenameFullPath)
                return False

        return True

    def appSetIndex(self):
        self.reindex = True


    def appCheckIndexDB(self, indexName):
        with closing(self.conn.cursor()) as c:
            c.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='%s'" % (indexName))
            if c.fetchone():
                return True
            else:
                return False


    def appLoadIndexesDB(self):
        # Load existing indexes for Entries table
        with closing(self.conn.cursor()) as c:
            c.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'index_Entries%'")
            rows = c.fetchall()
            if len(rows) > 0:
                self.reindex = False
                for row in rows:
                    self.indexList.append(row[0])


    def appIndexExistsDB(self, fieldName):
        # Return True if the field is indexed
        for index in self.indexList:
            if fieldName in index: return True
        return False


    def appAddIndexesDB(self):
        if self.reindex:
            self.reindex = False
            logger.info("Indexing sqlite DB %s " % self.dbfilenameFullPath)
            tmpconn = self.appConnectDB(self.dbfilenameFullPath)
            tmpconn.set_progress_handler(update_spinner, 10000)
            with closing(tmpconn.cursor()) as c:
                c.execute('''CREATE INDEX index_EntriesRowNumber on Entries(RowNumber)''')
                self.indexList.append("index_EntriesRowNumber")
                c.execute('''CREATE INDEX index_EntriesHostID on Entries(HostID)''')
                self.indexList.append("index_EntriesHostID")
                c.execute('''CREATE INDEX index_EntriesFileName on Entries(FileName)''')
                self.indexList.append("index_EntriesFileName")
                c.execute('''CREATE INDEX index_FilePathsFilePath on FilePaths(FilePath)''')
                self.indexList.append("index_FilePathsFilePath")
                c.execute('''CREATE INDEX index_EntriesRecon on Entries(Recon)''')
                self.indexList.append("index_EntriesRecon")
                c.execute('''CREATE INDEX index_EntriesSHA1 on Entries(SHA1)''')
                self.indexList.append("index_EntriesSHA1")
                c.execute('''CREATE INDEX index_EntriesFilePathID on Entries(FilePathID)''')
                self.indexList.append("index_EntriesFilePathID")
                # c.execute('''CREATE INDEX index_ReconCollateralRowID on ReconCollateral(RowID)''')
                # self.indexList.append("index_ReconCollateralRowID")
                tmpconn.commit()
                logger.debug("Indexing finished!")


    def appRequireIndexesDB(self, index_name, index_query, quiet=False):
        # Check we have the required index or add it
        if self.QueryInt("SELECT count(*) FROM sqlite_master WHERE name='%s'" % index_name) == 0:
            if not quiet: logger.info("Srry we need to add an index for you there (%s), hold on..." % index_name)
            tmpconn = self.appConnectDB(self.dbfilenameFullPath)
            tmpconn.set_progress_handler(update_spinner, 10000)
            with closing(tmpconn.cursor()) as c:
                c.execute(index_query)
                self.indexList.append(index_name)
                tmpconn.commit()


    def appDropIndexesDB(self):
        logger.info("Deleting indexes")
        with closing(self.conn.cursor()) as c:
            for i in self.indexList:
                c.execute("DROP INDEX '%s'" % (i))
            self.conn.commit()
        self.appSetIndex()


    def Status(self):
        """Print basic information on the status of the current session"""
        (num_hosts, num_instances, num_entries) = (self.CountHosts(), self.CountInstances(), self.CountEntries())
        return (self.dbfilenameFullPath, self.versionDB, num_hosts, num_instances, num_entries)


    def getFields(self, table_name):
        with closing(self.conn.cursor()) as c:
            data = c.execute("select * from " + table_name + " LIMIT 1")
        fields = [description[0].lower() for description in data.description]
        return fields


    def HasAppCompat(self, hostName):
        num_entries = self.Query("SELECT count(*) FROM Entries JOIN Hosts ON Entries.HostID = Hosts.HostID AND Hosts.HostName = '%s' WHERE EntryType = '0'" % hostName)[0][0]
        return (num_entries > 0)


    def HasAmCache(self, hostName):
        num_entries = self.Query("SELECT count(*) FROM Entries JOIN Hosts ON Entries.HostID = Hosts.HostID AND Hosts.HostName = '%s' WHERE EntryType = '1'" % hostName)[0][0]
        return (num_entries > 0)


    def QueryInt(self, query):
        with closing(self.conn.cursor()) as c:
            try:
                c.execute(query)
                data = c.fetchall()
            except sqlite3.Error as e:
                e.message = "SQLITE error: %s [%s]" % (e.message, query)
                logger.exception(e.message)
                raise
            else:
                if len(data) > 0:
                    return data[0][0]
                else: return None


    def QueryIntRAW(self, query):
        # todo: refactor this now that we've dropped row factory for speed reasons
        # RAW recreates a connection without using row factory in which namedtuples field validation complains about some queries
        tmpconn = sqlite3.connect(self.dbfilenameFullPath, timeout=10)
        with closing(tmpconn.cursor()) as c:
            try:
                c.execute(query)
                data = c.fetchall()
            except sqlite3.Error as e:
                e.message = "SQLITE error: %s [%s]" % (e.message, query)
                logger.exception(e.message)
                raise
            else:
                return data[0][0]


    def Query(self, query):
        with closing(self.conn.cursor()) as c:
            try:
                c.execute(query)
                data = c.fetchall()
            except sqlite3.Error as e:
                e.message = "SQLITE error: %s [%s]" % (e.message, query)
                logger.exception(e.message)
                raise
            except Exception as e:
                # todo: Add exception to the logger
                traceback.print_exc(file=sys.stdout)
            else:
                return data


    def QuerySpinner(self, query):
        tmpconn = self.appConnectDB(self.dbfilenameFullPath)
        tmpconn.set_progress_handler(update_spinner, 10000)
        with closing(tmpconn.cursor()) as c:
            try:
                c.execute(query)
                data = c.fetchall()
            except sqlite3.Error as er:
                logger.exception("SQLITE error: %s [%s]" % (er.message, query))
                raise
            else:
                return data


    def QueryRAW(self, query):
        with closing(self.connRAW.cursor()) as c:
            try:
                c.execute(query)
                data = c.fetchall()
            except sqlite3.Error as er:
                logger.exception("SQLITE error: %s [%s]" % (er.message, query))
                raise
            else:
                return data


    def ExecuteSpinner(self, query, printErrors=True):
        tmpconn = self.appConnectDB(self.dbfilenameFullPath)
        tmpconn.set_progress_handler(update_spinner, 10000)
        with closing(tmpconn.cursor()) as c:
            try:
                c.execute(query)
                tmpconn.commit()
            except sqlite3.Error as er:
                if printErrors:
                    logger.exception("SQLITE error: %s [%s]" % (er.message, query))
                    raise
                return False
            else:
                return True


    def Execute(self, query, printErrors=True):
        try:
            self.connRAW.execute(query)
            self.connRAW.commit()
        except sqlite3.Error as er:
            if printErrors:
                logger.exception("SQLITE error: %s [%s]" % (er.message, query))
                raise
            return False
        else:
            return True


    def ExecuteMany(self, query, data):
        tmpconn = self.appConnectDB(self.dbfilenameFullPath)
        tmpconn.set_progress_handler(update_spinner, 10000)
        with closing(tmpconn.cursor()) as c:
            try:
                c.executemany(query, data)
                tmpconn.commit()
            except sqlite3.Error as er:
                logger.exception("SQLITE error: %s [%s]" % (er.message, query))
                raise
            else:
                return True


    def CountHosts(self):
        with closing(self.conn.cursor()) as c:
            c.execute("SELECT count(*) FROM Hosts")
            count = c.fetchone()[0]
        return (count)


    def CountInstances(self):
        with closing(self.conn.cursor()) as c:
            c.execute("SELECT sum(InstancesCounter) FROM Hosts")
            count = c.fetchone()[0]
        return (count if count != None else 0)


    def CountEntries(self):
        with closing(self.conn.cursor()) as c:
            c.execute("SELECT count(*) FROM Entries")
            count = c.fetchone()[0]
        return (count)


    def CountConditional(self, table, fields, values):
        conditions = ' AND '.join(item[0] + " = " + item[1] for item in zip(fields, ("'" + val + "'" for val in map(str, values))))
        with closing(self.conn.cursor()) as c:
            c.execute("SELECT count(*) FROM %s WHERE %s" % (table, conditions))
            count = c.fetchone()[0]
        return (count)


    def CountReconEntries(self):
        with closing(self.conn.cursor()) as c:
            c.execute("SELECT count(*) FROM Entries WHERE Recon = '1'")
            count = c.fetchone()[0]
        return (count)


    def CountReconHosts(self, minReconCont):
        with closing(self.conn.cursor()) as c:
            c.execute("SELECT count(*) FROM Hosts WHERE Recon > '%s'" % minReconCont)
            count = c.fetchone()[0]
        return (count)


    def HostId2HostName(self, HostID):
        with closing(self.conn.cursor()) as c:
            c.execute("SELECT HostName FROM Hosts WHERE HostID = '%s'" %(HostID))
            hostName = c.fetchone()[0]
        return (hostName)


    def GetEntryRowID(self, RowID):
        with closing(self.conn.cursor()) as c:
            data = self.Query("SELECT HostName, LastModified, LastUpdate, FilePath, FileName, Size, ExecFlag FROM \
            Entries INNER JOIN Hosts ON Entries.HostID = Hosts.HostID WHERE RowID = '%s'" % RowID)
            results = []
            return ' '.join(map(str, data[0]))


    def PrintEntryRowID(self, RowID):
        with closing(self.conn.cursor()) as c:
            data = self.Query("SELECT HostName, LastModified, LastUpdate, FilePath, FileName, Size, ExecFlag FROM \
            Entries INNER JOIN Hosts ON Entries.HostID = Hosts.HostID WHERE RowID = '%s'" % RowID)
            results = []
            for row in data:
                results.append(('white', row))
        outputcolum(results)


    def PrintEntryRowIDList(self, rowIDList):
        with closing(self.conn.cursor()) as c:
            data = self.Query("SELECT HostName, LastModified, LastUpdate, FilePath, FileName, Size, ExecFlag FROM \
            Entries INNER JOIN Hosts ON Entries.HostID = Hosts.HostID WHERE RowID IN (%s)" % ",".join(rowIDList))
            if len(data) > 0:
                results = []
                results.append(('cyan', list(data[0]._fields)))
                for row in data:
                    results.append(('white', row))
                outputcolum(results)
            else:
                logger.error("PrintEntryRowIDList - nothing to print!")


    def PrintEntry(self, HostID, RowNumber, options):
        with closing(self.conn.cursor()) as c:
            # Check if Host exists
            count = self.QueryIntRAW("SELECT count(*) FROM Hosts WHERE HostID = '%s'" % HostID)
            if (count == 0):
                logger.error("Host not in Database")
                return(0)

            data = self.Query("SELECT * FROM Entries WHERE HostID = '%s' \
                AND RowNumber = '%d'" % (HostID, RowNumber))
            results = []
            results.append(('cyan', list(data[0]._fields)))
            for row in data:
                results.append(('white', row))
