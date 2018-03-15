
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
import csv

def get_frequency(f):	# return frequency in Hz
    if f.find('.') == -1:	# assume in Hz
        return int(f)
    else:     # assume in MHz due to '.'
        return int(float(f) * 1000000)

def get_int_dict(s):
    if s[0].isdigit():
        return dict.fromkeys([int(d) for d in s.split(',')])
    return dict.fromkeys([int(d) for d in open(s).readlines()])

def load_tsv(tsv_filename):
    hdrmap = []
    configs = {}
    with open(tsv_filename, 'rb') as csvfile:
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
            for i in xrange(len(row)):
                if row[i]:
                    fields[hdrmap[i]] = row[i]
                    if hdrmap[i] != 'sysname':
                        fields[hdrmap[i]] = fields[hdrmap[i]].lower()
            nac = int(fields['nac'], 0)
            configs[nac] = fields
    return configs

def make_config(configs):
    result_config = {}
    for nac in configs:
        result_config[nac] = {'cclist':[], 'offset':0, 'whitelist':None, 'blacklist':{}, 'tgid_map':{}, 'sysname': configs[nac]['sysname'], 'center_frequency': None}
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
            import csv
            with open(configs[nac]['tgid_tags_file'], 'rb') as csvfile:
                sreader = csv.reader(csvfile, delimiter='\t', quotechar='"', quoting=csv.QUOTE_ALL)
                for row in sreader:
                    tgid = int(row[0])
                    txt = row[1]
                    result_config[nac]['tgid_map'][tgid] = txt
        if 'center_frequency' in configs[nac]:
            result_config[nac]['center_frequency'] = get_frequency(configs[nac]['center_frequency'])
    return result_config

def main():
    import json
    result = make_config(load_tsv(sys.argv[1]))
    print json.dumps(result, indent=4, separators=[',',':'], sort_keys=True)

if __name__ == '__main__':
    main()
