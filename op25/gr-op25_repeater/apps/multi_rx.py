#!/usr/bin/env python

# Copyright 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020 Max H. Parke KA1RBI
# 
# This file is part of OP25
# 
# OP25 is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# OP25 is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
# License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with OP25; see the file COPYING. If not, write to the Free
# Software Foundation, Inc., 51 Franklin Street, Boston, MA
# 02110-1301, USA.

import os
import sys
import threading
import time
import json
import traceback
import osmosdr

from gnuradio import audio, eng_notation, gr, gru, filter, blocks, fft, analog, digital
from gnuradio.eng_option import eng_option
from math import pi
from optparse import OptionParser

import op25
import op25_repeater
import p25_demodulator
import p25_decoder

from gr_gnuplot import constellation_sink_c
from gr_gnuplot import fft_sink_c
from gr_gnuplot import mixer_sink_c
from gr_gnuplot import symbol_sink_f
from gr_gnuplot import eye_sink_f
from gr_gnuplot import setup_correlation

from nxdn_trunking import cac_message

os.environ['IMBE'] = 'soft'

_def_symbol_rate = 4800

# The P25 receiver
#

def byteify(input):	# thx so
    if sys.version[0] != '2':	# hack, must be a better way
        return input
    if isinstance(input, dict):
        return {byteify(key): byteify(value)
                for key, value in input.iteritems()}
    elif isinstance(input, list):
        return [byteify(element) for element in input]
    elif isinstance(input, unicode):
        return input.encode('utf-8')
    else:
        return input

class device(object):
    def __init__(self, config, tb):
        self.name = config['name']
        self.sample_rate = config['rate']
        self.args = config['args']
        self.tb = tb

        if config['args'].startswith('audio:'):
            self.init_audio(config)
        elif config['args'].startswith('file:'):
            self.init_file(config)
        elif config['args'].startswith('udp:'):
            self.init_udp(config)
        else:
            self.init_osmosdr(config)

    def init_file(self, config):
        filename = config['args'].replace('file:', '', 1)
        src = blocks.file_source(gr.sizeof_gr_complex, filename, repeat = False)
        throttle = blocks.throttle(gr.sizeof_gr_complex, config['rate'])
        self.tb.connect(src, throttle)
        self.src = throttle
        self.frequency = config['frequency']
        self.offset = config['offset']

    def init_audio(self, config):
        filename = config['args'].replace('audio:', '')
        src = audio.source(self.sample_rate, filename)
        gain = 1.0
        if config['gains'].startswith('audio:'):
           gain = float(config['gains'].replace('audio:', ''))
        self.src = blocks.multiply_const_ff(gain)
        self.tb.connect(src, self.src)

    def init_udp(self, config):
        hostinfo = config['args'].split(':')
        hostname = hostinfo[1]
        udp_port = int(hostinfo[2])
        bufsize = 32000		# might try enlarging this if packet loss
        self.src = blocks.udp_source(gr.sizeof_gr_complex, hostname, udp_port, payload_size = bufsize)
        self.ppm = 0
        self.frequency = config['frequency']
        self.offset = 0

    def init_osmosdr(self, config):
        speeds = [250000, 1000000, 1024000, 1800000, 1920000, 2000000, 2048000, 2400000, 2560000]

        sys.stderr.write('device: %s\n' % config)
        if config['args'].startswith('rtl') and config['rate'] not in speeds:
            sys.stderr.write('WARNING: requested sample rate %d for device %s may not\n' % (config['rate'], config['name']))
            sys.stderr.write("be optimal.  You may want to use one of the following rates\n")
            sys.stderr.write('%s\n' % speeds)
        self.src = osmosdr.source(config['args'])

        for tup in config['gains'].split(','):
            name, gain = tup.split(':')
            self.src.set_gain(int(gain), name)

        self.src.set_freq_corr(config['ppm'])
        self.ppm = config['ppm']

        self.src.set_sample_rate(config['rate'])

        self.src.set_center_freq(config['frequency'])
        self.frequency = config['frequency']

        self.offset = config['offset']

