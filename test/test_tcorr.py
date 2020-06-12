from __future__ import absolute_import
import logging
from unittest import TestCase
import settings
import sys, traceback
reload(sys)
sys.setdefaultencoding("utf-8")
import os
from AppCompatProcessor import main
from shutil import copyfile
from ShimCacheParser_ACP import read_mir, write_it
import tempfile
import appDB
import re, codecs
from test.auxTest import build_fake_DB, add_entry

# Setup the logger
logger = logging.getLogger()
DB = None


def create_ShimCacheTxtFile(fileFullPath):
    try:
        with file(fileFullPath, 'rb') as xml_data:
            (error, entries) = read_mir(xml_data, True)
            if not entries:
                if error == "":
                    print "[ShimCacheParser] found no entries for %s" % fileFullPath
                    settings.logger.error("[ShimCacheParser] found no entries for %s" % fileFullPath)
                else:
                    print "[ShimCacheParser] Error on file %s - [error]" % (fileFullPath, error)
                    settings.logger.error("[ShimCacheParser] Error on file %s - [error]" % (fileFullPath, error))
                return False
            else:
                write_it(entries, fileFullPath + "-shimcache.txt")
                fileFullPath += "-shimcache.txt"
    except IOError, err:
        print "[ShimCacheParser] Error opening binary file: %s" % str(err)
        settings.logger.error("[ShimCacheParser] Error opening binary file: %s" % str(err))


