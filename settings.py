import sys
import os
from namedlist import namedlist
import logging
import logging.config
import logging.handlers
from multiprocessing import Process, Queue, Event
import threading
from Queue import Empty
import time
import pprint

__author__ = 'matiasbevilacqua'
__version__ = '0.9.2'
__versiondate__ = "2021-07-13T12:32:00"

# Entry types:
__APPCOMPAT__ = 0
__AMCACHE__ = 1

# Python modules we use but can live without:
__TERMCOLOR__ = True
__PYREGF__ = True
__LEVEN__ = True
__FAKER__ = True
__PSUTIL__ = True

# Global logger:
logger = None
logger_stop_event = None
logger_process = None

logger_queue = Queue()

logger_config_initial = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'queue': {
            'class': 'settings.QueueHandler',
            'queue': logger_queue,
        },
    },
    'root': {
        'level': 'INFO',
        'handlers': ['queue']
    },
}

logger_config_worker = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'queue': {
            'class': 'settings.QueueHandler',
            'queue': logger_queue,
        },
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['queue']
    },
}

logger_config_listener = None

class QueueHandler(logging.Handler):
    """
    This handler sends events to a queue. Typically, it would be used together
    with a multiprocessing Queue to centralise logging to file in one process
    (in a multi-process application), so as to avoid file write contention
    between processes.

    This code is new in Python 3.2, but this class can be copy pasted into
    user code for use with earlier Python versions.

    From Python 3.2 source code.
    """

    def __init__(self, queue):
        """
        Initialise an instance, using the passed queue.
        """
        logging.Handler.__init__(self)
        self.queue = queue

    def enqueue(self, record):
        """
        Enqueue a record.

        The base implementation uses put_nowait. You may want to override
        this method if you want to use blocking, timeouts or custom queue
        implementations.
        """
        try:
            self.queue.put_nowait(record)
        # todo: Fix 'queue is not defined' error!
        except queue.Full:
            print("=>Logging queue full, dropping log entries!")

    def prepare(self, record):
        """
        Prepares a record for queuing. The object returned by this method is
        enqueued.

        The base implementation formats the record to merge the message
        and arguments, and removes unpickleable items from the record
        in-place.

        You might want to override this method if you want to convert
        the record to a dict or JSON string, or send a modified copy
        of the record while leaving the original intact.
        """
        # The format operation gets traceback text into record.exc_text
        # (if there's exception data), and also puts the message into
        # record.message. We can then use this to replace the original
        # msg + args, as these might be unpickleable. We also zap the
        # exc_info attribute, as it's no longer needed and, if not None,
        # will typically not be pickleable.
        self.format(record)
        record.msg = record.message
        record.args = None
        record.exc_info = None
        return record

    def emit(self, record):
        """
        Emit a record.

        Writes the LogRecord to the queue, preparing it for pickling first.
        """
        try:
            self.enqueue(self.prepare(record))
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

class QueueListener(object):
    """
    This class implements an internal threaded listener which watches for
    LogRecords being added to a queue, removes them and passes them to a
    list of handlers for processing.

    From Python 3.2 source code.
    """
    _sentinel = None

    def __init__(self, queue, *handlers):
        """
        Initialise an instance with the specified queue and
        handlers.
        """
        self.queue = queue
        self.handlers = handlers
        self._stop = threading.Event()
        self._thread = None

    def dequeue(self, block):
        """
        Dequeue a record and return it, optionally blocking.

        The base implementation uses get. You may want to override this method
        if you want to use timeouts or work with custom queue implementations.
        """
        return self.queue.get(block)

    def start(self):
        """
        Start the listener.

        This starts up a background thread to monitor the queue for
        LogRecords to process.
        """
        self._thread = t = threading.Thread(target=self._monitor)
        t.setDaemon(True)
        t.start()

    def prepare(self , record):
        """
        Prepare a record for handling.

        This method just returns the passed-in record. You may want to
        override this method if you need to do any custom marshalling or
        manipulation of the record before passing it to the handlers.
        """
        return record

    def handle(self, record):
        """
        Handle a record.

        This just loops through the handlers offering them the record
        to handle.
        """
        record = self.prepare(record)
        for handler in self.handlers:
            handler.handle(record)

    def _monitor(self):
        """
        Monitor the queue for records, and ask the handler
        to deal with them.

        This method runs on a separate, internal thread.
        The thread will terminate if it sees a sentinel object in the queue.
        """
        q = self.queue
        has_task_done = hasattr(q, 'task_done')
        try:
            while not self._stop.isSet():
                try:
                    record = self.dequeue(True)
                    if record is self._sentinel:
                        break
                    self.handle(record)
                    if has_task_done:
                        q.task_done()
                except Empty:
                    pass
            # There might still be records in the queue.
            while True:
                try:
                    record = self.dequeue(False)
                    if record is self._sentinel:
                        break
                    self.handle(record)
                    if has_task_done:
                        q.task_done()
                except Empty:
                    break
        except EOFError: # The pipe was close, no more log record will be queued
            pass

    def stop(self):
        """
        Stop the listener.

        This asks the thread to terminate, and then waits for it to do so.
        Note that if you don't call this before your application exits, there
        may be some records still left on the queue, which won't be processed.
        """
        if self._thread:
            self._stop.set()
            self.queue.put_nowait(self._sentinel)
            self._thread.join()
            self._thread = None

