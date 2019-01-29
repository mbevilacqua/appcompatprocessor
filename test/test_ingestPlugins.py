from __future__ import absolute_import
import logging
from unittest import TestCase
import os
import traceback
from AppCompatProcessor import main
import tempfile
from shutil import copyfile

# Setup the logger
logger = logging.getLogger()
DB = None


class TestAppLoadMP(TestCase):

    def BuildTestPath(self, folder):
        master_test_folder = os.path.join(os.path.abspath(os.path.join(os.path.join(os.path.dirname(__file__), os.pardir), os.pardir)), "appcompatprocessor-DataSets")
        load_test_path = os.path.join(master_test_folder, folder)

        return load_test_path


    def test_ingestTestSets1(self):
        test_sets = [("StructuredRepo/HX_Grabstuffr/ICE_Exec-Defaults/AmCache-Default", 2, 2, 366),
                     ("StructuredRepo/HX_Grabstuffr/ICE_Exec-Defaults/AppCompat-Default", 3, 3, 632),
                     ("StructuredRepo/HX_Grabstuffr/ICE_Exec-Defaults/ShimShady64b-Default", 3, 3, 479),
                     ("StructuredRepo/HX_Grabstuffr/ICE_Exec-Defaults", 3, 6, 1113)]

        for test in test_sets:
            load_test_path = self.BuildTestPath(test[0])
            # Get temp db name for the test
            tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase_ingestTestSets', dir=tempfile.gettempdir())
            tempdb.close()

            try:
                (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries) = main([tempdb.name, "load", load_test_path])
            except Exception as e:
                print traceback.format_exc()
                self.fail(traceback.format_exc())

            # Remove temp db
            os.remove(tempdb.name)

            if num_hosts <> test[1] or num_instances <> test[2] or num_entries <> test[3]:
                print("Test %s failed!" % test[0])
                self.fail("Test %s failed!" % test[0])

            self.assertEquals(num_hosts, test[1], "test failed!")
            self.assertEquals(num_instances, test[2], "test failed!")
            self.assertEquals(num_entries, test[3], "test failed!")


    def test_ingestTestSets2(self):
        test_sets = [("StructuredRepo/HX_Grabstuffr/ICE_32and64bShimShadyDefaults", 2, 2, 308),
                     ("StructuredRepo/HX_Grabstuffr/HXRegistryAPIAudit_AMCacheAquisition", 3, 4, 626),
                     ("StructuredRepo/HX_Grabstuffr/ICE_ACPBundle-Tunned", 3, 7, 1105),
                     ("StructuredRepo/HX_Grabstuffr/ICE_Stacking-Defaults", 3, 3, 368)]

        for test in test_sets:
            load_test_path = self.BuildTestPath(test[0])
            # Get temp db name for the test
            tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase_ingestTestSets', dir=tempfile.gettempdir())
            tempdb.close()

            try:
                (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries) = main([tempdb.name, "load", load_test_path])
            except Exception as e:
                print traceback.format_exc()
                self.fail(traceback.format_exc())

            # Remove temp db
            os.remove(tempdb.name)

            if num_hosts <> test[1] or num_instances <> test[2] or num_entries <> test[3]:
                print("Test %s failed!" % test[0])
                self.fail("Test %s failed!" % test[0])

            self.assertEquals(num_hosts, test[1], "test failed!")
            self.assertEquals(num_instances, test[2], "test failed!")
            self.assertEquals(num_entries, test[3], "test failed!")

    def test_ingestTestSets1HXTool(self):
        test_sets = [("StructuredRepo/HXToolsDownload/ICE_Exec-Defaults/AmCache-Default", 1, 1, 223),
                     ("StructuredRepo/HXToolsDownload/ICE_Exec-Defaults/AppCompat-Default", 2, 2, 411),
                     ("StructuredRepo/HXToolsDownload/ICE_Exec-Defaults/ShimShady64b-Default", 3, 3, 479),
                     ("StructuredRepo/HXToolsDownload/ICE_Exec-Defaults", 3, 6, 1113)]

        for test in test_sets:
            load_test_path = self.BuildTestPath(test[0])
            # Get temp db name for the test
            tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase_ingestTestSets', dir=tempfile.gettempdir())
            tempdb.close()

            try:
                (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries) = main([tempdb.name, "load", load_test_path])
            except Exception as e:
                print traceback.format_exc()
                self.fail(traceback.format_exc())

            # Remove temp db
            os.remove(tempdb.name)

            if num_hosts <> test[1] or num_instances <> test[2] or num_entries <> test[3]:
                print("Test %s failed!" % test[0])
                self.fail("Test %s failed!" % test[0])

            self.assertEquals(num_hosts, test[1], "test failed!")
            self.assertEquals(num_instances, test[2], "test failed!")
            self.assertEquals(num_entries, test[3], "test failed!")


    def test_ingestTestSets2HXTool(self):
        test_sets = [("StructuredRepo/HXToolsDownload/ICE_32and64bShimShadyDefaults", 2, 2, 308),
                     ("StructuredRepo/HXToolsDownload/HXRegistryAPIAudit_AMCacheAquisition", 2, 3, 405),
                     ("StructuredRepo/HXToolsDownload/ICE_ACPBundle-Tunned", 2, 5, 741),
                     ("StructuredRepo/HXToolsDownload/ICE_Stacking-Defaults", 2, 2, 147)]

        for test in test_sets:
            load_test_path = self.BuildTestPath(test[0])
            # Get temp db name for the test
            tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase_ingestTestSets', dir=tempfile.gettempdir())
            tempdb.close()

            try:
                (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries) = main([tempdb.name, "load", load_test_path])
            except Exception as e:
                print traceback.format_exc()
                self.fail(traceback.format_exc())

            # Remove temp db
            os.remove(tempdb.name)

            if num_hosts <> test[1] or num_instances <> test[2] or num_entries <> test[3]:
                print("Test %s failed!" % test[0])
                self.fail("Test %s failed!" % test[0])

            self.assertEquals(num_hosts, test[1], "test failed!")
            self.assertEquals(num_instances, test[2], "test failed!")
            self.assertEquals(num_entries, test[3], "test failed!")

