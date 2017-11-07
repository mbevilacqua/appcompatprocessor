import settings
import logging
import multiprocessing
import collections
import os
import re
from contextlib import closing
import time
import ntpath
import appDB
from appAux import update_progress, outputcolum, file_len
import hashlib
import operator
from datetime import timedelta
import glob
from collections import namedtuple
from namedlist import namedlist

logger = logging.getLogger(__name__)
reBulk_compiled = None

def re_fn(expr, item):
    global reBulk_compiled

    # Avoid unnecesary re-compilations of unified regex (<- almost useless with RE cache but was worth a shot)
    if reBulk_compiled is None:
        try:
            reBulk_compiled = re.compile(expr, re.IGNORECASE)
        except re.error, e:
            logger.debug("Error on regular expression: %s - %s" %(expr, e))
            raise
    return reBulk_compiled.search(item) is not None


class Producer(multiprocessing.Process):

    def __init__(self, task_queue, result_queue, dbfilenameFullPath, val, num_consumers, searchType, search_space, options, num_hits, known_bad_data):
        multiprocessing.Process.__init__(self)
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.dbfilenameFullPath = dbfilenameFullPath
        self.searchType = searchType
        self.val = val
        self.proc_name = self.name
        self.num_consumers = num_consumers
        self.search_space = search_space
        self.options = options
        self.num_hits = num_hits
        self.search_modifier_present_Literal = False
        self.search_modifier_Literal = ""
        self.search_modifier_present_Regex = False
        self.search_modifier_Regex = ""
        self.searchTermLiteral= ""
        self.searchTermRegex = ""
        self.searchTermRegexFilters = ""
        self.known_bad = None
        self.known_bad_with_filter = None

        # Extract searchTerm from options
        if searchType == "LITERAL":
            searchTerm = (options.searchLiteral[0], None)
        elif searchType == "REGEX":
            searchTerm = (None, options.searchRegex[0])
        elif searchType == "COMBINED":
            searchTerm = (options.searchLiteral[0], options.searchRegex[0])
        elif searchType == "KNOWNBAD":
            (self.searchTermRegex, self.searchTermRegexFilters, self.known_bad) = known_bad_data
            # Copy known_bad to known_bad_with_filter
            self.known_bad_with_filter = list(self.known_bad)
            # Drop from known_bad_with_filter entries with no filters, we have those covered in self.searchTermRegex
            for x in list(self.known_bad_with_filter):
                if x.filter is None:
                    self.known_bad_with_filter.remove(x)

        # Check for search modifiers on LITERAL
        if searchType == "LITERAL":
            if searchTerm[0][0] in ['=','>','<']:
                self.search_modifier_present_Literal = True
                self.search_modifier_Literal = searchTerm[0][0]
        # Check for search modifiers on REGEX
        if searchType == "REGEX" or searchType == "COMBINED":
            if searchTerm[1][0] in ['=','>','<']:
                self.search_modifier_present_Regex = True
                self.search_modifier_Regex = searchTerm[1][0]

        # Check the search type selected
        if searchType == "REGEX" or searchType == "COMBINED":
            if self.search_modifier_present_Regex:
                if self.search_modifier_Regex == "=":
                    self.searchTermRegex = '^' + searchTerm[1][1:].lower() + '$'
                else:
                    print "Invalid modifier! WTF?"
                    exit(-1)
            else:
                self.searchTermRegex = searchTerm[1].lower()
        if searchType == "LITERAL" or searchType == "COMBINED":
            if self.search_modifier_present_Literal:
                self.searchTermLiteral = searchTerm[0][1:].lower()
            else:
                self.searchTermLiteral = '%'+searchTerm[0].lower()+'%'

    def getPID(self):
        return (self.pid)

    def addHit(self, data):
        # logger.debug("%s - producing hit %d - %d" %(self.proc_name, self.num_hits.value, data))
        self.result_queue.put(data)
        with self.num_hits.get_lock():
            self.num_hits.value += 1

    def run(self):
        DB = appDB.DBClass(self.dbfilenameFullPath, True, settings.__version__)
        DB.appInitDB()
        conn = DB.appConnectDB()
        filter_skipped = 0

        # While there are tasks to be ran we grab and run them
        while True:
            # Start timer
            t0 = time.time()
            taskRows = []

            # Grab next job from job queue
            next_task = self.task_queue.get()
            if next_task is None:
                # Poison pill means shutdown
                self.task_queue.task_done()
                # Pass poison pills
                for _ in xrange(self.num_consumers):
                    self.result_queue.put(None)
                    logger.debug("%s - Adding poison pill for consumer" % (self.proc_name))
                logger.debug("%s - Exiting process" % (self.proc_name))
                # We're skipping way to much stuff improve filter skipper counter to detect what regexes have to be tightened
                logger.debug("filter_skipped: %d" % filter_skipped)
                return

            # Grab job data
            (startingRowID, entriesPerJob) = next_task()
            with closing(conn.cursor()) as c:
                # Start timer
                t0 = time.time()
                logger.debug("%s - Starting query [%d / %d]. SearchSpace: %s" % (self.proc_name, startingRowID, entriesPerJob, self.search_space))
                if self.searchType == 'REGEX' or self.searchType == 'KNOWNBAD':
                    results = c.execute("SELECT RowID, " + self.search_space + " AS SearchSpace FROM Entries_FilePaths \
                                        WHERE RowID >= %d AND RowID <= %d" %(startingRowID, startingRowID+entriesPerJob))
                elif self.searchType == 'LITERAL' or self.searchType == 'COMBINED':
                    if self.search_modifier_Literal in [">","<"]:
                        results = c.execute("SELECT RowID, " + self.search_space + " AS SearchSpace FROM Entries_FilePaths \
                                            WHERE RowID >= %d AND RowID <= %d \
                                            AND SearchSpace %s '%s'" % (startingRowID, startingRowID+entriesPerJob, self.search_modifier_Literal, self.searchTermLiteral))
                    else:
                        results = c.execute("SELECT RowID, " + self.search_space + " AS SearchSpace FROM Entries_FilePaths \
                                            WHERE RowID >= %d AND RowID <= %d \
                                            AND SearchSpace LIKE '%s'" % (startingRowID, startingRowID+entriesPerJob, self.searchTermLiteral))
                else:
                    logger.error("Unknown searchType %s" % (self.searchType))

                t1 = time.time()
                logger.debug("%s - Execute time: %s seconds" % (self.proc_name, "{0:.4f}".format(t1 - t0)))
                rows = c.fetchall()
                t2 = time.time()
                logger.debug("%s - Fetchall time: %s seconds (%s / %s)" % (self.proc_name, "{0:.4f}".format(t2 - t1), startingRowID, entriesPerJob))

                # Process row per row:
                for row in rows:
                    if row[1] is not None:
                        if self.searchType == 'LITERAL':
                            self.addHit(int(row[0]))
                        elif self.searchType == 'REGEX' or self.searchType == 'COMBINED':
                                if re_fn(self.searchTermRegex, str(row[1])):
                                    self.addHit(int(row[0]))
                        elif self.searchType == 'KNOWNBAD':
                                # Search for known bads with no filters:
                                if self.searchTermRegex != "()":
                                    if re_fn(self.searchTermRegex, str(row[1])):
                                        self.addHit(int(row[0]))
                                # Search for known bads which have a filter associated:
                                for x in list(self.known_bad_with_filter):
                                    assert(x.filter is not None)
                                    if re.compile(x.regex, re.IGNORECASE).search(str(row[1])) is not None:
                                        if re.compile(x.filter, re.IGNORECASE).search(str(row[1])) is None:
                                            self.addHit(int(row[0]))
                                            # One hit is enough for us
                                            break
                                        # fixme:
                                        else: filter_skipped += 1
                        else:
                            logger.error("Unknown searchType %s" % (self.searchType))

            t3 = time.time()
            logger.debug("%s - REGEX filtering time: %s seconds (%s / %s)" % (
            self.proc_name, "{0:.4f}".format(t3 - t2), startingRowID, entriesPerJob))
            if (t3 - t2) > 30:
                logger.warning("Warning: Producer queues clogged, throttling down.")
            logger.debug("%s Task results: %d execution time: %s seconds" % (self.proc_name, len(taskRows), "{0:.4f}".format(t3 - t0)))

            # Update progress counter
            with self.val.get_lock():
                self.val.value += 1
            self.task_queue.task_done()
        logger.warning("%s - Abnormal exit" % (self.proc_name))