class channel(object):
    def __init__(self, config, dev, verbosity, msgq = None):
        sys.stderr.write('channel (dev %s): %s\n' % (dev.name, config))
        self.device = dev
        self.name = config['name']
        self.symbol_rate = _def_symbol_rate
        if 'symbol_rate' in config.keys():
            self.symbol_rate = config['symbol_rate']
        self.config = config
        if dev.args.startswith('audio:'):
            self.demod = p25_demodulator.p25_demod_fb(
                         input_rate = dev.sample_rate,
                         filter_type = config['filter_type'],
                         if_rate = config['if_rate'],
                         symbol_rate = self.symbol_rate)
        else:
            self.demod = p25_demodulator.p25_demod_cb(
                         input_rate = dev.sample_rate,
                         demod_type = config['demod_type'],
                         filter_type = config['filter_type'],
                         excess_bw = config['excess_bw'],
                         relative_freq = dev.frequency + dev.offset - config['frequency'],
                         offset = dev.offset,
                         if_rate = config['if_rate'],
                         symbol_rate = self.symbol_rate)
        if msgq is None:
            q = gr.msg_queue(1)
        else:
            q = msgq
        self.decoder = op25_repeater.frame_assembler(config['destination'], verbosity, q)

        self.kill_sink = []

        if 'blacklist' in config.keys():
            for g in config['blacklist'].split(','):
                self.decoder.insert_blacklist(int(g))

        if 'whitelist' in config.keys():
            for g in config['whitelist'].split(','):
                self.decoder.insert_whitelist(int(g))

        if 'plot' not in config.keys():
            return

        self.sinks = []
        for plot in config['plot'].split(','):
            if plot == 'datascope':
                assert config['demod_type'] == 'fsk4'   ## datascope plot requires fsk4 demod type
                sink = eye_sink_f(sps=config['if_rate'] // self.symbol_rate)
                self.demod.connect_bb('symbol_filter', sink)
                self.kill_sink.append(sink)
            elif plot == 'symbol':
                sink = symbol_sink_f()
                self.demod.connect_float(sink)
                self.kill_sink.append(sink)
            elif plot == 'fft':
                assert config['demod_type'] == 'cqpsk'   ## fft plot requires cqpsk demod type
                i = len(self.sinks)
                self.sinks.append(fft_sink_c())
                self.demod.connect_complex('src', self.sinks[i])
                self.kill_sink.append(self.sinks[i])
            elif plot == 'mixer':
                assert config['demod_type'] == 'cqpsk'   ## mixer plot requires cqpsk demod type
                i = len(self.sinks)
                self.sinks.append(mixer_sink_c())
                self.demod.connect_complex('mixer', self.sinks[i])
                self.kill_sink.append(self.sinks[i])
            elif plot == 'constellation':
                i = len(self.sinks)
                assert config['demod_type'] == 'cqpsk'   ## constellation plot requires cqpsk demod type
                self.sinks.append(constellation_sink_c())
                self.demod.connect_complex('diffdec', self.sinks[i])
                self.kill_sink.append(self.sinks[i])
            elif plot == 'correlation':
                assert config['demod_type'] == 'fsk4'   ## correlation plot requires fsk4 demod type
                assert config['symbol_rate'] == 4800	## 4800 required for correlation plot
                sps=config['if_rate'] // self.symbol_rate
                sinks = setup_correlation(sps, self.name, self.demod.connect_bb)
                self.kill_sink += sinks
                self.sinks += sinks
            else:
                sys.stderr.write('unrecognized plot type %s\n' % plot)
                return

class du_queue_watcher(threading.Thread):
    def __init__(self, msgq,  callback, **kwds):
        threading.Thread.__init__ (self, **kwds)
        self.setDaemon(1)
        self.msgq = msgq
        self.callback = callback
        self.keep_running = True
        self.start()

    def run(self):
        while(self.keep_running):
            msg = self.msgq.delete_head()
            if not self.keep_running:
                break
            self.callback(msg)

class rx_block (gr.top_block):

    # Initialize the receiver
    #
    def __init__(self, verbosity, config):
        self.verbosity = verbosity
        gr.top_block.__init__(self)
        self.device_id_by_name = {}
        self.msgq = gr.msg_queue(10)
        self.configure_devices(config['devices'])
        self.configure_channels(config['channels'])
        self.du_q = du_queue_watcher(self.msgq, self.process_qmsg)

    def process_qmsg(self, msg):
        t = msg.type()
        s = msg.to_string()
        if t != -5:	# verify nxdn type
            return
        if isinstance(s[0], str):	# for python 2/3
            s = [ord(x) for x in s]
        msgtype = chr(s[0])
        lich = s[1]
        if self.verbosity > 2:
            sys.stderr.write ('process_qmsg: nxdn msg %s lich %x\n' % (msgtype, lich))
        if msgtype == 'c':	 # CAC type
            ran = s[2] & 0x3f
            msg = cac_message(s[2:])
            if msg['msg_type'] == 'CCH_INFO' and self.verbosity:
                sys.stderr.write ('%-10s %-10s system %d site %d ran %d\n' % (msg['cc1']/1e6, msg['cc2']/1e6, msg['location_id']['system'], msg['location_id']['site'], ran))
            if self.verbosity > 1:
                sys.stderr.write('%s\n' % json.dumps(msg))

    def configure_devices(self, config):
        self.devices = []
        for cfg in config:
            self.device_id_by_name[cfg['name']] = len(self.devices)
            self.devices.append(device(cfg, self))

    def find_device(self, chan):
        for dev in self.devices:
            if dev.args.startswith('audio:') and chan['demod_type'] == 'fsk4':
                return dev
            d = abs(chan['frequency'] - dev.frequency)
            nf = dev.sample_rate // 2
            if d + 6250 <= nf:
                return dev
        return None

    def configure_channels(self, config):
        self.channels = []
        for cfg in config:
            dev = self.find_device(cfg)
            if dev is None:
                sys.stderr.write('* * * Frequency %d not within spectrum band of any device - ignoring!\n' % cfg['frequency'])
                continue
            chan = channel(cfg, dev, self.verbosity, msgq=self.msgq)
            self.channels.append(chan)
            self.connect(dev.src, chan.demod, chan.decoder)
            if 'log_symbols' in cfg.keys():
                chan.logfile = blocks.file_sink(gr.sizeof_char, cfg['log_symbols'])
                self.connect(chan.demod, chan.logfile)

    def scan_channels(self):
        for chan in self.channels:
            sys.stderr.write('scan %s: error %d\n' % (chan.config['frequency'], chan.demod.get_freq_error()))

class rx_main(object):
    def __init__(self):
        self.keep_running = True

        # command line argument parsing
        parser = OptionParser(option_class=eng_option)
        parser.add_option("-c", "--config-file", type="string", default=None, help="specify config file name")
        parser.add_option("-v", "--verbosity", type="int", default=0, help="message debug level")
        parser.add_option("-p", "--pause", action="store_true", default=False, help="block on startup")
        (options, args) = parser.parse_args()

        # wait for gdb
        if options.pause:
            print ('Ready for GDB to attach (pid = %d)' % (os.getpid(),))
            raw_input("Press 'Enter' to continue...")

        if options.config_file == '-':
            config = json.loads(sys.stdin.read())
        else:
            config = json.loads(open(options.config_file).read())
        self.tb = rx_block(options.verbosity, config = byteify(config))
        sys.stderr.write('python version detected: %s\n' % sys.version)

    def run(self):
        try:
            self.tb.start()
            while self.keep_running:
                time.sleep(1)
        except:
            sys.stderr.write('main: exception occurred\n')
            sys.stderr.write('main: exception:\n%s\n' % traceback.format_exc())

if __name__ == "__main__":
    rx = rx_main()
    rx.run()
