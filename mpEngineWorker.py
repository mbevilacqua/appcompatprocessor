import logging
import multiprocessing
import signal
import Queue
import time

class GracefulKiller:
  kill_now = False
  def __init__(self):
    signal.signal(signal.SIGINT, self.exit_gracefully)
    signal.signal(signal.SIGTERM, self.exit_gracefully)

  def exit_gracefully(self,signum, frame):
    self.kill_now = True


class MPEngineWorker(multiprocessing.Process):

    def __init__(self, task_queue, results_queue, total_task_num, available_task_num, progress_counter, exitEvent, killed_event, extra_arg_list):
        multiprocessing.Process.__init__(self)
        # logging.config.dictConfig(logger_config_worker)
        # if os.name == 'posix':
        #     # On POSIX, the setup logger will have been configured in the
        #     # parent process, but should have been disabled following the
        #     # dictConfig call.
        #     # On Windows, since fork isn't used, the setup logger won't
        #     # exist in the child, so it would be created and the message
        #     # would appear - hence the "if posix" clause.
        #     self.logger = logging.getLogger('setup')
        #     self.logger.critical('worker_process - Should not appear, because of disabled logger ...')

        self.proc_name = self.name.split("-")[0]+"-"+str(int(self.name.split("-")[1]) - 1)
        self.logger = logging.getLogger(self.proc_name)
        self.logger.debug("%s - __init__" % self.proc_name)

        self.task_queue = task_queue
        self.results_queue = results_queue
        self.total_task_num = total_task_num
        self.available_task_num = available_task_num
        self.progress_counter = progress_counter
        self.exitEvent = exitEvent
        self.killed_event = killed_event

        assert(type(extra_arg_list) is list)
        self.extra_arg_list = extra_arg_list

        self.killer = GracefulKiller()

    def __del__(self):
        self.logger.debug("%s - __del__" % self.proc_name)

    def update_progress(self):
        self.logger.debug("%s - update_progress" % self.proc_name)
        self.task_queue.task_done()
        # Update progress
        with self.progress_counter.get_lock():
            self.progress_counter.value += 1

        # Check if we've been killed
        self.check_killed()

    def check_killed(self):
        # Check if they've tried to kill us
        if self.killer.kill_now:
            self.logger.error("+++%s - KILLED" % self.proc_name)
            self.killed_event.set()

    def run(self):
        self.logger.debug("%s - starting work! PID: %d" % (self.proc_name, self.pid))
        while not self.exitEvent.is_set():
            try:
                self.logger.debug("%s - trying to grab task" % self.proc_name)
                next_task = self.task_queue.get_nowait()
            except Queue.Empty:
                if self.exitEvent.is_set(): break
                else:
                    self.logger.debug("%s - no tasks but we're not ready to die, sleeping" % self.proc_name)
                    time.sleep(1)
                    continue

            self.logger.debug("%s - working" % self.proc_name)
            result = self.do_work(next_task)
            # Update progress
            self.update_progress()
            # Write results to the results_queue
            self.results_queue.put(result)

        # We clear the our exitEvent to indicate we've received it and will shutdown
        self.exitEvent.clear()
        self.logger.debug("%s - finished!" % self.proc_name)
        time.sleep(1)