class Task(object):
    def __init__(self, startingRowID, entriesPerJob):
        self.startingRowID = startingRowID
        self.entriesPerJob = entriesPerJob

    def __call__(self):
        return (self.startingRowID, self.entriesPerJob)


def ValidateRegex(regex, filter):
    if regex is not None:
        if u'\u200b' in regex:
            logger.warning("Warning: Regex has a zero width unicode character in it (used in .mmd file): %s" % regex)
        # Check for spaces at the end
        if regex[len(regex) - 1:len(regex)] == ' ':
            logger.warning("Warning: Regex has space at the end and won't match unless you really know what you're doing: %s" % regex)
        # Validate compile
        try:
            tmp_compiled_regex = re.compile(regex, re.IGNORECASE)
        except re.error, e:
            logger.debug("Error on regular expression: %s - %s" % (regex, e))
            return False

    if filter is not None:
        if u'\u200b' in filter:
            logger.warning("Warning: Filter has a zero width unicode character in it: %s" % filter)
        # Check for spaces at the end
        if regex[len(filter) - 1:len(filter)] == ' ':
            logger.warning("Warning: Filter has space at the end and won't match unless you really know what you're doing: %s" % filter)
        # Validate compile
        try:
            tmp_compiled_regex = re.compile(filter, re.IGNORECASE)
        except re.error, e:
            logger.debug("Error on regular expression: %s - %s" % (filter, e))
            return False
    return True


