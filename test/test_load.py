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
from shutil import copyfile

# Setup the logger
logger = logging.getLogger()
DB = None


class TestAppLoadMP(TestCase):

    def BuildTestPath(self, folder):
        master_test_folder = os.path.join(os.path.abspath(os.path.join(os.path.join(os.path.dirname(__file__), os.pardir), os.pardir)), "appcompatprocessor-DataSets")
        load_test_path = os.path.join(master_test_folder, folder)
        return load_test_path

    def test_SimpleLoadAppCompat(self):
        load_test_path = self.BuildTestPath("miniXML")

        # Remove all fake hosts
        filelist = [f for f in os.listdir(load_test_path) if f.startswith("new_test_")]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()

        try:
            (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries) = main([tempdb.name, "load", load_test_path])
        except Exception as e:
            print traceback.format_exc()
            self.fail(e.message + "\n" + traceback.format_exc())

        # Remove temp db
        os.remove(tempdb.name)

        self.assertEquals(num_hosts, 22, "test_SimpleLoad failed!")
        self.assertEquals(num_instances, 22, "test_SimpleLoad failed!")
        self.assertEquals(num_entries, 11561, "test_SimpleLoad failed!")

    def test_ShimcacheLeftOvers(self):
        # todo: Think this use case makes no sense anymore as we no longer dump to temp -shimcache.txt files:
        load_test_path = self.BuildTestPath("miniXML")
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries) = main([tempdb.name, "load", load_test_path])

        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Remove temp db
        os.remove(tempdb.name)

        (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries) = main([tempdb.name, "load", load_test_path])

        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        self.assertEquals(num_hosts, 22, "test_SimpleLoad failed!")
        self.assertEquals(num_entries, 11561, "test_SimpleLoad failed!")


    def test_SimpleLoadAmCache(self):
        load_test_path = self.BuildTestPath("TestData-AmCache")
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath1, db_version1, num_hosts1, num_instances1, num_entries1) = main(
            [tempdb.name, "load", load_test_path])
        # Remove temp db
        os.remove(tempdb.name)

        self.assertEquals(num_hosts1, 6, "test_SimpleLoad failed!")
        self.assertEquals(num_entries1, 31260, "test_SimpleLoad failed!")


    def test_MultipleInstancesLoadAppCompat(self):
        load_test_path = self.BuildTestPath("MultipleInstances-1")
        # Remove all pre-processed -shimcache.txt files:
        filelist = [f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt")]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath1, db_version1, num_hosts1, num_instances1, num_entries1) = main([tempdb.name, "load", load_test_path])
        # Remove temp db
        os.remove(tempdb.name)

        # Remove all pre-processed -shimcache.txt files:
        filelist = [f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt")]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        self.assertEquals(num_hosts1, 1, "test_MultipleInstancesLoadAppCompat failed!")
        self.assertEquals(num_instances1, 1, "test_MultipleInstancesLoadAppCompat failed!")


    def test_MultipleInstancesLoadAppCompat2(self):
        load_test_path = self.BuildTestPath("MultipleInstances-1")

        # Remove all pre-processed -shimcache.txt files:
        filelist = [f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt")]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath1, db_version1, num_hosts1, num_instances1, num_entries1) = main([tempdb.name, "load", load_test_path])

        self.assertEquals(num_hosts1, 1, "test_MultipleInstancesLoadAppCompat2 failed!")
        if num_instances1 == 2:
            print "stop"
        self.assertEquals(num_instances1, 1, "test_MultipleInstancesLoadAppCompat2 failed!")

        # Remove temp db
        os.remove(tempdb.name)

        # Remove all pre-processed -shimcache.txt files:
        filelist = [f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt")]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        load_test_path = self.BuildTestPath("MultipleInstances-2")
        # Get temp db name for the test

        # Remove all pre-processed -shimcache.txt files:
        filelist = [f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt")]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath2, db_version2, num_hosts2, num_instances2, num_entries2) = main([tempdb.name, "load", load_test_path])

        self.assertEquals(num_hosts1, 1, "test_MultipleInstancesLoadAppCompat2 failed!")
        self.assertEquals(num_hosts2, 1, "test_MultipleInstancesLoadAppCompat2 failed!")
        self.assertEquals(num_instances1, 1, "test_MultipleInstancesLoadAppCompat2 failed!")
        self.assertEquals(num_instances2, 2, "test_MultipleInstancesLoadAppCompat2 failed!")
        self.assertEquals(num_entries2, num_entries1 * 2, "test_MultipleInstancesLoadAppCompat2 failed!")

        # Remove all pre-processed -shimcache.txt files:
        filelist = [f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt")]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Remove temp db
        os.remove(tempdb.name)

    def test_MultipleInstancesLoadAppCompat3(self):
        load_test_path = self.BuildTestPath("MultipleInstances-1")
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath1, db_version1, num_hosts1, num_instances1, num_entries1) = main([tempdb.name, "load", load_test_path])
        # Remove temp db
        os.remove(tempdb.name)
        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Create new hosts
        new_filename = ""
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("_w32registry.xml") ]
        for f in filelist:
            new_filename = os.path.join(load_test_path, f.replace("49070f781b14d49c9086144819e45bee9fa215dea18dbe1223881c479314e8be","59070f781b14d49c9086144819e45bee9fa215dea18dbe1223881c479314e8be"))
            copyfile(os.path.join(load_test_path, f), new_filename)

        load_test_path = self.BuildTestPath("MultipleInstances-1")
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath2, db_version2, num_hosts2, num_instances2, num_entries2) = main([tempdb.name, "load", load_test_path])
        # Remove temp db
        os.remove(tempdb.name)
        # Remove new_filename
        os.remove(new_filename)
        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        self.assertEquals(num_hosts1, 1, "test_MultipleInstancesLoadAppCompat3 failed!")
        self.assertEquals(num_hosts2, 1, "test_MultipleInstancesLoadAppCompat3 failed!")
        self.assertEquals(num_instances1, 1, "test_MultipleInstancesLoadAppCompat3 failed!")
        self.assertEquals(num_instances2, 1, "test_MultipleInstancesLoadAppCompat3 failed!")
        self.assertEquals(num_entries1, num_entries2, "test_MultipleInstancesLoadAppCompat3 failed!")

    def test_MultipleInstancesLoadAppCompat4(self):
        load_test_path = self.BuildTestPath("MultipleInstances-1")
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath1, db_version1, num_hosts1, num_instances1, num_entries1) = main([tempdb.name, "load", load_test_path])
        # Remove temp db
        os.remove(tempdb.name)
        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Create new hosts
        new_filename = ""
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("_w32registry.xml") ]
        for f in filelist:
            new_filename = os.path.join(load_test_path, f.replace("49070f781b14d49c9086144819e45bee9fa215dea18dbe1223881c479314e8be","59070f781b14d49c9086144819e45bee9fa215dea18dbe1223881c479314e8be"))
            # Change timestamp
            with open(new_filename, "wt") as fout:
                with open(os.path.join(load_test_path, f), "rt") as fin:
                    for line in fin:
                        fout.write(line.replace('2016-01-19T10:50:30Z', '2020-01-19T10:50:35Z'))

        load_test_path = self.BuildTestPath("MultipleInstances-1")
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath2, db_version2, num_hosts2, num_instances2, num_entries2) = main([tempdb.name, "load", load_test_path])
        # Remove temp db
        os.remove(tempdb.name)
        # Remove new_filename
        os.remove(new_filename)
        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        self.assertEquals(num_hosts1, 1, "test_MultipleInstancesLoadAppCompat4 failed!")
        self.assertEquals(num_hosts2, 1, "test_MultipleInstancesLoadAppCompat4 failed!")
        self.assertEquals(num_instances1, 1, "test_MultipleInstancesLoadAppCompat4 failed!")
        self.assertEquals(num_instances2, 2, "test_MultipleInstancesLoadAppCompat4 failed!")
        self.assertEquals(num_entries1 * 2, num_entries2, "test_MultipleInstancesLoadAppCompat4 failed!")

    def test_AddExistingHostsAppCompat(self):
        load_test_path = self.BuildTestPath("miniXML")

        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        # Load hosts
        (db_filenameFullPath1, db_version1, num_hosts1, num_instances1, num_entries1) = main([tempdb.name, "load", load_test_path])

        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Reload the same set of hosts again
        (db_filenameFullPath2, db_version2, num_hosts2, num_instances2, num_entries2) = main([tempdb.name, "load", load_test_path])

        # Remove temp db
        os.remove(tempdb.name)

        self.assertEquals(num_hosts1, num_hosts2, "test_SimpleLoad failed!")
        self.assertEquals(num_entries1, num_entries2, "test_SimpleLoad failed!")

    def test_AddExistingHosts_PreProcessed(self):
        load_test_path = self.BuildTestPath("miniXML")

        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        # Load hosts
        (db_filenameFullPath1, db_version1, num_hosts1, num_instances1, num_entries1) = main([tempdb.name, "load", load_test_path])

        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Reload the same set of hosts again
        (db_filenameFullPath2, db_version2, num_hosts2, num_instances2, num_entries2) = main([tempdb.name, "load", load_test_path])

        # Remove temp db
        os.remove(tempdb.name)
        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        self.assertEquals(num_hosts1, num_hosts2, "test_AddExistingHosts_PreProcessed failed!")
        self.assertEquals(num_entries1, num_entries2, "test_AddExistingHosts_PreProcessed failed!")

    def test_AddNewHostsAppCompat(self):
        load_test_path = self.BuildTestPath("miniXML")

        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        # Load hosts
        (db_filenameFullPath1, db_version1, num_hosts1, num_instances1, num_entries1) = main([tempdb.name, "load", load_test_path])

        # Do simple search
        (num_hits1, num_hits_suppressed1, results1) = main([tempdb.name, "search", "-F", "calc.exe"])

        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Create new hosts
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("_w32registry.xml") ]
        for f in filelist:
            copyfile(os.path.join(load_test_path, f), os.path.join(load_test_path, "new_test_" + f))

        # Add new hosts just added
        (db_filenameFullPath2, db_version2, num_hosts2, num_instances2, num_entries2) = main([tempdb.name, "load", load_test_path])

        # Do simple search
        (num_hits2, num_hits_suppressed2, results2) = main([tempdb.name, "search", "-F", "calc.exe"])

        # Remove all fake hosts
        filelist = [ f for f in os.listdir(load_test_path) if f.startswith("new_test_") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Remove all pre-processed -shimcache.txt files:
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Remove temp db
        os.remove(tempdb.name)

        self.assertEquals(num_hosts1 * 2, num_hosts2, "test_SimpleLoad failed!")
        self.assertEquals(num_entries1 * 2, num_entries2, "test_SimpleLoad failed!")
        self.assertEquals(num_hits1 * 2, num_hits2, "test_LiteralSearch failed!")


    def test_AddExistingHostsAmCache(self):
        load_test_path = self.BuildTestPath("TestData-AmCache")
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        # Load hosts
        (db_filenameFullPath1, db_version1, num_hosts1, num_instances1, num_entries1) = main([tempdb.name, "load", load_test_path])

        # Reload the same set of hosts again
        (db_filenameFullPath2, db_version2, num_hosts2, num_instances2, num_entries2) = main([tempdb.name, "load", load_test_path])

        # Remove temp db
        os.remove(tempdb.name)

        self.assertEquals(num_hosts1, num_hosts2, "test_AddExistingHostsAmCache failed!")
        self.assertEquals(num_entries1, num_entries2, "test_AddExistingHostsAmCache failed!")
        self.assertEquals(num_instances1, num_instances2, "test_AddExistingHostsAmCache failed!")

    def test_AddNewHostsAmCache(self):
        load_test_path = self.BuildTestPath("TestData-AmCache")
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        # Load hosts
        (db_filenameFullPath1, db_version1, num_hosts1, num_instances1, num_entries1) = main([tempdb.name, "load", load_test_path])

        # Do simple search
        (num_hits1, num_hits_suppressed1, results1) = main([tempdb.name, "search", "-F", "calc.exe"])

        # Create new hosts
        filelist = [ f for f in os.listdir(load_test_path) if f.endswith("_octet-stream.xml") ]
        for f in filelist:
            copyfile(os.path.join(load_test_path, f), os.path.join(load_test_path, "new_test_" + f))

        # Add new hosts just added
        (db_filenameFullPath, db_version, num_hosts2, num_instances2, num_entries2) = main([tempdb.name, "load", load_test_path])

        # Do simple search
        (num_hits2, num_hits_suppressed2, results2) = main([tempdb.name, "search", "-F", "calc.exe"])

        # Remove all fake hosts
        filelist = [ f for f in os.listdir(load_test_path) if f.startswith("new_test_") ]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Remove temp db
        os.remove(tempdb.name)

        self.assertEquals(num_hosts1 * 2, num_hosts2, "test_AddNewHostsAmCache failed!")
        self.assertEquals(num_entries1 * 2, num_entries2, "test_AddNewHostsAmCache failed!")
        self.assertEquals(num_hits1 * 2, num_hits2, "test_AddNewHostsAmCache failed!")


    def test_RecursiveLoad(self):
        load_test_path = self.BuildTestPath("Recursive")

        # Remove all pre-processed -shimcache.txt files:
        filelist = [f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt")]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries) = main(
            [tempdb.name, "load", load_test_path])

        # Remove temp db
        os.remove(tempdb.name)
        # Remove all pre-processed -shimcache.txt files:
        filelist = [f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt")]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        self.assertEquals(num_hosts, 23, "test_RecursiveLoad failed!")
        self.assertEquals(num_entries, 12442, "test_RecursiveLoad failed!")


    def __test_ZipLoadAppCompat(self):
        load_test_path = self.BuildTestPath("TestZip-AppCompat/dir1/56fe48f9b8b35.zip")

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries) = main(
            [tempdb.name, "load", load_test_path])

        # Remove temp db
        os.remove(tempdb.name)

        self.assertEquals(num_hosts, 22, "test_ZipLoadAppCompat failed!")


    def __test_ZipLoadAmCache(self):
        load_test_path = self.BuildTestPath("TestData-AmCache")

        # Remove all pre-processed -shimcache.txt files:
        filelist = [f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt")]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Remove all fake hosts
        filelist = [f for f in os.listdir(load_test_path) if f.startswith("new_test_")]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries) = main(
            [tempdb.name, "load", load_test_path])

        # Remove temp db
        os.remove(tempdb.name)

        # Remove all pre-processed -shimcache.txt files:
        filelist = [f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt")]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        load_test_path = self.BuildTestPath("TestZip-AmCache/345a67b67f766.zip")

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath2, db_version2, num_hosts2, num_instances2, num_entries2) = main(
            [tempdb.name, "load", load_test_path])

        # Remove temp db
        os.remove(tempdb.name)

        self.assertEquals(num_hosts, num_hosts2, "test_ZipLoadAmCache failed!")
        self.assertEquals(num_instances, num_instances2, "test_ZipLoadAmCache failed!")
        self.assertEquals(num_entries, num_entries2, "test_ZipLoadAmCache failed!")


    def __test_ZipLoadRecursive(self):
        load_test_path = self.BuildTestPath("TestZip-AppCompat")

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries2) = main(
            [tempdb.name, "load", load_test_path])

        # Remove temp db
        os.remove(tempdb.name)

        self.assertEquals(num_hosts, 22, "test_ZipLoadRecursive failed!")


    def __test_ZipLoadRecursive2(self):
        load_test_path = self.BuildTestPath("miniXML")

        # Remove all pre-processed -shimcache.txt files:
        filelist = [f for f in os.listdir(load_test_path) if f.endswith("-shimcache.txt")]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Remove all fake hosts
        filelist = [f for f in os.listdir(load_test_path) if f.startswith("new_test_")]
        for f in filelist:
            os.remove(os.path.join(load_test_path, f))

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath, db_version, num_hosts, num_instances, num_entries) = main(
            [tempdb.name, "load", load_test_path])

        # Remove temp db
        os.remove(tempdb.name)

        load_test_path = self.BuildTestPath("TestZip-AppCompat")

        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        (db_filenameFullPath2, db_version2, num_hosts2, num_instances2, num_entries2) = main(
            [tempdb.name, "load", load_test_path])

        # Remove temp db
        os.remove(tempdb.name)

        self.assertEquals(num_hosts, num_hosts2, "test_ZipLoadRecursive failed!")
        self.assertEquals(num_instances, num_instances2, "test_ZipLoadRecursive failed!")
        self.assertEquals(num_entries, num_entries2, "test_ZipLoadRecursive failed!")

