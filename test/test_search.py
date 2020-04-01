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
import re, codecs
import appDB
import random
import string
from test.auxTest import build_fake_DB, add_entry

# Setup the logger
logger = logging.getLogger()


class TestAppSearchMP(TestCase):
    testset1 = ''

    @classmethod
    def setup_class(self):
        # Build test dataset
        self.testset1 = build_fake_DB(3)

    @classmethod
    def teardown_class(self):
        # Remove temp dbs
        os.remove(self.testset1)

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
                    count +=1

        return count


    def compare_output_files(self, filename1, filename2):
        with codecs.open(filename1, 'r', 'UTF8') as inputFile1:
            with codecs.open(filename2, 'r', 'UTF8') as inputFile2:
                content1 = sorted(inputFile1.readlines())
                content2 = sorted(inputFile2.readlines())
                if len(content1) != len(content2): return False
                for i in xrange(0,len(content1)):
                    if content1[i] != content2[i]:
                        return False
        return True


    def dumpCSV(self, dbfilenameFullPath, dumpfilenameFullPath):
        DB = appDB.DBClass(dbfilenameFullPath, True, settings.__version__)
        DB.appInitDB()
        conn = DB.appConnectDB()
        rows = DB.Query("SELECT * FROM Csv_Dump")
        with open(dumpfilenameFullPath, "w") as file_handle:
            for row in rows:
                line = [str(field) for field in row]
                file_handle.write("%s\n" % ','.join(line))
            file_handle.flush()


    def test_AppCompat_LiteralSearchNoHits(self):
        rndFileName = ''.join(random.choice(string.ascii_uppercase) for _ in range(20))
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

        # Get temp file name for the DB
        with tempfile.NamedTemporaryFile(suffix='.txt', prefix='test_AppCompat_LiteralSearch', dir=tempfile.gettempdir()) as temp_file:
            # Search
            (num_hits, num_hits_suppressed, results) = main(["-o", temp_file.name, self.testset1, "search", "-F", rndFileName])
            # Check we got at least as many as we added into the DB
            self.assertTrue(num_hits == 0, sys._getframe().f_code.co_name + " num_hits: %d" % num_hits)
            # Check output has the expected result
            self.assertEquals(num_hits - num_hits_suppressed, self.count_lines_regex(temp_file.name, rndFileName),
                              sys._getframe().f_code.co_name + " Output regex count doesn't match num_hits!")


    def test_AppCompat_LiteralSearch(self):
        rndFileName = ''.join(random.choice(string.ascii_uppercase) for _ in range(20))
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            for i in xrange(0,20):
                entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                      FilePath='C:\Temp', FileName=rndFileName, Size=i, ExecFlag='True')
                add_entry(DB, "TestHost01", entry_fields)

        # Get temp file name for the DB
        with tempfile.NamedTemporaryFile(suffix='.txt', prefix='test_AppCompat_LiteralSearch', dir=tempfile.gettempdir()) as temp_file:
            # Search
            (num_hits, num_hits_suppressed, results) = main(["-o", temp_file.name, self.testset1, "search", "-F", rndFileName])
            # Check we got at least as many as we added into the DB
            self.assertTrue(num_hits == 20, sys._getframe().f_code.co_name + " num_hits: %d" % num_hits)
            # Check output has the expected result
            self.assertEquals(num_hits - num_hits_suppressed, self.count_lines_regex(temp_file.name, rndFileName),
                              sys._getframe().f_code.co_name + " Output regex count doesn't match num_hits!")

    def test_AppCompat_LiteralSearch_Suppressed(self):
        rndFileName = ''.join(random.choice(string.ascii_uppercase) for _ in range(15))
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            # Add 10 entries
            for i in xrange(0, 10):
                entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                      FilePath='C:\Temp', FileName=rndFileName, Size=i, ExecFlag='True')
                add_entry(DB, "TestHost01", entry_fields)

            # Add 10 entries which will be deduped to 1 on search
            for i in xrange(0, 10):
                entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                  FilePath='C:\Temp', FileName=rndFileName, Size=1000,
                                  ExecFlag='True')
                add_entry(DB, "TestHost01", entry_fields)

        # Get temp file name for the DB
        with tempfile.NamedTemporaryFile(suffix='.txt', prefix='Output', dir=tempfile.gettempdir()) as temp_file:
            # Search
            (num_hits, num_hits_suppressed, results) = main(["-o", temp_file.name, self.testset1, "search", "-F", rndFileName])
            # Check we got as many hits as we expect
            self.assertTrue(num_hits == 10 + 10, sys._getframe().f_code.co_name + " num_hits: %d - %s" % (num_hits, self.testset1))
            # Check supression worked as expected
            self.assertTrue(num_hits_suppressed == 9, sys._getframe().f_code.co_name + " num_hits: %d" % num_hits)
            # Check output has the expected result
            self.assertEquals(num_hits - num_hits_suppressed, self.count_lines_regex(temp_file.name, rndFileName),
                              sys._getframe().f_code.co_name + " Output regex count doesn't match num_hits!")


    def test_AmCache_LiteralSearch(self):
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            for i in xrange(0, 10):
                entry_fields = settings.EntriesFields(EntryType=settings.__AMCACHE__,
                                                      FilePath='C:\Temp', FileName='calc.exe', Size=i, ExecFlag='True')
                add_entry(DB, "TestHost01", entry_fields)

        # Get temp file name for the DB
        with tempfile.NamedTemporaryFile(suffix='.txt', prefix='Output', dir=tempfile.gettempdir()) as temp_file:
            # Search
            (num_hits, num_hits_suppressed, results) = main(["-o", temp_file.name, self.testset1, "search", "-F", "calc.exe"])
            # Check we got at least as many as we added into the DB
            self.assertTrue(num_hits >= 10, sys._getframe().f_code.co_name + " num_hits: %d" % num_hits)
            # Check output has the expected result
            self.assertEquals(num_hits, self.count_lines_regex(temp_file.name, "calc\.exe"),
                              sys._getframe().f_code.co_name + " Output regex count doesn't match num_hits!")


    def test_AmCache_LiteralSearch_Suppressed(self):
        rndFileName = ''.join(random.choice(string.ascii_uppercase) for _ in range(15))
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            # Add 10 entries
            for i in xrange(0, 10):
                entry_fields = settings.EntriesFields(EntryType=settings.__AMCACHE__,
                                                      FilePath='C:\Temp', FileName=rndFileName, Size=i, ExecFlag='True')
                add_entry(DB, "TestHost01", entry_fields)

            # Add 10 entries which will be deduped to 1 on search
            for i in xrange(0, 10):
                entry_fields = settings.EntriesFields(EntryType=settings.__AMCACHE__,
                                                      FilePath='C:\Temp', FileName=rndFileName, Size=1000,
                                                      ExecFlag='True')
                add_entry(DB, "TestHost01", entry_fields)

        # Get temp file name for the DB
        with tempfile.NamedTemporaryFile(suffix='.txt', prefix='Output', dir=tempfile.gettempdir()) as temp_file:
            # Search
            (num_hits, num_hits_suppressed, results) = main(["-o", temp_file.name, self.testset1, "search", "-F", rndFileName])
            # Check we got as many hits as we expect
            self.assertTrue(num_hits == 10 + 10, sys._getframe().f_code.co_name + " num_hits: %d" % num_hits)
            # Check supression worked as expected
            self.assertTrue(num_hits_suppressed == 9, sys._getframe().f_code.co_name + " num_hits: %d" % num_hits)
            # Check output has the expected result
            self.assertEquals(num_hits - num_hits_suppressed, self.count_lines_regex(temp_file.name, rndFileName),
                              sys._getframe().f_code.co_name + " Output regex count doesn't match num_hits!")


    def test_AppCompat_IndexedSearchNoHits(self):
        rndFileName = ''.join(random.choice(string.ascii_uppercase) for _ in range(20))
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

        # Get temp file name for the DB
        with tempfile.NamedTemporaryFile(suffix='.txt', prefix='test_AppCompat_IndexedSearch', dir=tempfile.gettempdir()) as temp_file:
            # Search
            (num_hits, num_hits_suppressed, results) = main(["-o", temp_file.name, self.testset1, "fsearch", "FileName", "-F", rndFileName])
            # Check we got at least as many as we added into the DB
            self.assertTrue(num_hits == 0, sys._getframe().f_code.co_name + " num_hits: %d" % num_hits)
            # Check output has the expected result
            self.assertEquals(num_hits - num_hits_suppressed, self.count_lines_regex(temp_file.name, rndFileName),
                              sys._getframe().f_code.co_name + " Output regex count doesn't match num_hits!")



    def test_AppCompat_IndexedSearch(self):
        rndFileName = ''.join(random.choice(string.ascii_uppercase) for _ in range(20))
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            for i in xrange(0,20):
                entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                      FilePath='C:\Temp', FileName=rndFileName, Size=i, ExecFlag='True')
                add_entry(DB, "TestHost01", entry_fields)

        # Get temp file name for the DB
        with tempfile.NamedTemporaryFile(suffix='.txt', prefix='test_AppCompat_IndexedSearch', dir=tempfile.gettempdir()) as temp_file:
            # Search
            (num_hits, num_hits_suppressed, results) = main(["-o", temp_file.name, self.testset1, "fsearch", "FileName", "-F", rndFileName])
            # Check we got at least as many as we added into the DB
            self.assertTrue(num_hits == 20, sys._getframe().f_code.co_name + " num_hits: %d" % num_hits)
            # Check output has the expected result
            self.assertEquals(num_hits - num_hits_suppressed, self.count_lines_regex(temp_file.name, rndFileName),
                              sys._getframe().f_code.co_name + " Output regex count doesn't match num_hits!")


    def test_AppCompat_IndexedSearchFilePath(self):
        rndFileName = ''.join(random.choice(string.ascii_uppercase) for _ in range(20))
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            for i in xrange(0,20):
                entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                      FilePath='C:\\'+rndFileName, FileName="calc.exe", Size=i, ExecFlag='True')
                add_entry(DB, "TestHost01", entry_fields)

        # Get temp file name for the DB
        with tempfile.NamedTemporaryFile(suffix='.txt', prefix='test_AppCompat_IndexedSearch', dir=tempfile.gettempdir()) as temp_file:
            # Search
            (num_hits, num_hits_suppressed, results) = main(["-o", temp_file.name, self.testset1, "fsearch", "FilePath", "-F", "C:\\"+rndFileName])
            # Check we got at least as many as we added into the DB
            self.assertTrue(num_hits == 20, sys._getframe().f_code.co_name + " num_hits: %d" % num_hits)
            # Check output has the expected result
            self.assertEquals(num_hits - num_hits_suppressed, self.count_lines_regex(temp_file.name, rndFileName),
                              sys._getframe().f_code.co_name + " Output regex count doesn't match num_hits!")



    def test_AppCompat_IndexedSearch2(self):
        rndFileName = ''.join(random.choice(string.ascii_uppercase) for _ in range(20))
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            for i in xrange(0,20):
                entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                      FilePath='C:\Temp', FileName=rndFileName, Size=i, ExecFlag='True')
                add_entry(DB, "TestHost01", entry_fields)

        # Get temp file name for the DB
        with tempfile.NamedTemporaryFile(suffix='.txt', prefix='test_AppCompat_IndexedSearch', dir=tempfile.gettempdir()) as temp_file_indexed:
            with tempfile.NamedTemporaryFile(suffix='.txt', prefix='test_AppCompat_NormalSearch', dir=tempfile.gettempdir()) as temp_file_normal:
                # Indexed Search
                (num_hits, num_hits_suppressed, results) = main(["-o", temp_file_indexed.name, self.testset1, "fsearch", "FileName", "-F", rndFileName])
                # Standard Search
                (num_hits2, num_hits_suppressed2, results2) = main(["-o", temp_file_normal.name, self.testset1, "search", "-F", "\\" + rndFileName])
                # Check we got the same number of hits
                self.assertTrue(num_hits == num_hits2, sys._getframe().f_code.co_name + " num_hits: %d" % num_hits)
                # Check output has the expected results
                self.assertEquals(num_hits - num_hits_suppressed, self.count_lines_regex(temp_file_indexed.name, rndFileName),
                                  sys._getframe().f_code.co_name + " Output regex count doesn't match num_hits!")
                # Check output has the expected results
                self.assertEquals(num_hits2 - num_hits_suppressed2, self.count_lines_regex(temp_file_normal.name, rndFileName),
                                  sys._getframe().f_code.co_name + " Output regex count doesn't match num_hits!")
                # Check standard and indexed search produced the same results
                self.assertTrue(self.compare_output_files(temp_file_normal.name, temp_file_indexed.name), "Results differ!")
