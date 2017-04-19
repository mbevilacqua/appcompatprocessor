from __future__ import absolute_import
import logging
from unittest import TestCase
import settings
import sys, traceback
reload(sys)
sys.setdefaultencoding("utf-8")
import os
from AppCompatProcessor import main, appDumpHost
import tempfile
import re, codecs
import datetime
import appDB
from test.auxTest import build_fake_DB

# Setup the logger
logger = logging.getLogger()

class TestAppDump(TestCase):
    # Build test dataset
    testset10 = build_fake_DB(10)

    def __del__(self):
        # Remove temp dbs
        os.remove(self.testset10)

    def BuildTestPath(self, folder):
        master_test_folder = os.path.join(os.path.abspath(os.path.join(os.path.join(os.path.dirname(__file__), os.pardir), os.pardir)), "appcompatprocessor-DataSets")
        load_test_path = os.path.join(master_test_folder, folder)
        return load_test_path

    def count_lines_regex(self, input_filename, regex_string):
        regex = re.compile(regex_string, re.IGNORECASE)
        count = 0

        with codecs.open(input_filename, 'r', 'UTF8') as inputFile:
            content = inputFile.readlines()
            for line in content:
                if regex.search(line) is not None:
                    count += 1

        return count


    def test_Dump(self):
        try:
            # Init DB if required
            with appDB.DBClass(self.testset10, settings.__version__) as DB:
                DB.appInitDB()
                conn = DB.appConnectDB()

                # Get host list
                data = DB.Query("SELECT HostID, HostName, Recon, ReconScoring FROM Hosts ORDER BY ReconScoring DESC")
                # Dump all hosts
                for row in data:
                    hostname = row[1]
                    # Get temp dump filename
                    temp = tempfile.NamedTemporaryFile(suffix='.txt', prefix='testCase', dir=tempfile.gettempdir())
                    dump_filename = temp.name
                    temp.close()

                    # Dump host
                    dump = appDumpHost(DB, hostname, None)
                    appCompatREGEX = re.compile(
                        r'"((?:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})|N\/A)","((?:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})|N\/A)","(.*)\\([^\\]*)","(N\/A|\d*)","(N\/A|True|False)"')
                    with open(dump_filename, "wb") as file:
                        for item in dump:
                            if item == 'Last Modified,Last Update,Path,File Size,Exec Flag':
                                file.write("%s\r\n" % item)
                            else:
                                m = appCompatREGEX.match(item)
                                if m:
                                    if m.group(1) == '0001-01-01 00:00:00':
                                        LastModified = 'N/A'
                                    else:
                                        LastModified = datetime.datetime.strptime(unicode(m.group(1)),
                                        '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
                                    if m.group(2) == '0001-01-01 00:00:00':
                                        LastUpdate = 'N/A'
                                    else:
                                        LastUpdate = datetime.datetime.strptime(unicode(m.group(2)),
                                        '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
                                    file.write("%s,%s,%s\\%s,%s,%s\r\n" % (
                                    LastModified, LastUpdate, unicode(m.group(3)), unicode(m.group(4)), unicode(m.group(5)),
                                    unicode(m.group(6))))

                    # Remove dumped host
                    os.remove(dump_filename)

        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")