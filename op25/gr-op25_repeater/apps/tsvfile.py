
# Copyright 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018 Max H. Parke KA1RBI
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
import csv

def get_frequency(f):	# return frequency in Hz
    if f.find('.') == -1:	# assume in Hz
        return int(f)
    else:     # assume in MHz due to '.'
        return int(float(f) * 1000000)

def get_int_dict(s):
    # parameter string s is the file name to be read,
    # except when the first character of s is a digit,
    # in which case s itself is the comma-separated list of ints

    if s[0].isdigit():
        return dict.fromkeys([int(d) for d in s.split(',')])

    # create dict by reading from file
    d = {}                     # this is the dict
    with open(s,"r") as f:
        for v in f:
            v = v.split("\t",1) # split on tab
            try:
                v0 = int(v[0])				# first parameter is tgid or start of tgid range
                v1 = v0
                if (len(v) > 1) and (int(v[1]) > v0):	# second parameter if present is end of tgid range
                	v1 = int(v[1])

                for tg in range(v0, (v1 + 1)):
                    if tg not in d:      # is this a new tg?
                       d[tg] = []   # if so, add to dict (key only, value null)
                       sys.stderr.write('added talkgroup %d from %s\n' % (tg,s))

            except (IndexError, ValueError) as ex:
                continue
    f.close()
    return dict.fromkeys(d)

def utf_ascii(ustr):
    return (ustr.decode("utf-8")).encode("ascii", "ignore")

class id_registry:
    def __init__(self):
        self.cache = {}
        self.wildcards = {}

    def add(self, id_str, tag, color):
        if '-' in id_str:
            a = [int(x) for x in id_str.split('-')]
            if a[0] >= a[1]:
                raise AssertionError('invalid ID range in %s' % id_str)
            for i in range(a[0], a[1]+1):
                self.cache[i] = {'tag': tag, 'color': color}
        elif '.' in id_str:
            rc = id_str.find('.')
            self.wildcards[id_str] = {'prefix': id_str[:rc], 'len': len(id_str), 'tag': tag, 'color': color, 'type': '.'}
        elif '*' in id_str:
            rc = id_str.find('*')
            self.wildcards[id_str] = {'prefix': id_str[:rc], 'len': 0, 'tag': tag, 'color': color, 'type':  '*'}
        else:
            self.cache[int(id_str)] = {'tag': tag, 'color': color}

    def lookup(self, id):
        if id in self.cache.keys():
            return self.cache[id]
        id_str = '%d' % id
        for w in self.wildcards.keys():
            if not id_str.startswith(self.wildcards[w]['prefix']):
                continue
            if self.wildcards[w]['type'] == '.' and len(id_str) != self.wildcards[w]['len']:
                continue
            # wildcard matched
            self.cache[id] = {'tag': self.wildcards[w]['tag'], 'color': self.wildcards[w]['color']}
            return self.cache[id]
        # not found in cache, and no wildcard matched
        self.cache[id] = None
        return None

    def get_color(self, id):
        d = self.lookup(id)
        if not d:
            return 0
        return d['color']

    def get_tag(self, id):
        d = self.lookup(id)
        if not d:
            return ""
        return d['tag']

def load_tsv(tsv_filename):
    hdrmap = []
    configs = {}
    with open(tsv_filename, 'r') as csvfile:
        sreader = csv.reader(csvfile, delimiter='\t', quotechar='"', quoting=csv.QUOTE_ALL)
        for row in sreader:
            if not hdrmap:
                # process first line of tsv file - header line
                for hdr in row:
                    hdr = hdr.replace(' ', '_')
                    hdr = hdr.lower()
                    hdrmap.append(hdr)
                continue
            fields = {}
            for i in range(len(row)):
                if row[i]:
                    fields[hdrmap[i]] = row[i]
                    if hdrmap[i] != 'sysname':
                        fields[hdrmap[i]] = fields[hdrmap[i]].lower()
            nac = int(fields['nac'], 0)
            configs[nac] = fields
    return configs

def read_tags_file(tags_file, result):
    import csv
    with open(tags_file, 'r') as csvfile:
        sreader = csv.reader(csvfile, delimiter='\t', quotechar='"', quoting=csv.QUOTE_ALL)
        for row in sreader:
            id_str = row[0]
            txt = row[1]
            if len(row) >= 3:
                try:
                    color = int(row[2])
                except ValueError as ex:
                    color = 0
            else:
                color = 0
            result.add(id_str, txt, color)

def make_config(configs):
    result_config = {}
    for nac in configs:
        result_config[nac] = {'cclist':[], 'offset':0, 'whitelist':None, 'blacklist':{}, 'tgid_map':id_registry(), 'unit_id_map': id_registry(), 'sysname': configs[nac]['sysname'], 'center_frequency': None}
        for f in configs[nac]['control_channel_list'].split(','):
            result_config[nac]['cclist'].append(get_frequency(f))
        if 'offset' in configs[nac]:
            result_config[nac]['offset'] = int(configs[nac]['offset'])
        if 'modulation' in configs[nac]:
            result_config[nac]['modulation'] = configs[nac]['modulation']
        else:
            result_config[nac]['modulation'] = 'cqpsk'
        for k in ['whitelist', 'blacklist']:
            if k in configs[nac]:
                result_config[nac][k] = get_int_dict(configs[nac][k])
        if 'tgid_tags_file' in configs[nac]:
            fname = configs[nac]['tgid_tags_file']
            if ',' in fname:
                l = fname.split(',')
                tgid_tags_file = l[0]
                unit_id_tags_file = l[1]
            else:
                tgid_tags_file = fname
                unit_id_tags_file = None
            result_config[nac]['tgid_tags_file'] = tgid_tags_file
            result_config[nac]['unit_id_tags_file'] = unit_id_tags_file
            read_tags_file(tgid_tags_file, result_config[nac]['tgid_map'])
            if unit_id_tags_file is not None and os.access(unit_id_tags_file, os.R_OK):
                read_tags_file(unit_id_tags_file, result_config[nac]['unit_id_map'])
            
        if 'center_frequency' in configs[nac]:
            result_config[nac]['center_frequency'] = get_frequency(configs[nac]['center_frequency'])
    return result_config

def main():
    import json
    result = make_config(load_tsv(sys.argv[1]))
    print (json.dumps(result, indent=4, separators=[',',':'], sort_keys=True))

if __name__ == '__main__':
    main()
