#!/usr/bin/env python
import settings
from settings import logger_getDebugMode
import logging
import sys
reload(sys)
sys.setdefaultencoding("utf-8")
import os
import ntpath
import argparse
from contextlib import closing
import multiprocessing
import datetime
import re
import itertools
import traceback
from appAux import psutil_phymem_usage
from appAux import update_progress, outputcolum
from appLoad import appLoadMP
from appSearch import appSearchMP, KnownBadRegexCount
import appDB
import math

try:
    from test.auxTest import build_fake_DB
except ImportError:
    print("Missing tests folder or python faker module (won't be able to run unit tests)")
    pass

try:
    from termcolor import colored
except ImportError:
    if settings.__TERMCOLOR__:
        settings.__TERMCOLOR__ = False
    print "(Missing termcolor python module, we can live without it but you'd benefit from it)"
    def colored(s1, s2):
        return s1
else: settings.__TERMCOLOR__ = True

try:
    import Levenshtein
except ImportError:
    if settings.__LEVEN__:
        settings.__LEVEN__ = False
    print "(Missing Levenshtein python module, access to Leven module disabled)"
else: settings.__LEVEN__ = True

from collections import defaultdict

try:
    from IPython.terminal.embed import InteractiveShellEmbed
    try:
        from traitlets.config.loader import Config
    except ImportError:
        from IPython.config.loader import Config
except ImportError:
    pass

# Housekeeping and get ready to run
settings.init()
logger = None
__description__ = 'AppCompatProcessor (Beta ' + settings.__version__ + ' [' + settings.__versiondate__ + '])'


def ReconScan(DB, options):
    # Set Recon field in Entries for all recon commands in database
    syntaxError = False
    conn = DB.appConnectDB()
    logger.info("Scanning for recon activity")

    # Find reconFiles.txt
    recon_file = os.path.join(os.path.dirname(__file__), 'reconFiles.txt')
    if not os.path.isfile(recon_file):
        recon_file = '/etc/AppCompatProcessor/reconFiles.txt'
        if not os.path.isfile(recon_file):
            logger.error("Sorry, can't find know bad file: %s" % recon_file)
            syntaxError = True

    if not syntaxError:
        with open(recon_file) as f:
            reconTerms = f.read().splitlines()
        reconTerms = ','.join('"{0}"'.format(w) for w in reconTerms)

        # Extremely weird query but it's way faster than a traditional approach
        # This 0-zero's out everything and sets to 1 recon entries.
        # X15 times faster for very big lists of reconTerm, unfortunately no progessbar possible :(
        DB.ExecuteSpinner("UPDATE Entries SET Recon = (SELECT count(FileName) FROM Entries E2 \
            WHERE Entries.RowID = E2.RowID and Entries.FileName IN (%s) ) > 0" % reconTerms)

        logger.info("Total number of potential recon commands detected: %d" % DB.CountReconEntries())


def ReconTally(DB, options):
    # Add recon activity per Host and populate Recon field in Hosts table
    conn = DB.appConnectDB()
    logger.info("Tallying host recon activity")
    # c.execute("UPDATE Hosts SET Recon = \
    #     (SELECT count(*) FROM Entries \
    #     WHERE Hosts.HostID = Entries.HostID AND Recon = '1')")
    # Faster alternative:
    DB.ExecuteSpinner("UPDATE Hosts SET Recon = \
        (SELECT sum(Recon) FROM Entries \
        WHERE Hosts.HostID = Entries.HostID)")

    # todo: Report recon activity beyond a certain level only?
    logger.info("Total number of hosts with potential recon activity detected: %d / %d" % (DB.CountReconHosts(2), DB.CountHosts()))


def HostsReconScoringUpdate(DB, options):
    # Calculate ReconScoring for every host
    # todo: Improve speed - multithread counting and update scores at the end
    logger.info("Calculating host recon scorings")
    data = DB.Query("SELECT HostID, Instances FROM Hosts WHERE Recon > '2'")
    progressTotal = len(data)
    progressCurrent = 0
    for host in data:
        hostID = host[0]
        instances = eval(host[1])
        maxReconScoring = 0
        for instance in instances:
            hostScore = CalcInstanceReconScoring(DB, hostID, instance, options)
            if maxReconScoring < hostScore: maxReconScoring = hostScore
        DB.Execute("UPDATE Hosts SET ReconScoring = '%d' WHERE HostID = '%s'" % (maxReconScoring, host[0]))
        progressCurrent += 1
        update_progress(float(progressCurrent) / float(progressTotal))
    return progressCurrent


def CalcInstanceReconScoring(DB, HostID, InstanceID, options):
    # Split recon entries into recon sessions and calculate host scoring based on session cohesiveness
    conn = DB.appConnectDB()
    sessionScore = 0
    hostScore = 0
    reconSession = 1
    reconSessionLength = 0

    logger.debug("Calculating Recon Score for %s" % HostID)
    # Process based on RowNumber if it's an AppCompat instance
    if DB.CountConditional("Entries", ["HostID", "InstanceID", "EntryType"], [HostID, InstanceID, settings.__APPCOMPAT__]) > 0:
        with closing(conn.cursor()) as c:
            # Fetch all recon entries for the host
            c.execute("SELECT RowNumber FROM Entries WHERE HostID = '%d'AND InstanceID = '%s' AND Recon = '1' ORDER BY RowNumber" % (HostID, InstanceID))
            RowNumbers = c.fetchall()
            # We score based on how cohesive and extended the recon sessions are
            for r in range(0, len(RowNumbers) - 1):
                if(RowNumbers[r+1][0] - RowNumbers[r][0] <= 3):
                    # We're still on the on-going recon session
                    reconSessionLength += 1
                    sessionScore += (1.0 / (math.pow(abs(RowNumbers[r+1][0] - RowNumbers[r][0]),2))*10)
                    EntryUpdateReconSession(DB, HostID, InstanceID, RowNumbers[r][0], RowNumbers[r+1][0], reconSession)
                else:
                    # Recon session ended
                    if reconSessionLength > 2:
                        hostScore += sessionScore
                    reconSessionLength = 0
                    sessionScore = 0
                    reconSession += 1

    # Process based on FirstRun if its an AmCache instance
    else:
        with closing(conn.cursor()) as c:
            # Fetch all recon entries for the host
            c.execute("SELECT RowNumber, FirstRun FROM Entries WHERE HostID = '%d'AND InstanceID = '%s' AND Recon = '1' ORDER BY FirstRun" % (HostID, InstanceID))
            entries = c.fetchall()
            # We score based on how cohesive and extended the recon sessions are
            for r in range(0, len(entries) - 1):
                elapsedTime = entries[r+1][1] - entries[r][1]
                if(elapsedTime.seconds <= 2 * 60):
                    # We're still on the on-going recon session
                    reconSessionLength += 1
                    if ((math.pow(elapsedTime.microseconds / 1000000.0,2))*10) == 0:
                        elapsedTime = datetime.timedelta(microseconds = 1 * 100000)
                    sessionScore += (1.0 / (math.pow(elapsedTime.microseconds / 1000000.0,2))*10)
                    EntryUpdateReconSession(DB, HostID, InstanceID, entries[r][0], entries[r+1][0], reconSession)
                else:
                    # Recon session ended
                    if reconSessionLength > 2:
                        hostScore += sessionScore
                    reconSessionLength = 0
                    sessionScore = 0
                    reconSession += 1

    return(hostScore)


def EntryUpdateReconSession(DB, HostID, InstanceID, RowNumber1, RowNumber2, reconSession):
    conn = DB.appConnectDB()
    with closing(conn.cursor()) as c:
        c.execute("UPDATE Entries SET ReconSession = '%d' WHERE HostID = '%s' AND InstanceID = '%s' AND (RowNumber = '%d' OR RowNumber = '%d')" % (reconSession, HostID, InstanceID, RowNumber1, RowNumber2))
        conn.commit()


def PrintReconActivity(DB, options):
    hostName = options.host_name
    reconWindow = options.window
    results = []
    conn = DB.appConnectDB()
    with closing(conn.cursor()) as c:
        # Check if Host exists
        c.execute("SELECT count(*) FROM Hosts WHERE HostName = '%s'" % hostName)
        data = c.fetchone()[0]
        if (data == 0):
            print "Host not in Database"
            return(0)

        logger.info("Printing Recon Activity for %s" % hostName)
        # Process each recon session identified
        c.execute("SELECT ReconSession from Entries WHERE HostID = \
            (SELECT HostID FROM Hosts WHERE HostName = '%s')\
            AND ReconSession > 0 GROUP BY ReconSession ORDER BY LastModified" % (hostName))
        data=c.fetchall()
        for reconSession in data:
            # Get max and min row numbers for session
            c.execute("SELECT RowNumber FROM Entries WHERE HostID = \
                      (SELECT HostID FROM Hosts WHERE HostName = '%s')\
                      AND ReconSession = '%d' ORDER BY RowNumber DESC LIMIT 1" % (hostName, reconSession[0]))
            maxRowNumber = c.fetchone()[0]
            c.execute("SELECT RowNumber FROM Entries WHERE HostID = \
                      (SELECT HostID FROM Hosts WHERE HostName = '%s')\
                      AND ReconSession = '%d' ORDER BY RowNumber LIMIT 1" % (hostName, reconSession[0]))
            minRowNumber = c.fetchone()[0]

            c.execute("SELECT RowNumber,LastModified,LastUpdate,FilePath,FileName,Size,ExecFlag, Recon FROM Entries_Filepaths WHERE HostID = \
                (SELECT HostID FROM Hosts WHERE HostName = '%s')\
                 AND (RowNumber <= '%d' AND RowNumber >= '%d')" % (hostName, maxRowNumber+reconWindow, max(1,minRowNumber-reconWindow)))
            rows = c.fetchall()

            if (len(rows) > 0):
                results.append(('cyan', "\nRowNumber,LastModified,LastUpdate,FilePath,FileName,Size,ExecFlag".split(',')))
                for row in rows:
                    if (row[7] == 1):
                        results.append(('red', row))
                    else: results.append(('white', row))
    outputcolum(results)

    return results


