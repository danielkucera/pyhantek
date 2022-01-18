#!/usr/bin/python

import usb.core
import usb.util
import time
import socket
import random
import argparse
import threading
import struct

class Hantek:
    def __init__(self, bind_ip="localhost", control_port=5025, waveform_port=5026):
        dev = usb.core.find(idVendor=0x04b5, idProduct=0x6cde )

        if dev is None:
            raise ValueError('Device not found')

        # set the active configuration. With no arguments, the first
        # configuration will be the active one
        dev.set_configuration()
        
        # get an endpoint instance
        cfg = dev.get_active_configuration()
        
        intf = cfg[(0,0)]
        
        dev.set_interface_altsetting(interface = 0, alternate_setting = 0)
        
        self.ep2 = usb.util.find_descriptor(
            intf,
            custom_match = \
            lambda e: \
                e.bEndpointAddress == 2)
        
        self.ep6 = usb.util.find_descriptor(
            intf,
            custom_match = \
            lambda e: \
                e.bEndpointAddress == 0x86)
        
        assert self.ep2 is not None
        assert self.ep6 is not None

        self.dev = dev

        self.setup()

        self.configure2()

    # USB communication
    def ctrl(self, rtype, req, data, error=None, wValue=0):
        #print(data.hex())
        try:
            ret = self.dev.ctrl_transfer(rtype, req, wValue, 0, data)
        except usb.core.USBError as e:
            print("got", e.errno, e)
            if e.errno == error:
                return
            else:
                raise e
        return ret

    def bwrite(self, data, without_rst=False):
        if not without_rst:
            self.rst()
        self.ep2.write(data)
    
    def bread(self, length):
        timeout = 1000
        return self.dev.read(self.ep6.bEndpointAddress, length, timeout)

    # device controlls
    def ping(self):
        self.ctrl(0xc0, 178, 10)
    
    def rst(self):
        self.ctrl(0x40, 179, b"\x0f\x03\x03\x03\x00\x00\x00\x00\x00\x00")
        self.ctrl(0xc0, 178, 10)

    def getrlen(self):
        data = self.ctrl(0xc0, 178, 10)
        rlen = 64
        if data[0] > 0:
            rlen = 512
        print("rlen", rlen)
        return rlen

    def setup(self):
        self.ctrl(0x40, 234, [ 0x0 ]*10, 32)
        
        self.bwrite([0x0c, 0])
    
        # 37
        self.bwrite([0x0c, 0])
    
        ver = self.bwrite([0x0c, 0])
    
        data = self.bread(self.getrlen())
        # fpgaVersion = data[1,0
        print(data)
    
        # 43
        verB = self.ctrl(0xc0, 162, 71, 0, 0x1580)
        ver = bytearray(verB)
        print(ver)
        
        self.rst()
        
        # 49 eeprom f5f0 - driver version?
        self.ctrl(0xc0, 162, 8, 0, 0x15e0)
        
        # 55 j2376 STATIC
        self.bwrite(b"\x08\x00\x00\x77\x47\x12\x04\x00")
    
        time.sleep(0.002)
    
        # 61, j2387 STATIC
        self.bwrite(b"\x08\x00\x00\x03\x00\x33\x04\x00")
    
        time.sleep(0.002)
    
        # 67 j2390 STATIC
        self.bwrite(b"\x08\x00\x00\x65\x00\x30\x02\x00")
    
        time.sleep(0.002)
    
        # 73 j2395
        self.bwrite(b"\x08\x00\x00\x28\xf1\x0f\x02\x00")
    
        time.sleep(0.015)
    
        # 79 j2400
        self.bwrite(b"\x08\x00\x00\x12\x38\x01\x02\x00")

    def configure(self):
        #200us 4ch
        # write 0b 0 j4 i2 < mo13055a 100000000 # counter enabled 1 : 3, frequency meter enabled 
        self.bwrite(b"\x0b\x00\x00\xe1\xf5\x05\x03\x00")
        # pcbver & timebase fcion for me: 0x3f (63) - 4ns, 48 - 2ns, 25 - default
        self.bwrite(b"\x08\x00\x00\x3f\x00\x55\x04\x00")
        # TRIGGER OFFSET m356a triggerXPos something
        self.bwrite(b"\x10\x00\x2c\x47\x03\x00\x00\x00\x20\x23\x03\x00\x00\x00")
        # channel settings? mo13046a -> m361b
        self.bwrite(b"\x08\x00\x00\x10\x08\x3a\x04\x00")
        self.bwrite(b"\x08\x00\x00\x04\x02\x3b\x04\x00")
        self.bwrite(b"\x08\x00\x00\x00\x00\x0f\x04\x00")
        self.bwrite(b"\x08\x00\x00\x04\x02\x31\x04\x00")
        self.bwrite(b"\x08\x00\x00\x50\x55\x2a\x04\x00")
        # mo13046a dole timebase? 0f00 4b
        self.bwrite(b"\x0f\x00\x63\x00\x00\x00")
        # TRIGGER OFFSET m356a 1000 6b 6b 
        self.bwrite(b"\x10\x00\x2c\x47\x03\x00\x00\x00\x20\x23\x03\x00\x00\x00")
        # 0800 .... 0100 mo13047a
        self.bwrite(b"\x08\x00\x36\x36\x36\x36\x01\x00")
        time.sleep(0.004)
        # 0800 predosle & 134 0111
        self.bwrite(b"\x08\x00\x06\x06\x06\x06\x01\x01")
        time.sleep(0.050)
        # mo13047a -> m361b
        self.bwrite(b"\x08\x00\x00\x10\x08\x3a\x04\x00")
        self.bwrite(b"\x08\x00\x00\x04\x02\x3b\x04\x00")
        self.bwrite(b"\x08\x00\x00\x00\x00\x0f\x04\x00")
        self.bwrite(b"\x08\x00\x00\x04\x02\x31\x04\x00")
        self.bwrite(b"\x08\x00\x00\x50\x55\x2a\x04\x00")
        # mo13044a 1200 ????
        self.bwrite(b"\x12\x00\x3d\x00\x00\x00")
        # mo13051a [0,1,2,4]00 2b
        self.bwrite(b"\x00\x00\x01\x62")
        self.bwrite(b"\x01\x00\x64\x70")
        self.bwrite(b"\x02\x00\x80\x69")
        self.bwrite(b"\x04\x00\xd9\x72")
        # mo13045a
        self.bwrite(b"\x1e\x00\x00\x04\x00\x04\x00\x04\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")
        # TRIGGER LEVEL mo13049a {7, 0, b, b, b2, b2, b, b, b2, b2, b, b, b2, b2, b, b, b2, b2, b3, b3, b3, b3, b3, b3, b3, b3}) b3 - trigger level, b + delta, b2 - delta
        self.bwrite(b"\x07\x00\x76\x76\x6e\x6e\x76\x76\x6e\x6e\x76\x76\x6e\x6e\x76\x76\x6e\x6e\x72\x72\x72\x72\x72\x72\x72\x72")
        # mo13043a trigger slope 1100 (00 b) 0100
        self.bwrite(b"\x11\x00\x00\x00\x01\x00")
        # m308C trigger mode  0300 b 00 : CaptureMode.Roll - set bit 2^1, TriggerSweep.Auto - unset bit 2^0
        #self.bwrite("\x03\x00\x01\x00")

    def configure2(self):
        self.bwrite(b"\x0b\x00\x00\xe1\xf5\x05\x03\x00")
        self.bwrite(b"\x08\x00\x00\x3f\x00\x55\x04\x00")
        self.bwrite(b"\x10\x00\xc4\x31\x08\x00\x00\x00\xd0\xd7\x07\x00\x00\x00")
        self.bwrite(b"\x08\x00\x00\x10\x08\x3a\x04\x00")
        self.bwrite(b"\x08\x00\x00\x04\x02\x3b\x04\x00")
        self.bwrite(b"\x08\x00\x00\x00\x00\x0f\x04\x00")
        self.bwrite(b"\x08\x00\x00\x04\x02\x31\x04\x00")
        self.bwrite(b"\x08\x00\x00\x50\x55\x2a\x04\x00")
        self.bwrite(b"\x0f\x00\xf9\x00\x00\x00")
        self.bwrite(b"\x10\x00\xc4\x31\x08\x00\x00\x00\xd0\xd7\x07\x00\x00\x00")
        self.bwrite(b"\x08\x00\x36\x36\x36\x36\x01\x00")
        self.bwrite(b"\x08\x00\x06\x06\x06\x06\x01\x01")
        self.bwrite(b"\x08\x00\x00\x10\x08\x3a\x04\x00")
        self.bwrite(b"\x08\x00\x00\x04\x02\x3b\x04\x00")
        self.bwrite(b"\x08\x00\x00\x00\x00\x0f\x04\x00")
        self.bwrite(b"\x08\x00\x00\x04\x02\x31\x04\x00")
        self.bwrite(b"\x08\x00\x00\x50\x55\x2a\x04\x00")
        self.bwrite(b"\x12\x00\x3d\x00\x00\x00")
        self.bwrite(b"\x00\x00\xe9\x6e")
        self.bwrite(b"\x01\x00\x64\x70")
        self.bwrite(b"\x02\x00\x7a\x6f")
        self.bwrite(b"\x04\x00\xbc\x70")
        self.bwrite(b"\x1e\x00\x00\x04\x00\x04\x00\x04\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")
        self.bwrite(b"\x07\x00\x9b\x9b\x93\x93\x9b\x9b\x93\x93\x9b\x9b\x93\x93\x9b\x9b\x93\x93\x97\x97\x97\x97\x97\x97\x97\x97")
        self.bwrite(b"\x11\x00\x00\x00\x01\x00")


    def compute_trigg(self, trig23, trig45):
        channelsCount = 4
        fpgaDivTimebase = 0 # with higher timebases, ~230 (fpga constant) with low TB
        triggerXDiv100 = 0.5
    
        d8 = (1 - triggerXDiv100) * 4096
    
        j3 = trig23 - channelsCount * (d8 * (triggerXDiv100 * 4096))
        if j3 < 0:
            j3 += 65536
    
        print("j3", j3, j3 % 8)
    
        j5 = (7 - trig45) & 7
        # 4 channels
        j = (1 & j5) - 6
    
        j6 = j3 + j*channelsCount - fpgaDivTimebase * channelsCount
    
        j6 = int(j6)
    
        if (j6 < 0):
            j6 += 65536
    
        print("j6", j6)
    
        return j6
    
    def read_buffer(self):
        # 357, 291
        self.bwrite([3, 0, 1, 0])
    
        # 363, 297
        self.bwrite([6, 0])
        data = self.bread(512)
        #print("0600", data)
    
        # 373, 307
        self.bwrite([6, 0])
        data = self.bread(512)
        #print("0600", data)
    
        # 383, 317 - read trigger cmd
        self.bwrite([0x0d, 0])
    
        # 392, 325 - read trigger value (first 4 bytes)
        data = self.bread(512)
    
        trig23 = data[2] + data[3]*256
        trig45 = data[4]
        #print(trig23, trig45, "trigger", data[:6])
    
        # --------- READING ------------
    
        # j6 = compute_trigg(trig23, trig45)
        j6 = 0
    
        # 331, 397
        self.bwrite(b"\x0e\x00"+ bytes([ j6 & 255, (j6 >> 8) & 255 ]))
        
        # number of 512B usb packets to send, 0 gives maximum, 1 gives 2, 2 gives 3,...
        packets = 8
        if packets > 0:
            exp_len = (packets)*512
        else:
            exp_len = 65536
    
        # m358a
        self.bwrite([5, 0, 0, packets])
        
        self.ping()
        
        data = self.bread(exp_len)
    
        #print(data[:10], exp_len, len(data), byts, bs)
    
        ch1 = []
        ch2 = []
        ch3 = []
        ch4 = []
    
        for i in range(len(data)//4):
            ch1.append(data[i*4])
            ch2.append(data[i*4+1])
            ch3.append(data[i*4+2])
            ch4.append(data[i*4+3])
    
        return [ ch1, ch2, ch3, ch4 ]


class SCPIServer:
    def __init__(self, bind_ip="localhost", control_port=5025, waveform_port=5026):
        self.bind_ip       = bind_ip
        self.control_port  = control_port
        self.waveform_port = waveform_port
        self.hantek        = Hantek()

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