class MyHandler(object):
    """
    A simple handler for logging events. It runs in the listener process and
    dispatches events to loggers based on the name in the received record,
    which then get dispatched, by the logging system, to the handlers
    configured for those loggers.
    """
    def handle(self, record):
        logger = logging.getLogger(record.name)
        # The process name is transformed just to show that it's the listener
        # doing the logging to files and console
        # record.processName = '%s (for %s)' % (current_process().name, record.processName)
        logger.handle(record)

def logger_listener_process(q, stop_event, config):
    """
    This could be done in the main process, but is just done in a separate
    process for illustrative purposes.

    This initialises logging according to the specified configuration,
    starts the listener and waits for the main process to signal completion
    via the event. The listener is then stopped, and the process exits.
    """
    logging.config.dictConfig(config)
    listener = QueueListener(q, MyHandler())
    listener.start()
    if os.name == 'posix':
        # On POSIX, the setup logger will have been configured in the
        # parent process.
        # On Windows, since fork isn't used, the setup logger won't
        # exist in the child, so it would be created.
        logger = logging.getLogger('setup')
        # logger.critical('Should not appear, because of disabled logger ...')
    stop_event.wait()
    listener.stop()

def logger_Sart(log_filename, verboseMode):
    global logger, logger_stop_event, logger_process, logger_config_listener

    logger_config_listener = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'detailed': {
                'class': 'logging.Formatter',
                'format': '%(asctime)s %(name)-16s %(levelname)-8s %(processName)-10s %(message)s'
            },
            'simple': {
                'class': 'logging.Formatter',
                'format': '%(asctime)s %(levelname)-8s %(message)s'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'INFO',
                'formatter': 'simple',
            },
            'file': {
                'class': 'logging.FileHandler',
                'filename': log_filename + '.log',
                'mode': 'w',
                'formatter': 'detailed',
            },
            'errors': {
                'class': 'logging.FileHandler',
                'filename': log_filename + '-errors.log',
                'mode': 'w',
                'level': 'ERROR',
                'formatter': 'detailed',
            },
        },
        'root': {
            'level': 'DEBUG',
            'handlers': ['console', 'file', 'errors']
        },
    }

    logging.config.dictConfig(logger_config_initial)
    logger = logging.getLogger()

    # Create logger listener
    logger_stop_event = Event()
    logger_process = Process(target=logger_listener_process, name='listener', args=(logger_queue, logger_stop_event, logger_config_listener))
    logger_process.start()
    if verboseMode:
        logger.setLevel(logging.DEBUG)
    else: logger.setLevel(logging.INFO)


    logger.info("-------------------------------Log started-------------------------------")
    logger.debug("Python version: %s" % ''.join((sys.version).splitlines()))
    from appAux import psutil_phymem_usage
    logger.debug("Physical mem used: %d%%" % psutil_phymem_usage())


def logger_Stop():
    logger.debug('Shuting down logger listener.')
    logger_stop_event.set()
    time.sleep(1)
    logger_process.join()
    # Login final note to the root logger:
    # todo: Figure out why this never makes it to the log
    logging.getLogger().debug('All done.')


def logger_getDebugMode():
    level = logger.getEffectiveLevel()
    return (level <= logging.DEBUG)


def logger_Test():
    logger.info("Start logger test")
    logger.critical("# CRITICAL  50")
    logger.error("# ERROR     40")
    logger.warning("# WARNING   30")
    logger.info("# INFO      20")
    logger.debug("# DEBUG     10")
    # logger.verbose("# VERBOSE   05")
    logger.info("End logger test")


def init():
    global pp
    pp = pprint.PrettyPrinter(indent=4)

    global rawOutput
    rawOutput = False

    # todo: Try to dynamicaly construct this from DB schema
    global EntriesList
    EntriesList = ["RowID", "HostID", "EntryType", "RowNumber", "LastModified", "LastUpdate", "FilePathID", "FilePath", "FileName",
         "Size", "ExecFlag", "SHA1", "FileDescription", "FirstRun", "Created", "Modified1", "Modified2", "LinkerTS",
         "Product", "Company", "PE_sizeofimage", "Version_number", "Version", "Language", "Header_hash", "PE_checksum",
         "SwitchBackContext", "InstanceID", "Recon", "ReconSession"]
    global EntriesFields
    EntriesFields = namedlist("EntriesFields", EntriesList , default = None)

