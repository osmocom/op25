#!/usr/bin/env python

# Copyright 2011, 2012, 2013, 2014, 2015 Max H. Parke KA1RBI
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

import sys
import os
import time
import subprocess
import json
import threading
import glob

from gnuradio import gr, eng_notation
from gnuradio import blocks, audio
from gnuradio.eng_option import eng_option
import numpy as np
from gnuradio import gr
from math import pi, sin, cos

_def_debug = 0
_def_sps = 10

GNUPLOT = '/usr/bin/gnuplot'

FFT_AVG  = 0.25
MIX_AVG  = 0.15
BAL_AVG  = 0.05
FFT_BINS = 512

def degrees(r):
	d = 360 * r / (2*pi)
	while d <0:
		d += 360
	while d > 360:
		d -= 360
	return d

def limit(a,lim):
	if a > lim:
		return lim
	return a

def ensure_str(s):      # for python 2/3
    if isinstance(s[0], str):
        return s
    ns = ''
    for i in range(len(s)):
        ns += chr(s[i])
    return ns

PSEQ = 0

class wrap_gp(object):
	def __init__(self, sps=_def_sps, logfile=None, title="", color_cfg='plot-colors.json'):
		global PSEQ
		self.sps = sps
		self.center_freq = 0.0
		self.relative_freq = 0.0
		self.offset_freq = 0.0
		self.width = None
		self.ffts = ()
		self.freqs = ()
		self.avg_pwr = np.zeros(FFT_BINS)
		self.avg_sum_pwr = 0.0
		self.buf = np.array([])
		self.plot_count = 0
		self.last_plot = 0
		self.plot_interval = None
		self.sequence = 0
		self.output_dir = None
		self.filename = None
		self.logfile = logfile
		self.title = title
		self.sequence_id = PSEQ
		PSEQ += 1
		x = self.sequence_id % 3
		y = self.sequence_id // 3
		self.position = (x, y)

		self.colors = {}
		self.colors['label_color'] = ''
		self.colors['tic_color'] = ''
		self.colors['border_color'] = ''
		self.colors['plot_color'] = ''
		self.colors['background_color'] = ''
		if color_cfg and os.access(color_cfg, os.R_OK):
			ccfg = json.loads(open(color_cfg).read())
			for color in ccfg:
				self.colors[color] = ccfg[color]

		self.attach_gp()

	def attach_gp(self):
		args = (GNUPLOT, '-noraise')
		exe  = GNUPLOT
		self.gp = subprocess.Popen(args, executable=exe, stdin=subprocess.PIPE)

	def kill(self):
		try:
			self.gp.stdin.close()   # closing pipe should cause subprocess to exit
		except IOError:
			pass
		sleep_count = 0
		while True:                     # wait politely, but only for so long
			self.gp.poll()
			if self.gp.returncode is not None:
				break
			time.sleep(0.1)
			if self.gp.returncode is not None:
				break
			sleep_count += 1
			if (sleep_count & 1) == 0:
				self.gp.kill()
			if sleep_count >= 3:
				break

	def set_interval(self, v):
		self.plot_interval = v

	def set_output_dir(self, v):
		self.output_dir = v

	def set_sps(self, sps):
		self.sps = sps

	def plot(self, buf, bufsz, mode='eye'):
		BUFSZ = bufsz
		consumed = min(len(buf), BUFSZ-len(self.buf))
		if len(self.buf) < BUFSZ:
			self.buf = np.concatenate((self.buf, buf[:int(consumed)]))
		if len(self.buf) < BUFSZ:
			return consumed

		self.plot_count += 1
		if mode == 'eye' and self.plot_count % 20 != 0:
			self.buf = np.array([])
			return consumed

		plots = []
		s = ''
		plot_size = (320,240)
		if mode == 'eye':
			nplots = len(self.buf) // self.sps - 2
			for i in range(nplots):
				s += '\n'.join(['%f' % self.buf[i*self.sps+j] for j in range(self.sps+1)])
				s += '\ne\n'
				plots.append('"-" with lines')
		elif mode == 'cpm':
			nplots = len(self.buf)
			ab = np.abs(self.buf)
			for i in range(len(ab)):
				s += '%f\n' % ab[i]
			s += '\ne\n'
			plots.append('"-" with lines')
		elif mode == 'constellation':
			plot_size = (240,240)
			self.buf = self.buf[:100]
			for b in self.buf:
				s += '%f\t%f\n' % (degrees(np.angle(b)), limit(np.abs(b),1.0))
			s += 'e\n'
			plots.append('"-" with points')
			for b in self.buf:
				#s += '%f\t%f\n' % (b.real, b.imag)
				s += '%f\t%f\n' % (degrees(np.angle(b)), limit(np.abs(b),1.0))
			s += 'e\n'
			plots.append('"-" with lines')
		elif mode == 'symbol':
			for b in self.buf:
				s += '%f\n' % (b)
			s += 'e\n'
			plots.append('"-" with points')
		elif mode == 'fftf':
			self.ffts = np.fft.rfft(self.buf * np.blackman(BUFSZ)) / (0.42 * BUFSZ)
			#self.ffts = np.fft.fftshift(self.ffts)
			self.ffts = np.abs(self.ffts) ** 2.0
			self.ffts /= np.max(self.ffts)
			for i in range(len(self.ffts)):
				s += '%f\n' % (self.ffts[i])
			s += 'e\n'
			plots.append('"-" with lines')
		elif mode == 'fft' or mode == 'mixer':
			sum_pwr = 0.0
			self.ffts = np.fft.fft(self.buf * np.blackman(BUFSZ)) / (0.42 * BUFSZ)
			self.ffts = np.fft.fftshift(self.ffts)
			self.freqs = np.fft.fftfreq(len(self.ffts))
			self.freqs = np.fft.fftshift(self.freqs)
			tune_freq = (self.center_freq - self.relative_freq) / 1e6
			if self.center_freq and self.width:
                               	self.freqs = ((self.freqs * self.width) + self.center_freq + self.offset_freq) / 1e6
			for i in range(len(self.ffts)):
				if mode == 'fft':
					self.avg_pwr[i] = ((1.0 - FFT_AVG) * self.avg_pwr[i]) + (FFT_AVG * np.abs(self.ffts[i]))
				else:
					self.avg_pwr[i] = ((1.0 - MIX_AVG) * self.avg_pwr[i]) + (MIX_AVG * np.abs(self.ffts[i]))
				s += '%f\t%f\n' % (self.freqs[i], 20 * np.log10(self.avg_pwr[i]))
				if (mode == 'mixer') and (self.avg_pwr[i] > 1e-5):
					if (self.freqs[i] - self.center_freq) < 0:
						sum_pwr -= self.avg_pwr[i]
					elif (self.freqs[i] - self.center_freq) > 0:
						sum_pwr += self.avg_pwr[i]
					self.avg_sum_pwr = ((1.0 - BAL_AVG) * self.avg_sum_pwr) + (BAL_AVG * sum_pwr)
			s += 'e\n'
			plots.append('"-" with lines')
		elif mode == 'float' or mode == 'correlation':
			for b in self.buf:
				s += '%f\n' % (b)
			s += 'e\n'
			plots.append('"-" with lines')
		elif mode == 'sync':
			s_abs = np.abs(self.buf)
			sums = np.zeros(self.sps)
			for i in range(self.sps):
				sums[i] = np.sum(s_abs[range(i, len(self.buf), self.sps)])
			am = np.argmax(sums)
			samples = self.buf[am:]

			a1 = -np.angle(samples[0])
			rz = cos(a1) + 1j * sin(a1)

			while len(samples) >= self.sps+1:
				for i in range(self.sps+1):
					z = samples[i] * rz
					s += '%f\t%f\n' % (z.real, z.imag)
				s += 'e\n'
				plots.append('"-" with linespoints')
				samples = samples[self.sps:]

		self.buf = np.array([])

		# FFT processing needs to be completed to maintain the weighted average buckets
		# regardless of whether we actually produce a new plot or not.
		if self.plot_interval and self.last_plot + self.plot_interval > time.time():
			return consumed
		self.last_plot = time.time()

		filename = None
		if self.output_dir:
			if self.sequence >= 2:
				delete_pathname = '%s/plot-%s%d-%d.png' % (self.output_dir, mode, self.sequence_id, self.sequence-2)
				if os.access(delete_pathname, os.W_OK):
					os.remove(delete_pathname)
			h0= 'set terminal png size %d, %d\n' % (plot_size)
			filename = 'plot-%s%d-%d.png' % (mode, self.sequence_id, self.sequence)
			h0 += 'set output "%s/%s"\n' % (self.output_dir, filename)
			self.sequence += 1
		else:
			pos = ''
			if self.position is not None:
				x = self.position[0] * plot_size[0]
				y = self.position[1] * plot_size[1]
				x += 50
				y += 75
				pos = ' position %d, %d' % (x, y)
			h0= 'set terminal x11 noraise size %d, %d%s title "%s"\n' % (plot_size[0], plot_size[1], pos, self.title)
		background = ''

		label_color = ''
		tic_color = ''
		border_color = ''
		plot_color = ''
		background_color = ''

		if self.colors['label_color']:
			label_color = 'textcolor rgb"%s"' % self.colors['label_color']
		if self.colors['tic_color']:
			tic_color = 'textcolor rgb"%s"' % self.colors['tic_color']
		if self.colors['border_color']:
			border_color = 'linecolor rgb"%s"' % self.colors['border_color']
		if self.colors['plot_color']:
			plot_color = 'linecolor rgb"%s"' % self.colors['plot_color']
		if self.colors['background_color']:
			background_color = 'fillcolor rgb"%s"' % self.colors['background_color']

		background += 'set object 1 rectangle from screen 0,0 to screen 1,1 %s behind\n' % (background_color)
		background += 'set xtics %s\n' % (tic_color)
		background += 'set ytics %s\n' % (tic_color)
		background += 'set border %s\n' % (border_color)

		h = 'set key off\n'
		if mode == 'constellation':
			#h+= background
			plot_color = ''
			h+= 'set size square\n'
			h+= 'set xrange [-1:1]\n'
			h+= 'set yrange [-1:1]\n'
			h += 'unset border\n'
			h += 'set polar\n'
			h += 'set angles degrees\n'
			h += 'unset raxis\n'
			h += 'set object 1 rectangle from screen 0,0 to screen 1,1 %s behind\n' % (background_color)
			h += 'set object 2 circle at 0,0 size 1 fillcolor rgb 0x0f01 fillstyle solid behind\n'
			h += 'set object 3 circle at 0,0 size 1 %s\n' % 'linecolor rgb"#0000f0"'
			h += 'set style line 10 lt 1 lc rgb 0x404040 lw 0.1\n'
			h += 'set grid polar 45\n'
			h += 'set grid ls 10\n'
			h += 'set xtics axis\n'
			h += 'set ytics axis\n'
			h += 'set xtics scale 0\n'
			h += 'set xtics ("" 0.2, "" 0.4, "" 0.6, "" 0.8, "" 1)\n'
			h += 'set ytics 0, 0.2, 1\n'
			h += 'set format ""\n'
			h += 'set style line 11 lt 1 lw 2 pt 2 ps 2\n'

			h+= 'set title "Constellation %s" %s\n' % (self.title, label_color)
		elif mode == 'eye':
			h+= background
			h+= 'set yrange [-4:4]\n'
			h+= 'set title "Datascope %s" %s\n' % (self.title, label_color)
			plot_color = ''
		elif mode == 'cpm':
			h+= background
			#h+= 'set yrange [-4:4]\n'
			h+= 'set title "CPM RSSI %s" %s\n' % (self.title, label_color)
			#plot_color = ''
		elif mode == 'sync':
			h += 'set object 1 rect from screen 0,0 to screen 1,1 %s behind\n' % (background_color)
			h += 'set size square\n'
			h += 'set xtics %s\n' % (tic_color)
			h += 'set ytics %s\n' % (tic_color)
			h += 'set border %s\n' % (border_color)
		elif mode == 'symbol':
			h+= background
			h+= 'set yrange [-4:4]\n'
			h+= 'set title "Symbol %s" %s\n' % (self.title, label_color)
		elif mode == 'fft' or mode == 'mixer':
			h+= background
			h+= 'unset arrow; unset title\n'
			h+= 'set xrange [%f:%f]\n' % (self.freqs[0], self.freqs[len(self.freqs)-1])
			h+= 'set xlabel "Frequency"\n'
			h+= 'set ylabel "Power(dB)"\n'
			h+= 'set grid\n'
			h+= 'set yrange [-100:0]\n'
			if mode == 'mixer':	# mixer
				h+= 'set title "Mixer %s: balance %3.0f (smaller is better)" %s\n' % (self.title, np.abs(self.avg_sum_pwr * 1000), label_color)
			else:			# fft
				h+= 'set title "Spectrum %s" %s\n' % (self.title, label_color)
				if self.center_freq:
					arrow_pos = (self.center_freq - self.relative_freq) / 1e6
					h+= 'set arrow from %f, graph 0 to %f, graph 1 nohead\n' % (arrow_pos, arrow_pos)
					h+= 'set title "Spectrum: tuned to %f Mhz" %s\n' % (arrow_pos, label_color)
		elif mode == 'fftf':
			h+= 'set yrange [-1:1.2]\n'
			h+= 'set title "fftf"\n'
		elif mode == 'float':
			h+= background
			h+= 'set yrange [-2:2]\n'
			h+= 'set title "Oscilloscope %s" %s\n' % (self.title, label_color)
		elif mode == 'correlation':
			h+= background
			title = 'Correlation'
			if self.title:
				title = self.title
			h+= 'set yrange [-1.1:1.1]\n'
			h+= 'set title "%s" %s\n' % (title, label_color)
		if self.output_dir:
			s += 'set output\n'	## flush output png
		dat = '%s%splot %s %s\n%s' % (h0, h, ','.join(plots), plot_color, s)
		if self.logfile is not None:
			with open(self.logfile, 'a') as fd:
				fd.write(dat)
		if sys.version[0] != '2':
			dat = bytes(dat, 'utf8')
		self.gp.poll()
		if self.gp.returncode is None:	# make sure gnuplot is still running 
			try:
				rc = self.gp.stdin.write(dat)
			except (IOError, ValueError):
				pass
			try:
				self.gp.stdin.flush()
			except (IOError, ValueError):
				pass
		if filename:
			self.filename = filename
		return consumed

	def set_center_freq(self, f):
		self.center_freq = f

	def set_relative_freq(self, f):
		self.relative_freq = f

	def set_offset(self, f):
		self.offset_freq = f

	def set_width(self, w):
		self.width = w

	def set_logfile(self, logfile=None):
		self.logfile = logfile

	def set_title(self, title):
		self.title = title

