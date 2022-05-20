#
# Copyright 2005,2006,2007 Free Software Foundation, Inc.
#
# OP25 Demodulator Block
# Copyright 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020 Max H. Parke KA1RBI
# 
# This file is part of GNU Radio and part of OP25
# 
# This is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# It is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
# 

"""
P25 C4FM/CQPSK demodulation block.
"""

import sys
from gnuradio import gr, eng_notation
from gnuradio import filter, analog, digital, blocks
from gnuradio.eng_option import eng_option
import op25
import op25_repeater
from math import pi

sys.path.append('tx')
import op25_c4fm_mod

# default values (used in __init__ and add_options)
_def_output_sample_rate = 48000
_def_if_rate = 24000
_def_gain_mu = 0.025
_def_costas_alpha = 0.04
_def_symbol_rate = 4800
_def_symbol_deviation = 600.0
_def_bb_gain = 1.0
_def_excess_bw = 0.2

_def_gmsk_mu = None
_def_mu = 0.5
_def_freq_error = 0.0
_def_omega_relative_limit = 0.005

# /////////////////////////////////////////////////////////////////////////////
#                           demodulator
# /////////////////////////////////////////////////////////////////////////////

def get_decim(speed):
	s = int(speed)
	if_freqs = [24000, 25000, 32000]
	for i_f in if_freqs:
		if s % i_f != 0:
			continue
		q = s // i_f
		if q & 1:
			continue
		if q >= 40 and q & 3 == 0:
			decim = q//4
			decim2 = 4
		else:
			decim = q//2
			decim2 = 2
		return decim, decim2
	return None

class p25_demod_base(gr.hier_block2):
    def __init__(self,
                 if_rate	= None,
                 filter_type	= None,
                 excess_bw      = _def_excess_bw,
                 symbol_rate	= _def_symbol_rate):
        """
	Hierarchical block for P25 demodulation base class

        @param if_rate: sample rate of complex input channel
        @type if_rate: int
	"""
        self.if_rate = if_rate
        self.symbol_rate = symbol_rate
        self.bb_sinks = []

        self.baseband_amp = blocks.multiply_const_ff(_def_bb_gain)
        coeffs = op25_c4fm_mod.c4fm_taps(sample_rate=self.if_rate, span=9, generator=op25_c4fm_mod.transfer_function_rx).generate()
        sps = self.if_rate // self.symbol_rate
        if filter_type == 'rrc':
            ntaps = 7 * sps
            if ntaps & 1 == 0:
                ntaps += 1
            coeffs = filter.firdes.root_raised_cosine(1.0, if_rate, symbol_rate, excess_bw, ntaps)
            coeffs = [x*1.5 for x in coeffs]
        if filter_type == 'nxdn':
            coeffs = op25_c4fm_mod.c4fm_taps(sample_rate=self.if_rate, span=9, generator=op25_c4fm_mod.transfer_function_nxdn, symbol_rate=self.symbol_rate).generate()
            gain_adj = 1.8	# for nxdn48 6.25 KHz
            if self.symbol_rate == 4800:
               gain_adj = 0.77	# nxdn96 12.5 KHz
            coeffs = coeffs * gain_adj
        if filter_type == 'gmsk':
            # lifted from gmsk.py
            _omega = sps
            _gain_mu = _def_gmsk_mu
            _mu = _def_mu
            if not _gain_mu:
                _gain_mu = 0.175
            _gain_omega = .25 * _gain_mu * _gain_mu        # critically damped
            self.symbol_filter = blocks.multiply_const_ff(1.0)
            self.fsk4_demod = digital.clock_recovery_mm_ff(_omega, _gain_omega,
                                                           _mu, _gain_mu,
                                                           _def_omega_relative_limit)
            self.slicer = digital.binary_slicer_fb()
        elif filter_type == 'fsk4mm':
            self.symbol_filter = filter.fir_filter_fff(1, coeffs)
            _omega = sps
            _gain_mu = _def_gmsk_mu
            _mu = _def_mu
            if not _gain_mu:
                _gain_mu = 0.0175
            _gain_omega = .25 * _gain_mu * _gain_mu        # critically damped
            self.fsk4_demod = digital.clock_recovery_mm_ff(_omega, _gain_omega,
                                                           _mu, _gain_mu,
                                                           _def_omega_relative_limit)
            levels = [ -2.0, 0.0, 2.0, 4.0 ]
            self.slicer = op25_repeater.fsk4_slicer_fb(levels)
        else:
            self.symbol_filter = filter.fir_filter_fff(1, coeffs)
            autotuneq = gr.msg_queue(2)
            self.fsk4_demod = op25.fsk4_demod_ff(autotuneq, self.if_rate, self.symbol_rate)
            levels = [ -2.0, 0.0, 2.0, 4.0 ]
            self.slicer = op25_repeater.fsk4_slicer_fb(levels)

    def set_symbol_rate(self, rate):
        self.symbol_rate = rate

    def set_baseband_gain(self, k):
        self.baseband_amp.set_k(k)

    def disconnect_bb(self):
        # assumes lock held or init
        if not len(self.bb_sinks):
            return
        for t in self.bb_sinks:
            self.disconnect(t[0], t[1])
        self.bb_sinks = []

    def connect_bb(self, src, sink):
        # assumes lock held or init
        if src == 'symbol_filter':
            b = self.symbol_filter
        elif src == 'baseband_amp':
            b = self.baseband_amp
        self.connect(b, sink)
        self.bb_sinks.append([b, sink])

