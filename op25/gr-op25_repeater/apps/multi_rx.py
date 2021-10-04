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
import select
import traceback
import osmosdr

from gnuradio import audio, eng_notation, gr, gru, filter, blocks, fft, analog, digital
from gnuradio.eng_option import eng_option
from math import pi
from optparse import OptionParser

import trunking

import op25
import op25_repeater
import p25_demodulator
import p25_decoder
from sockaudio  import audio_thread

from sql_dbi import sql_dbi

from gr_gnuplot import constellation_sink_c
from gr_gnuplot import fft_sink_c
from gr_gnuplot import mixer_sink_c
from gr_gnuplot import symbol_sink_f
from gr_gnuplot import eye_sink_f
from gr_gnuplot import setup_correlation

from nxdn_trunking import cac_message

from terminal import op25_terminal

sys.path.append('tdma')
import lfsr

os.environ['IMBE'] = 'soft'

_def_symbol_rate = 4800
_def_interval = 3.0	# sec
_def_file_dir = '../www/images'
_def_audio_port = 23456		# udp port for audio thread
_def_audio_output = 'default'	# output device name for audio thread

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
        self.tunable = config['tunable']
        self.tb = tb
        self.frequency = 0

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

    def set_frequency(self, frequency):
        if frequency == self.frequency:
            return
        if not self.tunable:
            return
        self.frequency = frequency
        self.src.set_center_freq(frequency)

