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
from auxTest import build_fake_DB, add_entry

# Setup the logger
logger = logging.getLogger()
DB = None


class TestAppTStack(TestCase):
    # Build test dataset
    testset1 = build_fake_DB(3)

    def __del__(self):
        # Remove temp dbs
        os.remove(self.testset1)

    def test_TStack(self):
        rndFileName = 'randomfilename.rnd'
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            # Add stuff to stack
            for i in xrange(0,10):
                entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                    FilePath='C:\Windows', FileName=rndFileName, Size=i, LastModified = '1000-01-01 00:00:0' + str(i))
                add_entry(DB, "TestHost01", entry_fields)

            # Run
            ret = main([self.testset1, "tstack", '1000-01-01', '1000-01-02'])

        # Check we found the right file
        self.assertEquals(ret[1][1][0], rndFileName, "test_TStack failed!")
        # Check expected in count
        self.assertEquals(int(ret[1][1][1]), 10, "test_TStack failed!")
        # Check expected out count
        self.assertEquals(int(ret[1][1][2]), 0, "test_TStack failed!")