def FindEvil(DB, options):
    # Populate recon collaterals for all hosts
    conn = DB.appConnectDB()

    # Clear recon collateral table
    # todo: Check if pre-existing recon data can be reused?
    DB.ExecuteSpinner("DROP TABLE ReconCollateral", False)
    DB.ExecuteSpinner("CREATE TABLE ReconCollateral \
         (ReconID INTEGER PRIMARY KEY, RowID integer, \
         HostID integer, RowNumber integer, FOREIGN KEY(RowID) REFERENCES Entries(RowID))")
    conn.commit()

    hostIDs = DB.Query("SELECT HostID FROM Hosts WHERE ReconScoring >= 1 ORDER BY ReconScoring")

    # todo: Check if we can process all hosts at the same time more efficiently?
    progressTotal = len(hostIDs)
    progressCurrent = 0
    if len(hostIDs) > 0:
        for host in hostIDs:
            # Populate recon collaterals
            PopulateReconCollaterals(DB, host[0], options)
            progressCurrent += 1
            update_progress(float(progressCurrent) / float(progressTotal), "Populating recon collateral data / host")

        # Find correlations by FileName
        logger.info("Finished PopulateReconCollaterals, querying ReconCollateral")
        rows = DB.QuerySpinner("SELECT Entries_FilePaths.RowNumber,Entries_FilePaths.LastModified,Entries_FilePaths.LastUpdate,Entries_FilePaths.FilePath,Entries_FilePaths.FileName,Entries_FilePaths.Size,Entries_FilePaths.ExecFlag,Entries_FilePaths.Recon, count(*) \
                FROM ReconCollateral LEFT JOIN Entries_FilePaths ON \
                ReconCollateral.HostID = Entries_FilePaths.HostID AND ReconCollateral.RowNumber = Entries_FilePaths.RowNumber \
                WHERE Entries_FilePaths.ExecFlag = 'True' GROUP BY FileName \
                HAVING count(*) > 2 ORDER BY count(*) DESC")
        if (len(rows) > 0):
            results = []
            results.append(('cyan',"RowNumber,LastModified,LastUpdate,FilePath,FileName,Size,ExecFlag,Recon,Count".split(',')))
            logger.info("Repeating file names on recon sessions boundaries:")
            for row in rows:
                # We exclude stuff that's too wide spread in the environment to be of interest
                if (DB.CountConditional("Entries",["FileName"], [row[4]]) < 100) and row[7] == 0:
                    results.append(('white', row))
            outputcolum(results)
        else:
            logger.info("No Evil found :(")
            return []
    else:
        logger.error("Missing reconscoring data?")
        return None

    return(results)


def PopulateReconCollaterals(DB, HostID, options):
    # Only used for fevil
    logger.info("PopulateReconCollaterals on hostID %d" % HostID)
    conn = DB.appConnectDB()
    reconWindow = options.window
    # Process each instance associated to the host
    data = DB.Query("SELECT HostID, Instances FROM Hosts WHERE Recon > '2'")
    for host in data:
        hostID = host[0]
        instances = eval(host[1])
        maxReconScoring = 0
        for instance in instances:
            # Process AppCompat instance
            if DB.CountConditional("Entries",["HostID", "InstanceID", "EntryType"], [HostID, instance, settings.__APPCOMPAT__]) > 0:
                with closing(conn.cursor()) as c:
                    # Process each recon session identified
                    c.execute("SELECT ReconSession from Entries WHERE HostID = '%s' AND InstanceID = '%s'\
                        AND ReconSession > 0 GROUP BY ReconSession" % (HostID, instance))
                    data = c.fetchall()
                    for reconSession in data:
                        # Get max and min row numbers for recon session
                        c.execute("SELECT RowNumber FROM Entries WHERE HostID = '%s' AND InstanceID = '%s'\
                                  AND ReconSession = '%d' ORDER BY RowNumber DESC LIMIT 1" % (HostID, instance, reconSession[0]))
                        maxRowNumber = c.fetchone()[0]
                        c.execute("SELECT RowNumber FROM Entries WHERE HostID = '%s'AND InstanceID = '%s'\
                                  AND ReconSession = '%d' ORDER BY RowNumber LIMIT 1" % (HostID, instance, reconSession[0]))
                        minRowNumber = c.fetchone()[0]

                        # We pick anything before or after the recon session or anything in the middle that's not attributed as recon
                        c.execute("SELECT RowID, HostID, RowNumber FROM Entries WHERE HostID = '%s'AND InstanceID = '%s'\
                             AND ((RowNumber > '%d' AND RowNumber <= '%d') \
                            OR (RowNumber < '%d' AND RowNumber >= '%d')\
                            OR (RowNumber >= '%d' AND RowNumber <= '%d' AND Recon = '0'))" % (HostID, instance, maxRowNumber, maxRowNumber + reconWindow, minRowNumber, max(minRowNumber - reconWindow, 1), maxRowNumber, minRowNumber))
                        reconEntries = c.fetchall()
                        for line in reconEntries:
                            c.execute("INSERT INTO ReconCollateral VALUES (NULL,%s,%s,%s)" % (line[0], line[1], line[2]))
                        conn.commit()
            else:
                # Process based on FirstRun if it's an AmCache instance
                with closing(conn.cursor()) as c:
                    # Process each recon session identified
                    c.execute("SELECT ReconSession from Entries WHERE HostID = '%s' AND InstanceID = '%s'\
                        AND ReconSession > 0 GROUP BY ReconSession" % (HostID, instance))
                    data = c.fetchall()
                    for reconSession in data:
                        # Get max and min row FirstRun for recon session
                        c.execute("SELECT FirstRun FROM Entries WHERE HostID = '%s' AND InstanceID = '%s'\
                                  AND ReconSession = '%d' ORDER BY FirstRun DESC LIMIT 1" % (HostID, instance, reconSession[0]))
                        maxFirstRun = c.fetchone()[0]
                        c.execute("SELECT FirstRun FROM Entries WHERE HostID = '%s'AND InstanceID = '%s'\
                                  AND ReconSession = '%d' ORDER BY FirstRun LIMIT 1" % (HostID, instance, reconSession[0]))
                        minFirstRun = c.fetchone()[0]

                        # We pick anything before or after the recon session or anything in the middle that's not attributed as recon
                        c.execute("SELECT RowID, HostID, RowNumber FROM Entries WHERE HostID = '%s'AND InstanceID = '%s'\
                             AND ((FirstRun > '%s' AND FirstRun <= '%s') \
                            OR (FirstRun < '%s' AND FirstRun >= '%s')\
                            OR (FirstRun >= '%s' AND FirstRun <= '%s' AND Recon = '0'))" % \
                            (HostID, instance, maxFirstRun, maxFirstRun + (datetime.timedelta(minutes=reconWindow*2)), minFirstRun, \
                             minFirstRun - (datetime.timedelta(minutes=reconWindow*2)), maxFirstRun, minFirstRun))
                        reconEntries = c.fetchall()
                        for line in reconEntries:
                            c.execute("INSERT INTO ReconCollateral VALUES (NULL,%s,%s,%s)" % (line[0], line[1], line[2]))
                        conn.commit()

    return(0)

def PrintCollateralActivity(fileName, DB, reconWindow=3):
    # Create a list of hosts analyzed during the last temporal execution correlation scan
    results = []
    hostList = DB.Query("SELECT DISTINCT Entries.HostID \
        FROM TemporalCollateral LEFT JOIN Entries ON TemporalCollateral.RowID = Entries.RowID \
        WHERE Entries.FileName = '%s' ORDER BY Entries.HostID" % fileName)
    if (len(hostList) == 0):
        logger.error("File not found on last tcorr execution")
        return results

    progressTotal = len(hostList)
    progressCurrent = 0
    for row in hostList:
        hostID = row[0]
        results.append(('cyan',("\n=> %s,,,,," % DB.HostId2HostName(hostID)).split(',')))
        # Process each occurrence of the term
        data = DB.Query("SELECT RowNumber, FirstRun, EntryType from Entries WHERE HostID = '%s' \
            AND FileName = '%s' ORDER BY RowNumber" % (hostID, fileName))

        for row in data:
            rowNumber = row[0]
            firstRun = row[1]
            entryType = row[2]

            # We pick anything before or after the row of interest
            if entryType == settings.__APPCOMPAT__:
                minRowNumber = max(1, rowNumber - reconWindow)
                maxRowNumber = rowNumber + reconWindow
                reconEntries = DB.Query("SELECT LastModified,LastUpdate,FilePath,FileName,Size,ExecFlag,Recon FROM \
                    Entries_FilePaths WHERE HostID = '%s' \
                    AND (RowNumber >= '%d' AND RowNumber <= '%d') ORDER BY RowNumber" % (hostID, minRowNumber, maxRowNumber))
                results.append(('cyan',"LastModified,LastUpdate,FilePath,FileName,Size,ExecFlag".split(',')))
            else:
                minFirstRun = firstRun - datetime.timedelta(0,60 * reconWindow)
                maxFirstRun = firstRun + datetime.timedelta(0,60 * reconWindow)
                reconEntries = DB.Query("SELECT FirstRun,Modified2,FilePath,FileName,Size,ExecFlag,Recon FROM \
                    Entries_FilePaths WHERE HostID = '%s' \
                    AND (FirstRun >= '%s' AND FirstRun <= '%s') ORDER BY FirstRun DESC" % (hostID, minFirstRun, maxFirstRun))
                results.append(('cyan',"FirstRun,Modified2,FilePath,FileName,Size,ExecFlag".split(',')))

            for row in reconEntries:
                # Check FileName field
                if row[3] is not None and (row[3].lower() == fileName.lower()):
                    results.append(('red', row))
                else:
                    results.append(('white', row))
        progressCurrent += 1
        update_progress(float(progressCurrent) / float(progressTotal))

    outputcolum(results)
    return results


def appTcorr(fileName, sqlTweak, DB, directCorrelation, reconWindow):
    num_appCompatEntries = DB.CountConditional("Entries", ["EntryType"], [settings.__APPCOMPAT__])
    num_amCacheEntries = DB.CountConditional("Entries", ["EntryType"], [settings.__AMCACHE__])
    if num_appCompatEntries > 0:
        appCompatCorrelationData = appTcorrAppCompat(fileName, sqlTweak, DB, directCorrelation, reconWindow)
    if num_amCacheEntries > 0:
        amCacheCorrelationData = appTcorrAmCache(fileName, sqlTweak, DB, directCorrelation, reconWindow * 2)

    # Merge data from AppCompat and AmCache
    if num_appCompatEntries > 0 and num_amCacheEntries > 0:
        logger.info("Integrating AppCompat and AmCache temporal execution correlations...")
        correlationData = []
        for key,group in itertools.groupby(sorted(itertools.chain(appCompatCorrelationData, amCacheCorrelationData), \
        key=lambda x: x[3].lower()), lambda x: x[3]):
            tmp_tuple = []
            for item in group:
                if len(tmp_tuple) == 0:
                    tmp_tuple.extend([item[0],item[1],item[2],item[3],item[4],item[5],item[6],item[7],item[8],item[9],item[10]])
                else:
                    tmp_tuple[6] += item[6]
                    tmp_tuple[7] += item[7]
                    tmp_tuple[8] += item[8]
                    tmp_tuple[10] += item[10]
            correlationData.append(tuple(tmp_tuple))
        return sorted(correlationData, key=lambda x: x[8], reverse=True)
    elif num_appCompatEntries > 0:
        return appCompatCorrelationData
    elif num_amCacheEntries > 0:
        return amCacheCorrelationData
    else:
        logger.error("WTF?")


