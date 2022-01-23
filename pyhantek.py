#!/usr/bin/python

import usb.core
import usb.util
import time
import struct

class Hantek:
    def __init__(self):
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

        self.samplerate = 1250000
        self.slope = "rising"
        self.trigger_voltage = 1 # V

        self.config_wait = True

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
    
        # init ADC start
        # 67 j2390 STATIC
        self.bwrite(b"\x08\x00\x00\x65\x00\x30\x02\x00")
    
        time.sleep(0.002)
    
        # 73 j2395
        self.bwrite(b"\x08\x00\x00\x28\xf1\x0f\x02\x00")
    
        time.sleep(0.015)

        # init ADC end
    
        # 79 j2400
        self.bwrite(b"\x08\x00\x00\x12\x38\x01\x02\x00")

    def config_trigger_x_offset(self):
        # TRIGGER OFFSET m356a triggerXPos something
        offset_raw1 = 214828
        offset_raw2 = 205600
        or1lo = offset_raw1 & 0xffffffff
        or2lo = offset_raw2 & 0xffffffff
        or1hi = (offset_raw1 >> 32) & 0xffff
        or2hi = (offset_raw2 >> 32) & 0xffff
        offset_cmd = struct.pack("<BBIHIH", 0x10, 0x00, or1lo , or1hi, or2lo, or2hi)
        self.bwrite(offset_cmd)
        #self.bwrite(b"\x10\x00\x2c\x47\x03\x00\x00\x00\x20\x23\x03\x00\x00\x00")

    def config_timebase(self):
        # mo13046a dole timebase? 0f00 4b
        # 2us - 0x00; 5us - 0x01; 10us - 0x04; 20us - 0x09; 50us - 0x18 (24); 100us - 0x31 (49); 200us - 0x63 (99)
        timebase_raw = ( 250*10**6 // self.samplerate )//2 - 1
        if timebase_raw < 0:
            timebase_raw = 1250000
        timebase_cmd = struct.pack("<BBI", 0x0f, 0x00, timebase_raw)
        self.bwrite(timebase_cmd)
        #self.bwrite(b"\x0f\x00\x63\x00\x00\x00")

    def config_trigger_slope(self):
        # mo13043a trigger slope 1100 (00 b) 0100
        if self.slope == "rising":
            slope_raw = 0
        else:
            slope_raw = 1
        slope_cmd = struct.pack("<BBBBBB", 0x11, 0x00, 0 , slope_raw, 0, 0)
        self.bwrite(slope_cmd)
        #self.bwrite(b"\x11\x00\x00\x00\x01\x00")

    def config_trigger_level(self):
        delta = 4
        channel_offset = 1 # V
        v_per_div = 0.5
        full_scale = 8 * v_per_div
        trigger_pos = (self.trigger_voltage + channel_offset) / full_scale 
        #middle = (trigger_pos * 200)/256 + 28.5 TODO: check android
        middle = (trigger_pos * 200) + 28.5
        lo = middle - delta 
        hi = middle + delta
        if lo < 0:
            lo = 0
        if lo > 228:
            lo = 228
        if hi < 0:
            hi = 0
        if hi > 228:
            hi = 228

        b  = int(hi) & 0xff
        b2 = int(lo) & 0xff
        b3 = int(middle) & 0xff

        print("trigger raw", middle)

        # TRIGGER LEVEL mo13049a {7, 0, b, b, b2, b2, b, b, b2, b2, b, b, b2, b2, b, b, b2, b2, b3, b3, b3, b3, b3, b3, b3, b3}) b3 - trigger level, b + delta, b2 - delta
        data = [b, b, b2, b2] * 4
        data += [b3] * 8
        cmd = struct.pack("<BB24B", 0x07, 0, *data)
        self.bwrite(cmd)
        #self.bwrite(b"\x07\x00\x76\x76\x6e\x6e\x76\x76\x6e\x6e\x76\x76\x6e\x6e\x76\x76\x6e\x6e\x72\x72\x72\x72\x72\x72\x72\x72")

    def config_channel_offset(self):
        # mo13045a CHANNEL OFFSET
        #off1
        #off2
        #off3
        #off4

        self.bwrite(b"\x1e\x00\x00\x04\x00\x04\x00\x04\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")
        #self.bwrite(b"\x1e\x00\x00\x04\x00\x04\x00\x04\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")

    def config_trigger_source(self):
        # mo13044a 1200 channels enabled ???
        trigger_source = 0
        cmd = struct.pack("<BBBBBB", 0x12, 0x00, 0x3d, 0x00, 0x00, trigger_source)
        self.bwrite(cmd)
        #self.bwrite(b"\x12\x00\x3d\x00\x00\x00")

    def configure(self):
        print("configuring")
        #200us 4ch
        # write 0b 0 j4 i2 < mo13055a 100000000 # counter enabled 1 : 3, frequency meter enabled 
        self.bwrite(b"\x0b\x00\x00\xe1\xf5\x05\x03\x00")
        # pcbver & timebase fcion for me: 0x3f (63) - 4ns, 48 - 2ns, 25 - default
        self.bwrite(b"\x08\x00\x00\x3f\x00\x55\x04\x00")

        self.config_trigger_x_offset()

        # channel settings? mo13046a -> m361b
        self.bwrite(b"\x08\x00\x00\x10\x08\x3a\x04\x00")
        self.bwrite(b"\x08\x00\x00\x04\x02\x3b\x04\x00")
        self.bwrite(b"\x08\x00\x00\x00\x00\x0f\x04\x00")
        self.bwrite(b"\x08\x00\x00\x04\x02\x31\x04\x00")
        self.bwrite(b"\x08\x00\x00\x50\x55\x2a\x04\x00")

        self.config_timebase()

        self.config_trigger_x_offset()

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

        self.config_trigger_source()

        # mo13044a 1200 channels enabled
        self.bwrite(b"\x12\x00\x3d\x00\x00\x00")
        # mo13051a [0,1,2,4]00 2b
        self.bwrite(b"\x00\x00\x01\x62")
        self.bwrite(b"\x01\x00\x64\x70")
        self.bwrite(b"\x02\x00\x80\x69")
        self.bwrite(b"\x04\x00\xd9\x72")

        self.config_channel_offset()

        self.config_trigger_level()

        self.config_trigger_slope()

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
        if self.config_wait:
            self.config_wait = False
            self.configure()

        time.sleep(0.1)

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
        packets = 128
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

        fullscale = 8
        offset = 3
    
        for i in range(len(data)//4):
            ch1.append(data[i*4])
            ch2.append(data[i*4+1])
            ch3.append(data[i*4+2])
            ch4.append(data[i*4+3])
    
        return [ [ e/(255/fullscale) - offset for e in ch1], ch2, ch3, ch4 ]

    def set_rate(self, rate):
        if rate > 250000000:
            return False
        self.samplerate = rate
        self.config_wait = True

    def get_rate(self):
        return self.samplerate

    def get_rates(self):
        rates = []
        values = [ 1, 2, 4, 8, 20, 40, 80, 200, 400, 800, 2000, 4000, 8000, 20000, 40000, 80000]
        rates += [(value)*1000*1000 for value in values] #ns
        return rates

    def set_trigger_level(self, level):
        self.trigger_voltage = level
        self.config_wait = True