def LoadRegexBulkSearch(file_full_path):
    SearchLine = collections.namedtuple('SearchLine', 'name, regex, filter')
    regex_terms = []
    filter_delimiter = " / "

    file_path = ntpath.dirname(file_full_path)
    file_name, file_extension = os.path.splitext(file_full_path)

    # Load base file
    with open(file_full_path) as f:
        lines = f.read().splitlines()

    # Load extra files
    for filename in glob.iglob(file_name + '-*' +  file_extension):
        with open(filename) as f:
            lines += f.read().splitlines()

    # Load Known Bad queries and filters
    line_regex = re.compile(r'^(\[.*\])=(.*)$')
    line_regex_with_filter = re.compile(r'^(\[.*\])=(.*)%s\((.*)\)$' % filter_delimiter)

    # Start processing regular expressions
    for line in lines:
        if len(line) == 0: continue
        if line.startswith('#'): continue
        if "<RegexSignatures>" in line: continue
        if "</RegexSignatures>" == line: continue
        # Split on filtering separator
        if filter_delimiter in line:
            m = line_regex_with_filter.match(line)
            if m:
                # Convert regexes into non-capturing as they mess our MultiMarkDown tagging:
                clean_regex = m.group(2).replace('(?!', '[]').replace('(?:', '(').replace('(', '(?:').replace('[]', '(?!')
                clean_filter = m.group(3).strip()
                # Validate
                if ValidateRegex(clean_regex, clean_filter):
                    regex_terms.append(SearchLine(name=m.group(1), regex=clean_regex, filter=clean_filter))
            else:
                # Check if it's a simple regex that happens to have our delimiter somewhere in the pattern
                m = line_regex.match(line)
                if m:
                    # Convert regexes into non-capturing as they mess our MultiMarkDown tagging:
                    clean_regex = m.group(2).replace('(?!', '[]').replace('(?:', '(').replace('(', '(?:').replace('[]',
                                                                                                                  '(?!')
                    # Validate
                    if ValidateRegex(clean_regex, None):
                        regex_terms.append(SearchLine(name=m.group(1), regex=clean_regex, filter=None))
                else:
                    logger.warning("Warning: Looks like a bad formated line, skipping: %s" % line)
        else:
            m = line_regex.match(line)
            if m:
                # Convert regexes into non-capturing as they mess our MultiMarkDown tagging:
                clean_regex = m.group(2).replace('(?!', '[]').replace('(?:', '(').replace('(', '(?:').replace('[]', '(?!')
                # Validate
                if ValidateRegex(clean_regex, None):
                    regex_terms.append(SearchLine(name=m.group(1), regex=clean_regex, filter=None))
            else:
                logger.warning("Warning: Looks like a bad formated line, skipping: %s" % line)

    if regex_terms:
        # We setup the concatenation of regexes with no filters as searchTermRegex"
        tmp_list = []
        for x in list(regex_terms):
            if x.filter is None:
                tmp_list.append(x.regex)

        searchTermRegex = "(" + "|".join(tmp_list) + ")"
        logger.debug("Regex: %s" % searchTermRegex)

        # todo: Currently not used consider removing.
        # We setup the concatenation of filters as the searchTermRegexFilters:
        tmp_list[:] = []
        for x in list(regex_terms):
            if x.filter is not None:
                tmp_list.append(x.filter)
        searchTermRegexFilters = "(" + "|".join(tmp_list) + ")"
        logger.debug("Filters: %s" % searchTermRegexFilters)
    else:
        logger.error("No valid search terms found in %s" % file_full_path)
        raise Exception("No valid search terms found in %s" % file_full_path)

    return (searchTermRegex, searchTermRegexFilters, regex_terms)