def appTcorrAppCompat(fileName, sqlTweak, DB, directCorrelation, tcorrWindow):
    minCount = 2

    if directCorrelation:
        if sqlTweak is "":
            targetTotalCount = DB.CountConditional("Entries", ["EntryType", "FileName"], [settings.__APPCOMPAT__, fileName])
            logger.info("Searching for AppCompat temporal correlations on FileName: %s => [%d hits]" % (fileName, targetTotalCount))
        else:
            # todo: Gracefully handle this when there's an error in sqlTweak
            targetTotalCount = DB.QueryInt("SELECT count(*) FROM Entries_FilePaths WHERE EntryType = %s AND FileName = '%s' AND %s" % (settings.__APPCOMPAT__, fileName, sqlTweak))
            logger.info("Searching for AppCompat temporal correlations on FileName: %s [%s] => [%d hits]" % (fileName, sqlTweak, targetTotalCount))

        collateralDBTableName = "TemporalCollateral"
        # Clear TemporalCollateral table
        DB.Execute("DELETE from %s" % collateralDBTableName)
    else:
        DB.Execute('''CREATE TABLE TemporalInverseCollateral
             (TempID INTEGER PRIMARY KEY, RowID integer, Before integer, After integer, Weight integer, InvBond integer,\
             FOREIGN KEY(RowID) REFERENCES Entries(RowID))''')
        collateralDBTableName = "TemporalInverseCollateral"

    if sqlTweak is "":
        hostIDs = DB.QueryRAW("SELECT DISTINCT HostID FROM Entries WHERE EntryType = %s AND  FileName = '%s'" % (settings.__APPCOMPAT__, fileName))
    else: hostIDs = DB.QueryRAW("SELECT DISTINCT HostID FROM Entries_FilePaths WHERE EntryType = %s AND FileName = '%s' AND %s" % (settings.__APPCOMPAT__, fileName, sqlTweak))
    if len(hostIDs):
        # Add everything within our tcorrWindow to collateralDBTableName
        PopulateAppCompatTemporalCollaterals(fileName, sqlTweak, DB, collateralDBTableName, tcorrWindow)
        # todo: debug if we need to tweak this or not for sqlTweak to take effect
        if sqlTweak is "":
            directCorrelationData = DB.QueryRAW("SELECT Entries_FilePaths.LastModified,Entries_FilePaths.LastUpdate,Entries_FilePaths.FilePath,Entries_FilePaths.FileName,Entries_FilePaths.Size,Entries_FilePaths.ExecFlag, sum(Table1.Before), sum(Table1.After), sum(Table1.Weight) AS Weight \
            FROM %s AS Table1 JOIN Entries_FilePaths ON \
            Table1.RowID = Entries_FilePaths.RowID WHERE Entries_FilePaths.FileName  <> '%s' GROUP BY Entries_FilePaths.FileName \
            HAVING count(*) >= %d ORDER BY Weight DESC LIMIT %d" % (collateralDBTableName, fileName, minCount, tcorrWindow * 2))
        else:
            directCorrelationData = DB.QueryRAW("SELECT Entries_FilePaths.LastModified,Entries_FilePaths.LastUpdate,Entries_FilePaths.FilePath,Entries_FilePaths.FileName,Entries_FilePaths.Size,Entries_FilePaths.ExecFlag, sum(Table1.Before), sum(Table1.After), sum(Table1.Weight) AS Weight \
            FROM %s AS Table1 JOIN Entries_FilePaths ON \
            Table1.RowID = Entries_FilePaths.RowID WHERE Entries_FilePaths.FileName  <> '%s' GROUP BY Entries_FilePaths.FileName \
            HAVING count(*) >= %d ORDER BY Weight DESC LIMIT %d" % (collateralDBTableName, fileName, minCount, tcorrWindow * 2))

        # Calculate inverse temporal correlations
        if directCorrelation and directCorrelationData != None:
            for i in xrange(0, len(directCorrelationData)):
                inverseTotalCount = DB.CountConditional("Entries", ['FileName'], [directCorrelationData[i][3]])
                invBond = False
                # todo: Probably have to add --sql tweak consideration to this count too
                # We ignore calculating the InvBond if it'obvious we won't have one!
                if inverseTotalCount < 2 * targetTotalCount:
                    inverseCorrelationData = appTcorrAppCompat(directCorrelationData[i][3], sqlTweak, DB, False, tcorrWindow)
                    DB.Execute("DROP Table TemporalInverseCollateral")
                    # Tweak results to our needs
                    # Check if FileName is present in the inverse correlation results
                    for row in inverseCorrelationData:
                        if row[3].lower() == fileName.lower():
                            # Tag InvBond as True
                            invBond = True
                            break
                tmp = list(directCorrelationData[i])
                if invBond: tmp.append(u'True')
                else: tmp.append(u'  -  ')
                # Add Total_Count
                tmpTotalCount = DB.CountConditional("Entries", ["FileName"], [directCorrelationData[i][3]])
                tmp.append(tmpTotalCount)
                directCorrelationData[i] = tuple(tmp)

            if len(directCorrelationData) > 0:
                logger.info("AppCompat temporal execution correlation candidates for %s:" % fileName)
                results = []
                results.append(('cyan',"LastModified,LastUpdate,FilePath,FileName(*),Size,ExecFlag,Before,After,Weight,InvBond,Total_Count".split(',')))
                for row in directCorrelationData:
                    printRow = [row[x] for x in xrange(0, len(row))]
                    printRow[8] = round(row[8], 2)
                    results.append(('white', printRow))
                outputcolum(results)
                logger.info("(*)" \
                      " Note that context AppCompat data is pulled from first match in DB as an example (dates, paths, sizes, of other correlating files with the same FileName could be different)")
            else:
                logger.info(("No significant AppCompat temporal execution correlations found (>=%d ocurrences)" % minCount))
                return []
        return directCorrelationData
    else:
        logger.info("No appcompat entries found for: %s" % fileName)
        return []


def PopulateAppCompatTemporalCollaterals(fileName, sqlTweak, DB, collateralDBTableName, tcorrWindow=3):
    countHostsProcessed = 0
    # Process each occurrence of the FileName
    if sqlTweak is "":
        data = DB.Query("SELECT RowID, HostID, FileName from Entries WHERE EntryType = %s AND FileName = '%s'" % (settings.__APPCOMPAT__, fileName))
    else: data = DB.Query("SELECT RowID, HostID, FileName from Entries_FilePaths WHERE EntryType = %s AND FileName = '%s' AND %s" % (settings.__APPCOMPAT__, fileName, sqlTweak))

    rowList = []
    countRowsToProcess = len(data)
    countRowsProcessed = 0
    # Executed before
    for row in data:
        rowID = row[0]
        hostID = row[1]
        fileName = row[2]

        # todo: Suppress unnecessary insert
        # Insert entry into DB
        DB.Execute("INSERT INTO " + collateralDBTableName + " VALUES (NULL,%s, 0, 0, 0, 0)" % (rowID))

        # Grab everyting that executed before within our tcorrWindow and add it to the collateralDBTableName too:
        countRowsProcessed += 1
        update_progress(float(countRowsProcessed) / float(countRowsToProcess * 2), fileName)
        minRowNumber = rowID + 1
        maxRowNumber = rowID + tcorrWindow
        tcorrEntries = DB.Query("SELECT RowID, HostID, FileName FROM Entries WHERE EntryType = %s AND (RowID >= '%d' AND RowID <= '%d')" % (settings.__APPCOMPAT__, minRowNumber, maxRowNumber))
        # Filter out incorrect correlations when RowID jumps from one host to the next
        # Weight correlation value according to temporal execution distance
        for entry in tcorrEntries:
            if  entry[1] == hostID and entry[2] != fileName:
                weight = (1.0 / (math.pow(abs(rowID -entry[0]),2))*10)
                rowList.append(tuple((int(entry[0]), 1, 0, weight)))
    DB.ExecuteMany("INSERT INTO " + collateralDBTableName + " VALUES (NULL,?, ?, ?, ?, 0)", rowList)

    rowList = []
    countRowsToProcess = len(data)
    # Executed after
    for row in data:
        rowID = row[0]
        hostID = row[1]
        fileName = row[2]

        # todo: Suppress unnecessary insert
        # Insert entry into DB
        DB.Execute("INSERT INTO " + collateralDBTableName + " VALUES (NULL,%s, 0, 0, 0, 0)" % (rowID))

        # Grab everyting that executed after within our tcorrWindow and add it to the collateralDBTableName too:
        countRowsProcessed += 1
        update_progress(float(countRowsProcessed) / float(countRowsToProcess * 2), fileName)
        minRowNumber = max(0, rowID - tcorrWindow)
        maxRowNumber = max(0, rowID - 1)
        tcorrEntries = DB.Query("SELECT RowID, HostID, FileName FROM Entries WHERE EntryType = %s AND (RowID >= '%d' AND RowID <= '%d')" % (settings.__APPCOMPAT__, minRowNumber, maxRowNumber))
        # Filter out incorrect correlations when RowID jumps from one host to the next
        for entry in tcorrEntries:
            if  entry[1] == hostID and entry[2] != fileName:
                weight = (1.0 / (math.pow(abs(rowID -entry[0]),2))*10)
                rowList.append(tuple((int(entry[0]), 0, 1, weight)))
    DB.ExecuteMany("INSERT INTO " + collateralDBTableName + " VALUES (NULL,?, ?, ?, ?, 0)", rowList)


