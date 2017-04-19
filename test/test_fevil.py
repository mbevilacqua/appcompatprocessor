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
import tempfile


# Setup the logger
logger = logging.getLogger()
DB = None


def create_ShimCacheTxtFile(fileFullPath):
    try:
        with file(fileFullPath, 'rb') as xml_data:
            entries = read_mir(xml_data, True)
            if not entries:
                print "ShimCacheParser found no entries for %s" % fileFullPath
                settings.logger.error("[ShimCacheParser] found no entries for %s" % fileFullPath)
                return
            else:
                write_it(entries, fileFullPath + "-shimcache.txt")
                fileFullPath += "-shimcache.txt"
    except IOError, err:
        print "[ShimCacheParser] Error opening binary file: %s" % str(err)
        settings.logger.error("[ShimCacheParser] Error opening binary file: %s" % str(err))


class TestAppFevil(TestCase):

    def BuildTestPath(self, folder):
        master_test_folder = os.path.join(os.path.abspath(os.path.join(os.path.join(os.path.dirname(__file__), os.pardir), os.pardir)), "appcompatprocessor-DataSets")
        load_test_path = os.path.join(master_test_folder, folder)
        return load_test_path

    def test_Fevil1(self):
        # Very simple test, just make sure we don't crash and get something back
        # todo: Create a real unit test
        load_test_path = self.BuildTestPath("TestData-AmCache")

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir='/tmp')
        tempdb.close()

        try:
            (db_filenameFullPath1, db_version1, num_hosts1, num_instances1, num_entries2) = main([tempdb.name, "load", load_test_path])
            directCorrelationData1 = main([tempdb.name, "fevil"])
        except Exception as e:
            print traceback.format_exc()
            self.fail(e.message + "\n" + traceback.format_exc())

        # Remove temp db
        os.remove(tempdb.name)

        # Check missing reconscan data
        self.assertEquals(directCorrelationData1, None, "TestAppFevil1 - failed!")


    def test_Fevil2(self):
        # Very simple test, just make sure we don't crash and get something back
        # todo: Create a real unit test
        load_test_path = self.BuildTestPath("TestData-AmCache")

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir='/tmp')
        tempdb.close()

        (db_filenameFullPath1, db_version1, num_hosts1, num_instances1, num_entries2) = main(
            [tempdb.name, "load", load_test_path])
        try:
            directCorrelationData1 = main([tempdb.name, "reconscan"])
            directCorrelationData1 = main([tempdb.name, "fevil"])
        except Exception as e:
            print traceback.format_exc()
            self.fail(e.message + "\n" + traceback.format_exc())

        # Remove temp db
        os.remove(tempdb.name)

        # Check missing tcorr data
        self.assertEquals(0, 0, "TestAppFevil2 - failed!")
