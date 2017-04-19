from __future__ import absolute_import
import logging
from unittest import TestCase
import settings
import sys, traceback
reload(sys)
sys.setdefaultencoding("utf-8")
import os
from AppCompatProcessor import main
import appDB
import random
import string
from test.auxTest import build_fake_DB, add_entry

# Setup the logger
logger = logging.getLogger()
DB = None


class TestAppStack(TestCase):
    # Build test dataset
    testset1 = build_fake_DB(3)

    def __del__(self):
        # Remove temp dbs
        os.remove(self.testset1)

    def test_Stack(self):
        rndFileName = ''.join(random.choice(string.ascii_uppercase) for _ in range(15))
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            # Add stuff to stack
            for i in xrange(0,10):
                entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                    FilePath='C:\Windows', FileName=rndFileName, Size=i, ExecFlag='True')
                add_entry(DB, "TestHost01", entry_fields)

            # Run
            ret = main([self.testset1, "stack", "FileName", "FilePath = 'c:\Windows'"])

        # Check status count == db count
        count = int([i[1][0] for i in ret if rndFileName in i[1]][0])
        self.assertEquals(count, 10, "test_Stack failed!")


    def test_Stack_Generic01(self):
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            # Run
            (db_filenameFullPath, db_version, db_count, num_instances, num_entries) = main([self.testset1, "status"])
            ret = main([self.testset1, "stack", "FileName"])

        for item_count, item_file_name in [(int(i[1][0]), i[1][1]) for i in ret[1:]][1:10]:
            print "Checking: " + item_file_name
            (num_hits, num_hits_suppressed, results) = main([self.testset1, "search", "-F", '\\'+item_file_name])
            self.assertEquals(num_hits, item_count, "test_Stack_Generic01 failed!")
            (num_hits2, num_hits_suppressed2, results2) = main([self.testset1, "fsearch", "FileName", "-F", "="+item_file_name])
            self.assertEquals(num_hits2, item_count, "test_Stack_Generic01 failed!")

        # Check total entry count from stacking on FileName = total # entries.
        count = sum([int(i[1][0]) for i in ret[1:]])
        self.assertEquals(count, num_entries, "test_Stack_Generic01 failed!")
