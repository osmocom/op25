#! /usr/bin/env python

# Copyright 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018 Max H. Parke KA1RBI
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

import sys
import os
import time
import collections
import json
sys.path.append('tdma')
import lfsr
from tsvfile import make_config, load_tsv, id_registry, read_tags_file
from create_image import create_image

FILTERED_CC_EVENT = 'mot_grg_add_cmd grp_v_ch_grant_updt grp_v_ch_grant_updt_exp'.split()

def crc16(dat,len):	# slow version
    poly = (1<<12) + (1<<5) + (1<<0)
    crc = 0
    for i in range(len):
        bits = (dat >> (((len-1)-i)*8)) & 0xff
        for j in range(8):
            bit = (bits >> (7-j)) & 1
            crc = ((crc << 1) | bit) & 0x1ffff
            if crc & 0x10000:
                crc = (crc & 0xffff) ^ poly
    crc = crc ^ 0xffff
    return crc

def get_ordinals(s):
	t = 0
	if type(s) is not str and isinstance(s, bytes):
		for c in s:
			t = (t << 8) + c
	else:
		for c in s:
			t = (t << 8) + ord(c)
	return t

class trunked_system (object):
    def __init__(self, debug=0, config=None, send_event=None, nac=None):
        self.debug = debug
        self.freq_table = {}
        self.stats = {}
        self.stats['tsbks'] = 0
        self.stats['crc'] = 0
        self.tsbk_cache = {}
        self.secondary = {}
        self.adjacent = {}
        self.adjacent_data = {}
        self.rfss_syid = 0
        self.rfss_rfid = 0
        self.rfss_stid = 0
        self.rfss_chan = 0
        self.rfss_txchan = 0
        self.ns_syid = -1
        self.ns_wacn = -1
        self.ns_chan = 0
        self.voice_frequencies = {}
        self.blacklist = {}
        self.whitelist = None
        self.tgid_map = None
        self.unit_id_map = None
        self.offset = 0
        self.sysname = 0
        self.tgid_tags_tsv = ""
        self.unit_id_tags_tsv = ""

        self.trunk_cc = 0
        self.last_trunk_cc = 0
        self.cc_list = []
        self.cc_list_index = 0
        self.CC_HUNT_TIME = 5.0
        self.center_frequency = 0
        self.last_tsbk = 0
        self.cc_timeouts = 0
        self.next_hunt_cc = time.time() + 8.0
        self.last_voice_time = 0.0

        self.talkgroups = {}
        self.frequency_table = {}
        self.CALL_TIMEOUT = 0.7	# call expiration time (sec.)
        self.CHECK_INTERVAL = 0.1 # freq tracking check interval
        self.next_frequency_tracking_expire = 0
        if config:
            self.blacklist = config['blacklist']
            self.whitelist = config['whitelist']
            self.tgid_map  = config['tgid_map']
            self.unit_id_map  = config['unit_id_map']
            self.offset    = config['offset']
            self.sysname   = config['sysname']
            self.trunk_cc  = config['cclist'][0]	# TODO: scan thru list
            self.cc_list   = config['cclist']
            self.center_frequency = config['center_frequency']
            self.modulation = config['modulation']

        self.current_srcaddr = 0
        self.current_grpaddr = 0	# from P25 LCW
        self.current_alg = ""
        self.current_algid = 128
        self.current_keyid = 0
        self.send_event = send_event
        self.harris_sgs = {}
        self.nac = nac

    def to_dict(self):
        d = {}
        d['syid'] = self.rfss_syid
        d['sysname'] = self.sysname
        d['rfid'] = self.rfss_rfid
        d['stid'] = self.rfss_stid
        d['sysid'] = self.ns_syid
        d['rxchan'] = self.rfss_chan
        d['txchan'] = self.rfss_txchan
        d['wacn'] = self.ns_wacn
        d['secondary'] = [k for k in self.secondary.keys()]
        d['tsbks'] = self.stats['tsbks']
        d['frequencies'] = {}
        d['frequency_data'] = {}
        d['last_tsbk'] = self.last_tsbk
        d['srcaddr'] = self.current_srcaddr
        d['grpaddr'] = self.current_grpaddr
        d['algid'] = self.current_algid
        d['alg'] = self.current_alg
        d['keyid'] = self.current_keyid
        t = time.time()
        for f in self.voice_frequencies.keys():
            tgs = '%s %s' % (self.voice_frequencies[f]['tgid'][0], self.voice_frequencies[f]['tgid'][1])
            d['frequencies'][f] = 'voice frequency %f tgid(s) %s %4.1fs ago count %d' %  (f / 1000000.0, tgs, t - self.voice_frequencies[f]['time'], self.voice_frequencies[f]['counter'])

            d['frequency_data'][f] = {'tgids': self.voice_frequencies[f]['tgid'], 'last_activity': '%7.1f' % (t - self.voice_frequencies[f]['time']), 'counter': self.voice_frequencies[f]['counter']}
            for s in 'srcaddr tg_tag tg_color srcaddr_tag srcaddr_color'.split():
                d['frequency_data'][f][s] = self.voice_frequencies[f][s]
        d['adjacent_data'] = self.adjacent_data
        d['talkgroup_data'] = self.talkgroups
        self.frequency_tracking_expire(always=True)
        d['frequency_tracking'] = self.frequency_table
        d['harris_supergroups'] = self.harris_sgs
        return d

    def to_json(self):
        return json.dumps(self.to_dict())

    def to_string(self):
        s = []
        s.append('rf: syid %x rfid %d stid %d frequency %f uplink %f' % ( self.rfss_syid, self.rfss_rfid, self.rfss_stid, float(self.rfss_chan) / 1000000.0, float(self.rfss_txchan) / 1000000.0))
        s.append('net: syid %x wacn %x frequency %f' % ( self.ns_syid, self.ns_wacn, float(self.ns_chan) / 1000000.0))
        s.append('secondary control channel(s): %s' % ','.join(['%f' % (float(k) / 1000000.0) for k in self.secondary.keys()]))
        s.append('stats: tsbks %d crc %d' % (self.stats['tsbks'], self.stats['crc']))
        s.append('')
        t = time.time()
        for f in self.voice_frequencies:
            tgs = '%s %s' % (self.voice_frequencies[f]['tgid'][0], self.voice_frequencies[f]['tgid'][1])
            s.append('voice frequency %f tgid(s) %s %4.1fs ago count %d' %  (f / 1000000.0, tgs, t - self.voice_frequencies[f]['time'], self.voice_frequencies[f]['counter']))
        s.append('')
        for table in self.freq_table:
            a = self.freq_table[table]['frequency'] / 1000000.0
            b = self.freq_table[table]['step'] / 1000000.0
            c = self.freq_table[table]['offset'] / 1000000.0
            s.append('tbl-id: %x frequency: %f step %f offset %f' % ( table, a,b,c))
            #self.freq_table[table]['frequency'] / 1000000.0, self.freq_table[table]['step'] / 1000000.0, self.freq_table[table]['offset']) / 1000000.0)
        for f in self.adjacent:
            s.append('adjacent %f: %s' % (float(f) / 1000000.0, self.adjacent[f]))
        return '\n'.join(s)

    def post_event(self, d):
        if self.send_event is None:
            return
        if d['cc_event'] in FILTERED_CC_EVENT:
            return
        d['json_type'] = 'cc_event'
        d['sysid'] = self.rfss_syid if self.rfss_syid else 0
        d['sysname'] = self.sysname
        d['time'] = time.time()
        d['nac'] = self.nac
        self.send_event(d)

    def mk_tg_dict(self, tgid):
        return {'tg_id': tgid, 'tag': self.get_tag(tgid), 'priority': self.get_prio(tgid), 'color': self.get_tag_color(tgid)}

    def mk_src_dict(self, srcaddr):
        return {'unit_id': srcaddr, 'tag': self.get_unit_id_tag(srcaddr), 'color': self.get_unit_id_color(srcaddr)}

    def get_tdma_slot(self, id):
        table = (id >> 12) & 0xf
        channel = id & 0xfff
        if table not in self.freq_table:
            return None
        if 'tdma' not in self.freq_table[table]:
            return None
        return channel & 1