def appTcorrAmCache(fileName, sqlTweak, DB, directCorrelation, reconWindow):
    minCount = 2

    if directCorrelation:
        if sqlTweak is "":
            targetTotalCount = DB.CountConditional("Entries", ["EntryType", "FileName"], [settings.__AMCACHE__, fileName])
            logger.info("Searching for AmCache temporal correlations on FileName: %s => [%d hits]" % (fileName, targetTotalCount))
        else:
            # todo: Gracefully handle this when there's an error in sqlTweak
            targetTotalCount = DB.QueryInt("SELECT count(*) FROM Entries_FilePaths WHERE EntryType = %s AND FileName = '%s' AND %s" % (settings.__AMCACHE__, fileName, sqlTweak))
            logger.info("Searching for AmCache temporal correlations on FileName: %s [%s] => [%d hits]" % (fileName, sqlTweak, targetTotalCount))

        collateralDBTaleName = "TemporalCollateral"
        # Clear TemporalCollateral table
        DB.Execute("DELETE from %s" % collateralDBTaleName)
    else:
        DB.Execute('''CREATE TABLE TemporalInverseCollateral
             (TempID INTEGER PRIMARY KEY, RowID integer, Before integer, After integer, Weight integer, InvBond integer,\
             FOREIGN KEY(RowID) REFERENCES Entries(RowID))''')
        collateralDBTaleName = "TemporalInverseCollateral"

    if sqlTweak is "":
        hostIDs = DB.QueryRAW("SELECT DISTINCT HostID FROM Entries WHERE EntryType = %s AND  FileName = '%s'" % (settings.__AMCACHE__, fileName))
    else: hostIDs = DB.QueryRAW("SELECT DISTINCT HostID FROM Entries_FilePaths WHERE EntryType = %s AND FileName = '%s' AND %s" % (settings.__AMCACHE__, fileName, sqlTweak))
    if len(hostIDs):
        # Calculate direct temporal correlations
        PopulateAmCacheTemporalCollaterals(fileName, sqlTweak, DB, collateralDBTaleName, reconWindow)
        # todo: debug if we need to tweak this or not for sqlTweak to take effect
        if sqlTweak is "":
            directCorrelationData = DB.QueryRAW("SELECT Entries_FilePaths.FirstRun,Entries_FilePaths.LastUpdate,Entries_FilePaths.FilePath,Entries_FilePaths.FileName,Entries_FilePaths.Size,Entries_FilePaths.ExecFlag, sum(Table1.Before), sum(Table1.After), sum(Table1.Weight) AS Weight \
            FROM %s AS Table1 JOIN Entries_FilePaths ON \
            Table1.RowID = Entries_FilePaths.RowID WHERE Entries_FilePaths.FileName  <> '%s' GROUP BY Entries_FilePaths.FileName \
            HAVING count(*) >= %d ORDER BY Weight DESC LIMIT %d" % (collateralDBTaleName, fileName, minCount, reconWindow))
        else:
            directCorrelationData = DB.QueryRAW("SELECT Entries_FilePaths.FirstRun,Entries_FilePaths.LastUpdate,Entries_FilePaths.FilePath,Entries_FilePaths.FileName,Entries_FilePaths.Size,Entries_FilePaths.ExecFlag, sum(Table1.Before), sum(Table1.After), sum(Table1.Weight) AS Weight \
            FROM %s AS Table1 JOIN Entries_FilePaths ON \
            Table1.RowID = Entries_FilePaths.RowID WHERE Entries_FilePaths.FileName  <> '%s' GROUP BY Entries_FilePaths.FileName \
            HAVING count(*) >= %d ORDER BY Weight DESC LIMIT %d" % (collateralDBTaleName, fileName, minCount, reconWindow))

        # Calculate inverse temporal correlations
        if directCorrelation and directCorrelationData != None:
            for i in xrange(0, len(directCorrelationData)):
                inverseTotalCount = DB.CountConditional("Entries", ['FileName'], [directCorrelationData[i][3]])
                invBond = False
                # todo: Probably have to add --sql tweak consideration to this count too
                # We ignore calculating the InvBond if its obvious we won't have one
                if inverseTotalCount < 2 * targetTotalCount:
                    inverseCorrelationData = appTcorrAmCache(directCorrelationData[i][3], sqlTweak, DB, False, reconWindow)
                    DB.Execute("DROP Table TemporalInverseCollateral")
                    # Tweak results to our needs
                    # Check if FileName is present in the inverse correlation results
                    for row in inverseCorrelationData:
                        if row[3].lower() == fileName.lower():
                            # Tag InvBond as True
                            invBond = True
                            break
                tmp = list(directCorrelationData[i])
                if invBond: tmp.append(u'True')
                else: tmp.append(u'  -  ')
                # Add Total_Count
                tmpTotalCount = DB.CountConditional("Entries", ["FileName"], [directCorrelationData[i][3]])
                tmp.append(tmpTotalCount)
                directCorrelationData[i] = tuple(tmp)

            if len(directCorrelationData) > 0:
                logger.info("AmCache temporal execution correlation candidates for %s:" % fileName)
                results = []
                results.append(('cyan',"FirstRun,LastUpdate,FilePath,FileName(*),Size,ExecFlag,Before,After,Weight,InvBond,Total_Count".split(',')))
                for row in directCorrelationData:
                    printRow = [row[x] for x in xrange(0, len(row))]
                    printRow[8] = round(row[8], 2)
                    results.append(('white', printRow))
                outputcolum(results)
                logger.info("(*)" \
                      " Note that context AmCache data is pulled from first match in DB as an example (dates, paths, sizes, of other correlating files with the same FileName could be different)")
            else:
                logger.info("No significant AmCache temporal execution correlations found (>=%d ocurrences)" % minCount)
                return []
        return directCorrelationData
    else:
        logger.info("No AmCache entries found for: %s" % fileName)
        return []


def PopulateAmCacheTemporalCollaterals(fileName, sqlTweak, DB, collateralDBTableName, reconWindow=3):
    countHostsProcessed = 0
    # Process each occurrence of the FileName
    if sqlTweak is "":
        data = DB.Query("SELECT RowID, HostID, FileName, FirstRun from Entries WHERE EntryType = %s AND FileName = '%s'" % (settings.__AMCACHE__, fileName))
    else: data = DB.Query("SELECT RowID, HostID, FileName, FirstRun from Entries_FilePaths WHERE EntryType = %s AND FileName = '%s' AND %s" % (settings.__AMCACHE__, fileName, sqlTweak))

    rowList = []
    countRowsToProcess = len(data)
    countRowsProcessed = 0
    # Executed before
    for row in data:
        rowID = row[0]
        hostID = row[1]
        fileName = row[2]
        firstRun = row[3]
        # Insert entry into DB
        DB.Execute("INSERT INTO " + collateralDBTableName + " VALUES (NULL,%s, 0, 0, 0, 0)" % (rowID))

        # Check recon window
        countRowsProcessed += 1
        update_progress(float(countRowsProcessed) / float(countRowsToProcess), fileName)
        minFirstRun = firstRun - datetime.timedelta(0,60 * reconWindow)
        maxFirstRun = firstRun + datetime.timedelta(0,60 * reconWindow)
        reconEntries = DB.Query("SELECT RowID, HostID, FileName, FirstRun FROM Entries WHERE EntryType = %s AND (FirstRun >= '%s' AND FirstRun <= '%s')" % (settings.__AMCACHE__, minFirstRun, maxFirstRun))
        # Filter out incorrect correlations when RowID jumps from one host to the next
        # Weight correlation value according to temporal execution distance
        for entry in reconEntries:
            if  entry[1] == hostID and entry[2] != fileName:
                weight = (1.0 / (math.pow(abs(rowID -entry[0]),2))*10)
                if entry[3] < firstRun:
                    rowList.append(tuple((int(entry[0]), 1, 0, weight)))
                else:
                    rowList.append(tuple((int(entry[0]), 0, 1, weight)))
    DB.ExecuteMany("INSERT INTO " + collateralDBTableName + " VALUES (NULL,?, ?, ?, ?, 0)", rowList)


