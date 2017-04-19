from __future__ import absolute_import
import logging
from unittest import TestCase
import settings
import sys, traceback
reload(sys)
sys.setdefaultencoding("utf-8")
import os
from AppCompatProcessor import main
from ShimCacheParser import read_mir, write_it
import appDB
from test.auxTest import build_fake_DB, add_entry

# Setup the logger
logger = logging.getLogger()


def create_ShimCacheTxtFileTstomp(fileFullPath):
    try:
        with file(fileFullPath, 'rb') as xml_data:
            entries = read_mir(xml_data, True)
            if not entries:
                print "ShimCacheParser found no entries for %s" % fileFullPath
                settings.logger.error("[ShimCacheParser] found no entries for %s" % fileFullPath)
                return
            else:
                entries[10][0] = "2999-01-01 00:00:01"
                entries[10][2] = 'C:\\Windows\\system32\\svchost.exe'
                entries[11][0] = "2999-01-01 00:00:01"
                entries[11][2] = 'C:\\Web\\badguy.exe'
                write_it(entries, fileFullPath + "-shimcache.txt")
                fileFullPath += "-shimcache.txt"
    except IOError, err:
        print "[ShimCacheParser] Error opening binary file: %s" % str(err)
        settings.logger.error("[ShimCacheParser] Error opening binary file: %s" % str(err))


class TestAppTstomp(TestCase):
    # Build test dataset
    fake_bd_num_records = 3
    testset1 = build_fake_DB(fake_bd_num_records)

    def __del__(self):
        # Remove temp dbs
        os.remove(self.testset1)

    def BuildTestPath(self, folder):
        master_test_folder = os.path.join(os.path.abspath(os.path.join(os.path.join(os.path.dirname(__file__), os.pardir), os.pardir)), "appcompatprocessor-DataSets")
        load_test_path = os.path.join(master_test_folder, folder)
        return load_test_path

    def test_Tstomp1(self):
        # Note: Test has to account for previous test that incorporate tstomp-matching elements to the test DB
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Windows\System32', FileName='kernel32.dll', ExecFlag='True',
                                                  LastModified = '2000-01-01 00:00:01')
            add_entry(DB, "TestHost01", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                              FilePath='C:\Windows', FileName='badboy.exe', ExecFlag='True',
                                              LastModified='2000-01-01 00:00:01')
            add_entry(DB, "TestHost01", entry_fields)

            try:
                ret = main([self.testset1, "tstomp"])
            except Exception as e:
                print traceback.format_exc()
                self.fail(e.message + "\n" + traceback.format_exc())

            num_hits = len(ret)
            self.assertEquals(num_hits, 4, "test_Tstomp1 failed!")
            self.assertEquals(ret[2][1][5], 'kernel32.dll', "test_Tstomp1 failed!")
            self.assertEquals(ret[3][1][5], 'badboy.exe', "test_Tstomp1 failed!")
            self.assertEquals(ret[2][1][2], ret[3][1][2], "test_Tstomp1 failed!")


    def test_Tstomp2(self):
        # Note: Test has to account for previous test that incorporate tstomp-matching elements to the test DB
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            # Add AmCache entry with Modified2 entry with 0 microseconds in it's timestamp
            entry_fields = settings.EntriesFields(EntryType=settings.__AMCACHE__,
                                                  FilePath='C:\Windows\System32', FileName='badboy1.exe', ExecFlag='True',
                                                  Modified2='2000-01-01 00:00:01')
            add_entry(DB, "TestHost01", entry_fields)

            try:
                ret = main([self.testset1, "tstomp"])
            except Exception as e:
                print traceback.format_exc()
                self.fail(e.message + "\n" + traceback.format_exc())

            num_hits = len(ret)
            self.assertEquals(num_hits, 6, sys._getframe().f_code.co_name)
            self.assertEquals(ret[5][1][5], 'badboy1.exe', "test_Tstomp2 failed!")
