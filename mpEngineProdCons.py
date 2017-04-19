import settings
import logging
import multiprocessing
import Queue
import time
from datetime import timedelta, datetime
from appAux import psutil_phymem_usage
import gc

logger = logging.getLogger(__name__)
dying_workers = []

# Auto-balancing Producer-Consumer class

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


class MPEngineProdCons(object):

    def __init__(self, maxCores, producer_Class, consumer_Class, governorOffFlag = False):
        logger.debug("mpEngine initializing")
        self.governorOffFlag = governorOffFlag
        self.maxCores = maxCores
        self.__deleting__ = False
        self.__internalLock__ = multiprocessing.Lock()
        self.killed_event = multiprocessing.Event()

        # Producers
        self.num_producers = 0
        self.next_worker_num = 0
        self.producer_Class = producer_Class
        self.producer_pool = []
        self.producer_pool_exitEvent = []
        self.producer_task_queue = multiprocessing.JoinableQueue()
        self.producer_results_queue = multiprocessing.JoinableQueue()
        self.producer_pool_progress = multiprocessing.Value('i', 0)

        # Consumers
        self.num_consumers = 0
        self.next_consumer_num = 0
        self.consumer_Class = consumer_Class
        self.consumer_pool = []
        # Note: consumer_pool_exitEvent is used both to notify a worker it should end and for the worker to notify it has dones so
        self.consumer_pool_exitEvent = []
        self.consumer_task_queue = self.producer_results_queue
        self.consumer_results_queue = multiprocessing.JoinableQueue()
        self.consumer_pool_progress = multiprocessing.Value('i', 0)

        # Tasks
        self.num_tasks = multiprocessing.Value('i', 0)
        self.tasks_added = False

        # Rebalance checks
        self._rebalance_last_kick = datetime.now()
        self.rebalance_backoff_timer = 60 * 1
        self._rebalance_mem_last_kick = datetime.now()
        self.rebalance_mem_backoff_timer = 60 * 2

    def __enter__(self):
        return self


    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            print exc_type, exc_value, traceback

        self.__del__
        return self


    def __del__(self):
        # Lock internal
        self.__internalLock__.acquire()
        if not self.__deleting__:
            logger.debug("Bringing down mpEngine")
            self.__deleting__ = True

            while self.num_producers > 0: self.removeProducer(True)
            while self.num_consumers > 0: self.removeConsumer(True)

            logger.debug("mpEngine down")
        # Release internal
        self.__internalLock__.release()


    def check_mpEngineStatus(self):
        status_ok = True
        assert(len(self.producer_pool) == self.num_producers)
        assert(len(self.producer_pool) == len(self.producer_pool_exitEvent))
        assert(len(self.consumer_pool) == self.num_consumers)
        assert(len(self.consumer_pool) == len(self.consumer_pool_exitEvent))
        # Check all the processes we believe we have are really alive
        for (worker_num, worker, extra_arg_list) in self.producer_pool:
            if not worker.is_alive():
                logger.error("check_mpEngineStatus error, dead producer process: %s / %s" % (worker_num, worker.name))
                status_ok = False

        for (worker_num, worker, extra_arg_list) in self.consumer_pool:
            if not worker.is_alive():
                logger.error("check_mpEngineStatus error, dead consumer process: %s / %s" % (worker_num, worker.name))
                status_ok = False

        if self.killed_event.is_set(): status_ok = False
        return status_ok


    def working(self):
        # Internal check
        if self.killed_event.is_set() or not self.check_mpEngineStatus():
            print("\n\n\n==>Tearing down mpEngine, we've been killed! out of memory? (give me 60 secs to try to shutdown cleanly)")
            logger.error("Tearing down mpEngine, we've been killed!")
            self.endConsumers()
            time.sleep(2)
            self.endProducers()
            time.sleep(2)
            return False

        # Check if we still have work to do
        if (self.get_num_tasks() != self.getProgressConsumers()): return True
        else:
            logger.debug("mpEngine work finished!")
            # Wait until all our workers have exited
            while self.num_producers > 0: self.removeProducer(True)
            while self.num_consumers > 0: self.removeConsumer(True)
            return False


    def addTaskList(self, task_list):
        if not self.tasks_added:
            with self.num_tasks.get_lock():
                for new_task in task_list:
                    self.num_tasks.value += 1
                    self.producer_task_queue.put(new_task)
            return True
        else:
            logger.error("Can only add tasks once!")
            return False


    def getProgress(self):
        return (self.num_producers, self.num_consumers, self.get_num_tasks(), self.getProgressProducers(), self.getProgressConsumers())


    def get_num_tasks(self):
        with self.num_tasks.get_lock():
            return self.num_tasks.value


    def getProgressProducers(self):
        return self.producer_pool_progress.value


    def getProgressConsumers(self):
        return self.consumer_pool_progress.value


    def getProducerCount(self):
        return self.num_producers


    def addProducer(self, extra_arg_list = []):
        if self.num_producers < self.maxCores:
            # Lock internal
            self.__internalLock__.acquire()

            new_worker_num = self.next_worker_num
            logger.debug("Adding Producer-%d" % (new_worker_num))
            self.producer_pool_exitEvent.append(multiprocessing.Event())
            self.producer_pool.append((new_worker_num, self.producer_Class(
                self.producer_task_queue, self.producer_results_queue, self.get_num_tasks(), self.get_num_tasks(), self.producer_pool_progress,
                self.producer_pool_exitEvent[-1], self.killed_event, extra_arg_list), extra_arg_list))
            self.producer_pool[-1][1].daemon = False # Remove for debugging
            self.producer_pool[-1][1].start()

            # Update worker count
            self.num_producers += 1

            # Update next worker num
            self.next_worker_num += 1

            # Release internal
            self.__internalLock__.release()

            logger.debug("Producer-%d added" % new_worker_num)
        else:
            logger.error("Attempted to start workers beyond the maxCores setting")


    def removeProducer(self, noLock = False):
        if self.num_producers > 0:
            # Lock internal
            if not noLock: self.__internalLock__.acquire()

            # Remove last worker from worker pool
            (worker_num, producer, extra_arg_list) = self.producer_pool.pop()
            logger.debug("Removing Producer-%d" % worker_num)
            # Remove last worker's exitFlag
            producer_exitEvent = self.producer_pool_exitEvent.pop()

            # Set the worker's exit event
            if not producer_exitEvent.is_set():
                logger.debug("Producer-%d exitEvent SET" % worker_num)
                producer_exitEvent.set()

            # Update producer count
            self.num_producers -= 1

            # Release internal
            if not noLock: self.__internalLock__.release()
        else:
            logger.error("Attempted to remove producer from empty pool.")


    def startProducers(self, num_producers, extra_arg_list = []):
        logger.debug("Starting producers")
        if num_producers is None:
            for i in xrange(self.maxCores - 1): self.addProducer(extra_arg_list)
        else:
            for i in xrange(num_producers): self.addProducer(extra_arg_list)


    def restartProducers(self):
        logger.debug("Restarting producers")
        extra_arg_list_list = []
        current_num_producers = self.num_producers
        # Shut them all down
        for i in xrange(current_num_producers):
            # Grab extra_arg_list
            (worker_num, producer, extra_arg_list) = self.producer_pool[-1]
            extra_arg_list_list.append(extra_arg_list)
            self.removeProducer(True)
        # Start them all up again
        for i in xrange(current_num_producers):
            self.addProducer(extra_arg_list_list.pop())

        logger.debug("Restarting producers - done")


    def endProducers(self):
        logger.debug("Ending all producers")
        for i in xrange(self.num_producers): self.removeProducer()


    def getConsumerCount(self):
        return self.num_consumers


    def addConsumer(self, extra_arg_list = []):
        if self.num_consumers < self.maxCores:
            # Lock internal
            self.__internalLock__.acquire()

            new_worker_num = self.next_worker_num
            logger.debug("Adding Consumer-%d" % (new_worker_num))
            self.consumer_pool_exitEvent.append(multiprocessing.Event())
            self.consumer_pool.append((new_worker_num, self.consumer_Class(
                self.consumer_task_queue, self.consumer_results_queue, self.get_num_tasks(), self.producer_pool_progress, self.consumer_pool_progress,
                self.consumer_pool_exitEvent[-1], self.killed_event, extra_arg_list), extra_arg_list))
            self.consumer_pool[-1][1].daemon = False  # Remove for debugging
            self.consumer_pool[-1][1].start()

            # Update consumer count
            self.num_consumers += 1

            # Update next worker num
            self.next_worker_num += 1

            # Release internal
            self.__internalLock__.release()

            logger.debug("Consumer-%d added" % new_worker_num)
        else:
            logger.error("Attempted to start workers beyond the maxCores setting")


    def removeConsumer(self, noLock = True):
        if self.num_consumers > 0:
            # Lock internal
            if not noLock: self.__internalLock__.acquire()

            # Remove last worker from worker pool
            (worker_num, consumer, extra_arg_list) = self.consumer_pool.pop()
            logger.debug("Removing Consumer-%d" % worker_num)
            # Remove last worker's exitFlag
            consumer_exitEvent = self.consumer_pool_exitEvent.pop()

            # Set the worker's exit event
            if not consumer_exitEvent.is_set():
                logger.debug("Consumer-%d exitEvent SET" % worker_num)
                consumer_exitEvent.set()
                # Wait for the worker to acknowledge he has shutdown:
                while consumer_exitEvent.is_set():
                    logger.debug("Waiting for Consumer-%d to shutdown" % worker_num)
                    time.sleep(1)

            # Update consumer count
            self.num_consumers -= 1

            # Release internal
            if not noLock: self.__internalLock__.release()
        else:
            logger.error("Attempted to remove consumer from empty pool.")


    def startConsumers(self, num_consumers, extra_arg_list = []):
        logger.debug("Starting consumers")
        if num_consumers is None:
            for i in xrange(self.maxCores - 1): self.addConsumer(extra_arg_list)
        else:
            for i in xrange(num_consumers): self.addConsumer(extra_arg_list)


    def restartConsumers(self):
        logger.debug("Restarting consumers")
        extra_arg_list_list = []
        current_num_consumers = self.num_consumers
        # Shut them all down
        for i in xrange(current_num_consumers):
            # Grab extra_arg_list
            (worker_num, consumer, extra_arg_list) = self.consumer_pool[-1]
            extra_arg_list_list.append(extra_arg_list)
            self.removeConsumer(True)

        # Give them time to actually shutdown
        time.sleep(1)
        # Start them all up again
        for i in xrange(current_num_consumers):
            self.addConsumer(extra_arg_list_list.pop())

        logger.debug("Restarting consumers - done")


    def endConsumers(self):
        logger.debug("Ending all consumers")
        for i in xrange(self.num_consumers): self.removeConsumer()


    def grabResults(self):
        results = []
        try:
            while True:
                next_result = self.consumer_results_queue.get_nowait()
                results.append(next_result)
        except Queue.Empty:
            pass

        return results


    @rate_limited(1.0 / 10.0)
    def rebalance(self):
        if self.governorOffFlag:
            return
        progProducers = self.getProgressProducers()
        progConsumers = self.getProgressConsumers()
        num_tasks = self.get_num_tasks()
        elapsed_backoff_time = (datetime.now() - self._rebalance_last_kick).seconds

        logger.debug("Starting balancing (timer: %d/%d)" % (elapsed_backoff_time, self.rebalance_backoff_timer))

        # Kill producers if all tasks have been served
        if num_tasks == progProducers and progProducers > 0:
            self.endProducers()
            return

        # Restart paused production on backoff timer or if we have at least 20% memory available
        if self.num_producers == 0 and ((elapsed_backoff_time > self.rebalance_backoff_timer) or psutil_phymem_usage() < 80):
            logger.debug("Rebalancing, restarting production")
            self.addProducer()
            return

        # Memory governor
        # Pause production if we're over 90%
        if psutil_phymem_usage() > 90:
            logger.debug("Rebalancing, mem > 90%, pausing production")
            self.endProducers()
            self._rebalance_last_kick = datetime.now()
            return
        # Reduce production if we're over 75%
        if psutil_phymem_usage() > 75 and self.num_producers > 1:
            if (datetime.now() - self._rebalance_mem_last_kick).seconds > self.rebalance_mem_backoff_timer:
                logger.debug("Rebalancing, mem > 75%")
                self.removeProducer()
                self._rebalance_mem_last_kick = datetime.now()
                return

        # Memory pressure check
        if psutil_phymem_usage() > 70:
            if (datetime.now() - self._rebalance_mem_last_kick).seconds > self.rebalance_mem_backoff_timer:
                logger.debug("Rebalancing mem, recycling processes")
                self.restartConsumers()
                self.restartProducers()
                gc.collect()
                self._rebalance_mem_last_kick = datetime.now()
                logger.debug("Rebalancing mem, recycling processes - done")
                return
            else:
                logger.debug("Rebalance (Memory pressure check) postponed, waiting for rebalance_backoff_timer")

        # We wait until tasks are moving along to start rebalancing stuff
        if progProducers < (num_tasks / 10):
            return

        # Auto-balancing
        if progProducers > progConsumers * 2:
            if self.num_producers > 1:
                if elapsed_backoff_time > self.rebalance_backoff_timer:
                    logger.debug("Rebalancing, too many producers")
                    self.removeProducer()
                    self._rebalance_last_kick = datetime.now()
                    return
                else: logger.debug("Rebalance postponed, waiting for rebalance_backoff_timer")
        elif progProducers < progConsumers * 1.20:
            if num_tasks > progProducers * 1.20:
                if psutil_phymem_usage() < 70 and elapsed_backoff_time > self.rebalance_backoff_timer:
                    logger.debug("Rebalancing")
                    self.addProducer()
                    self._rebalance_last_kick = datetime.now()
                    return
                else: logger.debug("Rebalance (Auto-balancing) postponed, waiting for rebalance_backoff_timer")

        logger.debug("Balancing done")


