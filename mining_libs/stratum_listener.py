import time
import binascii
import struct
from twisted.internet import defer
from stratum.services import GenericService
from stratum.pubsub import Pubsub, Subscription
from stratum.custom_exceptions import ServiceException, RemoteServiceException
from jobs import JobRegistry
import stratum.logger
log = stratum.logger.get_logger('proxy')

class UpstreamServiceException(ServiceException):
    code = -2

class SubmitException(ServiceException):
    code = -2

class ReconnectSubscription(Subscription):
    event = 'mining.reconnect'
    @classmethod
    def reconnect(cls):
        cls.emit([])

class DifficultySubscription(Subscription):
    event = 'mining.set_difficulty'
    difficulty = 1
    
    @classmethod
    def on_new_difficulty(cls, new_difficulty):
        cls.difficulty = new_difficulty
        cls.emit(new_difficulty)
    
    def after_subscribe(self, *args):
        self.emit_single(self.difficulty)
        
class MiningSubscription(Subscription):
    '''This subscription object implements
    logic for broadcasting new jobs to the clients.'''
    
    event = 'mining.notify'
    last_broadcast = None
    
    @classmethod
    def disconnect_all(cls):
        for subs in Pubsub.iterate_subscribers(cls.event):
            if subs.connection_ref().transport != None:
                subs.connection_ref().transport.loseConnection()

    @classmethod
    def reconnect_all(cls):
        for subs in Pubsub.iterate_subscribers(cls.event):
            if subs.connection_ref().transport != None:
                subs.connection_ref().transport.loseConnection()

    @classmethod
    def print_subs(cls):
        c = Pubsub.get_subscription_count(cls.event)
        log.info(c)
        for subs in Pubsub.iterate_subscribers(cls.event):
            s = Pubsub.get_subscription(subs.connection_ref(), cls.event, key=None)
            log.info(s)

    @classmethod
    def get_num_connections(cls):
        return Pubsub.get_subscription_count(cls.event)

    @classmethod
    def on_template(cls, job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, clean_jobs):
        '''Push new job to subscribed clients'''
        cls.last_broadcast = (job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, clean_jobs)
        cls.emit(job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, clean_jobs)
        
    def _finish_after_subscribe(self, result):
        '''Send new job to newly subscribed client'''
        try:        
            (job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, _) = self.last_broadcast
        except Exception:
            log.error("Template not ready yet")
            return result
        
        self.emit_single(job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, True)
        return result
             
    def after_subscribe(self, *args):
        '''This will send new job to the client *after* he receive subscription details.
        on_finish callback solve the issue that job is broadcasted *during*
        the subscription request and client receive messages in wrong order.'''
        self.connection_ref().on_finish.addCallback(self._finish_after_subscribe)
        
class StratumProxyService(GenericService):
    service_type = 'mining'
    service_vendor = 'mining_proxy'
    is_default = True
    use_sharenotify = False
    stp = None # Reference to StratumProxy instance
   
    @classmethod  
    def _set_stratum_proxy(cls,stp):
        cls.stp = stp

    @classmethod  
    def _get_stratum_proxy(cls):
        return cls.stp
        
    @classmethod
    def _set_sharestats_module(cls, module):
        if module != None and len(module) > 1:
            cls.use_sharenotify = True
            cls.stp.sharestats.set_module(module)
           
    @defer.inlineCallbacks
    def authorize(self, worker_name, worker_password, *args):
        f = self._get_stratum_proxy().f
        if f.client == None or not f.client.connected:
            yield f.on_connect
        defer.returnValue(True)

    @defer.inlineCallbacks
    def subscribe(self, *args):    
        f = self._get_stratum_proxy().f
        job = self._get_stratum_proxy().jobreg

        if f.client == None or not f.client.connected:
            yield f.on_connect

        conn = self.connection_ref()

        if f.client == None or not f.client.connected or not conn:
            raise UpstreamServiceException("Upstream not connected")

        if job.extranonce1 == None:
            # This should never happen, because _f.on_connect is fired *after*
            # connection receive mining.subscribe response
            raise UpstreamServiceException("Not subscribed on upstream yet")

        (tail, extranonce2_size) = job._get_unused_tail()
        session = self.connection_ref().get_session()
        session['tail'] = tail
        # Remove extranonce from registry when client disconnect
        conn.on_disconnect.addCallback(job._drop_tail, tail)
        subs1 = Pubsub.subscribe(conn, DifficultySubscription())[0]
        subs2 = Pubsub.subscribe(conn, MiningSubscription())[0]            
        log.info("Sending subscription to worker: %s/%s" %(job.extranonce1+tail, extranonce2_size))
        defer.returnValue(((subs1, subs2),) + (job.extranonce1+tail, extranonce2_size))
    
    @defer.inlineCallbacks
    def submit(self, origin_worker_name, job_id, extranonce2, ntime, nonce, *args):
        f = self._get_stratum_proxy().f
        job = self._get_stratum_proxy().jobreg
        client = self._get_stratum_proxy().cservice

        if f.client == None or not f.client.connected:
            raise SubmitException("Upstream not connected")

        session = self.connection_ref().get_session()
        tail = session.get('tail')
        if tail == None:
            raise SubmitException("Connection is not subscribed")

        worker_name = client.auth[0]

        start = time.time()
        # We got something from pool, reseting client_service timeout

        try:
            job = job.get_job_from_id(job_id)
            difficulty = job.diff if job != None else DifficultySubscription.difficulty
            result = (yield f.rpc('mining.submit', [worker_name, job_id, tail+extranonce2, ntime, nonce]))
            client.reset_timeout()
        except RemoteServiceException as exc:
            response_time = (time.time() - start) * 1000
            log.info("[%dms] Share from %s (%s) rejected, diff %d: %s" % (response_time, origin_worker_name, worker_name, difficulty, str(exc)))
            self.stp.sharestats.register_job(job_id,origin_worker_name,difficulty,False,self.use_sharenotify)
            client.reset_timeout()
            raise SubmitException(*exc.args)

        response_time = (time.time() - start) * 1000
        log.info("[%dms] Share from %s (%s) accepted, diff %d" % (response_time, origin_worker_name, worker_name, difficulty))
        self.stp.sharestats.register_job(job_id,origin_worker_name,difficulty,True,self.use_sharenotify)
        defer.returnValue(result)

    def get_transactions(self, *args):
        log.warn("mining.get_transactions is not supported")
        return []
