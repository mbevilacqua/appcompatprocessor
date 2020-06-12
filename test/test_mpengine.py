from __future__ import absolute_import
import logging
from unittest import TestCase
import settings
from mpEngineProdCons import MPEngineProdCons
from mpEngineWorker import MPEngineWorker
import sys, traceback
import time
import appDB
import sqlite3
from contextlib import closing
import uuid
import tempfile

logger = logging.getLogger()

class WkrTestProd(MPEngineWorker):
    def do_work(self, task):
        time.sleep(1)
        return task

class WkrTestCons(MPEngineWorker):
    def do_work(self, task):
        print "Output: %s" % task
        time.sleep(1.5)
        return (task)

class WkrTestProdFast(MPEngineWorker):
    def do_work(self, task):
        time.sleep(0.1)
        return task

class WkrTestConsDB(MPEngineWorker):
    def run(self):
        self.logger.info("WorkerTestConsumerDB: Run")
        self.dbfilenameFullPath = self.extra_arg_list[0]
        self.DB = None
        self.conn = None

        # Init DB access to DB
        self.DB = appDB.DBClass(self.dbfilenameFullPath, True, settings.__version__)
        self.conn = self.DB.appConnectDB()
        self.logger.info("WorkerTestConsumerDB: appConnectDB done")

        # Call super run to continue with the natural worker flow
        super(WkrTestConsDB, self).run()

        # Close DB connection
        self.logger.info("%s - closing down DB" % self.proc_name)

        # # Simulate a very log pending queue of data that needs to be dumped to the DB before we can exit:
        # self.write_to_DB(10, 20)
        # self.conn.close()
        self.logger.info("%s - deleting DB object" % self.proc_name)
        del self.DB

    def write_to_DB(self, number, timer):
        with closing(self.conn.cursor()) as c:
            try:
                for i in xrange(1,number):
                    c.execute("INSERT INTO Internal (Property, Value) VALUES ('%s', 'aaaaa')" % str(uuid.uuid4()))
            except sqlite3.Error as er:
                self.logger.error("SQLITE error: %s" % (er.message))
                raise
            time.sleep(timer)
            self.conn.commit()

    def do_work(self, task):
        print "Starting do_work on: %s" % task
        # Simulate some light DB activity
        self.write_to_DB(10, 0.1)
        return (task)

def rate_limited(period, damping = 1.0):
  '''
  Prevent a method from being called
  if it was previously called before
  a time widows has elapsed.
  :param period: The time window after which method invocations can continue.
  :param damping: A factor by which to dampen the time window.
  :return function: Decorated function that will forward method invocations if the time window has elapsed.
  '''
  frequency = damping / float(period)
  def decorate(func):
    last_called = [0.0]
    def func_wrapper(*args, **kargs):
      elapsed = time.time() - last_called[0]
      left_to_wait = frequency - elapsed
      if left_to_wait > 0:
        # time.sleep(left_to_wait)
        # print left_to_wait
        return None
      ret = func(*args, **kargs)
      last_called[0] = time.time()
      return ret
    return func_wrapper
  return decorate


@rate_limited(1.0/3.0)
def dummy():
    print "dummy"


