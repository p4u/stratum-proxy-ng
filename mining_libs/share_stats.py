import time
import stratum.logger
import subprocess
import threading
log = stratum.logger.get_logger('proxy')

class ShareStats(object):	
    def __init__(self):
        self.accepted_jobs = 0
        self.rejected_jobs = 0
        self.accepted_ratio = 0
        self.rejected_ratio = 0
        self.lock = threading.Lock()

    def print_stats(self):
        # Calculate and print job statistics
        total_jobs = self.rejected_jobs+self.accepted_jobs
        if total_jobs > 0 and (total_jobs)%10 == 0:
            self.rejected_ratio = (self.rejected_jobs*100) / total_jobs
            self.accepted_ratio = (self.accepted_jobs*100) / total_jobs
            log.info("\n\n[Share stats] Accepted:%s%% Rejected:%s%%\n" %(self.accepted_ratio,self.rejected_ratio))

            # Reseting counters
            if total_jobs >= 65535:
                self.accepted_jobs = 0
                self.rejected_jobs = 0
                log.info("[Share stats] Reseting statistics")

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
        if accepted: self.accepted_jobs += 1
        else: self.rejected_jobs += 1
        self._execute_snippet(job_id,worker_name,dif,accepted)

    def _execute_snippet(self, job_id, worker_name,dif, accepted):
        log.info("Current active threads: %s" %threading.active_count())
        init_time = time.time()
        threading.Thread(target=self.on_share,args=[self,job_id,worker_name,init_time,dif,accepted]).start()