class eye_sink_f(gr.sync_block):
    """
    """
    def __init__(self, debug = _def_debug, sps = _def_sps):
        gr.sync_block.__init__(self,
            name="eye_sink_f",
            in_sig=[np.float32],
            out_sig=None)
        self.debug = debug
        self.sps = sps
        self.gnuplot = wrap_gp(sps=self.sps)

    def work(self, input_items, output_items):
        in0 = input_items[0]
        consumed = self.gnuplot.plot(in0, 100*self.sps, mode='eye')
        return consumed ### len(input_items[0])

    def set_title(self, title):
        self.gnuplot.set_title(title)

    def kill(self):
        self.gnuplot.kill()

class cpm_sink_c(gr.sync_block):
    """
    """
    def __init__(self, debug = _def_debug, sps = _def_sps):
        gr.sync_block.__init__(self,
            name="cpm_sink_c",
            in_sig=[np.complex64],
            out_sig=None)
        self.debug = debug
        self.sps = sps
        self.gnuplot = wrap_gp(sps=self.sps)

    def work(self, input_items, output_items):
        in0 = input_items[0]
        l = len(in0)
        consumed = self.gnuplot.plot(in0, self.sps*3000, mode='cpm')
        return consumed ### len(input_items[0])

    def set_title(self, title):
        self.gnuplot.set_title(title)

    def kill(self):
        self.gnuplot.kill()