class channel(object):
    def __init__(self, config, dev, verbosity, msgq = None, process_msg=None, msgq_id=-1, role=''):
        sys.stderr.write('channel (dev %s): %s\n' % (dev.name, config))
        self.device = dev
        self.name = config['name']
        self.symbol_rate = _def_symbol_rate
        self.process_msg = process_msg
        self.role = role
        self.dev = ''
        self.sysid = []
        self.nac = []
        if 'symbol_rate' in config.keys():
            self.symbol_rate = config['symbol_rate']
        self.config = config
        self.verbosity = verbosity
        self.frequency = 0
        self.tdma_state = False
        self.xor_cache = {}

        self.tuning_error = 0
        self.freq_correction = 0
        self.error_band = 0
        self.last_error_update = 0
        self.last_set_freq_at = time.time()
        self.warned_frequencies = {}
        self.msgq_id = msgq_id
        self.next_band_change = time.time()

        self.audio_port = _def_audio_port
        self.audio_output = _def_audio_output
        self.audio_gain = 1.0
        if 'audio_gain' in config:
            self.audio_gain = float(config['audio_gain'])

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
        if msgq is not None:
            q = msgq
        else:
            q = gr.msg_queue(20)
        if 'decode' in config.keys() and config['decode'].startswith('p25_decoder'):
            num_ambe = 1
            (proto, wireshark_host, udp_port) = config['destination'].split(':') 
            assert proto == 'udp'
            wireshark_host = wireshark_host.replace('/', '')
            udp_port = int(udp_port)
            if role == 'vc':
                self.audio_port = udp_port
            if 'audio_output' in config.keys():
                self.audio_output = config['audio_output']

            self.decoder = p25_decoder.p25_decoder_sink_b(dest='audio', do_imbe=True, num_ambe=num_ambe, wireshark_host=wireshark_host, udp_port=udp_port, do_msgq = True, msgq=q, audio_output=self.audio_output, debug=verbosity, msgq_id=self.msgq_id)
        else:
            self.decoder = op25_repeater.frame_assembler(config['destination'], verbosity, q, self.msgq_id)

        if self.symbol_rate == 6000 and role == 'cc':
            sps = config['if_rate'] // self.symbol_rate
            self.demod.set_symbol_rate(self.symbol_rate)   # this and the foll. call should be merged?
            self.demod.clock.set_omega(float(sps))
            self.demod.clock.set_tdma(True)
            sys.stderr.write('initializing TDMA control channel %s channel ID %d\n' % (self.name, self.msgq_id))

        if self.process_msg is not None and msgq is None:
            self.q_watcher = du_queue_watcher(q, lambda msg: self.process_msg(msg, sender=self))

        self.kill_sink = []

        if 'blacklist' in config.keys():
            for g in config['blacklist'].split(','):
                self.decoder.insert_blacklist(int(g))

        if 'whitelist' in config.keys():
            for g in config['whitelist'].split(','):
                self.decoder.insert_whitelist(int(g))

        self.sinks = []
        if 'plot' not in config.keys():
            return

        for plot in config['plot'].split(','):
            if plot == 'datascope':
                assert config['demod_type'] == 'fsk4'   ## datascope plot requires fsk4 demod type
                sink = eye_sink_f(sps=config['if_rate'] // self.symbol_rate)
                sink.set_title(self.name)
                self.sinks.append(sink)
                self.demod.connect_bb('symbol_filter', sink)
                self.kill_sink.append(sink)
            elif plot == 'symbol':
                sink = symbol_sink_f()
                sink.set_title(self.name)
                self.sinks.append(sink)
                self.demod.connect_float(sink)
                self.kill_sink.append(sink)
            elif plot == 'fft':
                assert config['demod_type'] == 'cqpsk'   ## fft plot requires cqpsk demod type
                i = len(self.sinks)
                sink = fft_sink_c()
                sink.set_title(self.name)
                self.sinks.append(sink)
                self.demod.connect_complex('src', self.sinks[i])
                self.kill_sink.append(self.sinks[i])
            elif plot == 'mixer':
                assert config['demod_type'] == 'cqpsk'   ## mixer plot requires cqpsk demod type
                i = len(self.sinks)
                sink = mixer_sink_c()
                sink.set_title(self.name)
                self.sinks.append(sink)
                self.demod.connect_complex('mixer', self.sinks[i])
                self.kill_sink.append(self.sinks[i])
            elif plot == 'constellation':
                i = len(self.sinks)
                assert config['demod_type'] == 'cqpsk'   ## constellation plot requires cqpsk demod type
                sink = constellation_sink_c()
                sink.set_title(self.name)
                self.sinks.append(sink)
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

    def set_frequency(self, frequency):
        assert frequency
        if self.device.tunable:
            self.device.set_frequency(frequency)
        relative_freq = self.device.frequency + self.device.offset + self.tuning_error - frequency
        if (not self.device.tunable) and abs(relative_freq) > ((self.demod.input_rate / 2) - (self.demod.if1 / 2)):
            if frequency not in self.warned_frequencies:
                sys.stderr.write('warning: set frequency %f to non-tunable device %s rejected.\n' % (frequency / 1000000.0, self.device.name))
                self.warned_frequencies[frequency] = 0
            self.warned_frequencies[frequency] += 1
            #print 'set_relative_frequency: error, relative frequency %d exceeds limit %d' % (relative_freq, self.demod.input_rate/2)
            return False
        self.demod.set_relative_frequency(relative_freq)
        self.last_set_freq_at = time.time()
        self.frequency = frequency

    def error_tracking(self, last_change_freq):
        curr_time = time.time()
        if self.config['demod_type'] == 'fsk4':
            return None # todo: allow tracking in fsk4 demod
        UPDATE_TIME = 3
        if self.last_error_update + UPDATE_TIME > curr_time:
            return None
        self.last_error_update = time.time()
        if not self.demod.is_muted():
            band = self.demod.get_error_band()
            freq_error = self.demod.get_freq_error()
            if band and curr_time >= self.next_band_change:
                self.next_band_change = curr_time + 20.0
                self.error_band += band
                sys.stderr.write('channel %d set error band %d\n' % (self.msgq_id, self.error_band))
            self.freq_correction += freq_error * 0.15
            self.freq_correction = int(self.freq_correction)
            if self.freq_correction > 600:
                self.freq_correction -= 1200
                self.error_band += 1
            elif self.freq_correction < -600:
                self.freq_correction += 1200
                self.error_band -= 1
            self.error_band = min(self.error_band, 2)
            self.error_band = max(self.error_band, -2)
            self.tuning_error = int(self.error_band * 1200 + self.freq_correction)
            e = 0
            if last_change_freq > 0:
                e = (self.tuning_error*1e6) / float(last_change_freq)
        else:
            e = 0
            freq_error = 0
            band = 0
        ### self.set_frequency(self.frequency)	# adjust relative frequency with updated tuning_error
        if self.verbosity >= 10:
            sys.stderr.write('%f\terror_tracking\t%s\t%d\t%d\t%d\t%d\t%d\t%f\n' % (curr_time, self.name, self.msgq_id, freq_error, self.error_band, self.tuning_error, self.freq_correction, e))
        d = {'time':   time.time(), 'json_type': 'freq_error_tracking', 'name': self.name, 'device': self.device.name, 'freq_error': freq_error, 'band': band, 'error_band': self.error_band, 'tuning_error': self.tuning_error, 'freq_correction': self.freq_correction}
        if self.frequency:
            self.set_frequency(self.frequency)
        return d

    def configure_tdma(self, params):
        set_tdma = False
        if params['tdma'] is not None:
            set_tdma = True
            self.decoder.set_slotid(params['tdma'])
        self.demod.clock.set_tdma(set_tdma)
        if set_tdma == self.tdma_state:
            return	# already in desired state
        self.tdma_state = set_tdma
        if set_tdma:
            hash = '%x%x%x' % (params['nac'], params['sysid'], params['wacn'])
            if hash not in self.xor_cache:
                self.xor_cache[hash] = lfsr.p25p2_lfsr(params['nac'], params['sysid'], params['wacn']).xor_chars
            self.decoder.set_xormask(self.xor_cache[hash], hash)
            self.decoder.set_nac(params['nac'])
            rate = 6000
        else:
            rate = 4800
        sps = self.config['if_rate'] / rate
        self.demod.set_symbol_rate(rate)   # this and the foll. call should be merged?
        self.demod.clock.set_omega(float(sps))

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
    def __init__(self, verbosity, config, trunk_conf_file=None, terminal_type=None, track_errors=False, udp_player=None):
        self.verbosity = verbosity
        gr.top_block.__init__(self)
        self.device_id_by_name = {}
        self.msg_types = {}
        self.terminal_type = terminal_type
        self.last_process_update = 0
        self.last_freq_params = {'freq' : 0.0, 'tgid' : None, 'tag' : "", 'tdma' : None}
        self.trunk_rx = None
        self.track_errors = track_errors
        self.last_change_freq = 0
        self.sql_db = sql_dbi()
        self.input_q = gr.msg_queue(20)
        self.output_q = gr.msg_queue(20)
        self.last_voice_channel_id = 0
        self.terminal = op25_terminal(self.input_q, self.output_q, terminal_type)
        self.configure_devices(config['devices'])
        self.configure_channels(config['channels'])
        if trunk_conf_file:
            self.trunk_rx = trunking.rx_ctl(frequency_set = self.change_freq, debug = self.verbosity, conf_file = trunk_conf_file, logfile_workers=[], send_event=self.send_event)
        self.sinks = []
        for chan in self.channels:
            if len(chan.sinks):
                self.sinks += chan.sinks
        if self.is_http_term():
            for sink in self.sinks:
                sink.gnuplot.set_interval(_def_interval)
                sink.gnuplot.set_output_dir(_def_file_dir)

        if udp_player:
            chan = self.find_audio_channel()	# find chan used for audio
            self.audio = audio_thread("127.0.0.1", chan.audio_port, chan.audio_output, False, chan.audio_gain)
        else:
            self.audio = None

    def find_channel_cc(self, params):
        channels = []
        for chan in self.channels:
            if chan.role != 'cc':
                continue
            if len(chan.nac) and params['nac'] not in chan.nac:
                continue
            if len(chan.sysid) and params['sysid'] not in chan.sysid:
                continue
            channels.append(chan)
            if self.verbosity > 0:
                sys.stderr.write('%f find_channel_cc: selected channel %d (%s) for tuning request type %s frequency %f\n' % (time.time(), chan.msgq_id, chan.name, 'cc', params['freq'] / 1000000.0))
        return channels

    def find_channel_vc(self, params):
        channels = []
        for chan in self.channels:   # pass1 - search for vc on non-tunable dev having frequency within band
            if chan.role != 'vc':
                continue
            if chan.device.tunable:
                continue
            if abs(params['freq'] - chan.device.frequency) >= chan.demod.relative_limit:
                #sys.stderr.write('%f skipping channel %d frequency %f dev freq %f limit %f\n' % (time.time(), chan.msgq_id, params['freq'] / 1000000.0, chan.device.frequency / 1000000.0, chan.demod.relative_limit / 1000000.0))
                continue
            channels.append(chan)
            if self.verbosity > 0:
                sys.stderr.write('%f find_channel_vc: selected channel %d (%s) for tuning request type %s frequency %f (1)\n' % (time.time(), chan.msgq_id, chan.name, 'vc', params['freq'] / 1000000.0))
            return channels
        for chan in self.channels:   # pass2 - search for vc on tunable dev
            if chan.role != 'vc':
                continue
            if not chan.device.tunable:
                continue
            channels.append(chan)
            if self.verbosity > 0:
                sys.stderr.write('%f find_channel_vc: selected channel %d (%s) for tuning request type %s frequency %f (2)\n' % (time.time(), chan.msgq_id, chan.name, 'vc', params['freq'] / 1000000.0))
            return channels
        return [] # pass 1 and 2 failed

    def do_error_tracking(self):
        if not self.track_errors:
            return
        for chan in self.channels:
            d = chan.error_tracking(self.last_change_freq)
            if d is not None and not self.input_q.full_p():
                msg = gr.message().make_from_string(json.dumps(d), -4, 0, 0)
                self.input_q.insert_tail(msg)

    def change_freq(self, params):
        self.last_freq_params = params
        freq = params['freq']
        self.last_change_freq = freq
        channel_type = params['channel_type']	# vc or cc
        if channel_type == 'vc':
            channels = self.find_channel_vc(params)
        elif channel_type == 'cc':
            channels = self.find_channel_cc(params)
        else:
            raise ValueError('change_freq: invalid channel_type: %s' % channel_type)
        if len(channels) == 0:
            sys.stderr.write('change_freq: no channel(s) found for %s frequency %f\n' % (channel_type, freq/1000000.0))
            return
        for chan in channels:
            chan.device.set_frequency(freq)
            chan.set_frequency(freq)
            chan.configure_tdma(params)
            self.freq_update()
            if channel_type == 'vc':
                self.last_voice_channel_id = chan.msgq_id
        #return
        if self.trunk_rx is None:
            return
        voice_chans = [chan for chan in self.channels if chan.role == 'vc']
        voice_state = channel_type == 'vc'
        # FIXME: fsk4 case needs work/testing
        for chan in voice_chans:
            if voice_state and chan.msgq_id == self.last_voice_channel_id:
                chan.demod.set_muted(False)
            else:
                chan.demod.set_muted(True)

    def is_http_term(self):
        if self.terminal_type.startswith('http:'):
            return True
        else:
            return False

    def process_terminal_msg(self, msg):
        # return true = end top block
        RX_COMMANDS = 'skip lockout hold'.split()
        s = msg.to_string()
        t = msg.type()
        if t == -4:
            d = json.loads(s)
            s = d['command']
        if type(s) is not str and isinstance(s, bytes):
            # should only get here if python3
            s = s.decode()
        if s == 'quit': return True
        elif s == 'update':	## deprecated here: to be removed
            pass
            # self.process_update()
        elif s == 'set_freq':
            sys.stderr.write('set_freq not supported\n')
            return
            #freq = msg.arg1()
            #self.last_freq_params['freq'] = freq
            #self.set_freq(freq)
        elif s == 'adj_tune':
            freq = msg.arg1()
        elif s == 'dump_tgids':
            self.trunk_rx.dump_tgids()
        elif s == 'reload_tags':
            nac = msg.arg1()
            self.trunk_rx.reload_tags(int(nac))
        elif s == 'add_default_config':
            nac = msg.arg1()
            self.trunk_rx.add_default_config(int(nac))
        elif s in RX_COMMANDS:
            if self.trunk_rx is not None:
                self.trunk_rx.process_qmsg(msg)
        elif s == 'settings-enable' and self.trunk_rx is not None:
            self.trunk_rx.enable_status(d['data'])
        return False

    def process_ajax(self):
        if not self.is_http_term():
            return
        if self.input_q.full_p():
            return
        filenames = [sink.gnuplot.filename for sink in self.sinks if sink.gnuplot.filename]
        error = []
        for chan in self.channels:
            if hasattr(chan.demod, 'get_freq_error'):
                error.append(chan.demod.get_freq_error())
        d = {'json_type': 'rx_update', 'error': error, 'files': filenames, 'time': time.time()}
        msg = gr.message().make_from_string(json.dumps(d), -4, 0, 0)
        self.input_q.insert_tail(msg)

    def process_update(self):
        UPDATE_INTERVAL = 1.0	# sec.
        now = time.time()
        if now < self.last_process_update + UPDATE_INTERVAL:
            return
        self.last_process_update = now
        self.freq_update()
        if self.input_q.full_p():
            return
        if self.trunk_rx is None:
            return ## possible race cond - just ignore
        js = self.trunk_rx.to_json()
        msg = gr.message().make_from_string(js, -4, 0, 0)
        self.input_q.insert_tail(msg)
        self.process_ajax()

    def send_event(self, d):	## called from trunking module to send json msgs / updates to client
        if d is not None:
            self.sql_db.event(d)
        if d and not self.input_q.full_p():
            msg = gr.message().make_from_string(json.dumps(d), -4, 0, 0)
            self.input_q.insert_tail(msg)
        self.process_update()

    def freq_update(self):
        if self.input_q.full_p():
            return
        params = self.last_freq_params
        params['json_type'] = 'change_freq'
        params['current_time'] = time.time()
        js = json.dumps(params)
        msg = gr.message().make_from_string(js, -4, 0, 0)
        self.input_q.insert_tail(msg)

    def process_msg(self, msg):
        mtype = msg.type()
        if mtype == -2 or mtype == -4:
            self.process_terminal_msg(msg)
        else:
            self.process_channel_msg(msg, mtype)

    def process_channel_msg(self, msg, mtype):
        msgtext = msg.to_string()
        aa55 = trunking.get_ordinals(msgtext[:2])
        assert aa55 == 0xaa55
        msgq_id = trunking.get_ordinals(msgtext[2:4])
        msgtext = msgtext[4:]
        if mtype == -5:
            self.process_nxdn_msg(msgtext)
        else:
            self.process_trunked_qmsg(msg, msgq_id)

    def process_nxdn_msg(self, s):
        if isinstance(s[0], str):	# for python 2/3
            s = [ord(x) for x in s]
        msgtype = chr(s[0])
        lich = s[1]
        if self.verbosity > 2:
            sys.stderr.write ('process_nxdn_msg %s lich %x\n' % (msgtype, lich))
        if msgtype == 'c':	 # CAC type
            ran = s[2] & 0x3f
            msg = cac_message(s[2:])
            if msg['msg_type'] == 'CCH_INFO' and self.verbosity:
                sys.stderr.write ('%-10s %-10s system %d site %d ran %d\n' % (msg['cc1']/1e6, msg['cc2']/1e6, msg['location_id']['system'], msg['location_id']['site'], ran))
            if self.verbosity > 1:
                sys.stderr.write('%s\n' % json.dumps(msg))

    def filtered(self, msg, msgq_id):
        # return True if msg should be suppressed
        chan = self.channels[msgq_id-1]
        t = msg.type()
        if chan.role == 'vc' and t in [7, 12]:	## suppress tsbk/mbt/pdu received over vc
            return True
        return False

    def process_trunked_qmsg(self, msg, msgq_id):	# p25 trunked message
        if self.trunk_rx is None:
            return
        if self.filtered(msg, msgq_id):
            return
        self.trunk_rx.process_qmsg(msg)
        self.trunk_rx.parallel_hunt_cc()
        self.do_error_tracking()

    def configure_devices(self, config):
        self.devices = []
        for cfg in config:
            self.device_id_by_name[cfg['name']] = len(self.devices)
            self.devices.append(device(cfg, self))

    def find_trunked_device(self, chan, requested_dev):
        if len(self.devices) == 1:	# single SDR 
            return self.devices[0]
        for dev in self.devices:
            if dev.name == requested_dev:
                return dev
        return None

    def find_device(self, chan, requested_dev):
        if 'decode' in chan.keys() and chan['decode'].startswith('p25_decoder'):
            return self.find_trunked_device(chan, requested_dev)
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
            decode_d = {'role': '', 'dev': ''}
            if 'decode' in cfg.keys() and cfg['decode'].startswith('p25_decoder'):
                decode_p = cfg['decode'].split(':')[1:]
                for p in decode_p:	# possible keys: dev, role, nac, sysid; valid roles: cc vc
                    (k, v) = p.split('=')
                    if k == 'nac' or k == 'sysid':
                        v = [int(x, base=0) for x in v.split(',')]
                    decode_d[k] = v
            dev = self.find_device(cfg, decode_d['dev'])
            if dev is None:
                sys.stderr.write('* * * No device found for channel %s- ignoring!\n' % cfg['name'])
                continue
            msgq_id = len(self.channels) + 1
            chan = channel(cfg, dev, self.verbosity, msgq=self.output_q, msgq_id = msgq_id, role=decode_d['role'])
            for k in decode_d.keys():
                setattr(chan, k, decode_d[k])
            self.channels.append(chan)
            self.connect(dev.src, chan.demod, chan.decoder)
            sys.stderr.write('assigning channel "%s" (channel id %d) to device "%s"\n' % (chan.name, chan.msgq_id, dev.name))
            if 'log_if' in cfg.keys():
                chan.logfile_if = blocks.file_sink(gr.sizeof_gr_complex, 'if-%d-%s' % (chan.config['if_rate'], cfg['log_if']))
                chan.demod.connect_complex('agc', chan.logfile_if)
            if 'log_symbols' in cfg.keys():
                chan.logfile = blocks.file_sink(gr.sizeof_char, cfg['log_symbols'])
                self.connect(chan.demod, chan.logfile)

    def find_audio_channel(self):
        for chan in self.channels:	# pass1 - look for 'vc'
            if chan.role == 'vc' and chan.audio_port:
                return chan
        for chan in self.channels:	# pass2 - any chan with audio port specified
            if chan.audio_port:
                return chan
        return self.channels[0]

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
        parser.add_option("-M", "--monitor-stdin", action="store_false", default=True, help="enable press ENTER to quit")
        parser.add_option("-T", "--trunk-conf-file", type="string", default=None, help="trunking config file name")
        parser.add_option("-l", "--terminal-type", type="string", default="curses", help="'curses' or udp port or 'http:host:port'")
        parser.add_option("-X", "--freq-error-tracking", action="store_true", default=False, help="enable experimental frequency error tracking")
        parser.add_option("-U", "--udp-player", action="store_true", default=False, help="enable built-in udp audio player")
        (options, args) = parser.parse_args()

        self.options = options

        # wait for gdb
        if options.pause:
            print ('Ready for GDB to attach (pid = %d)' % (os.getpid(),))
            raw_input("Press 'Enter' to continue...")

        if options.config_file == '-':
            config = json.loads(sys.stdin.read())
        else:
            config = json.loads(open(options.config_file).read())
        self.tb = rx_block(options.verbosity, config = byteify(config), trunk_conf_file=options.trunk_conf_file, terminal_type=options.terminal_type, track_errors=options.freq_error_tracking, udp_player = options.udp_player)
        sys.stderr.write('python version detected: %s\n' % sys.version)
        sys.stderr.flush()

    def run(self):
        self.tb.start()
        if self.options.monitor_stdin:
            print("Running. press ENTER to quit")
        while self.keep_running:
                if self.options.monitor_stdin and select.select([sys.stdin,],[],[],0.0)[0]:
                    c = sys.stdin.read(1)
                    self.keep_running = False
                    break
                msg = self.tb.output_q.delete_head()
                if self.tb.process_msg(msg):
                    self.keep_running = False
                    break
        print('Quitting - now stopping top block')
        self.tb.stop()

if __name__ == "__main__":
    rx = rx_main()
    try:
        rx.run()
    except KeyboardInterrupt:
        rx.keep_running = False
    print('Program ending')
    time.sleep(1)