def KnownBadRegexCount(file_full_path):
    file_path = ntpath.dirname(file_full_path)
    file_name, file_extension = os.path.splitext(file_full_path)

    # Load base file
    total_regex_count = KnownBadRegexCountFile(file_full_path)

    # Load extra files
    for filename in glob.iglob(file_name + '-*' +  file_extension):
        total_regex_count += KnownBadRegexCountFile(filename)

    return total_regex_count

def KnownBadRegexCountFile(file_full_path):
    num_expressions = 0
    with open(file_full_path) as f:
        lines = f.read().splitlines()

    for line in lines:
        if len(line) == 0: continue
        if line.startswith('#'): continue
        if "<RegexSignatures>" == line: continue
        if "</RegexSignatures>" == line: break
        num_expressions += 1

    return num_expressions

class Consumer(multiprocessing.Process):
    def __init__(self, task_queue, result_queue, val, num_producers, outputFile, dbfilenameFullPath, searchType, search_space, options, num_hits, num_hits_suppressed, hitHistogram_queue, known_bad_data):
        multiprocessing.Process.__init__(self)
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.val = val
        self.proc_name = self.name
        self.outputFile = outputFile
        self.dbfilenameFullPath = dbfilenameFullPath
        self.searchType = searchType
        self.search_space = search_space
        self.options = options
        self.num_hits = num_hits
        self.num_hits_suppressed = num_hits_suppressed
        self.hitHistogram_queue = hitHistogram_queue
        self.known_bad_data = known_bad_data
        self.DB = None
        self.conn = None
        self.num_producers = num_producers

    def getPID(self):
        return (self.pid)

    def run(self):
        proc_name = self.name
        exitFlag = False
        hit_dict = {}
        logger.debug("%s - Starting consumer process" % (self.proc_name))

        # Init DB if required
        self.DB = appDB.DBClass(self.dbfilenameFullPath, True, settings.__version__)
        self.conn = self.DB.appConnectDB()

        # Load known_bad if required
        if self.searchType == 'KNOWNBAD':
            (searchTermRegex, searchTermRegexFilters, known_bad_search_terms) = self.known_bad_data
            for x in known_bad_search_terms:
                hit_dict[x.regex] = [0, x.name, x.regex]

        # Open output files:
        tmp_counter = 0
        with open(self.outputFile, "w") as text_file:
            with open(os.path.join(ntpath.dirname(self.outputFile), ntpath.splitext(self.outputFile)[0] + ".mmd"), "w") as markdown_file:

                # While there are results to be processed we grab them and process them
                # todo: [High] We're holding all hits in memory now, stage file dumping activity?
                rowID_list = []
                while not exitFlag:
                    # Grab next result from queue
                    rowID = self.task_queue.get()
                    # Check for poison pill from Producers
                    if rowID is None:
                        self.num_producers -= 1
                        logger.debug("%s - Found one poison pill %d Producers left" % (self.proc_name, self.num_producers))
                        # Check if all Producers have finished
                        if self.num_producers == 0:
                            # Reverse poison pill
                            self.result_queue.put(None)
                            logger.debug("%s - Exiting process" % (self.proc_name))
                            exitFlag = True
                            continue
                    else:
                        tmp_counter += 1
                        # logger.debug("%s - consuming hit #%d: %d" % (self.proc_name, tmp_counter, rowID))
                        rowID_list.append(rowID)

                # Finished grabbing rowID, now we dump them all:
                dumped_set = set()
                for rowID in rowID_list:
                    # Grab entry data we want to save to the output file:
                    record = retrieveSearchData(rowID, self.DB, self.search_space)

                    # De-dup results:
                    entryMD5 = hashlib.md5(''.join([str(e) for e in [record[0],record[1],record[2],record[3],record[4],record[5],record[9]]])).hexdigest()
                    if entryMD5 in dumped_set:
                        # print("Suppressing row %d" % entry[6])
                        with self.num_hits_suppressed.get_lock():
                            self.num_hits_suppressed.value += 1
                    else:
                        dumped_set.add(entryMD5)
                        # Re-filter against known bad individually to build histogram and highlight
                        regex_hit_name = None
                        search_space = None
                        if self.searchType == 'KNOWNBAD':
                            # Search for known_bad one by one and filter if required
                            for x in list(known_bad_search_terms):
                                if re.compile(x.regex, re.IGNORECASE).search(str(record.Search_Space)) is not None:
                                    if x.filter is not None:
                                        if re.compile(x.filter, re.IGNORECASE).search(str(record.Search_Space)) is not None:
                                            regex_hit_name = x.name
                                            continue
                                    # 'u200b' is a zero width unicode character I have to use to avoid messy markdown highlighting:
                                    search_space = re.compile('(.*)('+x.regex+')(.*)', re.I).sub(r'\1'+u'\u200b'+r'**'+u'\u200b'+r'\2'+u'\u200b'+'**'+u'\u200b'+r'\3', record.Search_Space, re.IGNORECASE)
                                    # Add hit to know_bad hit counter:
                                    regex_hit_name = x.name
                                    hit_dict[x.regex][0] += 1

                                    # We only report the match with the first regex from our set
                                    break
                            # Program flow should never really make it here :)
                            assert(False, "We're in trouble")
                        else:
                            search_space = record.Search_Space
                            # search_space will be None if Producer hit but Consumer did not:
                            if search_space is None:
                                if regex_hit_name:
                                    logger.error(
                                        "Producer/Consumer hit mismatch (consumer filtered) ! (report bug please) sig: %s - %s" % (
                                            regex_hit_name, record.Search_Space))
                                else:
                                    logger.error("Producer/Consumer hit mismatch! (report bug please) - %s" % record.Search_Space)
                                pass

                        # We dump the data to the output file/s
                        saveSearchData(record, self.searchType, regex_hit_name, text_file, markdown_file)

                    # Update progress counter
                    with self.val.get_lock():
                        self.val.value += 1

        # Dump hit histogram
        time.sleep(0.5)
        for x in sorted(hit_dict.values(), key=operator.itemgetter(0), reverse=True):
            if x[0] > 0:
                self.hitHistogram_queue.put((x[1], x[2], x[0]))

