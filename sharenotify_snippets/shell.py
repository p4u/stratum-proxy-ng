def on_share(job_id, worker_name, init_time, dif, accepted):
    cmd = 'echo [%t] %w %j/%d ACCEPTED:%a>> /tmp/sharestats.log'
    cmd = cmd.replace('%j', job_id)
    cmd = cmd.replace('%w', worker_name)
    cmd = cmd.replace('%t', str(init_time))
    cmd = cmd.replace('%d', str(dif))
    cmd = cmd.replace('%a', str(accepted))
    log.info("Executing sharenotify command: %s" %cmd)
    subprocess.Popen(cmd, shell=True)