def appTstomp(DB, options):
    ret = []
    num_hits = 0
    # todo: Add whitelist: C:\Windows\splwow64.exe
    tsCopyCatCandidates = "'kernel32.dll', 'svchost.exe', 'ntdll.dll', 'shlwapi.dll', 'shell32.dll', 'msiexec.exe', 'user.exe'"
    # Find correlations by LastModified between tsCopyCatCandidates in System32 and files that are not in System32 or SysWOW64
    # Process AppCompatCache
    if DB.CountConditional("Entries", ["EntryType"], [settings.__APPCOMPAT__]) > 0:
        logger.info("Searching AppCompatCache data for files not in System32 matching Modified2 TS from files in System32 on the same host")
        rows = DB.QuerySpinner("SELECT RowID, HostID, FilePath FROM Entries_FilePaths WHERE EntryType = "+str(settings.__APPCOMPAT__)+" AND FilePath = 'C:\Windows\System32' AND FileName IN ("+tsCopyCatCandidates+") \
                AND LastModified IN (SELECT LastModified from Entries_FilePaths as E2 WHERE Entries_FilePaths.HostID = E2.HostID \
                AND FilePath NOT LIKE '%Windows\\System32%' AND FilePath NOT LIKE '%Windows\\SysWOW64%')")

        results = []
        if len(rows) > 0:
            for row in rows:
                rowID = row[0]
                hostID = row[1]
                FilePath = row[2]

                counter = DB.QueryInt("SELECT count(*) FROM Entries_FilePaths \
                WHERE EntryType = "+str(settings.__APPCOMPAT__)+" AND HostID = "+str(hostID)+" AND FilePath NOT LIKE '%Windows\\System32%' AND FilePath NOT LIKE '%Windows\\SysWOW64%' \
                AND LastModified = (SELECT LastModified FROM Entries WHERE RowID = "+str(rowID)+")")
                if counter > 0:
                    results.append(('cyan',("\n=>%s,,,,,,," % DB.HostId2HostName(hostID)).split(',')))
                    # Fetch context
                    results.append(('cyan',"RowID,RowNumber,LastModified,LastUpdate,FilePath,FileName,Size,ExecFlag".split(',')))
                    rows2 = DB.QuerySpinner("SELECT RowID, RowNumber, LastModified, LastUpdate, FilePath, FileName, Size, ExecFlag \
                    FROM Entries_FilePaths WHERE EntryType = %s AND HostID = %s \
                    AND LastModified = (SELECT LastModified FROM Entries WHERE RowID = %s)" % (str(settings.__APPCOMPAT__), hostID, rowID))
                    for row2 in rows2:
                        if row2[0] == row[0]:
                            results.append(('red', row2))
                        else:
                            # Ignore matches in system32/SysWOW64
                            if "Windows\\System32".lower() in row2[4].lower() or "Windows\\SysWOW64".lower() in row2[4].lower(): continue
                            results.append(('white', row2))
                            num_hits += 1
            outputcolum(results)
            ret.extend(results)

    # Process AmCache
    if DB.CountConditional("Entries", ["EntryType"], [settings.__AMCACHE__]) > 0:
        logger.info("Searching AmCache data for files not in System32 matching Modified2 TS from files in System32 on the same host")
        # todo: This query takes ages...
        rows = DB.QuerySpinner("SELECT RowID, HostID, FilePath \
            FROM Entries_FilePaths \
            WHERE EntryType = "+str(settings.__AMCACHE__)+" \
            AND FileName LIKE '%.exe' \
            AND FilePath = 'C:\Windows\System32' \
            AND Modified2 <> '0001-01-01 00:00:00' \
            AND Modified2 IN \
                (SELECT Modified2 from Entries_FilePaths as E2 \
                WHERE Entries_FilePaths.HostID = E2.HostID \
                AND FilePath NOT LIKE '%Windows\\System32%' \
                AND FilePath NOT LIKE '%Windows\\SysWOW64%')")

        results = []
        if len(rows) > 0:
            for row in rows:
                rowID = row[0]
                hostID = row[1]
                FilePath = row[2]

                # todo: Figure out where the "AND FileName LIKE '%.exe'" snippet came from and if we still need it here:
                counter = DB.QueryInt("SELECT count(*) FROM Entries_FilePaths \
                WHERE EntryType = "+str(settings.__AMCACHE__)+" AND HostID = "+str(hostID)+" AND FileName LIKE '%.exe' AND FilePath NOT LIKE '%Windows\\System32%' AND FilePath NOT LIKE '%Windows\\SysWOW64%' \
                AND Modified2 = (SELECT Modified2 FROM Entries_FilePaths WHERE RowID = "+str(rowID)+")")
                if counter > 0:
                    results.append(('cyan',("\n=>%s,,,,,,," % DB.HostId2HostName(hostID)).split(',')))
                    # Fetch context
                    results.append(('cyan',"RowID,RowNumber,FirstRun,Modified2,FilePath,FileName,Size,ExecFlag".split(',')))
                    rows2 = DB.QuerySpinner("SELECT RowID, RowNumber, FirstRun, Modified2, FilePath, FileName, Size, ExecFlag \
                    FROM Entries_FilePaths WHERE EntryType = %s AND HostID = %s \
                    AND Modified2 = (SELECT Modified2 FROM Entries WHERE RowID = %s)" % (str(settings.__AMCACHE__), hostID, rowID))
                    for row2 in rows2:
                        if row2[0] == row[0]:
                            results.append(('red', row2))
                        else:
                            # Ignore matches in system32/SysWOW64
                            if row2[4] is not None:
                                if "Windows\\System32".lower() in row2[4].lower() or "Windows\\SysWOW64".lower() in row2[4].lower(): continue
                                results.append(('white', row2))
                                num_hits += 1
            outputcolum(results)
            ret.extend(results)
        else:
            logger.info("No results found")

        # Search for AmCache timestamps with microseconds = 0
        logger.info("Searching AmCache data for .exe's with a Modified2 timestamp with microseconds = 0 (noisy)")
        # SQLITE only uses the first 3 decimals to compare datetime fields so we filter down to that and then filter from there
        rows = DB.QuerySpinner("SELECT RowID, HostID, FirstRun, Modified2, FilePath, FileName, Size, ExecFlag FROM Entries_FilePaths \
                WHERE EntryType = "+str(settings.__AMCACHE__)+ " AND FileName LIKE '%.exe' AND FilePath <> 'None' \
                AND CAST(SUBSTR(strftime('%f', Modified2),4,3) as integer) = 0")

        results = []
        if len(rows) > 0:
            outputcolum([('cyan',("\nAltered creation timestamp candidates (0 microsecond timestamps),,,,,,,".split(',')))])
            results.append(('cyan',"RowID,HostName,FirstRun,Modified2,FilePath,FileName,Size,ExecFlag".split(',')))
            for row in rows:
                rowID = row[0]
                hostID = row[1]
                hostName = DB.HostId2HostName(hostID)
                FirstRun = row[2]
                Modified2 = row[3]
                FilePath = row[4]
                FileName = row[5]
                Size = row[6]
                ExecFlag = row[7]

                if Modified2.microsecond == 0:
                    results.append(('white', (rowID,hostName,FirstRun,Modified2,FilePath,FileName,Size,ExecFlag)))
            else:
                outputcolum(results)
                ret.extend(results)
        else:
            logger.info("No results found")

    if num_hits == 0:
        logger.info("No last modification dates matching any of our current targets detected (%s)" % tsCopyCatCandidates)
    return(ret)


def appLevenshteinDistance(DB, options):
    single_file_mode = False
    whitelist = defaultdict(list)
    if options.file_name:
        legit_file_names = [options.file_name]
        single_file_mode = True

    else:
        legit_file_names = [u'attrib.exe', u'audiodg.exe', u'auditpol.exe', u'autochk.exe', u'autoconv.exe', u'autofmt.exe',
                            u'bcdboot.exe', u'bcdedit.exe', u'bitsadmin.exe', u'bootcfg.exe', u'bthudtask.exe',
                            u'cacls.exe', u'calc.exe', u'certenrollctrl.exe', u'certreq.exe', u'certutil.exe',
                            u'change.exe', u'charmap.exe', u'chglogon.exe', u'chgport.exe', u'chgusr.exe', u'chkdsk.exe',
                            u'chkntfs.exe', u'choice.exe', u'cipher.exe', u'cleanmgr.exe', u'cliconfg.exe', u'clip.exe',
                            u'cmdl32.exe', u'cmmon32.exe', u'cmstp.exe', u'cofire.exe', u'colorcpl.exe', u'comp.exe',
                            u'compact.exe', u'compmgmtlauncher.exe', u'computerdefaults.exe', u'conhost.exe',
                            u'consent.exe', u'control.exe', u'convert.exe', u'credwiz.exe', u'cscript.exe', u'csrss.exe',
                            u'ctfmon.exe', u'cttune.exe', u'cttunesvr.exe', u'dccw.exe', u'dcomcnfg.exe', u'ddodiag.exe',
                            u'defrag.exe', u'devicedisplayobjectprovider.exe', u'deviceeject.exe',
                            u'devicepairingwizard.exe', u'deviceproperties.exe', u'dfdwiz.exe', u'dfrgui.exe',
                            u'dialer.exe', u'diantz.exe', u'dinotify.exe', u'diskpart.exe', u'diskperf.exe',
                            u'diskraid.exe', u'dism.exe', u'dispdiag.exe', u'displayswitch.exe', u'djoin.exe',
                            u'dllhost.exe', u'dllhst3g.exe', u'dnscacheugc.exe', u'doskey.exe', u'dpapimig.exe',
                            u'dpiscaling.exe', u'dpnsvr.exe', u'driverquery.exe', u'drvinst.exe', u'dvdplay.exe',
                            u'dvdupgrd.exe', u'dwm.exe', u'dwwin.exe', u'dxdiag.exe', u'dxpserver.exe', u'eap3host.exe',
                            u'efsui.exe', u'ehstorauthn.exe', u'esentutl.exe', u'eudcedit.exe', u'eventcreate.exe',
                            u'eventvwr.exe', u'expand.exe', u'extrac32.exe', u'fc.exe', u'find.exe', u'findstr.exe',
                            u'finger.exe', u'fixmapi.exe', u'fltmc.exe', u'fontview.exe', u'forfiles.exe', u'fsquirt.exe',
                            u'fsutil.exe', u'ftp.exe', u'fvenotify.exe', u'fveprompt.exe', u'fxscover.exe', u'fxssvc.exe',
                            u'fxsunatd.exe', u'getmac.exe', u'gettingstarted.exe', u'gpresult.exe', u'gpscript.exe',
                            u'gpupdate.exe', u'grpconv.exe', u'hdwwiz.exe', u'help.exe', u'hostname.exe', u'hwrcomp.exe',
                            u'hwrreg.exe', u'icacls.exe', u'icardagt.exe', u'icsunattend.exe', u'ie4uinit.exe',
                            u'ieunatt.exe', u'iexpress.exe', u'infdefaultinstall.exe', u'ipconfig.exe', u'irftp.exe',
                            u'iscsicli.exe', u'iscsicpl.exe', u'iscsiexe.dll', u'isoburn.exe', u'klist.exe', u'ksetup.exe',
                            u'ktmutil.exe', u'label.exe', u'locationnotifications.exe', u'locator.exe', u'lodctr.exe',
                            u'logagent.exe', u'logman.exe', u'logoff.exe', u'logonui.exe', u'lpksetup.exe', u'lpremove.exe',
                            u'lsass.exe', u'lsm.exe', u'magnify.exe', u'makecab.exe', u'manage-bde.exe', u'mblctr.exe',
                            u'mcbuilder.exe', u'mctadmin.exe', u'mdres.exe', u'mdsched.exe', u'mfpmp.exe',
                            u'migautoplay.exe', u'mmc.exe', u'mobsync.exe', u'mountvol.exe', u'mpnotify.exe', u'mrinfo.exe',
                            u'msconfig.exe', u'msdt.exe', u'msdtc.exe', u'msfeedssync.exe', u'msg.exe', u'mshta.exe',
                            u'msiexec.exe', u'msinfo32.exe', u'mspaint.exe', u'msra.exe', u'mstsc.exe', u'mtstocom.exe',
                            u'muiunattend.exe', u'multidigimon.exe', u'napstat.exe', u'narrator.exe', u'nbtstat.exe',
                            u'ndadmin.exe', u'net.exe', u'net1.exe', u'netbtugc.exe', u'netcfg.exe', u'netiougc.exe',
                            u'netplwiz.exe', u'netproj.exe', u'netsh.exe', u'netstat.exe', u'newdev.exe', u'nltest.exe',
                            u'notepad.exe', u'nslookup.exe', u'ntoskrnl.exe', u'ntprint.exe', u'ocsetup.exe',
                            u'odbcad32.exe', u'odbcconf.exe', u'openfiles.exe', u'optionalfeatures.exe', u'osk.exe',
                            u'p2phost.exe', u'pathping.exe', u'pcalua.exe', u'pcaui.exe', u'pcawrk.exe', u'pcwrun.exe',
                            u'perfmon.exe', u'ping.exe', u'pkgmgr.exe', u'plasrv.exe', u'pnpunattend.exe', u'pnputil.exe',
                            u'poqexec.exe', u'powercfg.exe', u'presentationhost.exe', u'presentationsettings.exe',
                            u'prevhost.exe', u'print.exe', u'printbrmui.exe', u'printfilterpipelinesvc.exe',
                            u'printisolationhost.exe', u'printui.exe', u'proquota.exe', u'psr.exe', u'qappsrv.exe',
                            u'qprocess.exe', u'query.exe', u'quser.exe', u'qwinsta.exe', u'rasautou.exe', u'rasdial.exe',
                            u'raserver.exe', u'rasphone.exe', u'rdpclip.exe', u'rdrleakdiag.exe', u'reagentc.exe',
                            u'recdisc.exe', u'recover.exe', u'reg.exe', u'regedt32.exe', u'regini.exe',
                            u'registeriepkeys.exe', u'regsvr32.exe', u'rekeywiz.exe', u'relog.exe', u'relpost.exe',
                            u'repair-bde.exe', u'replace.exe', u'reset.exe', u'resmon.exe', u'rmactivate.exe',
                            u'rmactivate_isv.exe', u'rmactivate_ssp.exe', u'rmactivate_ssp_isv.exe', u'rmclient.exe',
                            u'robocopy.exe', u'route.exe', u'rpcping.exe', u'rrinstaller.exe', u'rstrui.exe', u'runas.exe',
                            u'rundll32.exe', u'runlegacycplelevated.exe', u'runonce.exe', u'rwinsta.exe', u'sbunattend.exe',
                            u'sc.exe', u'schtasks.exe', u'sdbinst.exe', u'sdchange.exe', u'sdclt.exe', u'sdiagnhost.exe',
                            u'searchfilterhost.exe', u'searchindexer.exe', u'searchprotocolhost.exe', u'secedit.exe',
                            u'secinit.exe', u'services.exe', u'sethc.exe', u'setieinstalleddate.exe', u'setspn.exe',
                            u'setupcl.exe', u'setupugc.exe', u'setx.exe', u'sfc.exe', u'shadow.exe', u'shrpubw.exe',
                            u'shutdown.exe', u'sigverif.exe', u'slui.exe', u'smss.exe', u'sndvol.exe', u'snippingtool.exe',
                            u'snmptrap.exe', u'sort.exe', u'soundrecorder.exe', u'spinstall.exe', u'spoolsv.exe',
                            u'sppsvc.exe', u'spreview.exe', u'srdelayed.exe', u'stikynot.exe', u'subst.exe', u'svchost.exe',
                            u'sxstrace.exe', u'synchost.exe', u'syskey.exe', u'systeminfo.exe',
                            u'systempropertiesadvanced.exe', u'systempropertiescomputername.exe',
                            u'systempropertiesdataexecutionprevention.exe', u'systempropertieshardware.exe',
                            u'systempropertiesperformance.exe', u'systempropertiesprotection.exe',
                            u'systempropertiesremote.exe', u'systray.exe', u'tabcal.exe', u'takeown.exe',
                            u'tapiunattend.exe', u'taskeng.exe', u'taskhost.exe', u'taskkill.exe', u'tasklist.exe',
                            u'taskmgr.exe', u'tcmsetup.exe', u'tcpsvcs.exe', u'timeout.exe', u'tpminit.exe',
                            u'tracerpt.exe', u'tracert.exe', u'tscon.exe', u'tsdiscon.exe', u'tskill.exe', u'tstheme.exe',
                            u'tswbprxy.exe', u'tswpfwrp.exe', u'typeperf.exe', u'tzutil.exe', u'ucsvc.exe',
                            u'ui0detect.exe', u'unlodctr.exe', u'unregmp2.exe', u'upnpcont.exe',
                            u'useraccountcontrolsettings.exe', u'userinit.exe', u'utilman.exe', u'vaultcmd.exe',
                            u'vaultsysui.exe', u'vds.exe', u'vdsldr.exe', u'verclsid.exe', u'verifier.exe', u'vmicsvc.exe',
                            u'vssadmin.exe', u'vssvc.exe', u'w32tm.exe', u'waitfor.exe', u'wbadmin.exe', u'wbengine.exe',
                            u'wecutil.exe', u'werfault.exe', u'werfaultsecure.exe', u'wermgr.exe', u'wevtutil.exe',
                            u'wextract.exe', u'wfs.exe', u'where.exe', u'whoami.exe', u'wiaacmgr.exe', u'wiawow64.exe',
                            u'wimserv.exe', u'windowsanytimeupgraderesults.exe', u'wininit.exe', u'winload.exe',
                            u'winlogon.exe', u'winresume.exe', u'winrs.exe', u'winrshost.exe', u'winsat.exe', u'winver.exe',
                            u'wisptis.exe', u'wksprt.exe', u'wlanext.exe', u'wlrmdr.exe', u'wowreg32.exe',
                            u'wpdshextautoplay.exe', u'wpnpinst.exe', u'write.exe', u'wscript.exe', u'wsmanhttpconfig.exe',
                            u'wsmprovhost.exe', u'wsqmcons.exe', u'wuapp.exe', u'wuauclt.exe', u'wudfhost.exe', u'wusa.exe',
                            u'xcopy.exe', u'xpsrchvw.exe', u'xwizard.exe']


        whitelist['ftp.exe'].append('tftp.exe')
        whitelist['sc.exe'].append('scw.exe')
        whitelist['tracerpt.exe'].append('tracert.exe')
        whitelist['dxdiag.exe'].append('dcdiag.exe')
        whitelist['taskhost.exe'].append('taskhostw.exe')
        whitelist['fsutil.exe'].append('dfsutil.exe')

    if single_file_mode:
        logger.info("Creating list of unique file names, hold on...")
        data = DB.QuerySpinner("SELECT DISTINCT FileName from Entries_FilePaths")
    else:
        logger.info("Creating list of unique file names in C:\Windows\System32, hold on...")
        data = DB.QuerySpinner("SELECT DISTINCT FileName from Entries_FilePaths WHERE FilePath = 'C:\Windows\System32'")

    unique_files = set()
    if len(data) > 0:
        for row in data:
            unique_files.add(row[0])

    logger.info("Searching for deviations, max distance: %d." % (options.distance))
    suspicious_files = []
    progressCurrent = 0
    progressTotal = len(unique_files) * len(legit_file_names)
    for real_name in legit_file_names:
        for file_name in unique_files:
            distance = Levenshtein.distance(real_name.lower(), file_name.lower())
            if (distance > 0  and distance <= options.distance):
                if file_name.lower() not in legit_file_names:
                    if file_name.lower() not in whitelist[real_name.lower()]:
                        if single_file_mode:
                            hit_count = DB.CountConditional("Entries_FilePaths", ["FileName"], [file_name])
                        else:
                            hit_count = DB.CountConditional("Entries_FilePaths", ["FileName", "FilePath"],
                                                   [file_name, "C:\Windows\System32"])
                        suspicious_files.append(("'"+real_name+"'", "'"+file_name+"'", hit_count))

            progressCurrent += 1
            update_progress(float(progressCurrent) / float(progressTotal))

    results = []
    if suspicious_files:
        if single_file_mode:
            results.append(('cyan', "Legit FileName,Suspicious FileName,Hit_Count".split(',')))
        else: results.append(('cyan', "Legit FileName,Suspicious FileName,Hit_Count (in System32)".split(',')))
        for row in suspicious_files:
            results.append(('white', row))
        outputcolum(results)

    return results


