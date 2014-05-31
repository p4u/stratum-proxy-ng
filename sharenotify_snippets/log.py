global slog
slog = open('/var/log/shares.log', 'a')
def on_share(job_id, worker_name, init_time, dif, accepted):
	log.info("Loging share for %s" %worker_name)
	slog.write("[%s] %s %s/%s ACCEPTED:%s\n" %(init_time,worker_name,job_id,dif,accepted))
	slog.flush()
