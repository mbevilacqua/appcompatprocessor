from __future__ import absolute_import
import logging
from unittest import TestCase
import settings
import sys, traceback
reload(sys)
sys.setdefaultencoding("utf-8")
import os
from AppCompatProcessor import main
import tempfile
import appDB
from auxTest import build_fake_DB, add_entry

# Setup the logger
logger = logging.getLogger()
DB = None


class TestAppFilehitcount(TestCase):
    # Build test dataset
    fake_bd_num_records = 3
    testset1 = build_fake_DB(fake_bd_num_records)

    def __del__(self):
        # Remove temp dbs
        os.remove(self.testset1)

    def test_Filehitcount1(self):
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__, FilePath='C:\Temp', FileName='test123.exe')
            add_entry(DB, "TestHost01", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__, FilePath='C:\Temp', FileName='test1234.exe')
            add_entry(DB, "TestHost01", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__, FilePath='C:\\test123.exe', FileName='nohit.exe')
            add_entry(DB, "TestHost01", entry_fields)

            # Get temp db name for the test
            temp_file = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
            temp_file.close()
            with open(temp_file.name, 'w') as fh:
                fh.write('test123.exe')

            try:
                ret = main([self.testset1, "filehitcount", temp_file.name])
            except Exception as e:
                print traceback.format_exc()
                self.fail(e.message + "\n" + traceback.format_exc())

            # Remove temp file
            os.remove(temp_file.name)

            num_hits = len(ret)
            self.assertEquals(num_hits, 2, sys._getframe().f_code.co_name)
            self.assertEquals(ret[1][1][1][0], 'test123.exe', "test_Tstomp1 failed!")
            self.assertEquals(int(ret[1][1][1][1]), 1, "test_Tstomp1 failed!")

