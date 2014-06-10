import zmq
import sys
context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("tcp://127.0.0.1:3999")
msg=""
for a in sys.argv[1::]:
	msg += "%s " %a
socket.send(msg)
reply = socket.recv()
print("> %s" %reply)