class p25_demod_fb(p25_demod_base):

    def __init__(self,
                 input_rate	= None,
                 filter_type	= None,
                 excess_bw      = _def_excess_bw,
                 if_rate        = _def_if_rate,
                 symbol_rate	= _def_symbol_rate):
        """
	Hierarchical block for P25 demodulation.

	The float input is fsk4-demodulated
        @param input_rate: sample rate of complex input channel
        @type input_rate: int
	"""

        gr.hier_block2.__init__(self, "p25_demod_fb",
				gr.io_signature(1, 1, gr.sizeof_float),       # Input signature
				gr.io_signature(1, 1, gr.sizeof_char)) # Output signature

        p25_demod_base.__init__(self, if_rate=if_rate, symbol_rate=symbol_rate, filter_type=filter_type)

        self.input_rate = input_rate
        self.if_rate = if_rate
        self.float_sink = None
        if input_rate != if_rate:
            assert if_rate < input_rate
            assert input_rate % if_rate == 0	### input rate must be multiple of if rate
            decim = input_rate // if_rate
            maxf = min(if_rate // 2, 6000)	### lpf cutoff at most 6 KHz
            lpf_coeffs = filter.firdes.low_pass(1.0, input_rate, maxf, maxf//8, filter.firdes.WIN_HAMMING)
            self.bb_decim = filter.fir_filter_fff(decim,  lpf_coeffs)
            self.connect(self, self.bb_decim, self.baseband_amp, self.symbol_filter, self.fsk4_demod, self.slicer, self)
        else:
            self.connect(self, self.baseband_amp, self.symbol_filter, self.fsk4_demod, self.slicer, self)

    def disconnect_float(self):
        # assumes lock held or init
        if not self.float_sink:
            return
        self.disconnect(self.float_sink[0], self.float_sink[1])
        self.float_sink = None

    def connect_float(self, sink):
        # assumes lock held or init
        self.disconnect_float()
        self.connect(self.fsk4_demod, sink)
        self.float_sink = [self.fsk4_demod, sink]

class p25_demod_cb(p25_demod_base):

    def __init__(self,
                 input_rate	= None,
                 demod_type	= 'cqpsk',
                 filter_type	= None,
                 excess_bw      = _def_excess_bw,
                 relative_freq	= 0,
                 offset		= 0,
                 if_rate	= _def_if_rate,
                 gain_mu	= _def_gain_mu,
                 costas_alpha	= _def_costas_alpha,
                 symbol_rate	= _def_symbol_rate,
                 use_old_decim	= False):
        """
	Hierarchical block for P25 demodulation.

	The complex input is tuned, decimated and demodulated
        @param input_rate: sample rate of complex input channel
        @type input_rate: int
	"""

        gr.hier_block2.__init__(self, "p25_demod_cb",
				gr.io_signature(1, 1, gr.sizeof_gr_complex),       # Input signature
				gr.io_signature(1, 1, gr.sizeof_char)) # Output signature
#				gr.io_signature(0, 0, 0)) # Output signature
        p25_demod_base.__init__(self, if_rate=if_rate, symbol_rate=symbol_rate, filter_type=filter_type)

        self.input_rate = input_rate
        self.if_rate = if_rate
        self.symbol_rate = symbol_rate
        self.connect_state = None
        self.offset = 0
        self.sps = 0.0
        self.lo_freq = 0
        self.float_sink = None
        self.complex_sink = None
        self.if1 = 0
        self.if2 = 0
        self.t_cache = {}
        if filter_type == 'rrc':
            self.set_baseband_gain(0.61)

        self.mixer = blocks.multiply_cc()
        if use_old_decim:
            decimator_values = None	# disable two stage decimator
        else:
            decimator_values = get_decim(input_rate)
        if decimator_values:
            self.decim, self.decim2 = decimator_values
            self.if1 = input_rate / self.decim
            self.if2 = self.if1 / self.decim2
            sys.stderr.write( 'Using two-stage decimator for speed=%d, decim=%d/%d if1=%d if2=%d\n' % (input_rate, self.decim, self.decim2, self.if1, self.if2))
            bpf_coeffs = filter.firdes.complex_band_pass(1.0, input_rate, -self.if1/2, self.if1/2, self.if1/2, filter.firdes.WIN_HAMMING)
            self.t_cache[0] = bpf_coeffs
            fa = 6250
            fb = self.if2 / 2
            if filter_type == 'nxdn' and self.symbol_rate == 2400:	# nxdn48 6.25 KHz
                fa = 3125
            lpf_coeffs = filter.firdes.low_pass(1.0, self.if1, (fb+fa)/2, fb-fa, filter.firdes.WIN_HAMMING)
            self.bpf = filter.fir_filter_ccc(self.decim,  bpf_coeffs)
            self.lpf = filter.fir_filter_ccf(self.decim2, lpf_coeffs)
            resampled_rate = self.if2
            self.relative_limit = (input_rate // 2) - (self.if1 // 2)
            self.bfo = analog.sig_source_c (self.if1, analog.GR_SIN_WAVE, 0, 1.0, 0)
            self.connect(self, self.bpf, (self.mixer, 0))
            self.connect(self.bfo, (self.mixer, 1))
        else:
            sys.stderr.write( 'Unable to use two-stage decimator for speed=%d\n' % (input_rate))
            # local osc
            self.lo = analog.sig_source_c (input_rate, analog.GR_SIN_WAVE, 0, 1.0, 0)
            f1 = 7250
            f2 = 1450
            if filter_type == 'nxdn' and self.symbol_rate == 2400:	# nxdn48 6.25 KHz
                f1 = 3125
                f2 = 625
            lpf_coeffs = filter.firdes.low_pass(1.0, input_rate, f1, f2, filter.firdes.WIN_HANN)
            decimation = int(input_rate / if_rate)
            self.lpf = filter.fir_filter_ccf(decimation, lpf_coeffs)
            resampled_rate = float(input_rate) / float(decimation) # rate at output of self.lpf
            self.relative_limit = (input_rate // 2) - f1
            self.connect(self, (self.mixer, 0))
            self.connect(self.lo, (self.mixer, 1))
        self.connect(self.mixer, self.lpf)


        if self.if_rate != resampled_rate:
            self.if_out = filter.pfb.arb_resampler_ccf(float(self.if_rate) / resampled_rate)
            self.connect(self.lpf, self.if_out)
        else:
            self.if_out = self.lpf

        fa = 6250
        fb = fa + 625
        cutoff_coeffs = filter.firdes.low_pass(1.0, self.if_rate, (fb+fa)/2, fb-fa, filter.firdes.WIN_HANN)
        self.cutoff = filter.fir_filter_ccf(1, cutoff_coeffs)

        omega = float(self.if_rate) / float(self.symbol_rate)
        gain_omega = 0.1  * gain_mu * gain_mu

        alpha = costas_alpha
        beta = 0.125 * alpha * alpha
        fmax = 2400	# Hz
        fmax = 2*pi * fmax / float(self.if_rate)

        self.clock = op25_repeater.gardner_costas_cc(omega, gain_mu, gain_omega, alpha,  beta, fmax, -fmax)

        self.agc = analog.feedforward_agc_cc(16, 1.0)

        # Perform Differential decoding on the constellation
        self.diffdec = digital.diff_phasor_cc()

        # take angle of the difference (in radians)
        self.to_float = blocks.complex_to_arg()

        # convert from radians such that signal is in -3/-1/+1/+3
        self.rescale = blocks.multiply_const_ff( (1 / (pi / 4)) )

        # fm demodulator (needed in fsk4 case)
        fm_demod_gain = if_rate / (2.0 * pi * _def_symbol_deviation)
        self.fm_demod = analog.quadrature_demod_cf(fm_demod_gain)

        self.connect_chain(demod_type)
        self.connect(self.slicer, self)

        self.set_relative_frequency(relative_freq)

    def get_error_band(self):
        return int(self.clock.get_error_band())

    def get_freq_error(self):	# get error in Hz (approx).
        return int(self.clock.get_freq_error() * self.symbol_rate)

    def is_muted(self):
        return self.clock.is_muted()

    def set_muted(self, v):
        self.clock.set_muted(v)

    def set_omega(self, omega):
        sps = self.if_rate / float(omega)
        if sps == self.sps:
            return
        self.sps = sps
        print ('set_omega %d %f' % (omega, sps))
        self.clock.set_omega(self.sps)

    def set_relative_frequency(self, freq):
        N = 500	# Hz, we tune the bpf in discrete steps of size N
        if abs(freq) > self.relative_limit:
            #print 'set_relative_frequency: error, relative frequency %d exceeds limit %d' % (freq, self.input_rate/2)
            return False
        if freq == self.lo_freq:
            return True
        self.lo_freq = freq
        if self.if1:
            r = freq % N
            bpf_freq = freq - r
            if r > N//2:
                bpf_freq += N	# round to nearest N Hz
            if bpf_freq not in self.t_cache.keys():
                if abs(bpf_freq) > self.relative_limit:
                    sys.stderr.write( 'set_relative_frequency: error, relative frequency %d(%d) exceeds limit %d\n' % (bpf_freq, freq, self.relative_limit))
                    return False
                self.t_cache[bpf_freq] = filter.firdes.complex_band_pass(1.0, self.input_rate, -bpf_freq - self.if1/2, -bpf_freq + self.if1/2, self.if1/2, filter.firdes.WIN_HAMMING)
            self.bpf.set_taps(self.t_cache[bpf_freq])
            bfo_f = self.decim * -freq / float(self.input_rate)
            bfo_f -= int(bfo_f)
            while bfo_f < -0.5:
                bfo_f += 1.0
            while bfo_f > 0.5:
                bfo_f -= 1.0
            self.bfo.set_frequency(-bfo_f * self.if1)
        else:
            self.lo.set_frequency(self.lo_freq)
        return True

    # assumes lock held or init
    def disconnect_chain(self):
        if self.connect_state == 'cqpsk':
            self.disconnect(self.if_out, self.cutoff, self.agc, self.clock, self.diffdec, self.to_float, self.rescale, self.slicer)
        elif self.connect_state == 'fsk4':
            self.disconnect(self.if_out, self.cutoff, self.fm_demod, self.baseband_amp, self.symbol_filter, self.fsk4_demod, self.slicer)
        self.connect_state = None

    # assumes lock held or init
    def connect_chain(self, demod_type):
        if self.connect_state == demod_type:
            return	# already in desired state
        self.disconnect_chain()
        self.connect_state = demod_type
        if demod_type == 'fsk4':
            self.connect(self.if_out, self.cutoff, self.fm_demod, self.baseband_amp, self.symbol_filter, self.fsk4_demod, self.slicer)
        elif demod_type == 'cqpsk':
            self.connect(self.if_out, self.cutoff, self.agc, self.clock, self.diffdec, self.to_float, self.rescale, self.slicer)
        else:
            print ('connect_chain failed, type: %s' % demod_type)
            assert 0 == 1
        if self.float_sink is not None:
            self.connect_float(self.float_sink[1])

    def disconnect_float(self):
        # assumes lock held or init
        if not self.float_sink:
            return
        self.disconnect(self.float_sink[0], self.float_sink[1])
        self.float_sink = None

    def connect_float(self, sink):
        # assumes lock held or init
        self.disconnect_float()
        if self.connect_state == 'cqpsk':
            self.connect(self.rescale, sink)
            self.float_sink = [self.rescale, sink]
        elif self.connect_state == 'fsk4':
            self.connect(self.fsk4_demod, sink)
            self.float_sink = [self.fsk4_demod, sink]
        else:
            print ('connect_float: state error', self.connect_state)
            assert 0 == 1

    def connect_complex(self, src, sink):
        # assumes lock held or init
        if src == 'clock':
            self.connect(self.clock, sink)
        elif src == 'diffdec':
            self.connect(self.diffdec, sink)
        elif src == 'mixer':
            self.connect(self.agc, sink)
        elif src == 'src':
            self.connect(self, sink)
        elif src == 'bpf':
            self.connect(self.bpf, sink)
        elif src == 'if_out':
            self.connect(self.if_out, sink)
        elif src == 'agc':
            self.connect(self.agc, sink)
