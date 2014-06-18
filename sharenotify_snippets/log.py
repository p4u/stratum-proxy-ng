def on_share(self,job_id, worker_name, init_time, dif, accepted):
	log.info("Loging share for %s" %worker_name)
	with open('/var/log/shares.log','a') as slog:
            if accepted:
                slog.write("[%s] %s %s accepted/%s\n" %(init_time,worker_name,job_id,dif))
            else:
                slog.write("[%s] %s %s rejected/%s\n" %(init_time,worker_name,job_id,dif))