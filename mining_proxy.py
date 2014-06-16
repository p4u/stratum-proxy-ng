#!/usr/bin/env python
'''
    Stratum mining proxy
    Copyright (C) 2012 Marek Palatinus <slush@satoshilabs.com>
    
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import argparse
import time
import os
import sys
import socket
import threading

def parse_args():
    parser = argparse.ArgumentParser(description='This proxy allows you to run getwork-based miners against Stratum mining pool.')
    parser.add_argument('-o', '--host', dest='host', type=str, default='stratum.bitcoin.cz', help='Hostname of Stratum mining pool')
    parser.add_argument('-p', '--port', dest='port', type=int, default=3333, help='Port of Stratum mining pool')
    parser.add_argument('-sh', '--stratum-host', dest='stratum_host', type=str, default='0.0.0.0', help='On which network interface listen for stratum miners. Use "localhost" for listening on internal IP only.')
    parser.add_argument('-sp', '--stratum-port', dest='stratum_port', type=int, default=3333, help='Port on which port listen for stratum miners.')
    parser.add_argument('-cs', '--custom-stratum', dest='custom_stratum', type=str, help='Override URL provided in X-Stratum header')
    parser.add_argument('-cu', '--custom-user', dest='custom_user', type=str, help='Use this username for submitting shares')
    parser.add_argument('-cp', '--custom-password', dest='custom_password', type=str, help='Use this password for submitting shares')
    parser.add_argument('-xp', '--control-port', dest='control_port', type=int, default=3999, help='Control port')
    parser.add_argument('--dirty-ping', dest='dirty_ping', action='store_true', help='Use dirty ping method to check if the pool is alive (not recommended).')
    parser.add_argument('--timeout', dest='pool_timeout', type=int, default=120, help='Set pool timeout (in seconds).')
    parser.add_argument('--blocknotify', dest='blocknotify_cmd', type=str, default='', help='Execute command when the best block changes (%%s in BLOCKNOTIFY_CMD is replaced by block hash)')
    parser.add_argument('--sharenotify', dest='sharestats_module', type=str, default=None, help='Execute a python snippet when a share is accepted. Use absolute path (i.e /root/snippets/log.py)')
    parser.add_argument('--socks', dest='proxy', type=str, default='', help='Use socks5 proxy for upstream Stratum connection, specify as host:port')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', help='Enable low-level debugging messages')
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', help='Make output more quiet')
    parser.add_argument('-i', '--pid-file', dest='pid_file', type=str, help='Store process pid to the file')
    parser.add_argument('-l', '--log-file', dest='log_file', type=str, help='Log to specified file')
    parser.add_argument('-st', '--scrypt-target', dest='scrypt_target', action='store_true', help='Calculate targets for scrypt algorithm')
    return parser.parse_args()

from stratum import settings
settings.LOGLEVEL='INFO'

if __name__ == '__main__':
    # We need to parse args & setup Stratum environment
    # before any other imports
    args = parse_args()
    if args.quiet:
        settings.DEBUG = False
        settings.LOGLEVEL = 'WARNING'
    elif args.verbose:
        settings.DEBUG = True
        settings.LOGLEVEL = 'DEBUG'
    if args.log_file:
        settings.LOGFILE = args.log_file

from twisted.internet import reactor, defer
from stratum.socket_transport import SocketTransportFactory, SocketTransportClientFactory
from stratum.services import ServiceEventHandler
from twisted.web.server import Site

from mining_libs import stratum_listener
from mining_libs import client_service
from mining_libs import jobs
from mining_libs import version
from mining_libs import utils
from mining_libs import share_stats
import zmq
import stratum.logger

class StratumServer():
    shutdown = False
    log = None
    backup = ['mine.coinshift.com',3333]
    def __init__(self,args,st_listen):
        if args.pid_file:
            fp = file(args.pid_file, 'w')
            fp.write(str(os.getpid()))
            fp.close()
        self.log = stratum.logger.get_logger('proxy-%s'%args.stratum_port)
        st_listen.log = stratum.logger.get_logger('proxy-%s'%args.stratum_port)
        stp = StratumProxy(st_listen)
        stp.set_pool(args.host,args.port,args.custom_user,args.custom_password)
        stp.connect()
        self.z = zmq.Context()
        self.control = threading.Thread(target=self.control,args=[stp,st_listen,args.control_port,self.z])
        self.watcher = threading.Thread(target=self.watcher,args=[stp,st_listen])
        self.control.daemon = True
        self.watcher.daemon = True
        self.control.start()
        self.watcher.start()
        # Setup stratum listener
        if args.stratum_port > 0:
            st_listen.StratumProxyService._set_stratum_proxy(stp)
            st_listen.StratumProxyService._set_sharestats_module(args.sharestats_module)
            reactor_listen = reactor.listenTCP(args.stratum_port, SocketTransportFactory(debug=False, event_handler=ServiceEventHandler), interface=args.stratum_host)
            reactor.addSystemEventTrigger('before', 'shutdown', self.on_shutdown, stp.f)
            self.log.warning("PROXY IS LISTENING ON ALL IPs ON PORT %d (stratum)" % (args.stratum_port))

    def on_shutdown(self,f):
        self.shutdown = True
        '''Clean environment properly'''
        self.log.info("Shutting down proxy...")
        f.is_reconnecting = False # Don't let stratum factory to reconnect again
        self.z.destroy()
        self.control.join(5.0)
        self.watcher.join(5.0)
        time.sleep(1)
        for thread in threading.enumerate():
            if thread.isAlive():
                try:
                    thread._Thread__stop()
                except:
                    self.log.error('Thread could not be terminated')

    def control(self,stp,stl,port,z):
        s = z.socket(zmq.REQ)
        self.log.info("Control port is %s" %port)
        s.bind("tcp://127.0.0.1:%s" %port)
        while not self.shutdown:
            try:
                s.send('READY')
            except Exception as e:
                if self.shutdown: break
                else: log.error("ZMQ error: %s" %e)

            msg = s.recv()
            self.log.info("Control message received: %s" %msg)
            margs = msg.split()
            if margs[0] == 'setpool':
                # host, port, user, passw
                #stl.MiningSubscription.reconnect_all()
                if len(margs) == 3: stp.reconnect(margs[1],int(margs[2]))
                if len(margs) == 4: stp.reconnect(margs[1],int(margs[2]),user=margs[3])
                if len(margs) == 5: stp.reconnect(margs[1],int(margs[2]),user=margs[3],passw=margs[4])
            if margs[0] == 'setbackup':
                if len(margs) == 2:
                    poolport = margs[1].split(':')
                    if len(poolport) == 2:
                        self.log.info("Setting new backup pool: %s:%s" %(poolport[0],poolport[1]))
                        self.backup = poolport

    def watcher(self,stp,stl):
        last_10_rejected = [0,0,0,0,0,0,0,0,0,0]
        rejected_counter = 0
        while not self.shutdown:
            conn = stl.MiningSubscription.get_num_connections()
            last_job_secs = stp.sharestats.get_last_job_secs()
            notify_time = stp.cservice.get_last_notify_secs()
            total_jobs = stp.sharestats.rejected_jobs+stp.sharestats.accepted_jobs
            if total_jobs == 0: total_jobs = 1
            rejected_ratio = float((stp.sharestats.rejected_jobs*100) / total_jobs)
            accepted_ratio = float((stp.sharestats.accepted_jobs*100) / total_jobs)

            last_10_rejected[rejected_counter] = rejected_ratio
            rejected_counter += 1
            if rejected_counter >= 10: rejected_counter = 0
            last_10_rejected_avg = 0
            for r in last_10_rejected: last_10_rejected_avg+=r
            last_10_rejected_avg = last_10_rejected_avg / 10

            self.log.info('Last job was %ss ago | Last notify was %ss ago | Accepted:%s%% Rejected:%s%%/%s%% | Num clients: %s' \
                %(last_job_secs,notify_time,accepted_ratio,rejected_ratio,last_10_rejected_avg,conn))

            if self.backup and conn > 0:
                if notify_time > 80 or rejected_ratio > 40 or last_job_secs > 360:
                    self.log.error('Detected problem with current pool, configuring backup')
                    stp.reconnect(self.backup[0],int(self.backup[1]))

            #stl.MiningSubscription.print_subs()
            time.sleep(10)


class StratumProxy():
    f = None
    jobreg = None
    cservice = None
    use_set_extranonce = False
    set_extranonce_pools = ['nicehash.com']

    def __init__(self,stl):
        self.log = stratum.logger.get_logger('proxy')
        self.stl = stl

    def _detect_set_extranonce(self):
        self.use_set_extranonce = False
        for pool in self.set_extranonce_pools:
            if self.host.find(pool) > 0:
                self.use_set_extranonce = True

    def set_pool(self,host,port,user,passw):
        self.log.warning("Trying to connect to Stratum pool at %s:%d" % (host, port))
        self.host = host
        self.port = int(port)
        self._detect_set_extranonce()
        self.cservice = client_service.ClientMiningService
        self.f = SocketTransportClientFactory(host, port,debug=True, event_handler=self.cservice)
        self.jobreg = jobs.JobRegistry(self.f, scrypt_target=True)
        self.cservice.job_registry = self.jobreg
        self.cservice.use_dirty_ping = False
        self.cservice.pool_timeout = 120
        self.cservice.reset_timeout()
        self.cservice.auth = (user, passw)
        self.sharestats = share_stats.ShareStats()
        self.cservice.f = self.f
        self.f.on_connect.addCallback(self.on_connect)
        self.f.on_disconnect.addCallback(self.on_disconnect)
    
    def reconnect(self,host,port,user=None,passw=None):
        self.host = host
        self.port = int(port)
        self._detect_set_extranonce()
        cuser,cpassw = self.cservice.auth
        if not user: user = cuser
        if not passw: passw = cpassw
        self.cservice.auth = (user, passw)
        self.f.reconnect(host, port, None)

    def connect(self):
        self.f.on_connect

    @defer.inlineCallbacks
    def on_connect(self,f):
        '''Callback when proxy get connected to the pool'''
        # Hook to on_connect again
        f.on_connect.addCallback(self.on_connect)

        # Subscribe for receiving jobs
        self.log.info("Subscribing for mining jobs")
        (_, extranonce1, extranonce2_size) = (yield self.f.rpc('mining.subscribe', []))[:3]
        self.jobreg.set_extranonce(extranonce1, extranonce2_size)

        if self.use_set_extranonce:
            self.log.info("Enable extranonce subscription method")
            f.rpc('mining.extranonce.subscribe', [])

        self.log.warning("Authorizing user %s, password %s" % self.cservice.auth)
        self.cservice.authorize(self.cservice.auth[0], self.cservice.auth[1])

        # Set controlled disconnect to False
        self.cservice.controlled_disconnect = False
        defer.returnValue(f)

    def on_disconnect(self,f):
        '''Callback when proxy get disconnected from the pool'''
        f.on_disconnect.addCallback(self.on_disconnect)
        if not self.cservice.controlled_disconnect:
            self.log.error("Disconnected from Stratum pool at %s:%d" % self.f.main_host)
        if self.cservice.controlled_disconnect:
            self.log.info("Controlled disconnect detected")
        self.stl.MiningSubscription.reconnect_all()
        return f


if __name__ == '__main__':
    ss = StratumServer(args,stratum_listener)
    reactor.run()
    
