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


class TestAppLeven(TestCase):
    # Build test dataset
    testset1 = build_fake_DB(3)

    def __del__(self):
        # Remove temp dbs
        os.remove(self.testset1)

    def test_Leven(self):
        rndFileName = ''.join(random.choice(string.ascii_uppercase) for _ in range(15))
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            # Add stuff
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__, FilePath='C:\Windows\System32', FileName=rndFileName)
            add_entry(DB, "TestHost01", entry_fields)

            # Run
            leven_fileName = 'a' + rndFileName
            ret = main([self.testset1, "leven", leven_fileName])
            # Check we found the right file
            self.assertEquals(ret[1][1][1], "'"+rndFileName+"'", "test_Leven failed!")


    def test_Leven2(self):
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            # Add stuff
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__, FilePath='C:\Windows\System32',
                FileName='svchosts.exe')
            add_entry(DB, "TestHost01", entry_fields)

            # Run
            ret = main([self.testset1, "leven"])
            # Check we found the right file
            self.assertEquals('svchosts.exe' in ret[1][1][1], True, "test_Leven2 failed!")
