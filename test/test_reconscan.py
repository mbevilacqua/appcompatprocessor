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

# Setup the logger
logger = logging.getLogger()
DB = None


class TestAppReconscan(TestCase):

    def BuildTestPath(self, folder):
        master_test_folder = os.path.join(os.path.abspath(os.path.join(os.path.join(os.path.dirname(__file__), os.pardir), os.pardir)), "appcompatprocessor-DataSets")
        load_test_path = os.path.join(master_test_folder, folder)
        return load_test_path

    def test_ReconscanAppCompat(self):
        load_test_path = self.BuildTestPath("miniXML")
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries) = main([tempdb.name, "load", load_test_path])

        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        num_hits = main([tempdb.name, "reconscan"])

        # Remove temp db
        os.remove(tempdb.name)

        self.assertEquals(num_hits, 10, "test_LiteralSearch failed!")

    def test_ReconscanAmCache(self):
        load_test_path = self.BuildTestPath("TestData-AmCache")
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries) = main([tempdb.name, "load", load_test_path])

        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        num_hits = main([tempdb.name, "reconscan"])

        # Remove temp db
        os.remove(tempdb.name)

        self.assertEquals(num_hits, 6, "test_LiteralSearch failed!")