def appHitCount(DB, searchTermsFile, options):
    if os.path.isfile(searchTermsFile):
        with open(searchTermsFile) as f:
            searchTerms = f.read().splitlines()
        searchTerms = ','.join('"{0}"'.format(w) for w in searchTerms)

        data = DB.Query("SELECT FileName, count(FileName) AS Hits FROM Entries_FilePaths WHERE FileName IN (%s) GROUP BY FileName ORDER BY Hits DESC;" % (searchTerms))
        results = []
        results.append(('cyan',"FileName,HitCount".split(',')))
        for row in data:
            results.append(('white', row))
        outputcolum(results)
        return (len(results), results)
    else:
        logger.error("File with search terms not found!")
        raise Exception("File with search terms not found!")


def appHashSearch(DB, options):
    cryo_data = []
    if options.hashsearch_file:
        if os.path.isfile(options.hashsearch_file):
            with open(options.hashsearch_file) as f:
                for line in f:
                    if (" - " in line):
                        m = re.match("^([a-z0-9]{40}) - (.*)$", line)
                        if m:
                            cryo_data.append((m.group(1), m.group(2)))
                        else:
                            logger.error("Unknown hashsearch output! (%s) - skipping" % line)

            progressTotal = len(cryo_data)
            progressCurrent = 0
            for item in cryo_data:
                sha1 = item[0]
                cryo_tags = item[1]
                try:
                    data = DB.Query("Select HostName, FirstRun, FilePath||'\\'||FileName, SHA1 FROM Entries_FilePaths \
                                        INNER JOIN Hosts ON Entries_FilePaths.hostID = Hosts.hostID WHERE SHA1 = '%s'" % (sha1))
                except Exception as e:
                    traceback.print_exc(file=sys.stdout)
                results = []
                if data:
                    print "\n\nHits for [%s - %s]:" % (sha1, cryo_tags)
                    results.append(('cyan', "HostName,FirstRun,FilePath,FileName,SHA1".split(',')))
                    for row in data:
                        results.append(('white', row))
                    outputcolum(results)

                # Update progress
                progressCurrent += 1
                update_progress(float(progressCurrent) / float(progressTotal))
        else:
            logger.error("File with hashsearch output not found!")
            raise Exception("File with hashsearch output not found!")


def appListHosts(DB):
    results = []
    conn = DB.appConnectDB()
    data = DB.Query("SELECT HostID, HostName, Instances, Recon, ReconScoring FROM Hosts ORDER BY ReconScoring DESC")
    results.append(('cyan', ('HostID', 'HostName', 'Instances', 'Recon', 'ReconScoring')))
    for row in data:
        results.append(('white', (row[0], row[1], len(eval(row[2])), row[3], row[4])))
    return (outputcolum(results))


def appDumpHost(DB, hostName, options):
    dump = []
    dumped_host = False
    if DB.HasAppCompat(hostName):
        print "AppCompat data:"
        # Dump AppCompat
        data = DB.Query("SELECT LastModified, LastUpdate, FilePath||'\\'||FileName, Size, ExecFlag \
                FROM Entries_FilePaths JOIN Hosts ON Entries_FilePaths.HostID = Hosts.HostID AND Hosts.HostName = '%s' \
                WHERE EntryType = '0' ORDER BY RowNumber ASC" % hostName)
        dumped_host = True
        print "Last Modified,Last Update,Path,File Size,Exec Flag"
        dump.append("Last Modified,Last Update,Path,File Size,Exec Flag")
        for row in data:
            if ','.join('"' + item + '"' for item in map(str, row)) not in dump:
                print ','.join('"' + item + '"' for item in map(str, row))
                dump.append(','.join('"' + item + '"' for item in map(str, row)))

    if DB.HasAmCache(hostName):
        # todo: Consider dumping raw and in a convenient timeline format onto a second file
        print "AmCache data:"
        # Dump AmCache
        data = DB.Query("SELECT FirstRun, Created, FilePath||'\\'||FileName, Size, SHA1, FileDescription, \
                        Modified1, Modified2, LinkerTS, Product, Company, PE_sizeofimage, Version_number, Version, \
                        Language, Header_hash, PE_checksum, SwitchBackContext \
                        FROM Entries_FilePaths JOIN Hosts ON Entries_FilePaths.HostID = Hosts.HostID AND Hosts.HostName = '%s' \
                        WHERE EntryType = '1' ORDER BY FirstRun ASC" % hostName)
        dumped_host = True
        if data:
            print "FirstRun,Created,Path,File Size,SHA1, FileDescription, Modified1, Modified2, LinkerTS, Product, Company, PE_sizeofimage, Version_number, Version, Language, Header_hash, PE_checksum, SwitchBackContext"
            dump.append("Last Modified,Last Update,Path,File Size,Exec Flag, Modified1, Modified2")
            for row in data:
                if ','.join('"' + item + '"' for item in map(str, row)) not in dump:
                    print ','.join('"' + item + '"' for item in map(str, row))
                    dump.append(','.join('"' + item + '"' for item in map(str, row)))
        else:
            print "Sorry, no data to dump (did you get an exception maybe?)"

    if not dumped_host:
        logger.error("No data for host: %s" % hostName)
        dump.append("No data for host: %s" % hostName)

    return dump


