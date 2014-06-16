import time
import datetime
import stratum.logger
import subprocess
import threading
log = stratum.logger.get_logger('proxy')

class ShareStats(object):	
    def __init__(self):
        self.accepted_jobs = 0
        self.rejected_jobs = 0
        self.lock = threading.Lock()
        self.last_job_time = datetime.datetime.now()

    def get_last_job_secs(self):
        return  int((datetime.datetime.now() - self.last_job_time).total_seconds())

    def set_module(self,module):
        try:
          mod_fd = open("%s" %(module),'r')
          mod_str = mod_fd.read()
          mod_fd.close()
          exec(mod_str)
          self.on_share = on_share
          log.info('Loaded sharenotify module %s' %module)

        except IOError:
          log.error('Cannot load sharenotify snippet')
          def do_nothing(job_id, worker_name, init_time, dif): pass
          self.on_share = do_nothing

    def register_job(self,job_id,worker_name,dif,accepted,sharenotify):
        if self.accepted_jobs + self.rejected_jobs >= 65535:
            self.accepted_jobs = 0
            self.rejected_jobs = 0
            log.info("[Share stats] Reseting statistics")
        self.last_job_time = datetime.datetime.now()
        if accepted: self.accepted_jobs += 1
        else: self.rejected_jobs += 1
        self._execute_snippet(job_id,worker_name,dif,accepted)

    def _execute_snippet(self, job_id, worker_name,dif, accepted):
        log.info("Current active threads: %s" %threading.active_count())
        if threading.active_count() > 10:
            try:
                log.error("Deadlock detected, trying to release it")
                self.lock.release()
            except Exception as e:
                log.error("%s" %e)
        init_time = time.time()
        t = threading.Thread(target=self.on_share,args=[self,job_id,worker_name,init_time,dif,accepted])
        t.daemon = True
        t.start()
