import zmq
import sys

if len(sys.argv) < 3:
    print("Usage: %s <control_port> <args...>")
    sys.exit(1)

context = zmq.Context()
socket = context.socket(zmq.REQ)    
socket.connect("tcp://127.0.0.1:%s" %sys.argv[1])
msg=""
for a in sys.argv[2::]:
	msg += "%s " %a
socket.send(msg)
reply = socket.recv()
print("> %s" %reply)
context.destroy()