class constellation_sink_c(gr.sync_block):
    """
    """
    def __init__(self, debug = _def_debug):
        gr.sync_block.__init__(self,
            name="constellation_sink_c",
            in_sig=[np.complex64],
            out_sig=None)
        self.debug = debug
        self.gnuplot = wrap_gp()

    def work(self, input_items, output_items):
        in0 = input_items[0]
        self.gnuplot.plot(in0, 1000, mode='constellation')
        return len(input_items[0])

    def set_title(self, title):
        self.gnuplot.set_title(title)

    def kill(self):
        self.gnuplot.kill()

class fft_sink_f(gr.sync_block):
    """
    """
    def __init__(self, debug = _def_debug):
        gr.sync_block.__init__(self,
            name="fft_sink_f",
            in_sig=[np.float32],
            out_sig=None)
        self.debug = debug
        self.gnuplot = wrap_gp()
        self.skip = 0

    def work(self, input_items, output_items):
        self.skip += 1
        if self.skip >= 50:
            self.skip = 0
            in0 = input_items[0]
            self.gnuplot.plot(in0, FFT_BINS, mode='fftf')
        return len(input_items[0])

    def kill(self):
        self.gnuplot.kill()

class fft_sink_c(gr.sync_block):
    """
    """
    def __init__(self, debug = _def_debug):
        gr.sync_block.__init__(self,
            name="fft_sink_c",
            in_sig=[np.complex64],
            out_sig=None)
        self.debug = debug
        self.gnuplot = wrap_gp()
        self.skip = 0

    def work(self, input_items, output_items):
        self.skip += 1
        if self.skip >= 50:
            self.skip = 0
            in0 = input_items[0]
            self.gnuplot.plot(in0, FFT_BINS, mode='fft')
        return len(input_items[0])

    def set_title(self, title):
        self.gnuplot.set_title(title)

    def kill(self):
        self.gnuplot.kill()

    def set_center_freq(self, f):
        self.gnuplot.set_center_freq(f)
        self.gnuplot.set_relative_freq(0.0)

    def set_relative_freq(self, f):
        self.gnuplot.set_relative_freq(f)

    def set_offset(self, f):
        self.gnuplot.set_offset(f)

    def set_width(self, w):
        self.gnuplot.set_width(w)

