import zmq
import sys
import json

def niceprint(data):
	return json.dumps(data,sort_keys=True,indent=4, separators=(',', ': ')).__str__()

if len(sys.argv) < 3:
    print("Usage: %s <control_port> <query> [key1=value1 key2=value2]" %sys.argv[0])
    sys.exit(1)

context = zmq.Context()
socket = context.socket(zmq.REQ)    
socket.connect("tcp://127.0.0.1:%s" %sys.argv[1])
msg = { 'query':sys.argv[2] }

for a in sys.argv[3::]:
	k,v = a.split('=')
	msg[k] = v

print("< %s" %msg)
socket.send(json.dumps(msg))
reply = json.loads(socket.recv())
print("> %s" %niceprint(reply))
context.destroy()