# return frequency in Hz
    def channel_id_to_frequency(self, id):
        table = (id >> 12) & 0xf
        channel = id & 0xfff
        if table not in self.freq_table:
            return None
        if 'tdma' not in self.freq_table[table]:
            return self.freq_table[table]['frequency'] + self.freq_table[table]['step'] * channel
        return self.freq_table[table]['frequency'] + self.freq_table[table]['step'] * int(channel / self.freq_table[table]['tdma'])

    def channel_id_to_string(self, id):
        f = self.channel_id_to_frequency(id)
        if f is None:
            return "ID-0x%x" % (id)
        return "%f" % (f / 1000000.0)

    def get_unit_id_color(self, unit_id):
        if not unit_id:
            return 0
        elif self.unit_id_map is None:
            return 0
        return self.unit_id_map.get_color(unit_id)

    def get_unit_id_tag(self, unit_id):
        if not unit_id:
            return ""
        elif self.unit_id_map is None:
            return "Unit %d" % unit_id
        return self.unit_id_map.get_tag(unit_id)

    def get_tag(self, tgid):
        if not tgid:
            return ""
        elif self.tgid_map is None:
            return "Talkgroup %d" % tgid
        return self.tgid_map.get_tag(tgid)

    def get_tag_color(self, tgid):
        if not tgid:
            return 0
        elif self.tgid_map is None:
            return 0
        return self.tgid_map.get_color(tgid) % 100

    # the third col in the tsv file performs two separate roles
    # low-order 2 decimal digits are taken as the tag color code
    # remaining upper digits are priority - this is incompatibile
    # with previous tsv files (if priorities are in use).
    def get_prio(self, tgid):
        if not tgid:
            return 0
        elif self.tgid_map is None:
            return 0
        return int(self.tgid_map.get_color(tgid) // 100)

    def end_call(self, call, code):
        d = {'cc_event': 'end_call', 'code': code, 'srcaddr': call['srcaddr'], 'tgid': call['tgid'], 'duration': call['end_time'] - call['start_time'], 'count': call['count'], 'opcode': -1 }
        self.post_event(d)
        return

    def frequency_tracking_expire(self, always=False):
        current_time = time.time()
        if current_time < self.next_frequency_tracking_expire and not always:
            return
        self.next_frequency_tracking_expire = current_time + self.CHECK_INTERVAL
        for f in self.frequency_table.keys():
            freq = self.frequency_table[f]
            for i in range(len(freq['calls'])):
                call = freq['calls'][i]
                if call is not None and call['end_time'] == 0 and call['last_active'] + self.CALL_TIMEOUT < current_time:
                    call['end_time'] = current_time
                    self.end_call(call, 1)

    def frequency_tracking(self, frequency, tgid, tdma_slot, srcaddr, protected):
        current_time = time.time()
        is_tdma = tdma_slot is not None
        slot = tdma_slot if is_tdma else 0
        if frequency not in self.frequency_table.keys():
            self.frequency_table[frequency] = {'counter':0,
                                               'calls': [None,None],
                                               'tgids': [None,None],
                                               'last_active': current_time}
            self.frequency_table[frequency]['tdma'] = is_tdma
            call = {'srcaddr': self.mk_src_dict(srcaddr),
                    'protected': protected,
                    'tgid': self.mk_tg_dict(tgid),
                    'count': 0,
                    'start_time': current_time,
                    'last_active': current_time,
                    'end_time': 0}

            self.frequency_table[frequency]['tgids'][slot] = tgid
            self.frequency_table[frequency]['calls'][slot] = call
            return

        self.frequency_table[frequency]['counter'] += 1
        self.frequency_table[frequency]['last_active'] = current_time
        found = 0
        for f in self.frequency_table.keys():
            freq = self.frequency_table[f]
            for i in range(len(freq['tgids'])):
                tg   = freq['tgids'][i]
                call = freq['calls'][i]
                if tg is None or call is None or tg != tgid:
                    continue
                # general housekeeping: expire calls
                if call['end_time'] == 0 and call['last_active'] + self.CALL_TIMEOUT < current_time:
                    call['end_time'] = current_time
                    self.end_call(call, 2)
                if f == frequency and freq['tdma'] == is_tdma and i == slot :
                    found = 1
                    call['last_active'] = current_time
                    call['end_time'] = 0
                    call['count'] += 1
                    if srcaddr is not None:
                        call['srcaddr'] = self.mk_src_dict(srcaddr)
                    if protected is not None:
                        call['protected'] = protected
                else:	# found other entry with matching tgid but freq and/or tdma is wrong
                    if call['end_time'] == 0:
                        call['end_time'] = current_time
                        self.end_call(call, 3)
        if found:
            return

        call = {'srcaddr': self.mk_src_dict(srcaddr),
                'protected': protected,
                'tgid': self.mk_tg_dict(tgid),
                'count': 0,
                'start_time': current_time,
                'last_active': current_time,
                'end_time': 0}
        self.frequency_table[frequency]['tdma'] = is_tdma
        self.frequency_table[frequency]['tgids'][slot] = tgid
        self.frequency_table[frequency]['calls'][slot] = call
        if not is_tdma:
            self.frequency_table[frequency]['tgids'][1] = None
            call = self.frequency_table[frequency]['calls'][1]
            if call and call['end_time'] == 0:
                call['end_time'] = current_time
                self.end_call(call, 4)
            self.frequency_table[frequency]['calls'][1] = None

    def update_talkgroup(self, frequency, tgid, tdma_slot, srcaddr):
        if self.debug >= 5:
            sys.stderr.write('%f set tgid=%s, srcaddr=%s\n' % (time.time(), tgid, srcaddr))

        if tgid not in self.talkgroups:
            self.talkgroups[tgid] = {'counter':0}
            if self.debug >= 5:
                sys.stderr.write('%f new tgid: %s %s prio %d\n' % (time.time(), tgid, self.get_tag(tgid), self.get_prio(tgid)))
        self.talkgroups[tgid]['time'] = time.time()
        self.talkgroups[tgid]['frequency'] = frequency
        self.talkgroups[tgid]['tdma_slot'] = tdma_slot
        self.talkgroups[tgid]['prio'] = self.get_prio(tgid)
        self.talkgroups[tgid]['tag_color'] = self.get_tag_color(tgid)

        if srcaddr is None or not srcaddr:
            self.talkgroups[tgid]['srcaddr'] = 0
            self.talkgroups[tgid]['srcaddr_tag'] = ""
            self.talkgroups[tgid]['srcaddr_color'] = 0
        else:
            self.talkgroups[tgid]['srcaddr'] = srcaddr
            self.talkgroups[tgid]['srcaddr_tag'] = self.get_unit_id_tag(srcaddr)
            self.talkgroups[tgid]['srcaddr_color'] = self.get_unit_id_color(srcaddr)

    def update_voice_frequency(self, frequency, tgid=None, tdma_slot=None, srcaddr=None, protected=None):
        if not frequency:	# e.g., channel identifier not yet known
            return
        self.frequency_tracking(frequency, tgid, tdma_slot, srcaddr, protected)
        self.update_talkgroup(frequency, tgid, tdma_slot, srcaddr)
        if frequency not in self.voice_frequencies:
            self.voice_frequencies[frequency] = {'counter':0}
            sorted_freqs = collections.OrderedDict(sorted(self.voice_frequencies.items()))
            self.voice_frequencies = sorted_freqs
            if self.debug >= 5:
                sys.stderr.write('%f new freq: %f\n' % (time.time(), frequency/1000000.0))

        if tdma_slot is None:
            tdma_slot = 0

        for s in 'tgid srcaddr tg_tag tg_color srcaddr_tag srcaddr_color'.split():
            if s not in self.voice_frequencies[frequency].keys():
                self.voice_frequencies[frequency][s] = [None, None]

        self.voice_frequencies[frequency]['tgid'][tdma_slot] = tgid
        self.voice_frequencies[frequency]['counter'] += 1
        self.voice_frequencies[frequency]['time'] = time.time()
        self.voice_frequencies[frequency]['tg_tag'][tdma_slot] = self.get_tag(tgid)
        self.voice_frequencies[frequency]['tg_color'][tdma_slot] = self.get_tag_color(tgid)
        if srcaddr is not None:
            self.voice_frequencies[frequency]['srcaddr'][tdma_slot] = srcaddr
            self.voice_frequencies[frequency]['srcaddr_tag'][tdma_slot] = self.get_unit_id_tag(srcaddr)
            self.voice_frequencies[frequency]['srcaddr_color'][tdma_slot] = self.get_unit_id_color(srcaddr)

    def get_updated_talkgroups(self, start_time):
        return [tgid for tgid in self.talkgroups if (
                       self.talkgroups[tgid]['time'] >= start_time and
                       tgid not in self.blacklist and
                       not (self.whitelist and tgid not in self.whitelist))]

    def blacklist_update(self, start_time):
        expired_tgs = [tg for tg in self.blacklist.keys()
                            if self.blacklist[tg] is not None
                            and self.blacklist[tg] < start_time]
        for tg in expired_tgs:
            self.blacklist.pop(tg)

    def find_talkgroup(self, start_time, tgid=None, hold=False):
        tgt_tgid = None
        self.blacklist_update(start_time)

        if tgid is not None and tgid in self.talkgroups:
            tgt_tgid = tgid

        for active_tgid in self.talkgroups:
            if hold:
                break
            if self.talkgroups[active_tgid]['time'] < start_time:
                continue
            if active_tgid in self.blacklist:
                continue
            if self.whitelist and active_tgid not in self.whitelist:
                continue
            if self.talkgroups[active_tgid]['tdma_slot'] is not None and (self.ns_syid < 0 or self.ns_wacn < 0):
                continue
            if tgt_tgid is None:
                tgt_tgid = active_tgid
            elif self.talkgroups[active_tgid]['prio'] < self.talkgroups[tgt_tgid]['prio']:
                tgt_tgid = active_tgid
                   
        if tgt_tgid is not None and self.talkgroups[tgt_tgid]['time'] >= start_time:
            return self.talkgroups[tgt_tgid]['frequency'], tgt_tgid, self.talkgroups[tgt_tgid]['tdma_slot'], self.talkgroups[tgt_tgid]['srcaddr']
        return None, None, None, None

    def dump_tgids(self):
        sys.stderr.write("Known tgids: { ")
        for tgid in sorted(self.talkgroups.keys()):
            sys.stderr.write("%d " % tgid);
        sys.stderr.write("}\n") 

    def add_blacklist(self, tgid, end_time=None):
        if not tgid:
            return
        self.blacklist[tgid] = end_time

    def decode_mbt_data(self, opcode, src, header, mbt_data):
        self.cc_timeouts = 0
        self.last_tsbk = time.time()
        updated = 0
        if self.debug > 10:
            sys.stderr.write('decode_mbt_data: %x %x\n' %(opcode, mbt_data))
        if opcode == 0x0:  # grp voice channel grant
            srcaddr = (header >> 48) & 0xffffff
            opts = (header >> 24) & 0xff
            ch1  = (mbt_data >> 64) & 0xffff
            ch2  = (mbt_data >> 48) & 0xffff
            ga   = (mbt_data >> 32) & 0xffff
            f = self.channel_id_to_frequency(ch1)
            if self.debug > 0 and src != srcaddr:
                sys.stderr.write('decode_mbt_data: grp_v_ch_grant: src %d does not match srcaddr %d\n' % (src, srcaddr))
            d = {'cc_event': 'grp_v_ch_grant_mbt', 'options': opts, 'frequency': f, 'group': self.mk_tg_dict(ga), 'srcaddr': self.mk_src_dict(srcaddr), 'opcode': opcode, 'tdma_slot': self.get_tdma_slot(ch1) }
            self.post_event(d)
            self.update_voice_frequency(f, tgid=ga, tdma_slot=self.get_tdma_slot(ch1), srcaddr=srcaddr, protected=opts&64 == 64)
            if f:
                updated += 1
            if self.debug > 10:
                sys.stderr.write('mbt00 voice grant ch1 %x ch2 %x addr 0x%x\n' %(ch1, ch2, ga))
        elif opcode == 0x3c:  # adjacent status
            syid = (header >> 48) & 0xfff
            rfid = (header >> 24) & 0xff
            stid = (header >> 16) & 0xff
            ch1  = (mbt_data >> 80) & 0xffff
            ch2  = (mbt_data >> 64) & 0xffff
            f1 = self.channel_id_to_frequency(ch1)
            f2 = self.channel_id_to_frequency(ch2)
            if f1 and f2:
                self.adjacent[f1] = 'rfid: %d stid:%d uplink:%f' % (rfid, stid, f2 / 1000000.0)
                self.adjacent_data[f1] = {'rfid': rfid, 'stid':stid, 'uplink': f2, 'table': None, 'sysid': syid}
            if self.debug > 10:
                sys.stderr.write('mbt3c adjacent sys %x rfid %x stid %x ch1 %x ch2 %x f1 %s f2 %s\n' % (syid, rfid, stid, ch1, ch2, self.channel_id_to_string(ch1), self.channel_id_to_string(ch2)))
        elif opcode == 0x3b:  # network status
            syid = (header >> 48) & 0xfff
            wacn = (mbt_data >> 76) & 0xfffff
            ch1  = (mbt_data >> 56) & 0xffff
            ch2  = (mbt_data >> 40) & 0xffff
            f1 = self.channel_id_to_frequency(ch1)
            f2 = self.channel_id_to_frequency(ch2)
            if f1 and f2:
                self.ns_syid = syid
                self.ns_wacn = wacn
                self.ns_chan = f1
            if self.debug > 10:
                sys.stderr.write('mbt3b net stat sys %x wacn %x ch1 %s ch2 %s\n' %(syid, wacn, self.channel_id_to_string(ch1), self.channel_id_to_string(ch2)))
        elif opcode == 0x3a:  # rfss status
            syid = (header >> 48) & 0xfff
            rfid = (mbt_data >> 88) & 0xff
            stid = (mbt_data >> 80) & 0xff
            ch1  = (mbt_data >> 64) & 0xffff
            ch2  = (mbt_data >> 48) & 0xffff
            f1 = self.channel_id_to_frequency(ch1)
            f2 = self.channel_id_to_frequency(ch2)
            if f1 and f2:
                self.rfss_syid = syid
                self.rfss_rfid = rfid
                self.rfss_stid = stid
                self.rfss_chan = f1
                self.rfss_txchan = f2
            if self.debug > 10:
                sys.stderr.write('mbt3a rfss stat sys %x rfid %x stid %x ch1 %s ch2 %s\n' %(syid, rfid, stid, self.channel_id_to_string(ch1), self.channel_id_to_string(ch2)))
        else:
            sys.stderr.write('decode_mbt_data(): received unsupported mbt opcode %x\n' % opcode)
        return updated

    def decode_tdma_blk(self, blk):
        self.stats['tsbks'] += 1
        op = (blk[0] >> 6) & 3
        moc = blk[0] & 0x3f
        if self.debug > 1:
            sys.stderr.write('tdma_cc: decode_blk: op %x moc %x\n' % (op, moc))
        if op == 1 and moc == 0x3c:	# adjacent
            msglen = 9
            msg = get_ordinals(blk[:msglen])
            syid = (msg >> 40) & 0xfff
            rfid = (msg >> 32) & 0xff
            stid = (msg >> 24) & 0xff
            ch1 = (msg >> 8) & 0xffff
            table = (ch1 >> 12) & 0xf
            cls = msg & 0xff
            print ('tdma adacent: %d %d %d %x' % (syid, rfid, stid, ch1))
            f1 = self.channel_id_to_frequency(ch1)
            if f1 and table in self.freq_table:
                self.adjacent[f1] = 'rfid: %d stid:%d uplink:%f tbl:%d sysid:0x%x' % (rfid, stid, (f1 + self.freq_table[table]['offset']) / 1000000.0, table, syid)
                self.adjacent_data[f1] = {'rfid': rfid, 'stid':stid, 'uplink': f1 + self.freq_table[table]['offset'], 'table': table, 'sysid':syid}
            if self.debug > 10:
                sys.stderr.write('tsbk3c adjacent: rfid %x stid %d ch1 %x(%s)\n' %(rfid, stid, ch1, self.channel_id_to_string(ch1)))
                if table in self.freq_table:
                    sys.stderr.write('tsbk3c : %s %s\n' % (self.freq_table[table]['frequency'] , self.freq_table[table]['step'] ))
        elif op == 1 and moc == 0x33:	# iden up tdma
            msglen = 9
            opcode = 0x33
            msg = get_ordinals(blk[:msglen])
            iden = (msg >> 60) & 0xf
            channel_type = (msg >> 56) & 0xf
            toff0 = (msg >> 42) & 0x3fff
            toff_sign = (toff0 >> 13) & 1
            toff = toff0 & 0x1fff
            if toff_sign == 0:
                toff = 0 - toff
            spac = (msg >> 32) & 0x3ff
            f1 = (msg) & 0xffffffff
            slots_per_carrier = [1,1,1,2,4,2]
            self.freq_table[iden] = {}
            self.freq_table[iden]['offset'] = toff * spac * 125
            self.freq_table[iden]['step'] = spac * 125
            self.freq_table[iden]['frequency'] = f1 * 5
            self.freq_table[iden]['tdma'] = slots_per_carrier[channel_type]
            d = {'cc_event': 'iden_up_tdma', 'iden': iden, 'offset': self.freq_table[iden]['offset'], 'step':  self.freq_table[iden]['step'], 'freq': self.freq_table[iden]['frequency'], 'slots':  self.freq_table[iden]['tdma'], 'opcode': opcode }
            self.post_event(d)          
            if self.debug > 10:
                sys.stderr.write('tsbk33 iden up tdma id %d f %d offset %d spacing %d slots/carrier %d\n' % (iden, self.freq_table[iden]['frequency'], self.freq_table[iden]['offset'], self.freq_table[iden]['step'], self.freq_table[iden]['tdma']))
        elif op == 1 and moc == 0x3b:	# network status
            msglen = 11
            opcode = 0x3b
            msg = get_ordinals(blk[:msglen])
            wacn = (msg >> 52) & 0xfffff
            syid = (msg >> 40) & 0xfff
            ch1  = (msg >> 24) & 0xffff
            color  = (msg      ) & 0xfff
            sys.stderr.write('tsbk3b net stat: color: 0x%x\n' % color)
            f1 = self.channel_id_to_frequency(ch1)
            if f1:
                self.ns_syid = syid
                self.ns_wacn = wacn
                self.ns_chan = f1
            if self.debug > 10:
                sys.stderr.write('tsbk3b net stat: wacn %x syid %x ch1 %x(%s)\n' %(wacn, syid, ch1, self.channel_id_to_string(ch1)))
        elif op == 1 and moc == 0x3a:	# rfss status
            msglen = 9
            opcode = 0x3a
            msg = get_ordinals(blk[:msglen])
            syid = (msg >> 40) & 0xfff
            rfid = (msg >> 32) & 0xff
            stid = (msg >> 24) & 0xff
            chan = (msg >> 8) & 0xffff
            f1 = self.channel_id_to_frequency(chan)
            if f1:
                self.rfss_syid = syid
                self.rfss_rfid = rfid
                self.rfss_stid = stid
                self.rfss_chan = f1
                self.rfss_txchan = f1 + self.freq_table[chan >> 12]['offset']
            if self.debug > 10:
                sys.stderr.write('tsbk3a rfss status: syid: %x rfid %x stid %d ch1 %x(%s)\n' %(syid, rfid, stid, chan, self.channel_id_to_string(chan)))
        elif op == 1 and moc == 0x39:	# secondary cc
            msglen = 9
            opcode = 0x39
            msg = get_ordinals(blk[:msglen])
            rfid = (msg >> 56) & 0xff
            stid = (msg >> 48) & 0xff
            ch1  = (msg >> 32) & 0xffff
            ch2  = (msg >> 8) & 0xffff
            f1 = self.channel_id_to_frequency(ch1)
            f2 = self.channel_id_to_frequency(ch2)
            if f1 and f2:
                self.secondary[ f1 ] = 1
                self.secondary[ f2 ] = 1
                sorted_freqs = collections.OrderedDict(sorted(self.secondary.items()))
                self.secondary = sorted_freqs
            if self.debug > 10:
                sys.stderr.write('tsbk39 secondary cc: rfid %x stid %d ch1 %x(%s) ch2 %x(%s)\n' %(rfid, stid, ch1, self.channel_id_to_string(ch1), ch2, self.channel_id_to_string(ch2)))
        elif op == 1 and moc == 0x3d:	# iden_up
            msglen = 9
            opcode = 0x3d
            msg = get_ordinals(blk[:msglen])
            iden = (msg >> 60) & 0xf
            bw   = (msg >> 51) & 0x1ff
            toff0 = (msg >> 42) & 0x1ff
            spac = (msg >> 32) & 0x3ff
            freq =  msg        & 0xffffffff
            toff_sign = (toff0 >> 8) & 1
            toff = toff0 & 0xff
            if toff_sign == 0:
                toff = 0 - toff
            txt = ["mob xmit < recv", "mob xmit > recv"]
            self.freq_table[iden] = {}
            self.freq_table[iden]['offset'] = toff * 250000
            self.freq_table[iden]['step'] = spac * 125
            self.freq_table[iden]['frequency'] = freq * 5
            d = {'cc_event': 'iden_up', 'iden': iden, 'offset': self.freq_table[iden]['offset'], 'step':  self.freq_table[iden]['step'], 'freq': self.freq_table[iden]['frequency'], 'opcode': opcode }
            self.post_event(d)
            if self.debug > 10:
                sys.stderr.write('tsbk3d iden id %d toff %f spac %f freq %f\n' % (iden, toff * 0.25, spac * 0.125, freq * 0.000005))
        else:
            msglen = -1
            if self.debug > 0:
                sys.stderr.write ('tdma_cc unknown request: %x %x %02x %02x %02x\n' % (op, moc, blk[0], blk[1], blk[2] ))
        return msglen

    def decode_tdma_cc(self, blk):
        rc = self.decode_tdma_blk(blk)
        # TODO: Attempt to decode remaining half? 

    def decode_tsbk_harris(self, tsbk, opcode, mfrid):
        HARRIS_SGS_EXPIRES = 5.0	# sec.
        updated = 0
        if opcode != 0x30: # GRG_EXENC_CMD
            sys.stderr.write('decode_tsbk: unsupported opcode %02x mfrid %02x\n' % (opcode, mfrid))
            return updated
        grg_options = (tsbk >> 72) & 0xff
        opt_2way = (grg_options & 0x80) == 0
        opt_group = (grg_options & 0x40) != 0
        opt_act = (grg_options & 0x20) != 0
        opt_ssn = grg_options & 0x1f
        sg = (tsbk >> 56) & 0xffff
        keyid = (tsbk >> 40) & 0xffff
        target = (tsbk >> 16) & 0xffffff
        d = {'cc_event': 'grg_exenc_cmd', 'mfrid': mfrid, 'opt_2way': opt_2way, 'opt_group': opt_group, 'opt_act': opt_act, 'opt_ssn': opt_ssn, 'sg': self.mk_tg_dict(sg), 'keyid': keyid}
        if opt_group: # target is a group
            algid = (target >> 16) & 0xff
            target = target & 0xffff
            d['target_group'] = self.mk_tg_dict(target)
        else: # target is a subscriber unit id
            algid = 128
            d['target_unit'] = self.mk_src_dict(target)
        d['algid'] = algid
        if opt_act and opt_group:	# only group id type supported
            sgkey = '%d-%d' % (sg, target)
            self.harris_sgs[sgkey] = {'supergroup': self.mk_tg_dict(sg), 'target_group': self.mk_tg_dict(target), 'algid': algid, 'keyid': keyid, 'expires': time.time() + HARRIS_SGS_EXPIRES}
        return updated

    def decode_tsbk_mot(self, tsbk, opcode, mfrid):
        updated = 0
        if opcode == 0x00: # MOT_GRG_ADD_CMD
            sg  = (tsbk >> 64) & 0xffff
            ga1   = (tsbk >> 48) & 0xffff
            ga2   = (tsbk >> 32) & 0xffff
            ga3   = (tsbk >> 16) & 0xffff
            d = {'cc_event': 'mot_grg_add_cmd', 'mfrid': mfrid, 'sg': self.mk_tg_dict(sg), 'ga1': self.mk_tg_dict(ga1), 'ga2': self.mk_tg_dict(ga2), 'ga3': self.mk_tg_dict(ga3), 'opcode': opcode }
            self.post_event(d)
            if self.debug > 10:
                sys.stderr.write('MOT_GRG_ADD_CMD(0x00): sg:%d ga1:%d ga2:%d ga3:%d\n' % (sg, ga1, ga2, ga3))
        elif opcode == 0x01: #MOT_GRG_DEL_CMD
            sg  = (tsbk >> 64) & 0xffff
            ga1   = (tsbk >> 48) & 0xffff
            ga2   = (tsbk >> 32) & 0xffff
            ga3   = (tsbk >> 16) & 0xffff
            d = {'cc_event': 'mot_grg_del_cmd', 'mfrid': mfrid, 'sg': self.mk_tg_dict(sg), 'ga1': self.mk_tg_dict(ga1), 'ga2': self.mk_tg_dict(ga2), 'ga3': self.mk_tg_dict(ga3), 'opcode': opcode }
            self.post_event(d)
            if self.debug > 10:
                sys.stderr.write('MOT_GRG_DEL_CMD(0x01): sg:%d ga1:%d ga2:%d ga3:%d\n' % (sg, ga1, ga2, ga3))
        elif opcode == 0x02: # MOT_GRG_CN_CRANT
            ch  = (tsbk >> 56) & 0xffff
            sg  = (tsbk >> 40) & 0xffff
            sa  = (tsbk >> 16) & 0xffffff
            f = self.channel_id_to_frequency(ch)
            d = {'cc_event': 'mot_grg_cn_grant', 'mfrid': mfrid, 'frequency': f, 'sg': self.mk_tg_dict(sg), 'sa': self.mk_src_dict(sa), 'opcode': opcode }
            self.post_event(d)
            self.update_voice_frequency(f, tgid=sg, tdma_slot=self.get_tdma_slot(ch), srcaddr=sa)
            if f:
                updated += 1
            if self.debug > 10:
                sys.stderr.write('MOT_GRG_CN_GRANT(0x02): freq %s sg:%d sa:%d\n' % (self.channel_id_to_string(ch), sg, sa))
        elif opcode == 0x03: #MOT_GRG_CN_GRANT_UPDT
            ch1   = (tsbk >> 64) & 0xffff
            sg1  = (tsbk >> 48) & 0xffff
            ch2   = (tsbk >> 32) & 0xffff
            sg2  = (tsbk >> 16) & 0xffff
            f1 = self.channel_id_to_frequency(ch1)
            f2 = self.channel_id_to_frequency(ch2)
            d = {'cc_event': 'mot_grg_cn_grant_updt', 'mfrid': mfrid, 'frequency1': f1, 'sg1': self.mk_tg_dict(sg1), 'opcode': opcode }
            self.update_voice_frequency(f1, tgid=sg1, tdma_slot=self.get_tdma_slot(ch1))
            if f1 != f2:
                self.update_voice_frequency(f2, tgid=sg2, tdma_slot=self.get_tdma_slot(ch2))
                d['sg2'] = self.mk_tg_dict(sg2)
                d['frequency2'] = f2
            self.post_event(d)
            if f1:
                updated += 1
            if f2:
                updated += 1
            if self.debug > 10:
                sys.stderr.write('MOT_GRG_CN_GRANT_UPDT(0x03): freq %s sg1:%d freq %s sg2:%d\n' % (self.channel_id_to_string(ch1), sg1, self.channel_id_to_string(ch2), sg2))
        else:
            if self.debug > 10:
                sys.stderr.write('decode_tsbk: unsupported opcode %02x mfrid %02x\n' % (opcode, mfrid))
        return updated

    def decode_tsbk(self, tsbk):
        self.cc_timeouts = 0
        self.last_tsbk = time.time()
        self.stats['tsbks'] += 1
        updated = 0
        tsbk = tsbk << 16	# for missing crc
        opcode = (tsbk >> 88) & 0x3f
        mfrid = (tsbk >> 80) & 0xff # mfrid
        if self.debug > 10:
            sys.stderr.write('TSBK: 0x%02x 0x%024x mfrid %02x\n' % (opcode, tsbk, mfrid))

        if mfrid == 0x90:
            return self.decode_tsbk_mot(tsbk, opcode, mfrid)
        elif mfrid == 0xa4:
            return self.decode_tsbk_harris(tsbk, opcode, mfrid)
        elif mfrid != 0:
            sys.stderr.write('unsupported tsbk mfrid: 0x%02x opcode 0x%02x\n' % (mfrid, opcode))
            return updated

        if opcode == 0x00:   # group voice chan grant
            opts  = (tsbk >> 72) & 0xff
            ch   = (tsbk >> 56) & 0xffff
            ga   = (tsbk >> 40) & 0xffff
            sa   = (tsbk >> 16) & 0xffffff
            f = self.channel_id_to_frequency(ch)
            d = {'cc_event': 'grp_v_ch_grant', 'mfrid': mfrid, 'options': opts, 'frequency': f, 'group': self.mk_tg_dict(ga), 'srcaddr': self.mk_src_dict(sa), 'opcode': opcode, 'tdma_slot': self.get_tdma_slot(ch) }
            self.post_event(d)
            self.update_voice_frequency(f, tgid=ga, tdma_slot=self.get_tdma_slot(ch), srcaddr=sa, protected=opts&64 == 64)
            if f:
                updated += 1
            if self.debug > 10:
                sys.stderr.write('tsbk00 grant freq %s ga %d sa %d\n' % (self.channel_id_to_string(ch), ga, sa))
        elif opcode == 0x02:   # group voice chan grant update
            ch1  = (tsbk >> 64) & 0xffff
            ga1  = (tsbk >> 48) & 0xffff
            ch2  = (tsbk >> 32) & 0xffff
            ga2  = (tsbk >> 16) & 0xffff
            f1 = self.channel_id_to_frequency(ch1)
            f2 = self.channel_id_to_frequency(ch2)
            d = {'cc_event': 'grp_v_ch_grant_updt', 'mfrid': mfrid, 'frequency1': f1, 'group1': self.mk_tg_dict(ga1), 'opcode': opcode, 'tdma_slot': self.get_tdma_slot(ch1) }
            self.update_voice_frequency(f1, tgid=ga1, tdma_slot=self.get_tdma_slot(ch1))
            if f1 != f2:
                self.update_voice_frequency(f2, tgid=ga2, tdma_slot=self.get_tdma_slot(ch2))
                d['frequency2'] = f2
                d['group2'] = self.mk_tg_dict(ga2)
            if f1:
                updated += 1
            if f2:
                updated += 1
            self.post_event(d)
            if self.debug > 10:
                sys.stderr.write('tsbk02 grant update: chan %s %d %s %d\n' %(self.channel_id_to_string(ch1), ga1, self.channel_id_to_string(ch2), ga2))
        elif opcode == 0x03:   # group voice chan grant update exp : TIA.102-AABC-B-2005 page 56
            opts  = (tsbk >> 72) & 0xff
            ch1  = (tsbk >> 48) & 0xffff
            ch2   = (tsbk >> 32) & 0xffff
            ga  = (tsbk >> 16) & 0xffff
            f = self.channel_id_to_frequency(ch1)
            d = {'cc_event': 'grp_v_ch_grant_updt_exp', 'mfrid': mfrid, 'options': opts, 'frequency': f, 'group': self.mk_tg_dict(ga), 'opcode': opcode, 'tdma_slot': self.get_tdma_slot(ch1) }
            self.post_event(d)
            self.update_voice_frequency(f, tgid=ga, tdma_slot=self.get_tdma_slot(ch1))
            if f:
                updated += 1
            if self.debug > 10:
                sys.stderr.write('tsbk03: freq-t %s freq-r %s ga:%d\n' % (self.channel_id_to_string(ch1), self.channel_id_to_string(ch2), ga))

        elif opcode == 0x16:   # sndcp data ch
            ch1  = (tsbk >> 48) & 0xffff
            ch2  = (tsbk >> 32) & 0xffff
            if self.debug > 10:
                sys.stderr.write('tsbk16 sndcp data ch: chan %x %x\n' % (ch1, ch2))
        elif opcode == 0x34:   # iden_up vhf uhf
            iden = (tsbk >> 76) & 0xf
            bwvu = (tsbk >> 72) & 0xf
            toff0 = (tsbk >> 58) & 0x3fff
            spac = (tsbk >> 48) & 0x3ff
            freq = (tsbk >> 16) & 0xffffffff
            toff_sign = (toff0 >> 13) & 1
            toff = toff0 & 0x1fff
            if toff_sign == 0:
                toff = 0 - toff
            txt = ["mob Tx-", "mob Tx+"]
            self.freq_table[iden] = {}
            self.freq_table[iden]['offset'] = toff * spac * 125
            self.freq_table[iden]['step'] = spac * 125
            self.freq_table[iden]['frequency'] = freq * 5
            d = {'cc_event': 'iden_up_vu', 'iden': iden, 'bwvu': bwvu, 'offset': self.freq_table[iden]['offset'], 'step':  self.freq_table[iden]['step'], 'freq': self.freq_table[iden]['frequency'], 'opcode': opcode }
            self.post_event(d)                          
            if self.debug > 10:
                sys.stderr.write('tsbk34 iden vhf/uhf id %d toff %f spac %f freq %f [%s]\n' % (iden, toff * spac * 0.125 * 1e-3, spac * 0.125, freq * 0.000005, txt[toff_sign]))
        elif opcode == 0x33:   # iden_up_tdma
            iden = (tsbk >> 76) & 0xf
            channel_type = (tsbk >> 72) & 0xf
            toff0 = (tsbk >> 58) & 0x3fff
            spac = (tsbk >> 48) & 0x3ff
            toff_sign = (toff0 >> 13) & 1
            toff = toff0 & 0x1fff
            if toff_sign == 0:
                toff = 0 - toff
            f1   = (tsbk >> 16) & 0xffffffff
            slots_per_carrier = [1,1,1,2,4,2]
            self.freq_table[iden] = {}
            self.freq_table[iden]['offset'] = toff * spac * 125
            self.freq_table[iden]['step'] = spac * 125
            self.freq_table[iden]['frequency'] = f1 * 5
            self.freq_table[iden]['tdma'] = slots_per_carrier[channel_type]
            d = {'cc_event': 'iden_up_tdma', 'iden': iden, 'offset': self.freq_table[iden]['offset'], 'step':  self.freq_table[iden]['step'], 'freq': self.freq_table[iden]['frequency'], 'slots':  self.freq_table[iden]['tdma'], 'opcode': opcode }
            self.post_event(d)          
            if self.debug > 10:
                sys.stderr.write('tsbk33 iden up tdma id %d f %d offset %d spacing %d slots/carrier %d\n' % (iden, self.freq_table[iden]['frequency'], self.freq_table[iden]['offset'], self.freq_table[iden]['step'], self.freq_table[iden]['tdma']))
        elif opcode == 0x3d:   # iden_up
            iden = (tsbk >> 76) & 0xf
            bw   = (tsbk >> 67) & 0x1ff
            toff0 = (tsbk >> 58) & 0x1ff
            spac = (tsbk >> 48) & 0x3ff
            freq = (tsbk >> 16) & 0xffffffff
            toff_sign = (toff0 >> 8) & 1
            toff = toff0 & 0xff
            if toff_sign == 0:
                toff = 0 - toff
            txt = ["mob xmit < recv", "mob xmit > recv"]
            self.freq_table[iden] = {}
            self.freq_table[iden]['offset'] = toff * 250000
            self.freq_table[iden]['step'] = spac * 125
            self.freq_table[iden]['frequency'] = freq * 5
            d = {'cc_event': 'iden_up', 'iden': iden, 'offset': self.freq_table[iden]['offset'], 'step':  self.freq_table[iden]['step'], 'freq': self.freq_table[iden]['frequency'], 'opcode': opcode }
            self.post_event(d)
            if self.debug > 10:
                sys.stderr.write('tsbk3d iden id %d toff %f spac %f freq %f\n' % (iden, toff * 0.25, spac * 0.125, freq * 0.000005))
        elif opcode == 0x3a:   # rfss status
            syid = (tsbk >> 56) & 0xfff
            rfid = (tsbk >> 48) & 0xff
            stid = (tsbk >> 40) & 0xff
            chan = (tsbk >> 24) & 0xffff
            f1 = self.channel_id_to_frequency(chan)
            if f1:
                self.rfss_syid = syid
                self.rfss_rfid = rfid
                self.rfss_stid = stid
                self.rfss_chan = f1
                self.rfss_txchan = f1 + self.freq_table[chan >> 12]['offset']
            if self.debug > 10:
                sys.stderr.write('tsbk3a rfss status: syid: %x rfid %x stid %d ch1 %x(%s)\n' %(syid, rfid, stid, chan, self.channel_id_to_string(chan)))
        elif opcode == 0x39:   # secondary cc
            rfid = (tsbk >> 72) & 0xff
            stid = (tsbk >> 64) & 0xff
            ch1  = (tsbk >> 48) & 0xffff
            ch2  = (tsbk >> 24) & 0xffff
            f1 = self.channel_id_to_frequency(ch1)
            f2 = self.channel_id_to_frequency(ch2)
            if f1 and f2:
                self.secondary[ f1 ] = 1
                self.secondary[ f2 ] = 1
                sorted_freqs = collections.OrderedDict(sorted(self.secondary.items()))
                self.secondary = sorted_freqs
            if self.debug > 10:
                sys.stderr.write('tsbk39 secondary cc: rfid %x stid %d ch1 %x(%s) ch2 %x(%s)\n' %(rfid, stid, ch1, self.channel_id_to_string(ch1), ch2, self.channel_id_to_string(ch2)))
        elif opcode == 0x3b:   # network status
            wacn = (tsbk >> 52) & 0xfffff
            syid = (tsbk >> 40) & 0xfff
            ch1  = (tsbk >> 24) & 0xffff
            f1 = self.channel_id_to_frequency(ch1)
            if f1:
                self.ns_syid = syid
                self.ns_wacn = wacn
                self.ns_chan = f1
            if self.debug > 10:
                sys.stderr.write('tsbk3b net stat: wacn %x syid %x ch1 %x(%s)\n' %(wacn, syid, ch1, self.channel_id_to_string(ch1)))
        elif opcode == 0x3c:   # adjacent status
            syid = (tsbk >> 56) & 0xfff
            rfid = (tsbk >> 48) & 0xff
            stid = (tsbk >> 40) & 0xff
            ch1  = (tsbk >> 24) & 0xffff
            table = (ch1 >> 12) & 0xf
            f1 = self.channel_id_to_frequency(ch1)
            if f1 and table in self.freq_table:
                self.adjacent[f1] = 'rfid: %d stid:%d uplink:%f tbl:%d' % (rfid, stid, (f1 + self.freq_table[table]['offset']) / 1000000.0, table)
                self.adjacent_data[f1] = {'rfid': rfid, 'stid':stid, 'uplink': f1 + self.freq_table[table]['offset'], 'table': table, 'sysid':syid}
            if self.debug > 10:
                sys.stderr.write('tsbk3c adjacent: rfid %x stid %d ch1 %x(%s) sysid 0x%x\n' %(rfid, stid, ch1, self.channel_id_to_string(ch1), syid))
                if table in self.freq_table:
                    sys.stderr.write('tsbk3c : %s %s\n' % (self.freq_table[table]['frequency'] , self.freq_table[table]['step'] ))
        elif opcode == 0x20:   # ACK_RESP_FNE
            aiv = (tsbk >> 79) & 1
            ex  = (tsbk >> 78) & 1
            addl = (tsbk >> 40) & 0xffffffff
            wacn = None
            sysid = None
            srcaddr = None
            if ex:
                wacn = (addl > 12) & 0xfffff
                sysid = addl & 0xfff
            else:
                srcaddr = addl & 0xffffff
            target = (tsbk >> 16) & 0xffffff
            d = {'cc_event': 'ack_resp_fne', 'aiv': aiv, 'ex': ex, 'addl': addl, 'wacn': wacn, 'tsbk_sysid': sysid, 'source': self.mk_src_dict(srcaddr), 'target': self.mk_src_dict(target), 'opcode': opcode}
            self.post_event(d)
            if self.debug > 10:
                sys.stderr.write('tsbk20 ack_resp_fne: aiv %d ex %d wacn %s sysid %s src %s\n' % (aiv, ex, wacn, sysid, srcaddr))
        elif opcode == 0x27:   # DENY_RESP
            aiv = (tsbk >> 79) & 1
            reason = (tsbk >> 64) & 0xff
            addl = (tsbk >> 40) & 0xffffff
            target = (tsbk >> 16) & 0xffffff
            d = {'cc_event': 'deny_resp', 'aiv': aiv, 'reason': reason, 'additional': addl, 'target': self.mk_src_dict(target), 'opcode': opcode}
            self.post_event(d)
            if self.debug > 10:
                sys.stderr.write('tsbk27 deny_resp: aiv %d reason %02x additional %x target %d\n' % (aiv, reason, addl, target))
        elif opcode == 0x28:   # grp_aff_rsp
            lg     = (tsbk >> 79) & 0x01
            gav    = (tsbk >> 72) & 0x03
            aga    = (tsbk >> 56) & 0xffff
            ga     = (tsbk >> 40) & 0xffff
            ta     = (tsbk >> 16) & 0xffffff
            d = {'cc_event': 'grp_aff_resp', 'affiliation': ['local', 'global'][lg], 'group_aff_value': gav, 'announce_group': self.mk_tg_dict(aga), 'group': self.mk_tg_dict(ga), 'target': self.mk_src_dict(ta), 'opcode': opcode}
            self.post_event(d)
            if self.debug > 10:
                sys.stderr.write('tsbk28 grp_aff_resp: mfrid: 0x%x, gav: %d, aga: %d, ga: %d, ta: %d\n' % (mfrid, gav, aga, ga, ta))
        elif opcode == 0x2a:   # GRP_AFF_Q
            target = (tsbk >> 40) & 0xffffff
            source = (tsbk >> 16) & 0xffffff
            d = {'cc_event': 'grp_aff_q', 'source': self.mk_src_dict(source), 'target': self.mk_src_dict(target), 'opcode': opcode}
            self.post_event(d)
            if self.debug > 10:
                sys.stderr.write('tsbk2a grp_aff_q: mfrid: 0x%x, target %d source %d\n' % (mfrid, target, source))
        elif opcode == 0x2b:   # LOC_REG_RESP
            rv  = (tsbk >> 72) & 3
            ga  = (tsbk >> 56) & 0xffff
            rfss  = (tsbk >> 48) & 0xff
            siteid  = (tsbk >> 40) & 0xff
            target = (tsbk >> 16) & 0xffffff
            d = {'cc_event': 'loc_reg_resp', 'rv': rv, 'rfss': rfss, 'siteid': siteid, 'group': self.mk_tg_dict(ga), 'target': self.mk_src_dict(target), 'opcode': opcode}
            self.post_event(d)
            if self.debug > 10:
                sys.stderr.write('tsbk2b loc_reg_resp: mfrid: 0x%x, rv %d group %d rfss 0x%x siteid 0x%x target %d\n' % (mfrid, rv, ga, rfss, siteid, target))
        elif opcode == 0x2c:   # U_REG_RESP
            rv  = (tsbk >> 76) & 1
            sysid = (tsbk >> 64) & 0xfff
            target = (tsbk >> 40) & 0xffffff
            source = (tsbk >> 16) & 0xffffff
            d = {'cc_event': 'u_reg_resp', 'rv': rv, 'tsbk_sysid': sysid, 'source': self.mk_src_dict(source), 'target': self.mk_src_dict(target), 'opcode': opcode}
            self.post_event(d)
            if self.debug > 10:
                sys.stderr.write('tsbk2c u_reg_resp: mfrid: 0x%x, rv %d sysid %x target %d source %d\n' % (mfrid, rv, sysid, target, source))
        elif opcode == 0x2d:   # U_REG_CMD
            target = (tsbk >> 40) & 0xffffff
            source = (tsbk >> 16) & 0xffffff
            d = {'cc_event': 'u_reg_cmd', 'source': self.mk_src_dict(source), 'target': self.mk_src_dict(target), 'opcode': opcode}
            self.post_event(d)
            if self.debug > 10:
                sys.stderr.write('tsbk2d u_reg_cmd: mfrid: 0x%x, target %d source %d\n' % (mfrid, target, source))
        elif opcode == 0x2f:   # U_DE_REG_ACK
            wacn  = (tsbk >> 52) & 0xfffff
            sysid  = (tsbk >> 40) & 0xfff
            source = (tsbk >> 16) & 0xffffff
            d = {'cc_event': 'u_de_reg_ack', 'wacn': wacn, 'tsbk_sysid': sysid, 'source': self.mk_src_dict(source), 'opcode': opcode}
            self.post_event(d)
            if self.debug > 10:
                sys.stderr.write('tsbk2f u_de_reg_ack: mfrid: 0x%x, wacn 0x%x sysid 0x%x source %d\n' % (mfrid, wacn, sysid, source))

        elif opcode == 0x24:   # EXT_FNCT_CMD
            efclass = (tsbk >> 72) & 0xff
            efoperand = (tsbk >> 64) & 0xff
            efargs  = (tsbk >> 40) & 0xffffff
            target  = (tsbk >> 16) & 0xffffff
            d = {'cc_event': 'ext_fnct_cmd', 'mfrid': mfrid, 'efclass': efclass, 'efoperand': efoperand, 'efargs': self.mk_src_dict(efargs), 'target': target, 'opcode': opcode}
            self.post_event(d)
            if self.debug > 10:
                sys.stderr.write('tsbk24 ext_fnct_cmd: efclass %d efoperand %d efargs %s sysid %s target %s\n' % (efclass, efoperand, efargs, sysid, target))


        #else:
        #	sys.stderr.write('tsbk other %x\n' % opcode)
        return updated

    def hunt_cc(self, curr_time):
        # return True if a tune request for frequency=self.trunk_cc should be issued
        HUNT_HOLD_TIME = 8.0
        #if self.cc_timeouts < 6:
        #    return False
        if self.last_tsbk + HUNT_HOLD_TIME > time.time():
            return False
        if self.last_voice_time + HUNT_HOLD_TIME > time.time():
            return False
        if time.time() < self.next_hunt_cc:
            return False
        self.next_hunt_cc = time.time() + HUNT_HOLD_TIME
        self.cc_timeouts = 0
        self.cc_list_index += 1
        if self.cc_list_index >= len(self.cc_list):
            self.cc_list_index = 0
        self.trunk_cc = self.cc_list[self.cc_list_index]
        sys.stderr.write('%f %s: cycling to next trunk_cc: %s\n' % (curr_time, self.sysname, self.trunk_cc))
        if self.trunk_cc != self.last_trunk_cc:
            self.last_trunk_cc = self.trunk_cc
            if self.debug >=5:
                sys.stderr.write('%f %s: control channel change: %f\n' % (curr_time, self.sysname, self.trunk_cc / 1000000.0))
            return True
        return True

    def frequency_change_params(self, current_tgid, new_frequency, nac, new_slot, new_frequency_type, curr_time):
        params = {
                'freq':   new_frequency,
                'tgid':   current_tgid,
                'offset': self.offset,
                'tag':    self.get_tag(current_tgid),
                'nac':    nac,
                'system': self.sysname,
                'center_frequency': self.center_frequency,
                'tdma':   new_slot, 
                'wacn':   self.ns_wacn, 
                'sysid':  self.ns_syid,
                'srcaddr':  self.current_srcaddr,
                'grpaddr':  self.current_grpaddr,
                'alg':  self.current_alg,
                'algid':  self.current_algid,
                'channel_type':  new_frequency_type,
                'keyid':  self.current_keyid,
                'prio':   self.get_prio(current_tgid),
                'tag_color':   self.get_tag_color(current_tgid),
                'srcaddr_color': self.get_unit_id_color(self.current_srcaddr),
                'srcaddr_tag': self.get_unit_id_tag(self.current_srcaddr),
                'effective_time': curr_time }
        return params

class rx_ctl (object):
    def __init__(self, debug=0, frequency_set=None, conf_file=None, logfile_workers=None, send_event=None):
        class _states(object):
            ACQ = 0
            CC = 1
            TO_VC = 2
            VC = 3
        self.states = _states

        self.current_state = self.states.CC
        self.trunked_systems = {}
        self.frequency_set = frequency_set
        self.debug = debug
        self.tgid_hold = None
        self.tgid_hold_until = time.time()
        self.hold_mode = False
        self.TGID_HOLD_TIME = 2.0	# TODO: make more configurable
        self.TGID_SKIP_TIME = 1.0	# TODO: make more configurable
        self.current_nac = None
        self.current_id = 0
        self.current_tgid = None
        self.current_slot = None
        self.TSYS_HOLD_TIME = 3.0	# TODO: make more configurable
        self.wait_until = time.time()
        self.configs = {}
        self.nacs = []
        self.logfile_workers = logfile_workers
        self.active_talkgroups = {}
        self.working_frequencies = {}
        self.xor_cache = {}
        self.last_garbage_collect = 0
        self.last_command = {'command': None, 'time': time.time()}
        if self.logfile_workers:
            self.input_rate = self.logfile_workers[0]['demod'].input_rate
        self.enabled_nacs = None
        self.next_status_png = time.time()
        self.send_event = send_event
        self.status_msg = ''
        self.next_hunt_time = time.time()

        if conf_file:
            if conf_file.endswith('.tsv'):
                self.build_config_tsv(conf_file)
            elif conf_file.endswith('.json'):
                self.build_config_json(conf_file)
            else:
                self.build_config(conf_file)
            self.nacs = [int (x) for x in self.configs.keys()]
            self.current_nac = self.find_next_tsys()
            self.current_state = self.states.CC

            tsys = self.trunked_systems[self.current_nac]

            if self.logfile_workers and tsys.modulation == 'c4fm':
                for worker in self.logfile_workers:
                    worker['demod'].connect_chain('fsk4')

            self.set_frequency({
                'freq':   tsys.trunk_cc,
                'channel_type':   'cc',
                'tgid':   None,
                'offset': tsys.offset,
                'tag':    "",
                'nac':    self.current_nac,
                'system': tsys.sysname,
                'center_frequency': tsys.center_frequency,
                'tdma':   None, 
                'wacn':   None, 
                'sysid':  None,
                'prio':   0,
                'tag_color': None })

    def build_config_json(self, conf_file):
        d = json.loads(open(conf_file).read())
        chans = [x for x in d['channels'] if x['active'] and x['trunked']]
        self.configs = { chan['nac']: {'cclist':chan['cclist'],
                    'offset':0,
                    'blacklist': {int(tgid):None for tgid in chan['blacklist']},
                    'whitelist': {int(tgid):None for tgid in chan['whitelist']},
                    'sysname': chan['name'],
                    'center_frequency': chan['frequency'],
                    'modulation': chan['demod_type'],
                    'tgid_map': {int(tgid): chan['tgids'][tgid] for tgid in chan['tgids'].keys()}}
                  for chan in chans}
        for nac in self.configs.keys():
            self.add_trunked_system(nac)

    def set_frequency(self, params):
        frequency = params['freq']
        if frequency and self.frequency_set:
            self.frequency_set(params)

    def enable_status(self, s):
        if self.debug >= 10:
            sys.stderr.write('rx_ctl: enable_status: %s\n' % s)
        nacs = s.split(',')
        if s and len(nacs):
            nacs = [int(x) for x in nacs]
        else:
            sys.stderr.write('cannot disable all NACs - request ignored\n')
            return
        self.enabled_nacs = nacs

    def add_trunked_system(self, nac):
        assert nac not in self.trunked_systems	# duplicate nac not allowed
        cfg = None
        if nac in self.configs:
            cfg = self.configs[nac]
        self.trunked_systems[nac] = trunked_system(debug = self.debug, config=cfg, send_event=self.send_event, nac=nac)

    def build_config_tsv(self, tsv_filename):
        self.setup_config(load_tsv(tsv_filename))

    def build_config(self, config_filename):
        import ConfigParser
        config = ConfigParser.ConfigParser()
        config.read(config_filename)
        configs = {}
        for section in config.sections():
            nac = int(config.get(section, 'nac'), 0)	# nac required
            assert nac != 0				# nac=0 not allowed
            assert nac not in configs	# duplicate nac not allowed
            configs[nac] = {}
            for option in config.options(section):
                configs[nac][option] = config.get(section, option).lower()
            configs[nac]['sysname'] = section
        self.setup_config(configs)

    def reload_tags(self, nac):
        if nac not in self.trunked_systems.keys():
            return
        tsys = self.trunked_systems[nac]
        tgid_tags_file = self.configs[nac]['tgid_tags_file']
        new_reg = id_registry()
        read_tags_file(tgid_tags_file, new_reg)
        tsys.tgid_map = new_reg
        sys.stderr.write('reloaded %s nac 0x%x\n' % (tgid_tags_file, nac))
        unit_id_tags_file = self.configs[nac]['unit_id_tags_file']
        if unit_id_tags_file is None:
            return
        new_reg = id_registry()
        read_tags_file(unit_id_tags_file, new_reg)
        tsys.unit_id_map = new_reg
        sys.stderr.write('reloaded %s nac 0x%x\n' % (unit_id_tags_file, nac))

    def add_default_config(self, nac, cclist=[], offset=0, whitelist=None, blacklist={}, tgid_map=None, unit_id_map=None,sysname=None, center_frequency=None, modulation='cqpsk'):
        if nac in self.configs.keys():
            return
        if nac not in self.trunked_systems.keys():
            return
        tsys = self.trunked_systems[nac]
        if not tsys.rfss_chan:
            return
        if not tsys.ns_chan:
            return
        if tsys.ns_wacn < 0:
            return
        if tsys.ns_syid < 0:
            return
        if not sysname:
            sysname = 'NAC 0x%x' % nac
        if not cclist:
            cclist = [tsys.rfss_chan]
            cclist.extend(tsys.secondary.keys())
            tsys.cc_list = cclist
        self.configs[nac] = {'cclist':cclist, 'offset':offset, 'whitelist':whitelist, 'blacklist':blacklist, 'tgid_map':tgid_map, 'unit_id_map': unit_id_map, 'sysname': sysname, 'center_frequency': center_frequency, 'modulation':modulation}
        self.current_nac = nac
        self.current_state = self.states.CC
        if nac not in self.nacs:
            self.nacs.append(nac)

    def setup_config(self, configs):
        self.configs = make_config(configs)
        for nac in self.configs.keys():
            self.add_trunked_system(nac)

    def find_next_tsys(self):
        wrap = 0
        while True:
            self.current_id += 1
            if self.current_id >= len(self.nacs):
                if wrap:
                    break
                self.current_id = 0
                wrap = 1
            if self.enabled_nacs is not None and self.nacs[self.current_id] not in self.enabled_nacs:
                continue
            return self.nacs[self.current_id]
        return self.nacs[0]   ## should not occur

    def to_json(self):
        current_time = time.time()
        d = {'json_type': 'trunk_update'}
        for nac in self.trunked_systems.keys():
            d[nac] = self.trunked_systems[nac].to_dict()
            if nac in self.configs.keys() and 'tgid_tags_file' in self.configs[nac]:
                d[nac]['tgid_tags_file'] = self.configs[nac]['tgid_tags_file']
            if nac in self.configs.keys() and 'unit_id_tags_file' in self.configs[nac]:
                d[nac]['unit_id_tags_file'] = self.configs[nac]['unit_id_tags_file']
        d['data'] = {'last_command': self.last_command['command'],
                     'last_command_time': int(self.last_command['time'] - current_time),
                     'tgid_hold': self.tgid_hold,
                     'tgid_hold_until': int(self.tgid_hold_until - current_time),
                     'hold_mode': self.hold_mode}
        d['time'] = current_time
        return json.dumps(d)

    def make_status_png(self):
        PNG_UPDATE_INTERVAL = 1.0
        output_file = '../www/images/status.png'
        tmp_output_file = '../www/images/tmp-status.png'
        if time.time() < self.next_status_png:
            return
        self.next_status_png = time.time() + PNG_UPDATE_INTERVAL
        status_str = 'OP25-hls hacks (c) Copyright 2020, 2021, KA1RBI\n'
        status_str += self.status_msg
        status_str += self.to_string()
        status = status_str.split('\n')
        status = [s for s in status if not s.startswith('tbl-id')]
        create_image(status, imgfile=tmp_output_file, bgcolor="#c0c0c0", windowsize=(640,480))
        if not os.access(tmp_output_file, os.R_OK):
            return
        os.rename(tmp_output_file, output_file)

    def frequency_tracking_expire(self):
        for nac in self.trunked_systems.keys():
            self.trunked_systems[nac].frequency_tracking_expire()

    def in_voice_state(self):
        rc = self.current_state == self.states.TO_VC or self.current_state == self.states.VC
        return rc

    def dump_tgids(self):
        for nac in self.trunked_systems.keys():
            self.trunked_systems[nac].dump_tgids()

    def to_string(self):
        s = ''
        for nac in self.trunked_systems:
            s += '\n====== NAC 0x%x ====== %s ======\n' % (nac, self.trunked_systems[nac].sysname)
            s += self.trunked_systems[nac].to_string()
        return s

    def process_qmsg(self, msg):
        self.frequency_tracking_expire()
        if self.send_event is not None:
            self.send_event(None)	# periodically sends general status info 
        mtype = msg.type()
        updated = 0
        curr_time = time.time()
        msgtext = msg.to_string()
        aa55 = get_ordinals(msgtext[:2])
        if mtype >= 0 or mtype in [-1, -3, -5, -6]:
            assert aa55 == 0xaa55
            msgq_id = get_ordinals(msgtext[2:4])
            msgtext = msgtext[4:]
        else:
            assert aa55 != 0xaa55
            msgq_id = None
        if mtype == -3:		# P25 call signalling data
            if self.debug > 10:
                sys.stderr.write("%f process_qmsg: P25 info: %s\n" % (time.time(), msgtext))
            js = json.loads(msgtext)
            nac = js['nac']
            if nac != self.current_nac:
                sys.stderr.write('warning: nac mismatch: nac %x current_nac %x js %s\n' % (nac, self.current_nac, msgtext))
            #    return
            if nac not in self.trunked_systems.keys():
                return
            tsys = self.trunked_systems[nac]
            if self.current_state != self.states.CC:
                tsys.last_voice_time = curr_time
            if 'srcaddr' in js.keys():
                tsys.current_srcaddr = js['srcaddr']
            if 'grpaddr' in js.keys():
                tsys.current_grpaddr = js['grpaddr']
            if 'algid' in js.keys():
                tsys.current_algid = js['algid']
            if 'alg' in js.keys():
                tsys.current_alg = js['alg']
            if 'keyid' in js.keys():
                tsys.current_keyid = js['keyid']
            return
        elif mtype == -2:	# request from gui
            cmd = msgtext
            if self.debug > 10:
                sys.stderr.write('process_qmsg: command: %s\n' % cmd)
            self.update_state(cmd, curr_time, int(msg.arg1()))   # self.update_state(cmd, curr_time)
            return
        elif mtype == -1:	# timeout
            if self.debug > 0:
                sys.stderr.write('%f process_data_unit timeout, channel %s\n' % (time.time(), msgq_id))
            self.update_state('timeout', curr_time)
            if self.logfile_workers:
                self.logging_scheduler(curr_time)
            return
        elif mtype == -6:	# p25 tdma cc
            # nac is always 1st two bytes
            nac = get_ordinals(msgtext[:2])
            msgtext = msgtext[2:]
            if nac not in self.trunked_systems.keys():
                sys.stderr.write('tdma_cc received from unexpected NAC 0x%x\n' % nac)
                return
            tsys = self.trunked_systems[nac]
            m1 = msgtext[1]
            b1 = (m1 >> 7) & 1
            b2 = (m1 >> 6) & 1
            moc = m1 & 0x3f
            tsys.decode_tdma_cc(msgtext[1:])
            return
        elif mtype < 0:
            sys.stderr.write('unknown message type %d\n' % (mtype))
            return
        s = msgtext
        # nac is always 1st two bytes
        nac = get_ordinals(s[:2])
        if nac == 0xffff:
            sys.stderr.write('received invalid nac 0xffff, mtype %d msgq_id %s\n' % (mtype, msgq_id))
            return
        s = s[2:]
        if self.debug > 10:
            sys.stderr.write('nac %x type %d at %f state %d len %d\n' %(nac, mtype, time.time(), self.current_state, len(s)))
        if (mtype == 7 or mtype == 12) and nac not in self.trunked_systems:
            if not self.configs:
                # TODO: allow whitelist/blacklist rather than blind automatic-add
                self.add_trunked_system(nac)
            else:
                sys.stderr.write("%f NAC %x not configured\n" % (time.time(), nac))
                return
        if nac not in self.trunked_systems.keys():
            sys.stderr.write('received unknown nac 0x%x, mtype %d len configs %d msgq_id %d\n' % (nac, mtype, len(self.configs.keys()), msgq_id))
            return
        tsys = self.trunked_systems[nac]
        if mtype == 0 or mtype == 5 or mtype == 10:	# HDU or LDU1 or LDU2 i.e. voice
            if self.current_state != self.states.CC:
                tsys.last_voice_time = curr_time
        elif mtype == 7:	# trunk: TSBK
            t = get_ordinals(s)
            updated += tsys.decode_tsbk(t)
        elif mtype == 12:	# trunk: MBT
            s1 = s[:10]		# header without crc
            s2 = s[12:]
            header = get_ordinals(s1)
            mbt_data = get_ordinals(s2)

            fmt = (header >> 72) & 0x1f
            sap = (header >> 64) & 0x3f
            src = (header >> 48) & 0xffffff
            if fmt != 0x17: # only Extended Format MBT presently supported
                return

            opcode = (header >> 16) & 0x3f
            if self.debug > 10:
                sys.stderr.write('type %d at %f state %d len %d/%d opcode %x [%x/%x]\n' %(mtype, time.time(), self.current_state, len(s1), len(s2), opcode, header,mbt_data))
            updated += tsys.decode_mbt_data(opcode, src, header << 16, mbt_data << 32)

        self.make_status_png()

        #if nac != self.current_nac:
        #    if self.debug > 10: # this is occasionally expected if cycling between different tsys
        #        cnac = self.current_nac
        #        if cnac is None:
        #            cnac = 0
        #        sys.stderr.write("%f received NAC %x does not match expected NAC %x\n" % (time.time(), nac, cnac))
        #    return

        if self.logfile_workers:
            self.logging_scheduler(curr_time)
            return

        if updated:
            self.update_state('update', curr_time)
        else:
            self.update_state('duid%d' % mtype, curr_time)

    def find_available_worker(self):
        for worker in self.logfile_workers:
            if not worker['active']:
                worker['active'] = True
                return worker
        return None

    def free_frequency(self, frequency, curr_time):
        assert not self.working_frequencies[frequency]['tgids']
        self.working_frequencies[frequency]['worker']['demod'].set_relative_frequency(0)
        self.working_frequencies[frequency]['worker']['active'] = False
        self.working_frequencies.pop(frequency)
        sys.stderr.write('%f release worker frequency %d\n' % (curr_time, frequency))

    def free_talkgroup(self, frequency, tgid, curr_time):
        decoder = self.working_frequencies[frequency]['worker']['decoder']
        tdma_slot = self.working_frequencies[frequency]['tgids'][tgid]['tdma_slot']
        index = tdma_slot
        if tdma_slot is None:
            index = 0
        self.working_frequencies[frequency]['tgids'].pop(tgid)
        sys.stderr.write('%f release tgid %d frequency %d\n' % (curr_time, tgid, frequency))

    def logging_scheduler(self, curr_time):
        tsys = self.trunked_systems[self.current_nac]
        for tgid in tsys.get_updated_talkgroups(curr_time):
            frequency = tsys.talkgroups[tgid]['frequency']
            tdma_slot = tsys.talkgroups[tgid]['tdma_slot']
            # see if this tgid active on any other freq(s)
            other_freqs = [f for f in self.working_frequencies if f != frequency and tgid in self.working_frequencies[f]['tgids']]
            if other_freqs:
                sys.stderr.write('%f tgid %d slot %s frequency %d found on other frequencies %s\n' % (curr_time, tgid, tdma_slot, frequency, ','.join(['%s' % f for f in other_freqs])))
                for f in other_freqs:
                    self.free_talkgroup(f, tgid, curr_time)
                    if not self.working_frequencies[f]['tgids']:
                        self.free_frequency(f, curr_time)
            diff = abs(tsys.center_frequency - frequency)
            if diff > self.input_rate/2:
                #sys.stderr.write('%f request for frequency %d tgid %d failed, offset %d exceeds maximum %d\n' % (curr_time, frequency, tgid, diff, self.input_rate/2))
                continue

            update = True
            if frequency in self.working_frequencies:
                tgids = self.working_frequencies[frequency]['tgids']
                if tgid in tgids:
                    if tgids[tgid]['tdma_slot'] == tdma_slot:
                        update = False
                    else:
                        sys.stderr.write('%f slot switch %s was %s tgid %d frequency %d\n' % (curr_time, tdma_slot, tgids[tgid]['tdma_slot'], tgid, frequency))
                        worker = self.working_frequencies[frequency]['worker']
                else:
                    #active_tdma_slots = [tgids[tg]['tdma_slot'] for tg in tgids]
                    sys.stderr.write("%f new tgid %d slot %s arriving on already active frequency %d\n" % (curr_time, tgid, tdma_slot, frequency))
                    previous_tgid = [id for id in tgids if tgids[id]['tdma_slot'] == tdma_slot]
                    assert len(previous_tgid) == 1   ## check for logic error
                    self.free_talkgroup(frequency, previous_tgid[0], curr_time)
                    worker = self.working_frequencies[frequency]['worker']
            else:
                worker = self.find_available_worker()
                if worker is None:
                    sys.stderr.write('*** error, no free demodulators, freq %d tgid %d\n' % (frequency, tgid))
                    continue
                self.working_frequencies[frequency] = {'tgids' : {}, 'worker': worker}
                worker['demod'].set_relative_frequency(tsys.center_frequency - frequency)
                sys.stderr.write('%f starting worker frequency %d tg %d slot %s\n' % (curr_time, frequency, tgid, tdma_slot))
            self.working_frequencies[frequency]['tgids'][tgid] = {'updated': curr_time, 'tdma_slot': tdma_slot}
            if not update:
                continue
            filename = 'tgid-%d-%f.wav' % (tgid, curr_time)
            sys.stderr.write('%f update frequency %d tg %d slot %s file %s\n' % (curr_time, frequency, tgid, tdma_slot, filename))
            # set demod speed, decoder slot, output file name
            demod = worker['demod']
            decoder = worker['decoder']
            symbol_rate = 4800

            if tdma_slot is None:
                index = 0
            else:
                index = tdma_slot
                symbol_rate = 6000
                xorhash = '%x%x%x' % (self.current_nac, tsys.ns_syid, tsys.ns_wacn)
                if xorhash not in self.xor_cache:
                    self.xor_cache[xorhash] = lfsr.p25p2_lfsr(self.current_nac, tsys.ns_syid, tsys.ns_wacn).xor_chars
                decoder.set_xormask(self.xor_cache[xorhash], xorhash, index=index)
                decoder.set_nac(self.current_nac, index=index)
            demod.set_omega(symbol_rate)
            decoder.set_output(filename, index=index)

        # garbage collection
        if self.last_garbage_collect + 1 > curr_time:
            return
        self.last_garbage_collect = curr_time

        gc_frequencies = []
        gc_tgids = []
        for frequency in self.working_frequencies:
            tgids = self.working_frequencies[frequency]['tgids']
            inactive_tgids = [[frequency, tgid] for tgid in tgids if tgids[tgid]['updated'] + self.TGID_HOLD_TIME < curr_time]
            if len(inactive_tgids) == len(tgids):
                gc_frequencies += [frequency]
            gc_tgids += inactive_tgids
        for frequency, tgid in gc_tgids:	# expire talkgroups
            self.free_talkgroup(frequency, tgid, curr_time)
        for frequency in gc_frequencies:	# expire working frequencies
            self.free_frequency(frequency, curr_time)

    def update_state(self, command, curr_time, cmd_data = 0): #   def update_state(self, command, curr_time):
        if not self.configs:
            return	# run in "manual mode" if no conf

        if type(command) is not str and isinstance(command, bytes):
            command = command.decode()

        nac = self.current_nac
        tsys = self.trunked_systems[nac]

        new_frequency = None
        new_tgid = None
        new_state = None
        new_nac = None
        new_slot = None
        new_frequency_type = None

        if command == 'timeout':
            if self.current_state == self.states.CC:
                if self.debug > 0:
                    sys.stderr.write("%f control channel timeout, current CC %d\n" % (time.time(), tsys.trunk_cc))
                tsys.cc_timeouts += 1
            elif self.current_state != self.states.CC and tsys.last_voice_time + 1.0 < curr_time:
                if self.debug > 0:
                    sys.stderr.write("%f voice timeout\n" % time.time())
                if self.hold_mode is False:
                    self.current_tgid = None
                tsys.current_srcaddr = 0
                new_state = self.states.CC
                new_frequency = tsys.trunk_cc
                new_frequency_type = 'cc'
        elif command == 'update':
            if self.current_state == self.states.CC:
                desired_tgid = None
                if (self.tgid_hold is not None) and (self.tgid_hold_until > curr_time):
                    if self.debug > 1:
                        sys.stderr.write("%f hold active tg(%s)\n" % (time.time(), self.tgid_hold))
                    desired_tgid = self.tgid_hold
                elif (self.tgid_hold is not None) and (self.hold_mode == False):
                    self.tgid_hold = None
                new_frequency, new_tgid, tdma_slot, srcaddr = tsys.find_talkgroup(curr_time, tgid=desired_tgid, hold=self.hold_mode)
                if new_frequency:
                    new_frequency_type = 'vc'
                    if self.debug > 0:
                        tslot = tdma_slot if tdma_slot is not None else '-'
                        sys.stderr.write("%f voice update:  tg(%s), freq(%s), slot(%s), prio(%d)\n" % (time.time(), new_tgid, new_frequency, tslot, tsys.get_prio(new_tgid)))
                    new_state = self.states.TO_VC
                    self.current_tgid = new_tgid
                    tsys.current_srcaddr = srcaddr
                    self.tgid_hold = new_tgid
                    self.tgid_hold_until = max(curr_time + self.TGID_HOLD_TIME, self.tgid_hold_until)
                    self.wait_until = curr_time + self.TSYS_HOLD_TIME
                    new_slot = tdma_slot
            elif 0: # # # # # else: # check for priority tgid preemption
                new_frequency, new_tgid, tdma_slot, srcaddr = tsys.find_talkgroup(tsys.talkgroups[self.current_tgid]['time'], tgid=self.current_tgid, hold=self.hold_mode)
                if new_tgid != self.current_tgid:
                    if self.debug > 0:
                        tslot = tdma_slot if tdma_slot is not None else '-'
                        sys.stderr.write("%f voice preempt: tg(%s), freq(%s), slot(%s), prio(%d)\n" % (time.time(), new_tgid, new_frequency, tslot, tsys.get_prio(new_tgid)))
                    new_frequency_type = 'vc'
                    new_state = self.states.TO_VC
                    self.current_tgid = new_tgid
                    tsys.current_srcaddr = srcaddr
                    self.tgid_hold = new_tgid
                    self.tgid_hold_until = max(curr_time + self.TGID_HOLD_TIME, self.tgid_hold_until)
                    self.wait_until = curr_time + self.TSYS_HOLD_TIME
                    new_slot = tdma_slot
                else:
                    new_frequency = None
        elif command == 'duid3' or command == 'tdma_duid3': # termination, no channel release
            if self.current_state != self.states.CC:
                self.tgid_hold = self.current_tgid
                self.tgid_hold_until = max(curr_time + self.TGID_HOLD_TIME, self.tgid_hold_until)
                self.wait_until = curr_time + self.TSYS_HOLD_TIME
        elif command == 'duid15' or command == 'tdma_duid15': # termination with channel release
            if self.current_state != self.states.CC:
                if self.debug > 1:
                    sys.stderr.write("%f %s, tg(%d)\n" % (time.time(), command, self.current_tgid))
                tsys.current_srcaddr = 0
                tsys.current_grpaddr = 0
                self.wait_until = curr_time + self.TSYS_HOLD_TIME
                self.tgid_hold = self.current_tgid
                self.tgid_hold_until = max(curr_time + self.TGID_HOLD_TIME, self.tgid_hold_until)
                if self.hold_mode is False:
                    self.current_tgid = None
                new_state = self.states.CC
                new_frequency = tsys.trunk_cc
                new_frequency_type = 'cc'
        elif command == 'duid0' or command == 'duid5' or command == 'duid10' or command == 'tdma_duid5':
            if self.current_state == self.states.TO_VC:
                new_state = self.states.VC
            self.tgid_hold = self.current_tgid
            self.tgid_hold_until = max(curr_time + self.TGID_HOLD_TIME, self.tgid_hold_until)
            self.wait_until = curr_time + self.TSYS_HOLD_TIME
        elif command == 'duid7' or command == 'duid12': # tsbk/pdu should never arrive here...
            pass
        elif command == 'hold':
            self.last_command = {'command': command, 'time': curr_time}
            if self.hold_mode:
                new_hold_mode = False
            else:
                new_hold_mode = True
            if new_hold_mode and (cmd_data is None or cmd_data < 1):
                if self.debug > 0:
                    sys.stderr.write ('%f set hold failed, unable to determine TGID\n' % (time.time()))
                new_hold_mode = False
            if new_hold_mode is False:	# unset hold
                self.current_tgid = None
                self.tgid_hold = None
                self.tgid_hold_until = curr_time
                self.hold_mode = new_hold_mode
            else:			# set hold
                self.tgid_hold = cmd_data
                self.tgid_hold_until = curr_time + 86400 * 10000
                self.hold_mode = new_hold_mode
                if self.debug > 0:
                    sys.stderr.write ('%f set hold tg(%s) until %f\n' % (time.time(), self.tgid_hold, self.tgid_hold_until))
            if self.debug > 0:
                sys.stderr.write ('%f set hold tg(%s) until %f mode %s current tgid %s\n' % (time.time(), self.tgid_hold, self.tgid_hold_until, self.hold_mode, self.current_tgid))
            if self.current_tgid != self.tgid_hold:
                self.current_tgid = self.tgid_hold
                self.current_srcaddr = 0
                self.current_grpaddr = 0
                self.current_alg = ""
                self.current_algid = 128
                self.current_keyid = 0
                new_state = self.states.CC
                new_frequency = tsys.trunk_cc
                new_frequency_type = 'cc'
        elif command == 'set_hold':
            self.last_command = {'command': command, 'time': curr_time}
            if self.current_tgid:
                self.tgid_hold = self.current_tgid
                self.tgid_hold_until = curr_time + 86400 * 10000
                self.hold_mode = True
                print ('set hold until %f' % self.tgid_hold_until)
        elif command == 'unset_hold':
            self.last_command = {'command': command, 'time': curr_time}
            if self.current_tgid:
                if self.debug > 0:
                    sys.stderr.write ('%f clear hold tg(%s)\n' % (time.time(), self.tgid_hold))
                self.current_tgid = None
                self.tgid_hold = None
                self.tgid_hold_until = curr_time
                self.hold_mode = False
        elif command == 'skip' or command == 'lockout':
            self.last_command = {'command': command, 'time': curr_time}
            if self.current_tgid:
                end_time = None
                if command == 'skip':
                    end_time = curr_time + self.TGID_SKIP_TIME
                tsys.add_blacklist(self.current_tgid, end_time=end_time)
                self.current_tgid = None
                self.tgid_hold = None
                self.tgid_hold_until = curr_time
                self.hold_mode = False
                tsys.current_srcaddr = 0
                if self.current_state != self.states.CC:
                    new_state = self.states.CC
                    new_frequency = tsys.trunk_cc
                    new_frequency_type = 'cc'
        else:
            sys.stderr.write('update_state: unknown command: %s\n' % command)
            assert 0 == 1

        if new_frequency is not None and tsys.trunk_cc != tsys.rfss_chan:
            sys.stderr.write('warning: trunk control channel frequency %f does not match rfss frequency %f\n' % (tsys.trunk_cc/1000000.0, tsys.rfss_chan/1000000.0))

        hunted_cc = tsys.hunt_cc(curr_time)

        if self.enabled_nacs is not None and self.current_nac not in self.enabled_nacs:
            tsys.current_srcaddr = 0
            tsys.current_grpaddr = 0
            new_nac = self.find_next_tsys()
            new_state = self.states.CC
        elif self.current_state != self.states.CC and self.tgid_hold_until <= curr_time and self.hold_mode is False and new_state is None:
            if self.debug > 1:
                sys.stderr.write("%f release tg(%s)\n" % (time.time(), self.current_tgid))
            self.tgid_hold = None
            self.current_tgid = None
            tsys.current_srcaddr = 0
            tsys.current_grpaddr = 0
            new_state = self.states.CC
            new_frequency = tsys.trunk_cc
            new_frequency_type = 'cc'
        elif self.wait_until <= curr_time and self.tgid_hold_until <= curr_time and self.hold_mode is False and new_state is None:
            self.wait_until = curr_time + self.TSYS_HOLD_TIME
            tsys.current_srcaddr = 0
            tsys.current_grpaddr = 0
            new_nac = self.find_next_tsys()
            new_state = self.states.CC

        if new_nac is not None:
            nac = self.current_nac = new_nac
            tsys = self.trunked_systems[nac]
            new_frequency = tsys.trunk_cc
            new_frequency_type = 'cc'
            tsys.current_srcaddr = 0
            tsys.current_grpaddr = 0
            self.current_tgid = None

        if new_frequency is not None:
            params = tsys.frequency_change_params(self.current_tgid, new_frequency, nac, new_slot, new_frequency_type, curr_time)
            self.status_msg = 'F %f TG %s %s at %s\n' % (params['freq'] / 1000000.0, params['tgid'], params['tag'], time.asctime())
            self.set_frequency(params)

        if new_state is not None:
            self.current_state = new_state

    def parallel_hunt_cc(self):
        curr_time = time.time()
        if curr_time < self.next_hunt_time:
            return
        self.next_hunt_time = curr_time + 1.0
        for nac in self.trunked_systems.keys():
            tsys = self.trunked_systems[nac]
            rc = tsys.hunt_cc(curr_time)
            if not rc:
                continue
            tgid = None
            freq = tsys.trunk_cc
            new_slot = None
            new_frequency_type = 'cc'
            params = tsys.frequency_change_params(tgid, freq, nac, new_slot, new_frequency_type, curr_time)
            self.status_msg = 'F %f TG %s %s at %s\n' % (params['freq'] / 1000000.0, params['tgid'], params['tag'], time.asctime())
            self.set_frequency(params)

def main():
    q = 0x3a000012ae01013348704a54
    rc = crc16(q,12)
    sys.stderr.write('should be zero: %x\n' % rc)
    assert rc == 0

    q = 0x3a001012ae01013348704a54
    rc = crc16(q,12)
    sys.stderr.write('should be nonzero: %x\n' % rc)
    assert rc != 0

    t = trunked_system(debug=255)
    q = 0x3a000012ae0101334870
    t.decode_tsbk(q)

    q = 0x02900031210020018e7c
    t.decode_tsbk(q)

if __name__ == '__main__':
    main()
