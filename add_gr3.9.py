#! /usr/bin/python3

# Copyright 2022, Max H. Parke KA1RBI
#
# This file is part of GNU Radio and part of OP25
#
# SPDX-License-Identifier: GPL-3.0-or-later
#

import sys
import os
import glob
import shutil
from gnuradio.modtool.core.newmod import ModToolNewModule
from gnuradio.modtool.core.add import ModToolAdd
from gnuradio.modtool.core.bind import ModToolGenBindings

msg = """
This is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 3, or (at your option)
any later version.
"""

print('\n%s Copyright 2022, Max H. Parke KA1RBI\nhttps://osmocom.org/projects/op25\n%s' % (sys.argv[0], msg))

TLD = 'op25'

MODS={
	'op25': 'decoder_bf decoder_ff fsk4_demod_ff fsk4_slicer_fb pcap_source_b'.split(),
	'op25_repeater': 'ambe_encoder_sb dmr_bs_tx_bb dstar_tx_sb frame_assembler fsk4_slicer_fb gardner_costas_cc nxdn_tx_sb p25_frame_assembler vocoder ysf_tx_sb'.split()
}

SKIP_CC = 'd2460.cc qa_op25.cc test_op25.cc qa_op25_repeater.cc test_op25_repeater.cc'.split()

SRC_DIR = sys.argv[1]
DEST_DIR = sys.argv[2]

if  '..' in SRC_DIR or not SRC_DIR.startswith('/'):
	sys.stderr.write('error, %s must be an absolute path\n' % SRC_DIR)
	sys.exit(1)

if not os.access(SRC_DIR, os.R_OK):
	sys.stderr.write('error, unable to access %s\n' % SRC_DIR)
	sys.exit(1)

if not os.path.isdir(SRC_DIR + '/op25/gr-op25_repeater'):
	sys.stderr.write('error, op25 package not found in %s\n' % SRC_DIR)
	sys.exit(3)

if os.access(DEST_DIR, os.F_OK) or os.path.isdir(DEST_DIR):
	sys.stderr.write('error, destination path %s must not exist\n' % DEST_DIR)
	sys.exit(4)

os.mkdir(DEST_DIR)
op25_dir = DEST_DIR + '/op25'
os.mkdir(op25_dir)
os.chdir(op25_dir)

def edit_cmake(filename, mod, srcfiles):
	lines = open(filename).read().rstrip().split('\n')
	srcdefs = []
	state = 0
	end_mark = 0
	tll = 0	# target_link_library
	srcfiles = [s.split('/')[-1] for s in srcfiles if s.endswith('.cc') or s.endswith('.c') or s.endswith('.cpp')]
	for i in range(len(lines)):
		if lines[i].startswith('list(APPEND op25_') and '_sources' in lines[i]:
			state = 1
			continue
		elif ')' in lines[i] and state:
			state = 0
			end_mark = i
			continue
		elif lines[i].startswith('target_link_libraries(gnuradio-op25'):
			assert lines[i].endswith(')')
			tll = i
			continue
		if state:
			srcdefs.append(lines[i].strip())
	srcfiles = ["    %s" % s for s in srcfiles if s not in srcdefs and s not in SKIP_CC]
	tlls = {
		'op25': 'target_link_libraries(gnuradio-op25 gnuradio::gnuradio-runtime Boost::system Boost::program_options Boost::filesystem Boost::thread itpp pcap)',
		'op25_repeater': 'target_link_libraries(gnuradio-op25_repeater PUBLIC gnuradio::gnuradio-runtime gnuradio::gnuradio-filter PRIVATE imbe_vocoder)'
	}
	assert tll	# fail if target_link_libraries line not found
	lines[tll] = tlls[mod]
	if mod == 'op25_repeater':
		lines = lines[:tll] + ['\n' + 'add_subdirectory(imbe_vocoder)\n'] + lines[tll:]

	new_lines = lines[:end_mark] + srcfiles + lines[end_mark:]
	s = '\n'.join(new_lines)
	s += '\n'
	with open(filename, 'w') as fp:
		fp.write(s)

def get_args_from_h(mod):
	lines = open(mod).read().rstrip().split('\n')

	lines = [line for line in lines if 'make' in line]

	answer = []
	for s in lines:
		s = s.rstrip()
		if s[-1] != ';':
			continue
		s = s[:-1]
		s = s.rstrip()
		if s[-1] != ')':
			continue
		s = s[:-1]
		lp = s.find('(')
		if lp > 0:
			s =s[lp+1:]
		else:
			continue
		for arg in s.split(','):
			eq = arg.find('=')
			if eq > 0:
				arg = arg[:eq]
			answer.append(arg)
		return ','.join(answer)
	return ''

for mod in sorted(MODS.keys()):
	m = ModToolNewModule(module_name=mod, srcdir=None)
	m.run()
	print('gr_modtool newmod %s getcwd now %s' % (mod, os.getcwd()))
	pfx = '%s/op25/gr-%s' % (SRC_DIR, mod)
	lib = '%s/lib' % pfx
	incl = '%s/include/%s' % (pfx, mod)
	d_pfx = '%s/op25/gr-%s' % (DEST_DIR, mod)
	d_lib = '%s/lib' % d_pfx
	d_incl = '%s/include/%s' % (d_pfx, mod)
	for block in MODS[mod]:
		include = '%s/%s.h' % (incl, block)
		args = get_args_from_h(include)
		t = 'sync' if block == 'fsk4_slicer_fb' else 'general'
		print ('add %s %s type %s directory %s args %s' % (mod, block, t, os.getcwd(), args))
		m = ModToolAdd(blockname=block,block_type=t,lang='cpp',copyright='Steve Glass, OP25 Group', argument_list=args)
		m.run()

	srcfiles = []
	srcfiles += glob.glob('%s/lib/*.cc' % pfx)
	srcfiles += glob.glob('%s/lib/*.cpp' % pfx)
	srcfiles += glob.glob('%s/lib/*.c' % pfx)
	srcfiles += glob.glob('%s/lib/*.h' % pfx)
	hfiles = []
	hfiles += glob.glob('%s/include/%s/*.h' % (pfx, mod))

	assert os.path.isdir(d_lib)
	assert os.path.isdir(d_incl)

	for f in srcfiles:
		shutil.copy(f, d_lib)
	for f in hfiles:
		shutil.copy(f, d_incl)

	if mod == 'op25_repeater':
		for d in 'imbe_vocoder ezpwd'.split():
			os.mkdir('%s/%s' % (d_lib, d))
			imbefiles = []
			imbefiles += glob.glob('%s/%s/*' % (lib, d))
			dest = '%s/%s' % (d_lib, d)
			for f in imbefiles:
				shutil.copy(f, dest)

	edit_cmake('%s/CMakeLists.txt' % d_lib, mod, srcfiles)

	os.system('/bin/bash %s/do_sed.sh' % (SRC_DIR))

	for block in MODS[mod]:
		print ('bind %s %s' % (mod, block))
		m = ModToolGenBindings(block, addl_includes='', define_symbols='')
		m.run()

	os.chdir(op25_dir)