class mixer_sink_c(gr.sync_block):
    """
    """
    def __init__(self, debug = _def_debug):
        gr.sync_block.__init__(self,
            name="mixer_sink_c",
            in_sig=[np.complex64],
            out_sig=None)
        self.debug = debug
        self.gnuplot = wrap_gp()
        self.skip = 0

    def work(self, input_items, output_items):
        self.skip += 1
        if self.skip >= 10:
            self.skip = 0
            in0 = input_items[0]
            self.gnuplot.plot(in0, FFT_BINS, mode='mixer')
        return len(input_items[0])

    def set_title(self, title):
        self.gnuplot.set_title(title)

    def kill(self):
        self.gnuplot.kill()

class sync_plot(threading.Thread):
    """
    """
    def __init__(self, debug = _def_debug, block = None, **kwds):
        threading.Thread.__init__ (self, **kwds)
        self.setDaemon(1)
        self.SLEEP_TIME = 3	## TODO - make more configurable
        self.sleep_until = time.time() + self.SLEEP_TIME
        self.last_file_time = time.time()
        self.keep_running = True
        self.debug = debug
        self.warned = False

        block.enable_sync_plot(True)	# block must refer to a gardner/costas instance
        self.blk_id = block.unique_id()

        self.gnuplot = wrap_gp(sps = _def_sps)
        self.start()

    def run(self):
        while self.keep_running == True:
            curr_time = time.time()
            if curr_time < self.sleep_until:
                time.sleep(1.0)
                if self.keep_running == False:
                    break
            else:
                self.sleep_until = time.time() + self.SLEEP_TIME
                self.check_update()

    def read_raw_file(self, fn):
        s = open(fn, 'rb').read()
        s_msg = ensure_str(s)
        p = s_msg.find('\n')
        if p < 1 or p > 24:
            return None # error
        hdrline = s_msg[:p]
        rest = s[p+1:]
        params = hdrline.split()
        params = [int(p) for p in params]	#idx, p1p2, sps, error
        idx = params[0]
        p1p2 = params[1]
        sps = params[2]
        error_amt = params[3]
        self.gnuplot.set_sps(sps)
        if error_amt != 0:
            self.set_title("Tuning Error %d" % error_amt)
        else:
            self.set_title("")
        samples = np.frombuffer(rest, dtype=np.complex64)
        samples2 = np.concatenate((samples[idx:], samples[:idx]))
        needed = sps * 25 if p1p2 == 1 else sps * 21
        if len(samples2) < needed:
            if not self.warned:
                self.warned = True
                sys.stderr.write('read_raw_file: insufficient samples %d, needed %d\n' % (needed, len(samples2)))
        elif len(samples2) > needed:
            trim = len(samples2) - needed
            samples2 = samples2[trim:]
        return samples2		# return trimmed buf in np.complex64 format

    def check_update(self):
        patt = 'sample-%d*.dat' % (self.blk_id)
        names = glob.glob(patt)
        if len(names) < 1:	# no files to work with
            return
        d = {n: os.stat(n).st_mtime for n in names}
        ds = sorted(d.items(), key=lambda x:x[1], reverse = True)[0]
        if ds[1] <= self.last_file_time:
            return
        self.last_file_time = ds[1]
        dat = self.read_raw_file(ds[0])
        self.gnuplot.plot(dat, len(dat), mode='sync')

    def kill(self):
        self.keep_running = False

    def set_title(self, title):
        self.gnuplot.set_title(title)

    def kill(self):
        self.gnuplot.kill()

