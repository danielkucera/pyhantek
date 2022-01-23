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
            in_buff = b""
            while True:
                try:
                    #data = client.recv(1024).decode("UTF-8")
                    data = client.makefile().readline()
                except Exception as e:
                    print(e)
                    print("Control: Disconnect")
                    client.close()
                if len(data) < 1:
                    break

                cmd = data.split()
                multi_cmd = cmd[0].split(":")
                print(cmd, multi_cmd)

                # Get
                if "IDN?" in data:
                    client.send(bytes("Hantek,Hantek6xx4B,0001,0.1\n", "UTF-8"))
                elif "CHANS?" in data:
                    client.send(bytes("4\n", "UTF-8"))
                elif "RATES?" in data:
                    rates = ",".join(map(str,self.hantek.get_rates()))
                    print(rates)
                    client.send(bytes(rates+"\n", "UTF-8"))
                elif "DEPTHS?" in data:
                    client.send(bytes("4096\n", "UTF-8"))
                elif "GAIN?" in data:
                    client.send(bytes("1\n", "UTF-8"))
                elif "OFFS?" in data:
                    client.send(bytes("0\n", "UTF-8"))

                # Set
                elif "RATE" == cmd[0]:
                    rate = int(cmd[1])
                    self.hantek.set_rate(rate)

                elif len(multi_cmd) > 1:
                    if multi_cmd[0] == "TRIG":
                        if multi_cmd[1] == "LEV":
                            level = float(cmd[1])
                            print("setting trigger level", level)
                            self.hantek.set_trigger_level(level)
                else:
                    client.send(b"")

    def _waveform_thread(self):
        while True:
            client, addr = self.waveform_sock.accept()
            print(f"Waveform: Connected with {addr[0]}:{str(addr[1])}")
            try:
                while True:
                    data = self.hantek.read_buffer()
                    rate = self.hantek.get_rate()
                    fs_per_sample = int((10**15) / rate)
                    # uint16_t numChannels; int64_t fs_per_sample;
                    sample_hdr = struct.pack("<Hq", len(data), fs_per_sample)
                    #print("snd smpl hdr", sample_hdr)
                    client.send(sample_hdr)
                    i = 0
                    for chdata in data:
                        # size_t chnum; size_t memdepth (samples, not bytes); float config[3]; (scale, offset, trigphase)
                        mx = max(chdata)
                        mn = min(chdata)
                        rng = mx-mn
                        if rng == 0:
                            rng = 1
                        scale = 65532/rng
                        offset = mx - rng/2
                        trigphase = 0
                        channel_hdr = struct.pack("<QQfff", i, len(chdata), 1/scale, offset, trigphase)
                        #print("snd chnl hdr", channel_hdr)
                        client.send(channel_hdr)

                        values = [int((element-offset)*scale) for element in chdata]
                        #print(values)
                        pdata = struct.pack("<"+str(len(chdata))+"h", *values)
                        #print("snd data", pdata[:20])
                        client.send(pdata)
                        i += 1
            except BrokenPipeError as e:
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


