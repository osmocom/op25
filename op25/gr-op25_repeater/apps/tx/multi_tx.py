#!/usr/bin/env python

#################################################################################
# 
# Multiprotocol Digital Voice TX (C) Copyright 2017, 2018, 2019, 2020 Max H. Parke KA1RBI
# 
# This file is part of OP25
# 
# This is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this software; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
#################################################################################


"""
Transmit M simultaneous RF channels via N devices
"""

import sys
import os
import math
import json
from gnuradio import gr, gru, audio, eng_notation
from gnuradio import filter, blocks, analog, digital
from gnuradio.eng_option import eng_option
from optparse import OptionParser

import osmosdr
import op25
import op25_repeater

from math import pi

from op25_c4fm_mod import p25_mod_bf

_def_symbol_rate = 4800
_def_bt = 0.5

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

class pipeline_sb(gr.hier_block2):
    def __init__(self, protocol=None, config_file=None, gain_adjust=None, verbose=0, fullrate_mode=False, alt_input=None):
        gr.hier_block2.__init__(self, "dv_encoder",
            gr.io_signature(1, 1, gr.sizeof_short),       # Input signature
            gr.io_signature(1, 1, gr.sizeof_char))  # Output signature

        if protocol == 'dmr':
            assert config_file
            ENCODER  = op25_repeater.ambe_encoder_sb(verbose)
            ENCODER2 = op25_repeater.ambe_encoder_sb(verbose)
            ENCODER2.set_gain_adjust(gain_adjust)
            DMR = op25_repeater.dmr_bs_tx_bb(verbose, config_file)
            self.connect(self, ENCODER, (DMR, 0))
            if not alt_input:
                alt_input = self
            self.connect(alt_input, ENCODER2, (DMR, 1))
        elif protocol == 'dstar':
            assert config_file
            ENCODER = op25_repeater.dstar_tx_sb(verbose, config_file)
        elif protocol == 'p25':
            ENCODER = op25_repeater.vocoder(True,		# 0=Decode,True=Encode
                                  False,	# Verbose flag
                                  0,	# flex amount
                                  "",			# udp ip address
                                  0,			# udp port
                                  False) 		# dump raw u vectors
        elif protocol == 'ysf':
            assert config_file
            ENCODER = op25_repeater.ysf_tx_sb(verbose, config_file, fullrate_mode)
        elif protocol.startswith('nxdn'):
            assert config_file
            ENCODER = op25_repeater.nxdn_tx_sb(verbose, config_file, protocol == 'nxdn96')
        ENCODER.set_gain_adjust(gain_adjust)
        if protocol == 'dmr':
            self.connect(DMR, self)
        else:
            self.connect(self, ENCODER, self)

