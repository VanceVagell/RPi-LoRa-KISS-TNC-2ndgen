#!/usr/bin/python3
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# -*- coding: utf-8 -*-
from __future__ import print_function
import sys
from threading import Thread
import socket
from KissHelper import SerialParser
import KissHelper
import config
import datetime

def logf(message):
    timestamp = datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S - ')
    if config.log_enable:
       fileLog = open(config.logpath,"a")
       fileLog.write(timestamp + message+"\n")
       fileLog.close()
    print(timestamp + message+"\n")

client_address = []
RECV_BUFFER_LENGTH = 1024

class KissServer(Thread):
    '''TCP Server to be connected to by a KISS client'''

    txQueue = None

    # host and port as configured in aprx/aprx.conf.lora-aprs < interface > section
    def __init__(self, txQueue, host="127.0.0.1", port=bytes(10001)):
        Thread.__init__(self)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((host, port))
        self.socket.listen(1)
        self.data = str()
        self.txQueue = txQueue
        self.connection = None
        logf("KISS-Server: Started. Listening on IP "+host+" Port: "+str(port))

    def run(self):
        global client_address
        parser = SerialParser(self.queue_frame)

        # test packets (uncomment to test tx)

        # 1. Largest packet possible (pre-segmented into 201 bytes)
        # self.queue_frame(b'\xc0\x00\x96\xach\xa0@@\xe6\x96\xach\xa0@@e\x92\xcf\x96\xach\xa0@@r\x96\xach\xa0@@t\x07\x06\xcc\x01\x02\x05\x01NKV4P-9 KY4ZC-9 Z4ZC09 6.0.21.40\r\x01NKV4P-9 KD4UNX-9 ZUNX09 6.0.21.40\r\x01NKV4P-9 K4LBX-9 ZLBX09 6.0.21.40\r\x01NKV4P-9 NC4AU-9 Z4AU09 6.0.21.40\r\x01NKV4P-9 W3KHG-9 ZKHG09 6.0\xc0')

        # 2. Long packets that will need to be segmented
        # self.queue_frame(b'\xc0\x00\x96\xach\xa0@@\xe6\x96\xach\xa0@@e\x92\xcf\x96\xach\xa0@@r\x96\xach\xa0@@t\x07\x06\xcc\x01\x02\x05\x01NKV4P-9 KY4ZC-9 Z4ZC09 6.0.21.40\r\x01NKV4P-9 KD4UNX-9 ZUNX09 6.0.21.40\r\x01NKV4P-9 K4LBX-9 ZLBX09 6.0.21.40\r\x01NKV4P-9 NC4AU-9 Z4AU09 6.0.21.40\r\x01NKV4P-9 W3KHG-9 ZKHG09 6.0.21.40\r\x01NKV4P-9 KO4IBM-9 ZIBM09 6.0.21.40\r\x01NKV4P-9 KW4KZ-9 Z4KZ09 6.0.21\xc0')
        # self.queue_frame(b'\xc0\x00\x96\xach\xa0@@\xe4\x96\xach\xa0@@g<\xcf\x96\xach\xa0@@t\x96\xach\xa0@@r\x07\x04\x9fV\xce\x05\x01DKV4P-10 KV4P If you do want to play with Lora I recommend the pi bonnet linked on the wiki, just because the libraries for interfacing are chipset specific and you can save yourself effort tracking down the right way to interface\r\xc0')

        while True:
            self.connection = None
            self.connection, client_address = self.socket.accept()
            parser.reset()
            logf("KISS-Server: Accepted Connection from %s" % client_address[0])
            while True:
                try:
                    data = self.connection.recv(RECV_BUFFER_LENGTH)
                except Exception:
                    logf("Exception while attempting to receive data in TCPServer.")
                    continue
                if data:
                    parser.parse(data)
                else:
                    logf("KISS-Server: Closed Connection from %s" % client_address[0])
                    self.connection.close()
                    break

    def segment_ax25_packet(self, packet):
        # The maximum size for the data in each segment.
        MAX_SEGMENT_SIZE = 200

        # If packet is small enough to transmit in one go, return as is
        if len(packet) <= MAX_SEGMENT_SIZE:
            return [packet]

        segments = []

        # Start breaking the data into segments.
        while packet:
            segment_data = packet[:MAX_SEGMENT_SIZE]
            packet = packet[MAX_SEGMENT_SIZE:]

            # Mark the first or continuation segments with a "0" in first byte, and the final segment with "1"
            segment = (b'0' if packet else b'1') + segment_data
            segments.append(segment)

        return segments

    def queue_frame(self, frame, verbose=True):
        global client_address
        try:
            logf("Received from IP: "+str(client_address[0])+" KISS Frame: "+repr(frame))
        except Exception as e:
            logf("Exception in queue_frame: " + repr(e))
        decoded_data = KissHelper.decode_kiss_AX25(frame)
        #logf("Decapsulated Kiss Frame :"+ repr(decoded_data))

        # subdivide any packets that are too large into <255 bytes to fit in LoRa module tx register
        segments = self.segment_ax25_packet(decoded_data)
        for segment in segments:
            self.txQueue.put(segment, block=True)

    def __del__(self):
        self.socket.shutdown()

    def send(self, data,signalreport):
        global peer
        LORA_APRS_HEADER = b"<\xff\x01"
        # remove LoRa-APRS header if present
        logf("\033[94mTrying standard AX25 decoding...\033[0m")
        try:
            encoded_data = KissHelper.encode_kiss_AX25(data,signalreport)
        except Exception as e:
            logf("KISS encoding went wrong (exception while parsing)")
            traceback.print_tb(e.__traceback__)
            encoded_data = None
        if encoded_data != None:
            if self.connection:
                logf("Sending to ip: " + client_address[0] + " port:" + str(client_address[1]) + " Frame: " + repr(encoded_data))
                self.connection.sendall(encoded_data)
