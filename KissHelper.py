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


# Inspired by:
# * Python script to decode AX.25 from KISS frames over a serial TNC
#   https://gist.github.com/mumrah/8fe7597edde50855211e27192cce9f88
#
# * Sending a raw AX.25 frame with Python
#   https://thomask.sdf.org/blog/2018/12/15/sending-raw-ax25-python.html
#
#   KISS-TNC for LoRa radio modem
#   https://github.com/IZ7BOJ/RPi-LoRa-KISS-TNC

import struct
import datetime
import config

KISS_FEND = 0xC0  # Frame start/end marker
KISS_FESC = 0xDB  # Escape character
KISS_TFEND = 0xDC  # If after an escape, means there was an 0xC0 in the source message
KISS_TFESC = 0xDD  # If after an escape, means there was an 0xDB in the source message

def logf(message):
    timestamp = datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S - ')
    if config.log_enable:
       fileLog = open(config.logpath,"a")
       fileLog.write(timestamp + message+"\n")
       fileLog.close()
    print(timestamp + message)

MAX_SEGMENT_LENGTH = 200 # for segmented packets
segments = []

def encode_kiss_AX25(frame,signalreport): #from Lora to Kiss, Standard AX25
    global segments

    if len(frame) > MAX_SEGMENT_LENGTH + 1:
        logf("Warning: Discarded very long frame, even longer than a segmented frame. Likely corrupted.")
        return

    # If this is a data segment, process it as such.
    if len(frame) >= MAX_SEGMENT_LENGTH + 1 or len(segments) > 0:
        if frame[0:1] == b'0':
            if len(segments) == 0:
                logf("Start of segmented data, caching to recombine.")
            else:
                logf("Continuation of segmented data, adding to cache.")
            segments.append(frame[1:MAX_SEGMENT_LENGTH + 1])
            return
        elif frame[0:1] == b'1':
            if len(segments) == 0:
                logf("Warning, corrupt segmentation, received end segment with no prior segments. Discarding.")
                segments = []
                return
            else:
                logf("End of segmented data, adding to cache and returning complete packet via KISS.")
                segments.append(frame[1:])
                frame = bytearray()
                for segment in segments:
                    for b in segment:
                        frame.append(b)
                segments = []

    packet_escaped = []
    for x in frame:
        if x == KISS_FEND:
            packet_escaped += [KISS_FESC, KISS_TFEND]
        elif x == KISS_FESC:
            packet_escaped += [KISS_FESC, KISS_TFESC]
        else:
            packet_escaped += [x]

    kiss_cmd = 0x00  # Two nybbles combined - TNC 0, command 0 (send data)
    kiss_frame = [KISS_FEND, kiss_cmd] + packet_escaped + [KISS_FEND]

    try:
        output = bytearray(kiss_frame)
    except ValueError:
        logf("Invalid value in frame.")
        return None
    return output

def decode_kiss_AX25(frame): #from kiss to LoRA, Standard AX25
    result = b""

    if frame[0] != 0xC0 or frame[len(frame) - 1] != 0xC0:
        logf("Kiss Header not found, abort decoding of Frame: "+repr(frame))
        return None
    frame=frame[2:len(frame) - 1] #cut kiss delimitator 0xc0 and command 0x00

    return frame


class SerialParser():
    '''Simple parser for KISS frames. It handles multiple frames in one packet
    and calls the callback function on each frame'''
    STATE_IDLE = 0
    STATE_FEND = 1
    STATE_DATA = 2
    KISS_FEND = KISS_FEND

    def __init__(self, frame_cb=None):
        self.frame_cb = frame_cb
        self.reset()

    def reset(self):
        self.state = self.STATE_IDLE
        self.cur_frame = bytearray()

    def parse(self, data):
        try:
            for c in data:
                if self.state == self.STATE_IDLE:
                    if c == self.KISS_FEND:
                        self.cur_frame.append(c)
                        self.state = self.STATE_FEND
                elif self.state == self.STATE_FEND:
                    if c == self.KISS_FEND:
                        self.reset()
                    else:
                        self.cur_frame.append(c)
                        self.state = self.STATE_DATA
                elif self.state == self.STATE_DATA:
                    self.cur_frame.append(c)
                    if c == self.KISS_FEND:
                        # frame complete
                        if self.frame_cb:
                            self.frame_cb(self.cur_frame)
                        self.reset()
        except Exception as e:
            logf("Exception in SerialParser.parse(), callback NOT called.")
            logf(str(e))