class TestAppMPEngine(TestCase):
    def setUp(self):
        print("Unittest setUP")
        # Setup the logger
        # settings.init()
        # settings.logger_Sart("unittest.log", True)
        # logger.setLevel(logging.DEBUG)

    def tearDown(self):
        print("Unittest tearDown")
        # settings.logger_Stop()


    def test_MPEngine_DatabaseLocked(self):
        try:
            logger.info("Starting test_MPEngine_end2end_BalanceSimulation")
            # Get temp db name for the test
            tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
            tempdb.close()
            dbfilenameFullPath = tempdb.name
            with appDB.DBClass(dbfilenameFullPath, settings.__version__) as DB:
                DB.appInitDB()

            num_tasks = 50
            mpe = MPEngineProdCons(4, WkrTestProdFast, WkrTestConsDB)
            # Add tasks
            task_list = [i for i in xrange(1, num_tasks + 1)]
            mpe.addTaskList(task_list)

            mpe.addConsumer([dbfilenameFullPath])
            mpe.addProducer()

            loop_test_num = num_tasks
            while mpe.working():
                (num_prod, num_cons, task1, task2, task3) = mpe.getProgress()
                print("Prod: %d / Cons: %d | %s -> %s -> %s" % mpe.getProgress())
                time.sleep(1)
                if task3 >= 20  and task3 <= 30:
                    logger.info("Simulating rebalance (task3: %d task1/2: %d" %(task3, task1/2))
                    mpe.restartConsumers()
                    mpe.restartProducers()
                loop_test_num -= 1

            results = mpe.grabResults()
            self.assertEquals(len(results), num_tasks, "test_MPEngine_end2end")
            self.assertEquals(results[-1], num_tasks, "test_MPEngine_end2end")

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine_end2end")


    def test_MPEngine_ProducerSimple(self):
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        dbfilenameFullPath = tempdb.name
        try:
            with appDB.DBClass(dbfilenameFullPath, settings.__version__) as DB:
                DB.appInitDB()

            print "Starting test"
            mpe = MPEngineProdCons(6, WkrTestProd, WkrTestCons)
            # Add tasks
            task_list = [i for i in xrange(1, 5)]
            mpe.addTaskList(task_list)

            mpe.addProducer()
            mpe.removeProducer()
            time.sleep(2)

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")

    def test_MPEngine_ConsumerSimple(self):
        try:
            # Get temp db name for the test
            tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
            tempdb.close()
            dbfilenameFullPath = tempdb.name
            with appDB.DBClass(dbfilenameFullPath, settings.__version__) as DB:
                DB.appInitDB()

            print "Starting test"
            mpe = MPEngineProdCons(6, WkrTestProd, WkrTestConsDB)
            # Add tasks
            task_list = [i for i in xrange(1, 5)]
            mpe.addTaskList(task_list)

            mpe.addConsumer([dbfilenameFullPath])
            time.sleep(1)
            mpe.removeConsumer()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")

    def test_MPEngine(self):
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        dbfilenameFullPath = tempdb.name
        try:
            with appDB.DBClass(dbfilenameFullPath, settings.__version__) as DB:
                DB.appInitDB()

            print "Starting test"
            mpe = MPEngineProdCons(6, WkrTestProd, WkrTestCons)
            # Add tasks
            task_list = [i for i in xrange(1, 5)]
            mpe.addTaskList(task_list)

            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.addProducer()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")

    def test_MPEngine_brute_producers(self):
        try:
            print "Starting test"
            mpe = MPEngineProdCons(99, WkrTestProd, WkrTestCons)
            # Add tasks
            task_list = [i for i in xrange(1, 5)]
            mpe.addTaskList(task_list)


            for i in xrange(0,99): mpe.addProducer()
            for i in xrange(0,99): mpe.removeProducer()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")

    def test_MPEngine_brute_consumers(self):
        try:
            print "Starting test"
            mpe = MPEngineProdCons(99, WkrTestProd, WkrTestCons)
            # Add tasks
            task_list = [i for i in xrange(1, 5)]
            mpe.addTaskList(task_list)

            for i in xrange(0,25):
                print("Adding consumer %d" % i)
                mpe.addConsumer()
            for i in xrange(0,25):
                print("Removing consumer %d" % i)
                mpe.removeConsumer()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")

    def test_MPEngine_brute_both(self):
        try:
            print "Starting test"
            mpe = MPEngineProdCons(99, WkrTestProd, WkrTestCons)
            max_procs = 5
            # Add tasks
            task_list = [i for i in xrange(1, 5)]
            mpe.addTaskList(task_list)

            for i in xrange(0, max_procs): mpe.addProducer()
            for i in xrange(0, max_procs): mpe.removeProducer()
            for i in xrange(0, max_procs): mpe.addConsumer()
            for i in xrange(0, max_procs): mpe.removeConsumer()

            for i in xrange(0, max_procs): mpe.addProducer()
            for i in xrange(0, max_procs): mpe.addConsumer()
            for i in xrange(0, max_procs): mpe.removeProducer()
            for i in xrange(0, max_procs): mpe.removeConsumer()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")

    def test_MPEngine_brute_both_badmix(self):
        try:
            print "Starting test"
            mpe = MPEngineProdCons(99, WkrTestProd, WkrTestCons)
            max_procs = 10
            # Add tasks
            task_list = [i for i in xrange(1, 5)]
            mpe.addTaskList(task_list)

            for i in xrange(0, max_procs): mpe.addProducer()
            for i in xrange(0, max_procs): mpe.removeProducer()
            for i in xrange(0, max_procs): mpe.addConsumer()
            for i in xrange(0, max_procs): mpe.removeConsumer()

            for i in xrange(0, max_procs): mpe.addProducer()
            for i in xrange(0, max_procs): mpe.addConsumer()
            for i in xrange(0, max_procs): mpe.removeProducer()
            for i in xrange(0, max_procs): mpe.removeConsumer()

            for i in xrange(0, max_procs): mpe.addProducer()
            for i in xrange(0, max_procs): mpe.addConsumer()
            for i in xrange(0, max_procs): mpe.removeConsumer()
            for i in xrange(0, max_procs): mpe.removeProducer()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")

    def test_MPEngine_brute_both_badmix_single(self):
        try:
            print "Starting test"
            mpe = MPEngineProdCons(99, WkrTestProd, WkrTestCons)
            max_procs = 10
            # Add tasks
            task_list = [i for i in xrange(1, 5)]
            mpe.addTaskList(task_list)

            mpe.addProducer()
            mpe.removeProducer()
            mpe.addConsumer()
            mpe.removeConsumer()
            mpe.addProducer()
            mpe.addConsumer()
            mpe.removeProducer()
            mpe.removeConsumer()
            mpe.addProducer()
            mpe.addConsumer()
            mpe.removeConsumer()
            mpe.removeProducer()

            if(mpe.check_mpEngineStatus()): print("++Status looks ok!")
            else:  print("++Status looks wrong!")

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")

    def test_MPEngine_end2end(self):
        try:
            print "Starting test"
            num_tasks = 5
            mpe = MPEngineProdCons(4, WkrTestProd, WkrTestCons)
            # Add tasks
            task_list = [i for i in xrange(1, num_tasks + 1)]
            mpe.addTaskList(task_list)

            mpe.addProducer()
            mpe.addConsumer()

            while mpe.working():
                print("Prod: %d / Cons: %d | %s -> %s -> %s" % mpe.getProgress())
                time.sleep(1)
                mpe.rebalance()

            results = mpe.grabResults()
            self.assertEquals(len(results), num_tasks, "test_MPEngine_end2end")
            self.assertEquals(results[-1], num_tasks, "test_MPEngine_end2end")

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine_end2end")


    def test_MPEngine_end2end_Restart(self):
        try:
            print "Starting test"
            num_tasks = 10
            mpe = MPEngineProdCons(4, WkrTestProd, WkrTestCons)
            # Add tasks
            task_list = [i for i in xrange(1, num_tasks + 1)]
            mpe.addTaskList(task_list)

            mpe.addProducer()
            mpe.addConsumer()

            loop_test_num = 5
            while mpe.working():

                print("Prod: %d / Cons: %d | %s -> %s -> %s" % mpe.getProgress())
                time.sleep(1)
                if loop_test_num == 0:
                    print "++++Test loop"
                    mpe.restartConsumers()
                    mpe.restartProducers()
                loop_test_num -= 1

            results = mpe.grabResults()
            self.assertEquals(len(results), num_tasks, "test_MPEngine_end2end")
            self.assertEquals(results[-1], num_tasks, "test_MPEngine_end2end")

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine_end2end")


    def test_MPEngine_end2end_Restart_v2(self):
        try:
            print "Starting test"
            num_tasks = 10
            mpe = MPEngineProdCons(4, WkrTestProd, WkrTestCons)
            # Add tasks
            task_list = [i for i in xrange(1, num_tasks + 1)]
            mpe.addTaskList(task_list)

            mpe.addProducer()
            mpe.addConsumer()

            loop_test_num = 5
            while mpe.working():

                print("Prod: %d / Cons: %d | %s -> %s -> %s" % mpe.getProgress())
                time.sleep(1)
                if loop_test_num == 0:
                    print "++++Test loop"
                    mpe.restartConsumers()
                    mpe.restartProducers()
                loop_test_num -= 1

            results = mpe.grabResults()
            self.assertEquals(len(results), num_tasks, "test_MPEngine_end2end")
            self.assertEquals(results[-1], num_tasks, "test_MPEngine_end2end")

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine_end2end")


    def test_MPEngine1(self):
        try:
            print "Starting test"
            mpe = MPEngineProdCons(6, WkrTestProd, WkrTestCons)
            # Add tasks
            task_list = [i for i in xrange(1, 5)]
            mpe.addTaskList(task_list)

            mpe.addProducer()
            mpe.addProducer()
            mpe.addProducer()
            mpe.addProducer()
            mpe.addProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.removeProducer()
            mpe.removeProducer()
            mpe.removeProducer()
            mpe.removeProducer()
            mpe.removeProducer()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")


    def test_MPEngine2(self):
        try:
            print "Starting test"
            mpe = MPEngineProdCons(6, WkrTestProd, WkrTestCons)

            mpe.addProducer()
            mpe.removeProducer()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")

    def test_MPEngine3(self):
        try:
            print "Starting test"
            mpe = MPEngineProdCons(6, WkrTestProd, WkrTestCons)

            mpe.addProducer()
            mpe.removeProducer()
            mpe.removeProducer()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")

    def test_MPEngine4(self):
        try:
            print "Starting test"
            mpe = MPEngineProdCons(6, WkrTestProd, WkrTestCons)

            mpe.removeProducer()
            mpe.removeProducer()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")


    def test_MPEngine5(self):
        try:
            print "Starting test"
            maxCores = 6

            mpe = MPEngineProdCons(maxCores, WkrTestProd, WkrTestCons)
            # Add tasks
            task_list = [i for i in xrange(1, 10)]
            mpe.addTaskList(task_list)

            mpe.startProducers(maxCores)
            mpe.startConsumers(1)

            while mpe.working():
                print("Prod: %d / Cons: %d | %s -> %s -> %s" % mpe.getProgress())
                time.sleep(1)
                mpe.rebalance()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")

    def test_MPEngine_dropProducers(self):
        try:
            print "Starting test"
            maxCores = 6

            mpe = MPEngineProdCons(maxCores, WkrTestProd, WkrTestCons)
            # Add tasks
            task_list = [i for i in xrange(1, 10)]
            mpe.addTaskList(task_list)

            mpe.startProducers(4)
            mpe.addProducer()
            mpe.addProducer()
            mpe.removeProducer()
            mpe.removeProducer()
            mpe.startConsumers(1)

            while mpe.working():
                print("Prod: %d / Cons: %d | %s -> %s -> %s" % mpe.getProgress())
                time.sleep(1)
                mpe.rebalance()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")

    def test_MPEngine_regressionBug(self):
        try:
            print "Starting test"
            maxCores = 4

            mpe = MPEngineProdCons(maxCores, WkrTestProd, WkrTestCons)
            # Add tasks
            task_list = [i for i in xrange(1, 8)]
            mpe.addTaskList(task_list)

            mpe.startProducers(3)
            time.sleep(2)
            mpe.startConsumers(1)
            time.sleep(2)
            mpe.endProducers()
            mpe.endConsumers()
            time.sleep(2)
            mpe.addConsumer()
            mpe.addProducer()
            time.sleep(2)
            mpe.addProducer()
            time.sleep(2)
            logger.debug("restartConsumers")
            mpe.restartConsumers()
            logger.debug("restartProducers")
            mpe.restartProducers()
            time.sleep(2)

            while mpe.working():
                print("Prod: %d / Cons: %d | %s -> %s -> %s" % mpe.getProgress())
                time.sleep(1)
                # mpe.rebalance()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")


    def test_MPEngine6(self):
        try:
            print "Starting test"
            mpe = MPEngineProdCons(6, WkrTestProd, WkrTestCons)

            task_list = [i for i in xrange(1, 10)]
            mpe.addTaskList(task_list)

            mpe.addConsumer()
            time.sleep(5)
            mpe.addProducer()

            while mpe.working():
                print("Prod: %d / Cons: %d | %s -> %s -> %s" % mpe.getProgress())
                time.sleep(1)
                mpe.rebalance()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")


    def test_MPEngine_restart(self):
        try:
            print "Starting test"
            with MPEngineProdCons(6, WkrTestProd, WkrTestCons) as mpe:

                mpe.addProducer(["1"])
                mpe.addProducer(["2"])
                mpe.addProducer(["3"])
                mpe.addProducer(["4"])
                self.assertEquals(mpe.getProducerCount(), 4, "test_MPEngine")
                time.sleep(1)
                mpe.restartProducers()
                self.assertEquals(mpe.getProducerCount(), 4, "test_MPEngine")

                while mpe.working():
                    print("Prod: %d / Cons: %d | %s -> %s -> %s" % mpe.getProgress())
                    time.sleep(1)
                    mpe.rebalance()

            del mpe
            print "Test ended"
        except Exception:
            traceback.print_exc(file=sys.stdout)
            self.fail("Exception triggered")

        # Pass
        self.assertEquals(1, 1, "test_MPEngine")