class mod_pipeline_bc(gr.hier_block2):
    def __init__(self, protocol=None, mod_adjust=None, output_gain=None, if_freq=0, if_rate=0, verbose=0, sample_rate=0, bt=0):
        from dv_tx import RC_FILTER
        gr.hier_block2.__init__(self, "dv_modulator",
            gr.io_signature(1, 1, gr.sizeof_char),       # Input signature
            gr.io_signature(1, 1, gr.sizeof_gr_complex))  # Output signature
        MOD = p25_mod_bf(output_sample_rate = sample_rate, dstar = (protocol == 'dstar'), bt = bt, rc = RC_FILTER[protocol])

        AMP = blocks.multiply_const_ff(output_gain)

        max_dev = 12.5e3
        k = 2 * math.pi * max_dev / if_rate

        FM_MOD = analog.frequency_modulator_fc (k * mod_adjust)

        INTERP = filter.rational_resampler_fff(if_rate // sample_rate, 1)

        MIXER = blocks.multiply_cc()
        LO = analog.sig_source_c(if_rate, analog.GR_SIN_WAVE, if_freq, 1.0, 0)

        self.connect(self, MOD, AMP, INTERP, FM_MOD, (MIXER, 0))
        self.connect(LO, (MIXER, 1))
        self.connect(MIXER, self)

class device(object):
    def __init__(self, config, tb):
        self.name = config['name']
        self.sample_rate = config['rate']
        self.args = config['args']
        self.frequency = config['frequency']
        self.tb = tb
        self.sum = blocks.add_cc()
        self.sum_count = 0
        self.output_throttle = None

    def get_sum_p(self):
        seq = self.sum_count
        self.sum_count += 1
        return (self.sum, seq)

class channel(object):
    def __init__(self, config, dev, verbosity, msgq = None):
        sys.stderr.write('channel (dev %s): %s\n' % (dev.name, config))
        self.device = dev
        self.name = config['name']
        self.symbol_rate = _def_symbol_rate
        if 'symbol_rate' in config.keys():
            self.symbol_rate = config['symbol_rate']
        self.config = config

def get_protocol(chan):
    # try to autodetect protocol, return None if failed
    if chan.config['filter_type'].startswith('nxdn'):
        if chan.symbol_rate == 2400:
            return 'nxdn48'
        else:
            return 'nxdn96'
    elif chan.config['filter_type'] == 'rc':
        return 'p25'
    elif chan.config['filter_type'] == 'gmsk':
        return 'dstar'
    elif chan.config['filter_type'] != 'rrc':
        return None
    if 'dmr' in chan.config['name'].lower():
        return 'dmr'
    if 'ysf' in chan.config['name'].lower():
        return 'ysf'
    return None

def get_source(config, k, audio_source):
    if k not in config.keys():
        return None
    s = config[k]
    if s.startswith('audio:'):
        return audio_source
    elif s.startswith('udp:'):	# S16_LE at 8000 rate 
        hostinfo = s.split(':')
        hostname = hostinfo[1]
        udp_port = int(hostinfo[2])
        bufsize = 32000
        return blocks.udp_source(gr.sizeof_short, hostname, udp_port, payload_size = bufsize)
    else:
        return blocks.file_source(gr.sizeof_short, s, repeat =  True)

class tx_block(gr.top_block):
    def __init__(self, verbosity, config):
        self.verbosity = verbosity
        gr.top_block.__init__(self)

        self.configure_devices(config['devices'])
        self.configure_channels(config['channels'])

        audio_chans = [chan for chan in self.channels if chan.config['source'].startswith('audio:')]
        if len(audio_chans):
            AUDIO = audio.source(options.alsa_rate, options.audio_input)
            lpf_taps = filter.firdes.low_pass(1.0, options.alsa_rate, 3400.0, 3400 * 0.1, filter.firdes.WIN_HANN)
            audio_rate = 8000
            AUDIO_DECIM = filter.fir_filter_fff (int(options.alsa_rate / audio_rate), lpf_taps)
            AUDIO_SCALE = blocks.multiply_const_ff(32767.0 * options.gain)
            AUDIO_F2S = blocks.float_to_short()
            self.connect(AUDIO, AUDIO_DECIM, AUDIO_SCALE, AUDIO_F2S)
            audio_source = AUDIO_F2S
        else:
            audio_source = None

        from dv_tx import output_gains, gain_adjust, gain_adjust_fullrate, mod_adjust

        for chan in self.channels:
            protocol = get_protocol(chan)
            if protocol is None:
                sys.stderr.write('failed to detect protocol, ignoring: %s\n' % (cfg))
                continue
            cfg = chan.config
            dev = chan.device
            modulator_rate = 24000	## FIXME
            bt = _def_bt
            if 'bt' in cfg.keys():
                bt = cfg['bt']
            MOD = mod_pipeline_bc(
                protocol = protocol,
                output_gain = output_gains[protocol],
                mod_adjust = mod_adjust[protocol],
                if_freq = cfg['frequency'] - dev.frequency,
                if_rate = dev.sample_rate,
                sample_rate = modulator_rate,
                bt = bt)
            if cfg['source'].startswith('symbols:'):
                filename = cfg['source'].split(':')[1]
                source = blocks.file_source(gr.sizeof_char, filename, repeat=True)
                self.connect(source, MOD, dev.get_sum_p())
            else:
                source = get_source(cfg, 'source', audio_source)
                source2 = get_source(cfg, 'source2', audio_source)
                fullrate_mode = False	### TODO
                if (fullrate_mode and protocol == 'ysf') or protocol == 'p25':
                    gain_adj = gain_adjust_fullrate[protocol]
                else:
                    gain_adj = gain_adjust[protocol]
                cfgfile = None
                if protocol in 'dmr ysf dstar'.split():
                    cfgfile = '%s-cfg.dat' % (protocol)
                elif protocol.startswith('nxdn'):
                    cfgfile = 'nxdn-cfg.dat'
                CHANNEL = pipeline_sb(
                    protocol = protocol,
                    gain_adjust = gain_adj,
                    fullrate_mode = fullrate_mode,
                    alt_input = source2,
                    verbose = self.verbosity,
                    config_file = cfgfile)
                self.connect(source, CHANNEL, MOD, dev.get_sum_p())
        for dev in self.devices:
            assert dev.sum_count > 0	# device must have at least one valid channel
            dev.amp = blocks.multiply_const_cc(1.0 / float(dev.sum_count))
            if dev.output_throttle is not None:
                self.connect(dev.sum, dev.amp, dev.output_throttle, dev.u)
            else:
                self.connect(dev.sum, dev.amp, dev.u)

    def configure_devices(self, config):
        self.devices = []
        for cfg in config:
            dev = device(cfg, self)
            if cfg['args'].startswith('udp:'):
                self.setup_udp_output(dev, cfg)
            else:
                self.setup_sdr_output(dev, cfg)
            self.devices.append(dev)

    def find_device(self, chan):
        for dev in self.devices:
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
            chan = channel(cfg, dev, self.verbosity, msgq=None)
            self.channels.append(chan)

    def setup_udp_output(self, dev, config):
        dev.output_throttle = blocks.throttle(gr.sizeof_gr_complex, config['rate'])
        hostinfo = config['args'].split(':')
        hostname = hostinfo[1]
        udp_port = int(hostinfo[2])
        dev.u = blocks.udp_sink(gr.sizeof_gr_complex, hostname, udp_port)

    def setup_sdr_output(self, dev, config):
        dev.u = osmosdr.sink (config['args'])
        gain_names = dev.u.get_gain_names()
        for name in gain_names:
            range = dev.u.get_gain_range(name)
            print ("gain: name: %s range: start %d stop %d step %d" % (name, range[0].start(), range[0].stop(), range[0].step()))
        if config['gains']:
            for t in config['gains'].split(","):
                name, gain = t.split(":")
                gain = int(gain)
                print ("setting gain %s to %d" % (name, gain))
                dev.u.set_gain(gain, name)

        print ('setting sample rate %d' % config['rate'])
        dev.u.set_sample_rate(config['rate'])
        print ('setting SDR tuning frequency %d' % config['frequency'])
        dev.u.set_center_freq(config['frequency'])
        dev.u.set_freq_corr(config['ppm'])

class tx_main(object):
    def __init__(self):
        parser = OptionParser(option_class=eng_option)

        parser.add_option("-c", "--config-file", type="string", default=None, help="specify config file name")
        parser.add_option("-v", "--verbosity", type="int", default=0, help="additional output")
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
        self.tb = tx_block(options.verbosity, config = byteify(config))

    def run(self):
        try:
            self.tb.run()
        except KeyboardInterrupt:
            self.tb.stop()

if __name__ == "__main__":
    print ('Multiprotocol Digital Voice TX (C) Copyright 2017-2020 Max H. Parke KA1RBI')
    tx = tx_main()
    tx.run()
