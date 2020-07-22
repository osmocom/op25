#!/usr/bin/env python

#
# (C) Copyright 2020 Max H. Parke, KA1RBI
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

#
# nxdn trunking:
# -  CAC decoding 
#

import sys
import os

sys.path.append('tdma')
from bit_utils import *

def locid(id):
	save_id = mk_int(id)
	cat = mk_int(id[:2])
	if cat == 0:
		ssize = 10
	elif cat == 2:
		ssize = 14
	elif cat == 1:
		ssize = 17
	else:
		return {'category': -1, 'system': -1, 'site': -1, 'id': '0x%x' % save_id}
	id = id[2:]
	syscode = mk_int(id[:ssize])
	id = id[ssize:]
	sitecode = mk_int(id)
	return {'category': cat, 'system': syscode, 'site': sitecode, 'id': '0x%x' % save_id}

def mk_freq(f):
	### todo: UHF currently untested; may fail at 400 MHz
	return int(f * 1250 + 100000000)	# frequency in Hz

def cac_message(s):
	d = {}
	bits = []
	for c in s:
		for i in range(8):
			bits.append((c >> (7-i)) & 1)
	d['structure'] = mk_int(bits[:2])
	d['ran'] = mk_int(bits[2:8])
	bits = bits[8:]
	msg_type = mk_int(bits[2:8])
	d['msg_typeid'] = msg_type
	if msg_type == 0x18:	# SITE_INFO
		assert len(bits) == 144
		d['msg_type'] = 'SITE_INFO'
		bits = bits[8:]
		d['location_id'] = locid(bits[:24])
		bits = bits[24:]
		d['channel_info'] = mk_int(bits[:16])
		bits = bits[16:]
		d['service_info'] = mk_int(bits[:16])
		bits = bits[16:]
		d['restr_info'] = mk_int(bits[:24])
		bits = bits[24:]
		d['access_info'] = mk_int(bits[:24])
		bits = bits[24:]
		d['version_no'] = mk_int(bits[:8])
		bits = bits[8:]
		d['adjacent_alloc'] = mk_int(bits[:4])
		bits = bits[4:]
		d['cc1'] = mk_int(bits[:10])
		bits = bits[10:]
		d['cc2'] = mk_int(bits[:10])
	elif msg_type == 0x19:	# SRV_INFO
		assert len(bits) >= 72
		d['msg_type'] = 'SRV_INFO'
		bits = bits[8:]
		d['location_id'] = locid(bits[:24])
		bits = bits[24:]
		d['service_info'] = mk_int(bits[:16])
		bits = bits[16:]
		d['restr_info'] = mk_int(bits[:24])
	elif msg_type == 0x1a:	# CCH_INFO
		assert len(bits) >= 72
		d['msg_type'] = 'CCH_INFO'
		bits = bits[8:]
		d['location_id'] = locid(bits[:24])
		bits = bits[24:]
		d['flags1'] = mk_int(bits[:8])
		bits = bits[8:]
		d['cc1'] = mk_freq(mk_int(bits[:16]))
		bits = bits[16:]
		d['cc2'] = mk_freq(mk_int(bits[:16]))
	elif msg_type == 0x1b:	# ADJ_SITE_INFO
		assert len(bits) >= 72
		d['msg_type'] = 'ADJ_SITE_INFO'
		d1 = {}
		d2 = {}
		bits = bits[8:]
		d1['location'] = locid(bits[:24])
		bits = bits[24:]
		d1['option'] = mk_int(bits[:8])
		bits = bits[8:]
		d1['cc'] = mk_freq(mk_int(bits[:16]))
		bits = bits[16:]
		d2['location'] = locid(bits[:24])
		bits = bits[24:]
		d2['option'] = mk_int(bits[:8])
		bits = bits[8:]
		d2['cc'] = mk_freq(mk_int(bits[:16]))
		bits = bits[16:]
		d['sites'] = [d1, d2]
		#d['location_3'] = locid(bits[:24])
		#bits = bits[24:]
		#d['option_3'] = mk_int(bits[:6])
		#bits = bits[6:]
		#d['cc_3'] = mk_int(bits[:10])
	elif msg_type == 0x01:	# VCALL_RESP
		assert len(bits) >= 64
		d['msg_type'] = 'VCALL_RESP'
		bits = bits[8:]
		d['option'] = mk_int(bits[:8])
		bits = bits[8:]
		d['call_type'] = mk_int(bits[:3])
		d['call_option'] = mk_int(bits[3:8])
		bits = bits[8:]
		d['source_id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['destination_id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['cause'] = mk_int(bits[:8])
		bits = bits[8:]
	elif msg_type == 0x09:	# DCALL_RESP
		assert len(bits) >= 64
		d['msg_type'] = 'DCALL_RESP'
		bits = bits[8:]
		d['option'] = mk_int(bits[:8])
		bits = bits[8:]
		d['call_type'] = mk_int(bits[:3])
		d['call_option'] = mk_int(bits[3:8])
		bits = bits[8:]
		d['source_id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['destination_id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['cause'] = mk_int(bits[:8])
		bits = bits[8:]
	elif msg_type == 0x04:	# VCALL_ASSGN
		assert len(bits) >= 72
		bits2 = bits
		s = ''
		while len(bits2):
			s += '%02x' % mk_int(bits2[:8])
			bits2 = bits2[8:]
		d['hexdata'] = s
		d['msg_type'] = 'VCALL_ASSGN'
		bits = bits[8:]
		d['option'] = mk_int(bits[:8])
		bits = bits[8:]
		d['call_type'] = mk_int(bits[:3])
		d['call_option'] = mk_int(bits[3:8])
		bits = bits[8:]
		d['source_id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['group_id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['timer'] = mk_int(bits[:8])
		d['channel'] = mk_int(bits[6:16])
		bits = bits[8:]
		d['f1'] = mk_freq(mk_int(bits[:16]))
		bits = bits[16:]
		d['f2'] = mk_freq(mk_int(bits[:16]))
	elif msg_type == 0x0e:	# DCALL_ASSGN
		assert len(bits) >= 104
		d['msg_type'] = 'DCALL_ASSGN'
		bits = bits[8:]
		d['option'] = mk_int(bits[:8])
		bits = bits[8:]
		d['call_type'] = mk_int(bits[:3])
		d['call_option'] = mk_int(bits[3:8])
		bits = bits[8:]
		d['source_id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['group_id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['timer'] = mk_int(bits[:8])
		bits = bits[8:]
		d['f1'] = mk_freq(mk_int(bits[:16]))
		bits = bits[16:]
		d['f2'] = mk_freq(mk_int(bits[:16]))
	elif msg_type == 0x20:	# REG_RESP
		assert len(bits) >= 72
		d['msg_type'] = 'REG_RESP'
		bits = bits[8:]
		d['option'] = mk_int(bits[:8])
		bits = bits[8:]
		d['location id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['unit_id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['group_id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['cause'] = mk_int(bits[:8])
		bits = bits[8:]
		d['visitor_unit'] = mk_int(bits[:16])
		bits = bits[16:]
		d['visitor_group'] = mk_int(bits[:16])
	elif msg_type == 0x22:	# REG_C_RESP
		assert len(bits) >= 56
		d['msg_type'] = 'REG_C_RESP'
		bits = bits[8:]
		d['option'] = mk_int(bits[:8])
		bits = bits[8:]
		d['location id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['unit_id'] = mk_int(bits[:16])
	elif msg_type == 0x24:	# GRP_REG_RESP
		assert len(bits) >= 72
		d['msg_type'] = 'GRP_REG_RESP'
		bits = bits[8:]
		d['option'] = mk_int(bits[:8])
		bits = bits[8:]
		d['destination id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['group_id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['cause'] = mk_int(bits[:8])
		bits = bits[8:]
		d['visitor_group_id'] = mk_int(bits[:16])
	elif msg_type == 0x32:	# STAT_REQ
		assert len(bits) >= 72
		d['msg_type'] = 'STAT_REQ'
		bits = bits[8:]
		d['option'] = mk_int(bits[:8])
		bits = bits[8:]
		d['call_type'] = mk_int(bits[:3])
		d['call_option'] = mk_int(bits[3:8])
		bits = bits[8:]
		d['source id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['destination_id'] = mk_int(bits[:16])
		bits = bits[8:]
		d['spare'] = mk_int(bits[:8])
		status = bits[8:]
	elif msg_type == 0x33:	# STAT_RESP
		assert len(bits) >= 64
		d['msg_type'] = 'STAT_RESP'
		bits = bits[8:]
		d['option'] = mk_int(bits[:8])
		bits = bits[8:]
		d['call_type'] = mk_int(bits[:3])
		d['call_option'] = mk_int(bits[3:8])
		bits = bits[8:]
		d['source id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['destination_id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['cause'] = mk_int(bits[:8])
	elif msg_type == 0x38:	# SDCALL_REQ_HEADER
		assert len(bits) >= 64
		d['msg_type'] = 'SDCALL_REQ_HEADER'
		bits = bits[8:]
		d['option'] = mk_int(bits[:8])
		bits = bits[8:]
		d['call_type'] = mk_int(bits[:3])
		d['call_option'] = mk_int(bits[3:8])
		bits = bits[8:]
		d['source id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['destination_id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['cipher_type'] = mk_int(bits[:2])
		d['key_id'] = mk_int(bits[2:8])
	elif msg_type == 0x39:	# SDCALL_REQ_USERDATA
		assert len(bits) >= 64
		d['msg_type'] = 'SDCALL_REQ_USERDATA'
		bits = bits[8:]
		d['packet_frame'] = mk_int(bits[:4])
		d['block_number'] = mk_int(bits[4:8])
		bits = bits[8:]
		s = ''
		while len(bits):
			s += '%02x' % mk_int(bits[:8])
			bits = bits[8:]
		d['hexdata'] = s
	elif msg_type == 0x3b:	# SDCALL_RESP
		assert len(bits) >= 64
		d['msg_type'] = 'SDCALL_RESP'
		bits = bits[8:]
		d['option'] = mk_int(bits[:8])
		bits = bits[8:]
		d['call_type'] = mk_int(bits[:3])
		d['call_option'] = mk_int(bits[3:8])
		bits = bits[8:]
		d['source id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['destination_id'] = mk_int(bits[:16])
		bits = bits[16:]
		d['cause'] = mk_int(bits[:8])
		bits = bits[8:]
	else:	# msg type unhandled
		d['msg_type'] = 'UNSUPPORTED 0x%x' % (msg_type)
	return d