class TestAppTcorr(TestCase):
    testset1 = ''

    @classmethod
    def setup_class(self):
        # Build test dataset
        self.testset1 = build_fake_DB(1)

    @classmethod
    def teardown_class(self):
        # Remove temp dbs
        os.remove(self.testset1)

    def BuildTestPath(self, folder):
        master_test_folder = os.path.join(
            os.path.abspath(os.path.join(os.path.join(os.path.dirname(__file__), os.pardir), os.pardir)),
            "appcompatprocessor-DataSets")
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

    def test_TcorrTest_prog1(self):
        with appDB.DBClass(self.testset1, settings.__version__) as DB:
            DB.appInitDB()
            conn = DB.appConnectDB()

            # TestHost01
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='AAA.exe', Size=1,ExecFlag='True')
            add_entry(DB, "TestHost01", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='BBB.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost01", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='CCC.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost01", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='DDD.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost01", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='EEE.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost01", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='FFF.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost01", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='GGG.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost01", entry_fields)


            # TestHost02
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='AAA.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost02", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='BBB.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost02", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='CCC.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost02", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='DDD.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost02", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='EEE.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost02", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='FFF.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost02", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='GGG.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost02", entry_fields)

            try:
                directCorrelationData = main([self.testset1, "tcorr", "DDD.exe", "-w 1"])
            except Exception as e:
                print traceback.format_exc()
                self.fail(e.message + "\n" + traceback.format_exc())

            # Check Names
            self.assertEquals(directCorrelationData[1][3], "CCC.exe", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[0][3], "EEE.exe", "test_TcorrTest_prog1 - Name failed!")
            # Check Before
            self.assertEquals(directCorrelationData[1][6], 0, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[0][6], 2, "test_TcorrTest_prog1 - Name failed!")
            # Check After
            self.assertEquals(directCorrelationData[1][7], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[0][7], 0, "test_TcorrTest_prog1 - Name failed!")
            # Check InvBond
            self.assertEquals(directCorrelationData[1][9], "True", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[0][9], "True", "test_TcorrTest_prog1 - Name failed!")
            # Check Total_Count
            self.assertEquals(directCorrelationData[1][10], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[0][10], 2, "test_TcorrTest_prog1 - Name failed!")

            try:
                directCorrelationData = main([self.testset1, "tcorr", "DDD.exe", "-w 2"])
            except Exception as e:
                print traceback.format_exc()
                self.fail(e.message + "\n" + traceback.format_exc())

            # Check Names
            self.assertEquals(directCorrelationData[0][3], "CCC.exe", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][3], "EEE.exe", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[2][3], "BBB.exe", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[3][3], "FFF.exe", "test_TcorrTest_prog1 - Name failed!")
            # Check Before
            self.assertEquals(directCorrelationData[0][6], 0, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][6], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[2][6], 0, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[3][6], 2, "test_TcorrTest_prog1 - Name failed!")
            # Check After
            self.assertEquals(directCorrelationData[0][7], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][7], 0, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[2][7], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[3][7], 0, "test_TcorrTest_prog1 - Name failed!")
            # Check InvBond
            self.assertEquals(directCorrelationData[0][9], "True", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][9], "True", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[2][9], "True", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[3][9], "True", "test_TcorrTest_prog1 - Name failed!")
            # Check Total_Count
            self.assertEquals(directCorrelationData[0][10], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][10], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[2][10], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[3][10], 2, "test_TcorrTest_prog1 - Name failed!")
            # Check Weight
            self.assertTrue(directCorrelationData[0][8] > directCorrelationData[2][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[0][8] > directCorrelationData[3][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[1][8] > directCorrelationData[2][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[1][8] > directCorrelationData[3][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[0][8] == directCorrelationData[1][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[2][8] == directCorrelationData[3][8], "test_TcorrTest_prog1 - Name failed!")

            try:
                directCorrelationData = main([self.testset1, "tcorr", "DDD.exe", "-w 3"])
            except Exception as e:
                print traceback.format_exc()
                self.fail(e.message + "\n" + traceback.format_exc())

            # Check Names
            self.assertEquals(directCorrelationData[0][3], "CCC.exe", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][3], "EEE.exe", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[2][3], "BBB.exe", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[3][3], "FFF.exe", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[4][3], "AAA.exe", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[5][3], "GGG.exe", "test_TcorrTest_prog1 - Name failed!")
            # Check Before
            self.assertEquals(directCorrelationData[0][6], 0, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][6], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[2][6], 0, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[3][6], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[4][6], 0, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[5][6], 2, "test_TcorrTest_prog1 - Name failed!")
            # Check After
            self.assertEquals(directCorrelationData[0][7], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][7], 0, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[2][7], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[3][7], 0, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[4][7], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[5][7], 0, "test_TcorrTest_prog1 - Name failed!")
            # Check InvBond
            self.assertEquals(directCorrelationData[0][9], "True", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][9], "True", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[2][9], "True", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[3][9], "True", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[4][9], "True", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[5][9], "True", "test_TcorrTest_prog1 - Name failed!")
            # Check Total_Count
            self.assertEquals(directCorrelationData[0][10], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][10], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[2][10], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[3][10], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[4][10], 2, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[5][10], 2, "test_TcorrTest_prog1 - Name failed!")
            # Check Weight
            self.assertTrue(directCorrelationData[0][8] > directCorrelationData[2][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[0][8] > directCorrelationData[3][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[0][8] > directCorrelationData[4][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[0][8] > directCorrelationData[5][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[1][8] > directCorrelationData[2][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[1][8] > directCorrelationData[3][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[1][8] > directCorrelationData[4][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[1][8] > directCorrelationData[5][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[0][8] == directCorrelationData[1][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[2][8] == directCorrelationData[3][8], "test_TcorrTest_prog1 - Name failed!")
            self.assertTrue(directCorrelationData[4][8] == directCorrelationData[5][8], "test_TcorrTest_prog1 - Name failed!")

            # TestHost03
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='AAA.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost03", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='BBB.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost03", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='CCC.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost03", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='DDD.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost03", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='EEE.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost03", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='FFF.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost03", entry_fields)
            entry_fields = settings.EntriesFields(EntryType=settings.__APPCOMPAT__,
                                                  FilePath='C:\Temp', FileName='GGG.exe', Size=1, ExecFlag='True')
            add_entry(DB, "TestHost03", entry_fields)

            try:
                directCorrelationData = main([self.testset1, "tcorr", "DDD.exe", "-w 1"])
            except Exception as e:
                print traceback.format_exc()
                self.fail(e.message + "\n" + traceback.format_exc())

            # Check Names
            self.assertEquals(directCorrelationData[0][3], "CCC.exe", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][3], "EEE.exe", "test_TcorrTest_prog1 - Name failed!")
            # Check Before
            self.assertEquals(directCorrelationData[0][6], 0, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][6], 3, "test_TcorrTest_prog1 - Name failed!")
            # Check After
            self.assertEquals(directCorrelationData[0][7], 3, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][7], 0, "test_TcorrTest_prog1 - Name failed!")
            # Check InvBond
            self.assertEquals(directCorrelationData[0][9], "True", "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][9], "True", "test_TcorrTest_prog1 - Name failed!")
            # Check Total_Count
            self.assertEquals(directCorrelationData[0][10], 3, "test_TcorrTest_prog1 - Name failed!")
            self.assertEquals(directCorrelationData[1][10], 3, "test_TcorrTest_prog1 - Name failed!")


    def _test_TcorrMixed(self):
        # Verify that AmCache data doesn't get mixed in with AppCompat in the tcorr module
        # Note that we currently print results separately but return a unique structure with aggregates both datasets
        load_test_path = self.BuildTestPath("TestData-mini")
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries) = main([tempdb.name, "load", load_test_path])
        directCorrelationData1 = main([tempdb.name, "tcorr", "net.exe", "-w 3"])
        # Check Name
        self.assertEquals(directCorrelationData1[0][3], "net1.exe", "test_TcorrTest1 - Name failed!")
        # Check Before
        self.assertEquals(directCorrelationData1[0][6], 0, "test_TcorrTest1 - Before failed!")
        # Check After
        self.assertEquals(directCorrelationData1[0][7], 158, "test_TcorrTest1 - After failed!")

        load_test_path = self.BuildTestPath("TestData-AmCache")
        (db_filenameFullPath2, db_version2, num_hosts2, num_instances2, num_entries2) = main([tempdb.name, "load", load_test_path])
        directCorrelationData2 = main([tempdb.name, "tcorr", "net.exe", "-w 3"])
        # Remove temp db
        os.remove(tempdb.name)
        # Check Name
        self.assertEquals(directCorrelationData2[0][3], "net1.exe", "test_TcorrTest1 - Name failed!")
        # Check Before
        self.assertEquals(directCorrelationData2[0][6], 0 + 0, "test_TcorrTest1 - Before failed!")
        # Check After
        self.assertEquals(directCorrelationData2[0][7], 158 + 21, "test_TcorrTest1 - After failed!")

    def _test_TcorrAmCache(self):
        load_test_path = self.BuildTestPath("TestData-AmCache")
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath1, db_version1, num_hosts1, num_instances1, num_entries2) = main([tempdb.name, "load", load_test_path])
        directCorrelationData1 = main([tempdb.name, "tcorr", "net.exe", "-w 3"])
        # Remove temp db
        os.remove(tempdb.name)
        # Check Name
        self.assertEquals(directCorrelationData1[0][3], "net1.exe", "test_TcorrTest1 - Name failed!")
        # Check Before
        self.assertEquals(directCorrelationData1[0][6], 0, "test_TcorrTest1 - Before failed!")
        # Check After
        self.assertEquals(directCorrelationData1[0][7], 21, "test_TcorrTest1 - After failed!")