def retrieveSearchData(rowID, DB, search_space):
    queryRecordList = ["HostName","FilePath","FileName","LastModified","LastUpdate","Size","ExecFlag","RowID","EntryType","FirstRun","SHA1","Search_Space"]
    queryRecordFields = namedlist("queryRecordList", queryRecordList, default=None)

    # Grab all fields in the queryRecordList
    selectQuery = ','.join(queryRecordList)
    selectQuery = selectQuery.replace('Search_Space', search_space)
    # Execute the query
    entry = DB.Query("SELECT %s FROM Entries_FilePaths INNER JOIN Hosts \
        ON Entries_FilePaths.HostID = Hosts.HostID WHERE RowID = '%s'" % (selectQuery, rowID))[0]

    # todo: There has to be a more pythonic way to do this
    record = queryRecordFields()
    tmpDict = dict(zip(queryRecordList, entry))
    i = 0
    for field in queryRecordList:
        record[i] = tmpDict[field]
        i += 1
    return record


def saveSearchData(record, searchType, regex_hit_name, text_file, markdown_file):
    sha1 = ""

    if record.EntryType == settings.__APPCOMPAT__:
        entry_type = "Ap"
        date1 = record.LastModified
    else:
        entry_type = "Am"
        date1 = record.FirstRun
        if record.SHA1 is not None:
            sha1 = " [" + record.SHA1 + "]"

    # Add name of regex that was hit to simplify searching and filtering (on KnownBad searches only)
    if searchType == 'KNOWNBAD':
        markdown_file.write("%s %s %s %s %s %s %s (%s)\n" % (
            regex_hit_name, record.HostName, date1, record.LastUpdate, record.Search_Space, record.Size, record.ExecFlag, entry_type))
        text_file.write("%s %s %s %s %s %s %s (%s)\n" % \
            (regex_hit_name, record.HostName, date1, record.LastUpdate, record.Search_Space, record.Size, record.ExecFlag, entry_type))
    else:
        markdown_file.write("%s %s %s %s %s %s (%s)%s\n" % (
            record.HostName, date1, record.LastUpdate, record.FilePath + '\\' + record.FileName, record.Size, record.ExecFlag, entry_type, sha1))
        text_file.write("%s %s %s %s %s %s (%s)%s\n" % \
            (record.HostName, date1, record.LastUpdate, record.FilePath + '\\' + record.FileName, record.Size, record.ExecFlag, entry_type, sha1))