def appTimeStack(DB, options):
    tstack_data = []
    # Check we have the indexes we want for this:
    DB.appRequireIndexesDB("index_EntriesFirstRun", "CREATE INDEX index_EntriesFirstRun on Entries(FirstRun)")
    DB.appRequireIndexesDB("index_EntriesLastModified", "CREATE INDEX index_EntriesLastModified on Entries(LastModified)")

    print "Starting Time Stacker"
    hits_total = DB.QuerySpinner("SELECT LOWER(FileName), count(*) FROM Entries_FilePaths WHERE %s GROUP BY LOWER(FileName)" % options.stack_from)
    hits_in = DB.QuerySpinner("SELECT LOWER(FileName), FileName, count(*) FROM Entries_FilePaths WHERE \
                        (CASE WHEN EntryType = 0 then LastModified else FirstRun END) >= '%s' \
                        AND (CASE WHEN EntryType = 0 then LastModified else FirstRun END) <= '%s' \
                        AND %s \
                        GROUP BY LOWER(FileName)" % (options.start_date, options.end_date, options.stack_from))

    hits_total_lookup = dict(hits_total)
    hits_total = []
    for item in hits_in:
        file_name_lower = item[0]
        file_name = item[1]
        hits_in = item[2]
        hits_out = hits_total_lookup[item[0]] - hits_in
        tstack_data.append((file_name, hits_in, hits_out, float(hits_in) / max(0.1, float(hits_out)), len(file_name)))

    # Sort time-stacked data
    tstack_data.sort(key=lambda tup: float(tup[1]) / max(0.1, float(tup[2])), reverse=True)

    # Print results:
    results = []
    results.append(('cyan', ('FullPath', 'Hits In', 'Hits Out', 'Ratio')))
    # limit = 60
    for item in tstack_data:
        # if limit == 0: break
        # limit -= 1
        ratio = '%.3f' % (float(item[1]) / max(0.1, float(item[2])))
        if ratio < 1.0: break
        results.append(('white', (item[0], item[1], item[2], ratio )))

    return (outputcolum(results))


def appStack(DB, options):
    import operator
    results = []

    # Grab data
    rows = DB.QuerySpinner("SELECT %s FROM Entries_FilePaths WHERE %s" %(options.stack_what.strip('\\\''), options.stack_from))
    if (len(rows) > 0):
        # Stack it up manually, seems to be much faster that the equivalent GROUP BY
        stack = defaultdict(int)
        for row in rows:
            stack[tuple(row)] += 1

        sorted_stack = sorted(stack.items(), key=operator.itemgetter(1))
        filler = ',-' * (len(rows[0]) - 2)
        results.append(('cyan', ("Count,What %s" % filler).split(',')))
        for item in sorted_stack:
            results.append(('white', (item[1], ', '.join([str(x) for x in item[0]]))))
        outputcolum(results)
    else:
        print "No results"

    return results


def rndsearch(DB, options):
    from zxcvbn import zxcvbn
    from datetime import timedelta

    freq_list = dict()
    results = list()

    print("Searching for likely random filenames where len(filename)=8|16 and filepath in (C:\, C:\Windows\Temp, C:\Windows, C:\Windows\System32, ADMIN$)")
    if options.path is not None:
        print("Performing analysis on:\n %s" % (options.path))
        query = "SELECT DISTINCT(FileName) FROM Entries_FilePaths WHERE FileName LIKE '%.exe' AND (FilePath = '{}')".format(options.path)
    else:
        print("Performing analysis on:\n C:\, C:\Windows, C:\Windows\Windows\System32, %\ADMIN$")
        query = "SELECT DISTINCT(FileName) FROM Entries_FilePaths WHERE FileName LIKE '%.exe' AND (LENGTH(FileName) = 8+1+3 OR LENGTH(FileName) = 11+1+3 OR LENGTH(FileName) = 16+1+3) AND (FilePath = 'C:\\' OR FilePath = 'C:\\Windows\\Temp' OR FilePath = 'C:\\Windows' OR FilePath = 'C:\\Windows\\Windows\\System32' OR FilePath LIKE '%\\ADMIN$\\' OR FilePath LIKE '%\\ADMIN$')"

    # Grab unique filenames of interest
    rows = DB.QuerySpinner(query)
    if (len(rows) > 0):
        for row in rows:
            filenameFull = row[0]
            filename = os.path.splitext(filenameFull)[0]
            fileext = os.path.splitext(filenameFull)[1]
            length = len(filename)

            #Check how common the actual filename is in the dataset
            hostCount = DB.QueryInt("SELECT COUNT(DISTINCT(HostID)) FROM Entries_FilePaths WHERE FileName = '%s'" % (filenameFull))
            if hostCount > 2:
                #print("Too common?: %s [#hosts: %s]" % (filenameFull, hostCount))
                pass
            else:
                # Calc_time seemed like a good idea but doesn't really yield the results I was looking for, needs more work.
                td = zxcvbn(filename, user_inputs=[])['calc_time']
                results.append((filenameFull, td, hostCount))

        results = sorted(results, key=lambda i: i[1], reverse=True)

        for item in results:
            print("Potentially random: %s [rnd: %s | #hosts: %s]" % (item[0], item[1], item[2]))
            rows = DB.Query("SELECT RowID FROM Entries WHERE FileName = '%s'" % item[0])
            for row in rows:
                DB.PrintEntryRowID(row[0])


