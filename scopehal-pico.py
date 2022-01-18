#!/usr/bin/python

import time
import socket
import argparse
import threading
import struct
import pyhantek

class SCPIServer:
    def __init__(self, bind_ip="localhost", control_port=5025, waveform_port=5026):
        self.bind_ip       = bind_ip
        self.control_port  = control_port
        self.waveform_port = waveform_port
        self.hantek        = pyhantek.Hantek()

    def open(self):
        print(f"Opening Server {self.bind_ip}:c{self.control_port:d}:w{self.waveform_port:d}...")
        self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.control_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.control_sock.bind((self.bind_ip, self.control_port))
        self.control_sock.listen(1)

        self.waveform_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.waveform_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.waveform_sock.bind((self.bind_ip, self.waveform_port))
        self.waveform_sock.listen(1)

    def close(self):
        print("Closing Server...")
        self.control_sock.close()
        del self.control_sock
        self.waveform_sock.close()
        del self.waveform_sock

    def _control_thread(self):
        while True:
            client, addr = self.control_sock.accept()
            #client.settimeout(1000)
            print(f"Control: Connected with {addr[0]}:{str(addr[1])}")
            try:
                while True:
                    data = client.recv(1024).decode("UTF-8")
                    if len(data) > 0:
                        print(data)
                    else:
                        raise Exception("empty command")
                    if "IDN?" in data:
                        client.send(bytes("Hantek,Hantek6xx4B,0001,0.1\n", "UTF-8"))
                    elif "CHANS?" in data:
                        client.send(bytes("4\n", "UTF-8"))
                    elif "GAIN?" in data:
                        client.send(bytes("1\n", "UTF-8"))
                    elif "OFFS?" in data:
                        client.send(bytes("0\n", "UTF-8"))
                    else:
                        client.send(b"")
            except Exception as e:
                print(e)
                print("Control: Disconnect")
                client.close()

    def _waveform_thread(self):
        while True:
            client, addr = self.waveform_sock.accept()
            print(f"Waveform: Connected with {addr[0]}:{str(addr[1])}")
            try:
                while True:
                    data = self.hantek.read_buffer()
                    # uint16_t numChannels; int64_t fs_per_sample;
                    sample_hdr = struct.pack("<Hq", len(data), 500*1000*1000*1000)
                    #print("snd smpl hdr", sample_hdr)
                    client.send(sample_hdr)
                    i = 0
                    for chdata in data:
                        # size_t chnum; size_t memdepth (samples, not bytes); float config[3]; (scale, offset, trigphase)
                        channel_hdr = struct.pack("<QQfff", i, len(chdata), 1/(2**10), 0, 0)
                        #print("snd chnl hdr", channel_hdr)
                        client.send(channel_hdr)

                        pdata = struct.pack("<"+str(len(chdata))+"h", *[ (element-128) * 64 for element in chdata])
                        #print("snd data", pdata[:20])
                        client.send(pdata)
                        i += 1
            except Exception as e:
                print(e)
                print("Waveform: Disconnect")
                client.close()

    def start(self):
        self.control_thread = threading.Thread(target=self._control_thread)
        self.control_thread.setDaemon(True)
        self.control_thread.start()

        self.waveform_thread = threading.Thread(target=self._waveform_thread)
        self.waveform_thread.setDaemon(True)
        self.waveform_thread.start()

# Run ----------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SCPI Server for Hantek USB Oscilloscope 6xx4 .")
    parser.add_argument("--bind-ip",       default="localhost", help="Host bind address.")
    parser.add_argument("--control-port",  default=5025,        help="Host bind Control port.")
    parser.add_argument("--waveform-port", default=5026,        help="Host bind Waveform port.")
    args = parser.parse_args()

    server = SCPIServer(
        bind_ip       = args.bind_ip,
        control_port  = int(args.control_port),
        waveform_port = int(args.waveform_port)
    )
    server.open()
    server.start()
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()


