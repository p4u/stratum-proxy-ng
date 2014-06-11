from twisted.internet import reactor

from stratum.event_handler import GenericEventHandler
from jobs import Job
import utils
import version as _version
import time
import datetime
import stratum_listener

import stratum.logger
log = stratum.logger.get_logger('proxy')

class ClientMiningService(GenericEventHandler):
    job_registry = None # Reference to JobRegistry instance
    timeout = None # Reference to IReactorTime object
    f = None # Factory of Stratum client
    ping_sent = False
    controlled_disconnect = False
    auth = False
    is_backup_active = False
    use_dirty_ping = False
    pool_timeout = 120
    authorized = None
    last_notify_time = None

    @classmethod
    def set_controlled_disconnect(cls,c):
        cls.controlled_disconnect = c

    @classmethod
    def get_last_notify_secs(cls):
        s = 0
        if cls.last_notify_time != None:
            s = int((datetime.datetime.now() - cls.last_notify_time).total_seconds())
        return s

    @classmethod
    def reset_timeout(cls):
        cls.last_notify_time = datetime.datetime.now()
        if cls.timeout != None:
            if not cls.timeout.called:
                cls.timeout.cancel()
            cls.timeout = None
        cls.timeout = reactor.callLater(cls.pool_timeout, cls.on_timeout)

    @classmethod
    def on_ping_reply(cls,result):
        cls.ping_sent = False
        cls.reset_timeout()

    @classmethod
    def send_ping(cls):
        if cls.f.client == None or not cls.f.client.connected:
            cls.on_timeout()
        else:
            log.info("Sending ping to pool")
            d = cls.f.rpc('mining.ping', [])
            d.addCallback(cls.on_ping_reply)
            d.addErrback(cls.on_ping_reply)
            cls.timeout = reactor.callLater(5, cls.on_timeout)

    @classmethod
    def on_timeout(cls):
        '''
            Try to reconnect to the pool after two minutes of no activity on the connection.
            It will also drop all Stratum connections to sub-miners
            to indicate connection issues.
        '''
        if (not cls.use_dirty_ping) or cls.ping_sent:
            cls.ping_sent = False
            log.error("Connection to upstream pool timed out")
            cls.reset_timeout()
            cls.job_registry.f.reconnect()
            cls.set_controlled_disconnect(False)
            pool = list(cls.job_registry.f.main_host[::])
            cls.job_registry.f.reconnect(pool[0], pool[1], None)
        else:
            cls.ping_sent = True
            cls.send_ping()

    @classmethod
    def _on_fail_authorized(self,resp,worker_name):
        log.exception("Cannot authorize worker '%s'" % worker_name)
        self.authorized = False

    @classmethod
    def _on_authorized(self,resp,worker_name):
        log.info("Worker '%s' autorized by pool" % worker_name)
        self.authorized = True

    @classmethod
    def authorize(self, worker_name, password):
        self.authorized = None
        d = self.f.rpc('mining.authorize', [worker_name, password])
        d.addCallback(self._on_authorized, worker_name)
        d.addErrback(self._on_fail_authorized, worker_name)

    def handle_event(self, method, params, connection_ref):
        '''Handle RPC calls and notifications from the pool'''
        # Yay, we received something from the pool,
        # let's restart the timeout.
        self.reset_timeout()
        
        if method == 'mining.notify':
            '''Proxy just received information about new mining job'''
            
            (job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, clean_jobs) = params[:9]
            diff = self.job_registry.difficulty
            #print len(str(params)), len(merkle_branch)
            '''
            log.debug("Received new job #%s" % job_id)
            log.debug("prevhash = %s" % prevhash)
            log.debug("version = %s" % version)
            log.debug("nbits = %s" % nbits)
            log.debug("ntime = %s" % ntime)
            log.debug("clean_jobs = %s" % clean_jobs)
            log.debug("coinb1 = %s" % coinb1)
            log.debug("coinb2 = %s" % coinb2)
            log.debug("merkle_branch = %s" % merkle_branch)
            log.debug("difficulty = %s" % diff)
            '''
            # Broadcast to Stratum clients
            stratum_listener.MiningSubscription.on_template(
                            job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, clean_jobs)
            
            # Broadcast to getwork clients
            job = Job.build_from_broadcast(job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, diff)
            log.info("New job %s for prevhash %s, clean_jobs=%s" % \
                 (job.job_id, utils.format_hash(job.prevhash), clean_jobs))

            self.job_registry.add_template(job, clean_jobs)
            
        elif method == 'mining.set_difficulty':
            difficulty = params[0]
            log.info("Setting new difficulty: %s" % difficulty)
            stratum_listener.DifficultySubscription.on_new_difficulty(difficulty)
            self.job_registry.set_difficulty(difficulty)
                    
        elif method == 'client.reconnect':
            try:
                (hostname, port, wait) = params[:3]
            except:
                log.error("Pool sent client.reconnect")
                hostname = False
                port = False
                wait = False
            new = list(self.job_registry.f.main_host[::])
            if hostname and len(hostname) > 6: new[0] = hostname
            if port and port > 2: new[1] = port
            log.info("Reconnecting to %s:%d" % tuple(new))
            self.set_controlled_disconnect(True)
            self.job_registry.f.reconnect(new[0], new[1], wait)

        elif method == 'mining.set_extranonce':
            '''Method to set new extranonce'''
            try:
                extranonce1 = params[0]
                extranonce2_size = params[1]
                log.info("Setting new extranonce: %s/%s" %(extranonce1,extranonce2_size))
            except:
                log.error("Wrong extranonce information got from pool, ignoring")
                return False
            self.job_registry.set_extranonce(extranonce1, int(extranonce2_size))
            stratum_listener.MiningSubscription.reconnect_all()

            return True
        
        elif method == 'client.add_peers':
            '''New peers which can be used on connection failure'''
            return False
            '''
            peerlist = params[0] # TODO
            for peer in peerlist:
                self.job_registry.f.add_peer(peer)
            return True
            '''
        elif method == 'client.get_version':
            return "stratum-proxy/%s" % _version.VERSION

        elif method == 'client.show_message':
            
            # Displays message from the server to the terminal
            utils.show_message(params[0])
            return True
            
        elif method == 'mining.get_hashrate':
            return {} # TODO
        
        elif method == 'mining.get_temperature':
            return {} # TODO
        
        else:
            '''Pool just asked us for something which we don't support...'''
            log.error("Unhandled method %s with params %s" % (method, params))