def main(args):
    global logger
    DB = None
    ret = None

    # Bail out on unsupported environments
    # todo: Bring back support for Windows
    if os.name == 'nt':
        print("Support for running AppCompatProcessor on Windows platforms has been temporarily removed.")
        print("Differing implementations of multiprocessing mean that an important re-write of the logging module is required.")
        exit(0)
    if sys.version_info < 2.7:
        print "Python 2.7+ required"
        exit(0)

    oParser = argparse.ArgumentParser(description = __description__, formatter_class=argparse.RawTextHelpFormatter)
    if len(args) > 0 and '--version' not in args[0]:
        oParser.add_argument("database_file", help="The database to create or work with")
    oParser.add_argument('--maxCores', action="store", type=int, dest="maxCores", default=max(1, multiprocessing.cpu_count()), help='set maximum number of cores to use')
    oParser.add_argument('-o', action="store", type=str, dest="outputFile", default="Output.txt", help='custom output file')
    oParser.add_argument('-r', action="store_true", dest="rawoutput", default=False, help='remove termcolor use')
    oParser.add_argument('-v', action='count', dest='verbose', default=0, help='verbose logging')
    oParser.add_argument('--version', action='version', version="Version: %s" % settings.__version__)
    subparsers = oParser.add_subparsers(dest="module_name")
    loadParser = subparsers.add_parser('load', help='Load (or add new) AppCompat / AmCache data')
    loadParser.add_argument('pathtoload', type=str, help='path to load into the database')
    loadParser.add_argument('--governorOff', action="store_true", dest="governorOffFlag", default=False, help='activate memory governor')
    statusParser = subparsers.add_parser('status', help='Print status of database')
    listParser = subparsers.add_parser('list', help='List hosts in database')
    dumpParser = subparsers.add_parser('dump', help='Recreate AppCompat/AmCache dump for a given host')
    dumpParser.add_argument('host_name', type=str, help='hostname to dump')
    searchParser = subparsers.add_parser('search', help='Search module')
    searchParser.add_argument('knownbad_file', nargs='?', help='file with known bad regular expressions, defaults to AppCompatSearch.txt delivered with the tool')
    searchParser.add_argument('-f', action='store', dest="searchRegex", nargs=1, help='regex search')
    searchParser.add_argument('-F', action='store', dest="searchLiteral", nargs=1, help='literal search')
    fsearchParser = subparsers.add_parser('fsearch', help='Field search module')
    fsearchParser.add_argument('field_name', type=str, help='database field to search')
    fsearchParser.add_argument('-F', action="store", type=str, dest="searchLiteral", nargs=1, help='literal search')
    fsearchParser.add_argument('-f', action="store", type=str, dest="searchRegex", nargs=1, help='regex search')
    fsearchParser.add_argument('--sql', action="store_true", dest="sqlTweak", default=False, help='interpret field name as RAW SQL to build the SearchSpace')
    filehitcountParser = subparsers.add_parser('filehitcount', help='Count # of FileName hits from a user supplied file')
    filehitcountParser.add_argument('file_path', type=str, help='file with filename for filehitcount module')
    tcorrParser = subparsers.add_parser('tcorr', help='Perform temporal execution correlation on a user supplied filename')
    tcorrParser.add_argument('tcorr_filename', type=str, help='filename to calculate execution correlations for')
    tcorrParser.add_argument('-w', action="store", type=int, dest="window", default=5, help='recon window size')
    tcorrParser.add_argument('--sql', action="store", type=str, dest="sqlTweak", default="", help='tweak fsearch/tcorr sql queries')
    ptcorrParser = subparsers.add_parser('ptcorr', help='Print temporal correlation context for the previously calculated tcorr')
    ptcorrParser.add_argument('ptcorr_filename', type=str, help='filename to print execution correlations for')
    ptcorrParser.add_argument('-w', action="store", type=int, dest="window", default=5, help='recon window size')
    tstompParser = subparsers.add_parser('tstomp', help='Attempt to detect modified last modification timestamps (experimental)')
    tstackParser = subparsers.add_parser('tstack', help='Time stacking module (experimental)')
    tstackParser.add_argument('start_date', type=str, help='start date')
    tstackParser.add_argument('end_date', type=str, help='end date')
    tstackParser.add_argument('stack_from', type=str, nargs='?', default='1=1', help='sql snippet, what to stack (defaults to all entries)')
    stackParser = subparsers.add_parser('stack', help='Good old stacking with a sql twist')
    stackParser.add_argument('stack_what', type=str, help='sql snippet of what to stack')
    stackParser.add_argument('stack_from', type=str, nargs='?', default='1=1', help='sql snippet, what to stack (defaults to all entries)')
    levenParser = subparsers.add_parser('leven', help='Find file name anomalies based on Levenshtein distance')
    levenParser.add_argument('file_name', type=lambda s: unicode(s, 'utf8'), nargs='?', help='filename to perform Levenshtein analysis on')
    levenParser.add_argument('-d', action="store", type=int, dest="distance", default=1, help='max Levenshtein distance to report')
    reconscanParser = subparsers.add_parser('reconscan', help='Calculate recon activity in the database')
    preconParser = subparsers.add_parser('precon', help='Print contextual activity to recon commands identified on a host')
    preconParser.add_argument('host_name', type=lambda s: unicode(s, 'utf8'), help='host name')
    preconParser.add_argument('-w', action="store", type=int, dest="window", default=5, help='recon window size')
    fevilParser = subparsers.add_parser('fevil', help='Use temporal correlation on recon sessions to find potential evil (experimental)')
    fevilParser.add_argument('-w', action="store", type=int, dest="window", default=5, help='recon window size')
    rndSearchParser = subparsers.add_parser('rndsearch', help='Experimental - search for randomly named files of interest')
    rndSearchParser.add_argument('-p', action="store", type=str, dest="path", default=None, help='Perform analysis the path provided')
    hashsearchParser = subparsers.add_parser('hashsearch', help='hashsearch module')
    hashsearchParser.add_argument('hashsearch_file', nargs='?', help='file with significant SHA1 hashes to process')
    testsetParser = subparsers.add_parser('testset', help='Build fake testset database')
    testsetParser.add_argument('num_hosts', type=int, nargs='?', default=10, help='number of fake hosts to populate (default 10)')
    options = oParser.parse_args(args)

    # Setup the logger
    settings.logger_Sart(options.outputFile, options.verbose)
    logger = logging.getLogger(__name__)
    logger.info("Starting to process request...")

    # Log dbg stuff
    logger.debug("Arguments [%d]: %s" % (len(args), args))
    logger.debug("Options: %s" % (options))

    # Testset module
    if(options.module_name == "testset"):
        if settings.__FAKER__:
            if options.database_file:
                bdname = build_fake_DB(options.num_hosts, 0, options.database_file)
            else: bdname = build_fake_DB(options.num_hosts, 0)
        else: logger.error("testset module unavailable, you need the python faker module for that.")
        settings.logger_Stop()
        exit(0)

    # Set output flag
    settings.rawOutput = options.rawoutput

    if len(args) == 0:
        logger.info("Detected CPUs: %d" % multiprocessing.cpu_count())
        oParser.print_help()
        print('')
        return
    elif len(args) > 1:
        # Init DB if required
        dbfilenameFullPath = options.database_file
        DB = appDB.DBClass(dbfilenameFullPath, (True if options.module_name == 'load' else False), settings.__version__)
        if DB.appInitDB():
            conn = DB.appConnectDB()
            logger.debug("Database version: %s" % DB.appDBGetVersion())

            # Log dbg stuff
            DB.appDBDebugInfo()

            if(options.module_name == "status"):
                logger.info("Displaying database status...")
                ret = DB.Status()
                (dbfilenameFullPath, versionDB, num_hosts, num_instances, num_entries) = ret
                logger.info("DB: %s" % dbfilenameFullPath)
                logger.info("DB version: %s" % versionDB)
                logger.info("Total hosts: %d" % num_hosts)
                logger.info("Total instances: %d" % num_instances)
                logger.info("Total entries: %d" % num_entries)
            elif(options.module_name == "list"):
                ret = appListHosts(DB)
            elif(options.module_name == "load"):
                logger.info("Loading / adding records to database...")
                if os.path.isdir(options.pathtoload) or\
                    (os.path.isfile(options.pathtoload) and options.pathtoload.endswith('.zip')):
                    appLoadMP(options.pathtoload, dbfilenameFullPath, options.maxCores, options.governorOffFlag)
                    ret = DB.Status()
                    (dbfilenameFullPath, versionDB, num_hosts, num_instances, num_entries) = ret
                    print("\n")
                    logger.info("Loading done.")
                    logger.info("Total hosts: %d" % num_hosts)
                    logger.info("Total instances: %d" % num_instances)
                    logger.info("Total entries: %d" % num_entries)
                else:
                    logger.error("Invalid path: %s" % options.pathtoload)
            elif(options.module_name == "search" or options.module_name == "fsearch"):
                syntaxError = False
                if not os.path.isfile(options.database_file):
                    logger.error("Expecting a database, got: %s" % options.database_file)
                    syntaxError = True
                if options.module_name == "search":
                    search_space = "(FilePath || '\\' || FileName)"

                    # Check if a search pattern was provided
                    if not options.searchLiteral and not options.searchRegex:
                        # Check if the user provided a known_bad file to use
                        # default=os.path.join(os.path.dirname(__file__),"AppCompatSearch.txt")
                        if not options.knownbad_file:
                            # We first try to set the file to the same folder ACP is running from
                            options.knownbad_file = os.path.join(os.path.dirname(__file__), 'AppCompatSearch.txt')
                            if not os.path.isfile(options.knownbad_file):
                                options.knownbad_file = '/etc/AppCompatProcessor/AppCompatSearch.txt'
                                if not os.path.isfile(options.knownbad_file):
                                    logger.error("Sorry, can't find know bad file: %s" % options.knownbad_file)
                                    syntaxError = True
                        else:
                            # We check if the user provided known bad file exists
                            if not os.path.isfile(options.knownbad_file):
                                logger.error("Sorry, can't find know bad file: %s" % options.knownbad_file)

                else:
                    if options.searchRegex and options.searchRegex[0] in ['>','<']:
                        logger.error("</> search term modifiers make no sense in a REGEX search")
                        syntaxError = True

                    # Check for 'list' field name
                    if options.field_name == "list":
                        print DB.getFields("Entries_FilePaths")
                        syntaxError = True

                    # Check field exists in the Entries table:
                    entries_fields = DB.getFields("Entries_FilePaths")
                    if not options.sqlTweak and options.field_name.lower() not in entries_fields:
                        logger.error("Field does not exist in Entries_FilePaths table (use: fsearch 'list')")
                        syntaxError = True
                    else:
                        # Setup SearchSpace
                        search_space = options.field_name

                    # Check if we have an index on it and create it if we don't
                    # todo: Discriminate on what table we need to create the index (will fail for non-entries fields like FilePath)
                    # index_name = 'index_Entries'+str.lower(options.field_name)
                    # DB.appRequireIndexesDB(index_name, "CREATE INDEX "+index_name+" on Entries("+options.field_name+")", quiet=False)

                if not syntaxError:
                    if(options.searchRegex is not None and options.searchLiteral is not None):
                        logger.info("Searching for combined literal/regex: %s/%s - SearchSpace: %s => %s" % (options.searchLiteral[0], options.searchRegex[0], search_space, options.outputFile))
                        ret = appSearchMP(dbfilenameFullPath, 'COMBINED', search_space, options)
                    elif options.searchRegex is not None:
                        logger.info("Searching for regex: %s - SearchSpace: %s => %s" % (options.searchRegex[0], search_space, options.outputFile))
                        ret = appSearchMP(dbfilenameFullPath, 'REGEX', search_space, options)
                    elif options.searchLiteral is not None:
                        logger.info("Searching for literal: %s - SearchSpace: %s => %s" % (options.searchLiteral[0], search_space, options.outputFile))
                        ret = appSearchMP(dbfilenameFullPath, 'LITERAL', search_space, options)
                    elif options.searchRegex is None and options.searchLiteral is None:
                        logger.info("Searching for known bad list: %s (%d search terms) - SearchSpace: %s => %s" % (options.knownbad_file, KnownBadRegexCount(options.knownbad_file), search_space, options.outputFile))
                        ret = appSearchMP(dbfilenameFullPath, 'KNOWNBAD', search_space, options)
                    else:
                        print "Can't figure out what you're trying to do here..."
            elif(options.module_name == "tcorr"):
                ret = appTcorr(options.tcorr_filename.decode(sys.getfilesystemencoding()), options.sqlTweak, DB, True, options.window)
            elif(options.module_name == "ptcorr"):
                ret = PrintCollateralActivity(options.ptcorr_filename, DB, options.window)
            elif(options.module_name == "reconscan"):
                logger.info("Analysing database for recon activity...")
                ReconScan(DB, options)
                ReconTally(DB, options)
                ret = HostsReconScoringUpdate(DB, options)
            elif (options.module_name == "precon"):
                ret = PrintReconActivity(DB, options)
            elif(options.module_name == "fevil"):
                logger.info("Searching for evil...")
                ret = FindEvil(DB, options)
            elif(options.module_name == "tstomp"):
                ret = appTstomp(DB, options)
            elif (options.module_name == "leven"):
                if settings.__LEVEN__:
                    ret = appLevenshteinDistance(DB, options)
                else:
                    logger.error("Missing Levenshtein python module, sorry!")
            elif(options.module_name == "filehitcount"):
                if len(args) > 2 and os.path.isfile(args[2]):
                    ret = appHitCount(DB, args[2], options)
                else:
                    logger.error("Path to file with filenames to count missing!")
            elif(options.module_name == "dump"):
                ret = appDumpHost(DB, options.host_name, options)
            elif (options.module_name == "tstack"):
                ret = appTimeStack(DB, options)
            elif (options.module_name == "stack"):
                ret = appStack(DB, options)
            elif(options.module_name == "hashsearch"):
                if options.hashsearch_file:
                    ret = appHashSearch(DB, options)
            elif(options.module_name == "shell"):
                cfg = Config()
                # See ipython.config.py
                prompt_config = cfg.PromptManager
                # prompt_config.confirm_exit = False
                prompt_config.in_template = 'N.In <\\#>: '
                prompt_config.in2_template = '   .\\D.: '
                prompt_config.out_template = 'N.Out<\\#>: '
                cfg.InteractiveShellEmbed.autocall = 2
                banner_msg = ("AppCompat Processor interactive shell started.\n"
                "Press CTRL+D to exit")
                exit_msg = 'Leaving AppCompat Processor shell'
                cfg.TerminalInteractiveShell.confirm_exit = False

                ipshell = InteractiveShellEmbed(config=cfg, banner1=banner_msg, exit_msg=exit_msg)
                ipshell()
            elif(options.module_name == "rndsearch"):
                    rndsearch(DB, options)

    logger.info("Done")
    settings.logger_Stop()
    print "\n"
    return ret


if __name__ == '__main__':
    import sys
    main(sys.argv[1:])