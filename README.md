stratum-proxy-ng
====================

Application providing a proxy between a Stratum mining server and a Stratum mining client.

Stratum specification: http://mining.bitcoin.cz/stratum-mining

Current version: alpha 0.1

License: GNU Affero General Public License version 3 (see COPYING)

New features
====================

0. Remove all GetWork related code. 
1. Heavy redesign of the main class code (simple and easier to understand now).
2. Define a backup pool which is used if there is some problem with the current pool.
3. Control thread: new interface to control the proxy via TCP socket and JSON (i.e origin pool can be changed without restarting proxy).
4. Watcher thread: informs about current details of the proxy every 10 seconds
5. Share notify snippets support added (allows execute custom python code when a share is found) 
6. Support for new set extranonce stratum method (partial)
7. Some other small features

Installation on Linux using Git
-------------------------------
This is advanced option for experienced users, but give you the easiest way for updating the proxy.

1. git clone git://github.com/p4u/stratum-proxy-ng.git
2. cd stratum-mining-proxy
3. sudo apt-get install python-dev python-zmq
4. sudo python distribute_setup.py # This will upgrade setuptools package
5. sudo python setup.py develop # This will install required dependencies (namely Twisted and Stratum libraries),
but don't install the package into the system.
6. You can start the proxy by typing "python2.7 stproxy-ng.py" in the terminal window. ``` python2.7 stproxy-ng.py -o originpool.com -p 3333 -sp 3334 -sh 0.0.0.0 -xp 10001 -cu myUser -cp myPass --sharenotify sharenotify_snippets/log.py --control-listen 127.0.0.1 -v```
7. Now you can use the control.py scrypt to control the proxy ```python2.7 control.py 127.0.0.1:10001 setbackup host=poolbackup.com port=3333 user=newUser pass=newPass``` ```python2.7 control.py 127.0.0.1:10001 setpool host=newpool.com port=3333 user=newUser pass=newPass```
8. If you want to update the proxy, type "git pull" in the package directory.

Contact
-------

This proxy is based on the work done by Slush (slush(at)satoshilabs.com).

New generation version created and currently maintained by p4u (p4u(at)dabax.net)

Donation
--------

BTC: 1BaE7aavLF17jj618QKYFc5x6NGxk7uBkC

Thanks ;)