def runIndexedSearch(dbfilenameFullPath, search_space, options):
    # todo: Handle duplicate hit supression
    logger.info("Performing indexed search")
    DB = appDB.DBClass(dbfilenameFullPath, True, settings.__version__)
    DB.appInitDB()
    DB.appConnectDB()

    searchTerm = options.searchLiteral[0]
    numHits = 0
    # Run actual indexed query
    data = DB.Query("SELECT RowID FROM Entries_FilePaths WHERE %s == '%s';" % (search_space, searchTerm))
    if data:
        # results = []
        # results.append(('cyan', "FileName,HitCount".split(',')))
        with open(options.outputFile, "w") as text_file:
            with open(os.path.join(ntpath.dirname(options.outputFile), ntpath.splitext(options.outputFile)[0] + ".mmd"), "w") as markdown_file:
                for row in data:
                    # results.append(('white', row))
                    record = retrieveSearchData(row[0], DB, search_space)
                    saveSearchData(record, None, None, text_file, markdown_file)
                    numHits += 1
                # outputcolum(results)

        return (numHits, 0, [])
    else: return(0, 0, [])


def appSearchMP(dbfilenameFullPath, searchType, search_space, options):
    (outputFile, maxCores) = (options.outputFile, options.maxCores)
    known_bad_data = None
    # Start timer
    t0 = time.time()

    # If possible use the available indexes
    if searchType == 'LITERAL' and options.searchLiteral[0][0] not in ['=','>','<'] and (search_space.lower() == 'filename' or search_space.lower() == 'filepath'):
        num_hits = namedtuple('hits', 'value')
        num_hits_suppressed = namedtuple('hits', 'value')
        (num_hits.value, num_hits_suppressed.value, results) = runIndexedSearch(dbfilenameFullPath, search_space, options)

    else:
        # Get total number of entries to search
        DB = appDB.DBClass(dbfilenameFullPath, True, settings.__version__)
        conn = DB.appConnectDB()
        entriesCount = DB.CountEntries()
        logger.debug("Total entries in search space: %d" % entriesCount)

        # Pre-load known_bad if required
        if searchType == 'KNOWNBAD':
            known_bad_data = LoadRegexBulkSearch(options.knownbad_file)

        # Establish communication queues
        tasks = multiprocessing.JoinableQueue()
        resultsProducers = multiprocessing.Queue()
        resultsConsumers = multiprocessing.Queue()
        hitHistogram_queue = multiprocessing.Queue()

        # Start producers/consumers
        num_consumers = 1
        num_producers = max(1, maxCores - 1)

        # Prep lock for progress update Producers
        progProducers = multiprocessing.Value('i', 0)
        # Prep lock for progress update Consumers
        progConsumers = multiprocessing.Value('i', 0)
        # Prep Consumers return values
        num_hits = multiprocessing.Value('i', 0)
        num_hits_suppressed = multiprocessing.Value('i', 0)

        logger.debug('Using %d cores for searching / %d cores for dumping results' % (num_producers, num_consumers))

        # Queue tasks for Producers
        # Limit rowsPerJob to constrain memory use and ensure reasonable progress updates
        rowsPerJob = min((entriesCount / 8), 5000)
        logger.debug("RowsPerJob: %d" % rowsPerJob)
        num_tasks = 0
        for startingRowID in range(0, entriesCount-rowsPerJob, rowsPerJob):
            tasks.put(Task(startingRowID, rowsPerJob - 1))
            logger.debug("Creating search job %d: [%d - %d]" % (num_tasks, startingRowID, startingRowID + rowsPerJob - 1))
            num_tasks += 1
        logger.debug("Creating search job %d: [%d - %d]" % (num_tasks, num_tasks*(rowsPerJob), ((num_tasks*rowsPerJob) + (entriesCount - (num_tasks*(rowsPerJob)- 1)))))
        # Special consideration for the last one:
        tasks.put(Task(num_tasks*(rowsPerJob), (entriesCount - ((num_tasks*rowsPerJob)- 1))))
        logger.debug("Number of tasks: %d" % num_tasks)

        # Add a poison pill for each producer
        for i in xrange(num_producers):
            tasks.put(None)

        # Start producer threads
        producers = [Producer(tasks, resultsProducers, dbfilenameFullPath, progProducers, num_consumers, \
                              searchType, search_space, options, num_hits, known_bad_data) for i in xrange(num_producers)]
        for producer in producers:
            producer.daemon = True # Remove for debugging
            producer.start()

        # Start consumer threads
        consumers = [Consumer(resultsProducers, resultsConsumers, progConsumers, num_producers, outputFile, \
                              dbfilenameFullPath, searchType, search_space, options, num_hits, \
                              num_hits_suppressed, hitHistogram_queue, known_bad_data) for i in xrange(num_consumers)]
        for consumer in consumers:
            consumer.daemon = True  # Remove for debugging
            consumer.start()

        # Producer progress loop
        while (num_tasks > progProducers.value and progProducers.value >= 0):
            logger.debug("Producer num_tasks: %d - v.value: %d" % (num_tasks, progProducers.value))
            update_progress(min(1, float(progProducers.value) / float(num_tasks)), "Searching [%d]" % (num_hits.value - num_hits_suppressed.value))
            time.sleep(0.5)
        update_progress(1, "Searching [%d]" % (num_hits.value - num_hits_suppressed.value))

        # Wait for consumers dumping results to finish too
        while (num_hits.value > progConsumers.value and progConsumers.value >= 0):
            logger.debug("Consuming hit: %d / %d" % (progConsumers.value, num_hits.value))
            update_progress(min(1, float(progConsumers.value) / float(num_hits.value)), "Dumping results to disk [%d]" % progConsumers.value)
            time.sleep(0.5)

        # Make sure we dumped as many hits as we found
        assert(num_hits.value == progConsumers.value)
        update_progress(1, "Dumping results to disk [%d]" % progConsumers.value)

        # Track Consumers deaths
        logger.debug("Waiting for consumer reverse-poison pills")
        while num_consumers > 0:
            tmp = resultsConsumers.get()
            # Check for reverse-poison pill
            if tmp is None:
                num_consumers -= 1
                logger.debug("Consumer finished!")
        logger.debug("All consumers accounted for")

        # Wait for consumer threads to finish
        logger.debug("Waiting for consumer threads to finish")
        for consumer in consumers:
            consumer.join()
        logger.debug("Consumer threads finished")

        # Print hit histogram:
        results = []
        results.append(('cyan', ("Hit histogram:","","")))
        while not hitHistogram_queue.empty():
            (name, regex, regex_hits) = hitHistogram_queue.get()
            results.append(('white', (name, regex, regex_hits)))
        if len(results) > 1:
            outputcolum(results)

    # Stop timer
    t1 = time.time()

    logger.info("Search hits: %d" % num_hits.value)
    logger.info("Suppresed duplicate hits: %d" % num_hits_suppressed.value)
    logger.info("Search time: %s" % (str(timedelta(seconds=(t1 - t0)))))

    if num_hits.value:
        logger.info("Head:")
        # Dump head of output file:
        num_lines = file_len(options.outputFile)
        from itertools import islice
        with open(options.outputFile) as myfile:
            head = list(islice(myfile, 5))
        for line in head:
            logger.info(line.strip('\n\r'))
        logger.info("(%d lines suppressed)" % max(0, (num_lines - 5)))

    return (num_hits.value, num_hits_suppressed.value, results)