class symbol_sink_f(gr.sync_block):
    """
    """
    def __init__(self, debug = _def_debug):
        gr.sync_block.__init__(self,
            name="symbol_sink_f",
            in_sig=[np.float32],
            out_sig=None)
        self.debug = debug
        self.gnuplot = wrap_gp()

    def work(self, input_items, output_items):
        in0 = input_items[0]
        self.gnuplot.plot(in0, 2400, mode='symbol')
        return len(input_items[0])

    def set_title(self, title):
        self.gnuplot.set_title(title)

    def kill(self):
        self.gnuplot.kill()

class float_sink_f(gr.sync_block):
    """
    """
    def __init__(self, debug = _def_debug):
        gr.sync_block.__init__(self,
            name="float_sink_f",
            in_sig=[np.float32],
            out_sig=None)
        self.debug = debug
        self.gnuplot = wrap_gp()

    def work(self, input_items, output_items):
        in0 = input_items[0]
        self.gnuplot.plot(in0, 2000, mode='float')
        return len(input_items[0])

    def set_title(self, title):
        self.gnuplot.set_title(title)

    def kill(self):
        self.gnuplot.kill()

class correlation_sink_f(gr.sync_block):
    """
    """
    def __init__(self, sps=_def_sps, debug = _def_debug):
        gr.sync_block.__init__(self,
            name="plot_sink_f",
            in_sig=[np.float32],
            out_sig=None)
        self.debug = debug
        self.sps = sps
        self.gnuplot = wrap_gp()
        self.fs = []
        self.cbuf = np.array([])
        self.ignore = 0
        self.pktlen = 1024

    def set_length(self, l):
        self.pktlen = l

    def set_title(self, title):
        self.gnuplot.set_title(title)

    def set_signature(self, fs):
        self.fs = []
        for s in fs:
            for i in range(self.sps):
                self.fs.append(s)
        self.fs.reverse()	# reverse order for np.convolve
        self.fs = np.array(self.fs)

    def work(self, input_items, output_items):
        if len(self.cbuf) == 0 and self.ignore > 0:
            self.ignore -= len(input_items[0])
            if self.ignore < 0:
                self.ignore = 0
            return len(input_items[0])
        if len(self.fs) == 0:
            return len(input_items[0])
        in0 = input_items[0]
        self.cbuf = np.append(self.cbuf, in0)
        if len(self.cbuf) < self.pktlen:
            return len(input_items[0])
        result = np.convolve(self.cbuf[:self.pktlen], self.fs)
        hi = np.max(np.abs(result))
        if hi != 0:
            result = result / hi
        self.cbuf = []
        self.ignore = 3000 * self.sps
        self.gnuplot.plot(result, len(result), mode='correlation')
        return len(input_items[0])

    def kill(self):
        self.gnuplot.kill()

def setup_correlation(sps, title, connect_bb):
    CFG_FILE = 'correlation.json'
    if not os.access(CFG_FILE, os.R_OK):
        sys.stderr.write('correlation plot ignored, missing config file %s\n' % CFG_FILE)
        return []
    ccfg = json.loads(open(CFG_FILE).read())
    sinks = []
    for cfg in ccfg:
        sink = correlation_sink_f(sps=sps)
        sink.set_title('%s %s' % (title, cfg['name']))
        l = cfg['length'] * sps * 4
        LENGTH_LIMIT = 10000
        if l > LENGTH_LIMIT:
            l = LENGTH_LIMIT
        sink.set_length(l)
        sink.set_signature(cfg['fs'])
        connect_bb('baseband_amp', sink)
        sinks.append(sink)
    return sinks
