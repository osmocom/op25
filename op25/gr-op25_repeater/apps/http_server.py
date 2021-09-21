#!/usr/bin/env python

# Copyright 2017, 2018, 2019, 2020 Max H. Parke KA1RBI
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
import re
import json
import socket
import traceback
import threading
import glob
import subprocess
import zmq

from gnuradio import gr
from waitress.server import create_server
from optparse import OptionParser
from multi_rx import byteify
from tsvfile import load_tsv, make_config

import logging
logging.basicConfig()

my_input_q = None
my_output_q = None
my_recv_q = None
my_port = None
my_backend = None
CFG_DIR = '../www/config/'
TSV_DIR = './'

"""
fake http and ajax server module
TODO: make less fake
"""
def ensure_str(s):	# for python 2/3
    if isinstance(s[0], str):
        return s
    ns = ''
    for i in range(len(s)):
        ns += chr(s[i])
    return ns

class event_iterator:
    def __iter__(self):
        return self

    def __next__(self):
        _jslog_file = None	 # set to str(filename) to enable json log
        msgs = []
        while True:
            msg = my_input_q.delete_head()
            assert msg.type() == -4
            d = json.loads(msg.to_string())
            msgs.append(d)
            if my_input_q.empty_p():
                break
        js = json.dumps(msgs)
        # TODO: json.loads followed by dumps is redundant - 
        #       can this be optimized?
        s = 'data:%s\r\n\r\n' % (js)

        if _jslog_file:
            t = json.dumps(msgs, indent=4, separators=[',',':'], sort_keys=True)
            with open(_jslog_file, 'a') as logfd:
                logfd.write('%s\n' % t)
        
        if sys.version[0] != '2':
            if isinstance(s, str):
                s = s.encode()
        return s

    next = __next__	# for python2

def static_file(environ, start_response):
    content_types = {'tsv': 'text/tab-separated-values', 'json': 'application/json', 'png': 'image/png', 'jpeg': 'image/jpeg', 'jpg': 'image/jpeg', 'gif': 'image/gif', 'css': 'text/css', 'js': 'application/javascript', 'html': 'text/html', 'ico': 'image/vnd.microsoft.icon'}
    img_types = 'png jpg jpeg gif ico'.split()
    data_types = 'tsv txt json db'.split()
    if environ['PATH_INFO'] == '/':
        filename = 'index.html'
    else:
        filename = re.sub(r'[^a-zA-Z0-9_.\-/]', '', environ['PATH_INFO'])
    suf = filename.split('.')[-1]
    pathname = '../www/www-static'
    if suf in img_types:
        pathname = '../www/images'
    elif suf in data_types:
        pathname = TSV_DIR
    pathname = '%s/%s' % (pathname, filename)
    if suf not in content_types.keys() or '..' in filename or not os.access(pathname, os.R_OK):
        sys.stderr.write('404 %s\n' % pathname)
        status = '404 NOT FOUND - PATHNAME: %s FILENAME: %s CWD: %s' % (pathname, filename, os. getcwd())
        content_type = 'text/plain'
        output = status
    else:
        output = open(pathname, 'rb').read()
        content_type = content_types[suf]
        status = '200 OK'
    return status, content_type, output

def valid_tsv(filename):
    if not os.access(filename, os.R_OK):
        return False
    line = open(filename).readline()
    for word in 'Sysname Offset NAC Modulation TGID Whitelist Blacklist'.split():
        if word not in line:
            return False
    return True

def tsv_config(filename):
    DEFAULT_CFG = '../www/config/default.json'
    filename = '%s%s' % (TSV_DIR, filename)
    filename = filename.replace('[TSV]', '.tsv')
    if not valid_tsv(filename):
        return None
    cfg = make_config(load_tsv(filename))
    default_cfg = json.loads(open(DEFAULT_CFG).read())

    result = default_cfg
    channels = [ {'active': True,
                  'blacklist': cfg[nac]['blacklist'],
                  'whitelist': cfg[nac]['whitelist'],
                  'cclist': cfg[nac]['cclist'],
                  'demod_type': 'cqpsk',
                  'destination': 'udp://127.0.0.1:23456',
                  'filter_type': 'rc',
                  'frequency': 500000000,
                  'if_rate': 24000,
                  'nac': nac,
                  'name': cfg[nac]['sysname'],
                  'phase2_tdma': False,
                  'plot': "",
                  'tgids': cfg[nac]['tgid_map'],
                  'trunked': True
                 }
                for nac in cfg.keys() ]
    result['channels'] = channels
    return {'json_type':'config_data', 'data': result}

def do_request(d):
    global my_backend
    if d['command'].startswith('rx-'):
        msg = gr.message().make_from_string(json.dumps(d), -2, 0, 0)
        if not my_backend.input_q.full_p():
            my_backend.input_q.insert_tail(msg)
        return None
    elif d['command'] == 'config-load':
        if '[TSV]' in d['data']:
            return tsv_config(d['data'])
        filename = '%s%s.json' % (CFG_DIR, d['data'])
        if not os.access(filename, os.R_OK):
            return None
        js_msg = json.loads(open(filename).read())
        return {'json_type':'config_data', 'data': js_msg}
    elif d['command'] == 'config-list':
        files = glob.glob('%s*.json' % CFG_DIR)
        files = [x.replace('.json', '') for x in files]
        files = [x.replace(CFG_DIR, '') for x in files]
        if d['data'] == 'tsv':
            tsvfiles = glob.glob('%s*.tsv' % TSV_DIR)
            tsvfiles = [x for x in tsvfiles if valid_tsv(x)]
            tsvfiles = [x.replace('.tsv', '[TSV]') for x in tsvfiles]
            tsvfiles = [x.replace(TSV_DIR, '') for x in tsvfiles]
            files += tsvfiles
        return {'json_type':'config_list', 'data': files}
    elif d['command'] == 'config-save':
        name = d['data']['name']
        if '..' in name or '.json' in name or '/' in name:
            return None
        filename = '%s%s.json' % (CFG_DIR, d['data']['name'])
        open(filename, 'w').write(json.dumps(d['data']['value'], indent=4, separators=[',',':'], sort_keys=True))
        return None
    elif d['command'] == 'config-savesettings':
        filename = 'ui-settings.json'
        open(filename, 'w').write(d['data'])
        sys.stderr.write('saved UI settings to %s\n' % filename)
        return None
    elif d['command'] == 'config-tsvsave':
        filename = d['file']
        ok = True
        if  filename.lower().endswith('tsv'):
            ok = True
        elif  filename.lower().endswith('json'):
            ok = True
        else:
            ok = False
        if filename.startswith('.'):
            ok = False
        if '/' in filename:
            ok = False
        if '..' in filename:
            ok = False
        if not ok:
            sys.stderr.write('cfg-tsvsave: invalid filename %s\n' % filename)
            return None
        open(filename, 'w').write(d['data'])
        sys.stderr.write('saved UI settings to %s\n' % filename)
        return None

def post_req(environ, start_response, postdata):
    global my_input_q, my_output_q, my_recv_q, my_port
    resp_msg = []
    data = []
    try:
        data = json.loads(postdata)
    except:
        sys.stderr.write('post_req: error processing input: %s:\n' % (postdata))
        traceback.print_exc(limit=None, file=sys.stderr)
        sys.stderr.write('*** end traceback ***\n')
    for d in data:
        if type(d) is str:
            sys.stderr.write('%f possible json sequence error: len %d type %s value %s\n' % (time.time(), len(d), type(d), d))
            continue
        elif type(d) is not dict:
            sys.stderr.write('%f possible json sequence error: type %s value %s\n' % (time.time(), type(d), d))
            continue
        if d['command'].startswith('config-') or d['command'].startswith('rx-'):
            resp = do_request(d)
            if resp:
                resp_msg.append(resp)
            continue
        if d['command'].startswith('settings-'):
            msg = gr.message().make_from_string(json.dumps(d), -4, 0, 0)
        else:
            msg = gr.message().make_from_string(str(d['command']), -2, d['data'], 0)
        if my_output_q.full_p():
            my_output_q.delete_head_nowait()   # ignores result
        if not my_output_q.full_p():
            my_output_q.insert_tail(msg)
    time.sleep(0.2)

    status = '200 OK'
    content_type = 'application/json'
    output = json.dumps(resp_msg)
    return status, content_type, output

def http_request(environ, start_response):
    if environ['REQUEST_METHOD'] == 'GET' and '/stream' in environ['PATH_INFO']:
        status = '200 OK'
        content_type = 'text/event-stream'
        response_headers = [('Content-type', content_type),
                            ('Access-Control-Allow-Origin', '*')]
        start_response(status, response_headers)
        return iter(event_iterator())
    elif environ['REQUEST_METHOD'] == 'GET':
        status, content_type, output = static_file(environ, start_response)
    elif environ['REQUEST_METHOD'] == 'POST':
        postdata = environ['wsgi.input'].read()
        status, content_type, output = post_req(environ, start_response, postdata)
    else:
        status = '200 OK'
        content_type = 'text/plain'
        output = status
        sys.stderr.write('http_request: unexpected input %s\n' % environ['PATH_INFO'])
    
    response_headers = [('Content-type', content_type),
                        ('Access-Control-Allow-Origin', '*'),
                        ('Content-Length', str(len(output)))]
    start_response(status, response_headers)

    if sys.version[0] != '2':
        if isinstance(output, str):
            output = output.encode()
    return [output]

def application(environ, start_response):
    failed = False
    try:
        result = http_request(environ, start_response)
    except:
        failed = True
        sys.stderr.write('application: request failed:\n%s\n' % traceback.format_exc())
    if failed:
        status = '500 Internal Server Error'
        response_headers = [ ('Access-Control-Allow-Origin', '*') ]
        start_response(status, response_headers)
        output = status
        if sys.version[0] != '2':
            if isinstance(output, str):
                output = output.encode()
        return [output]

    return result

def process_qmsg(msg):
    if my_recv_q.full_p():
        my_recv_q.delete_head_nowait()   # ignores result
    if my_recv_q.full_p():
        return
    my_recv_q.insert_tail(msg)

class http_server(object):
    def __init__(self, input_q, output_q, endpoint, **kwds):
        global my_input_q, my_output_q, my_recv_q, my_port
        host, port = endpoint.split(':')
        if my_port is not None:
            raise AssertionError('this server is already active on port %s' % my_port)
        my_input_q = input_q
        my_output_q = output_q
        my_port = int(port)

        my_recv_q = gr.msg_queue(10)

        SEND_BYTES = 1024
        NTHREADS = 10	# TODO: make #threads a function of #plots ?
        self.server = create_server(application, host=host, port=my_port, send_bytes=SEND_BYTES, expose_tracebacks=True, threads=NTHREADS)

    def run(self):
        self.server.run()

class queue_watcher(threading.Thread):
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
            self.callback(msg)

class Backend(threading.Thread):
    def __init__(self, options, input_q, output_q, init_config=None, **kwds):
        threading.Thread.__init__ (self, **kwds)
        self.setDaemon(1)
        self.keep_running = True
        self.rx_options = None
        self.input_q = input_q
        self.output_q = output_q
        self.verbosity = options.verbosity

        self.zmq_context = zmq.Context()
        self.zmq_port = options.zmq_port

        self.zmq_sub = self.zmq_context.socket(zmq.SUB)
        self.zmq_sub.connect('tcp://localhost:%d' % self.zmq_port)
        self.zmq_sub.setsockopt_string(zmq.SUBSCRIBE, '')

        self.zmq_pub = self.zmq_context.socket(zmq.PUB)
        self.zmq_pub.sndhwm = 5
        self.zmq_pub.bind('tcp://*:%d' % (self.zmq_port+1))

        self.start()
        self.subproc = None
        self.msg = None

        self.q_watcher = queue_watcher(self.input_q, self.process_msg)

        if init_config:
            d = {'command': 'rx-start', 'data': init_config}
            msg = gr.message().make_from_string(json.dumps(d), -4, 0, 0)
            self.input_q.insert_tail(msg)

    def publish(self, msg):
        t = msg.type()
        s = msg.to_string()
        a = msg.arg1()
        s = ensure_str(s)
        self.zmq_pub.send_string(json.dumps({'command': s, 'data': a, 'msgtype': t}))

    def check_subproc(self):	# return True if subprocess is active
        if not self.subproc:
            return False
        rc = self.subproc.poll()
        if rc is None:
            return True
        else:
            self.subproc.wait()
            self.subproc = None
            return False

    def process_msg(self, msg):
        def make_command(options, config_file):
            py_exe = 'python'
            if sys.version[0] == '3':
                py_exe = 'python3'
            trunked_ct = [True for x in options._js_config['channels'] if x['trunked']]
            total_ct = [True for x in options._js_config['channels']]
            if trunked_ct and len(trunked_ct) != len(total_ct):
                self.msg = 'no suitable backend found for this configuration'
                return None
            if not trunked_ct:
                self.backend = '%s/%s' % (os.getcwd(), 'multi_rx.py')
                opts = [py_exe, self.backend]
                filename = '%s%s.json' % (CFG_DIR, config_file)
                opts.append('--config-file')
                opts.append(filename)
                return opts

            # TODO: this probably should be external and/or configurable
            # these options must match up one for one with the rx.py cli opts
            types = {'costas-alpha': 'float',
                'trunk-conf-file': 'str',
                'demod-type': 'str',
                'logfile-workers': 'int',
                'decim-amt': 'int',
                'wireshark-host': 'str',
                'gain-mu': 'float',
                'phase2-tdma': 'bool',
                'seek': 'int',
                'ifile': 'str',
                'pause': 'bool',
                'antenna': 'str',
                'calibration': 'float',
                'fine-tune': 'float',
                'raw-symbols': 'str',
                'audio-output': 'str',
                'vocoder': 'bool',
                'input': 'str',
                'wireshark': 'bool',
                'gains': 'str',
                'args': 'str',
                'sample-rate': 'int',
                'terminal-type': 'str',
                'gain': 'float',
                'excess-bw': 'float',
                'offset': 'float',
                'audio-input': 'str',
                'audio': 'bool',
                'plot-mode': 'str',
                'audio-if': 'bool',
                'tone-detect': 'bool',
                'frequency': 'int',
                'freq-corr': 'float',
                'hamlib-model': 'int',
                'udp-player': 'bool',
                'verbosity': 'int',
                'audio-gain': 'float',
                'freq-error-tracking': 'bool',
                'nocrypt': 'bool',
                'wireshark-port': 'int'
            }
            self.backend = '%s/%s' % (os.getcwd(), 'rx.py')
            opts = [py_exe, self.backend]
            for k in [ x for x in dir(options) if not x.startswith('_') ]:
                kw = k.replace('_', '-')
                val = getattr(options, k)
                if kw not in types.keys():
                    self.msg = 'make_command: unknown option: %s %s type %s' % (k, val, type(val))
                    return None
                elif types[kw] == 'str':
                    if val:
                        opts.append('--%s' % kw)
                        opts.append('%s' % (val))
                elif types[kw] == 'float':
                    opts.append('--%s' % kw)
                    if val:
                        opts.append('%f' % (val))
                    else:
                        opts.append('%f' % (0))
                elif types[kw] == 'int':
                    opts.append('--%s' % kw)
                    if val:
                        opts.append('%d' % (val))
                    else:
                        opts.append('%d' % (0))
                elif types[kw] == 'bool':
                    if val:
                        opts.append('--%s' % kw)
                else:
                    self.msg = 'make_command: unknown2 option: %s %s type %s' % (k, val, type(val))
                    return None
            return opts

        msg = json.loads(msg.to_string())
        if msg['command'] == 'rx-start':
            if self.check_subproc():
                self.msg = 'start command failed: subprocess pid %d already active' % self.subproc.pid
                return
            options = rx_options(msg['data'])
            if getattr(options, '_js_config', None) is None:
                self.msg = 'start command failed: rx_options: unable to initialize config=%s' % (msg['data'])
                return
            options.verbosity = self.verbosity
            options.terminal_type = 'zmq:tcp:%d' % (self.zmq_port)
            cmd = make_command(options, msg['data'])
            sys.stderr.write('executing %s\n' % (' '.join(cmd)))
            if cmd:
                self.subproc = subprocess.Popen(cmd)
        elif msg['command'] == 'rx-stop':
            if not self.check_subproc():
                self.msg = 'stop command failed: subprocess not active'
                return
            if msg['data'] == 'kill':
                self.subproc.kill()
            else:
                self.subproc.terminate()
        elif msg['command'] == 'rx-state':
            d = {}
            if self.check_subproc():
                d['rx-state'] = 'subprocess pid %d active' % self.subproc.pid
            else:
                d['rx-state'] = 'subprocess not active, last msg: %s' % self.msg
            msg = gr.message().make_from_string(json.dumps(d), -4, 0, 0)
            if not self.output_q.full_p():
                self.output_q.insert_tail(msg)

    def run(self):
        while self.keep_running:
            js = self.zmq_sub.recv()
            if not self.keep_running:
                break
            js = ensure_str(js)
            msg = gr.message().make_from_string(js, -4, 0, 0)
            if not self.output_q.full_p():
                self.output_q.insert_tail(msg)

class rx_options(object):
    def __init__(self, name):
        def map_name(k):
            return k.replace('-', '_')

        filename = '%s%s.json' % (CFG_DIR, name)
        if not os.access(filename, os.R_OK):
            sys.stderr.write('unable to access config file %s\n' % (filename))
            return
        config = byteify(json.loads(open(filename).read()))
        dev = [x for x in config['devices'] if x['active']][0]
        if not dev:
            return
        chan = [x for x in config['channels'] if x['active']][0]
        if not chan:
            return
        options = object()
        for k in config['backend-rx'].keys():
            setattr(self, map_name(k), config['backend-rx'][k])
        for k in 'args frequency gains offset'.split():
            setattr(self, k, dev[k])
        self.demod_type = chan['demod_type']
        self.freq_corr = dev['ppm']
        self.sample_rate = dev['rate']
        self.plot_mode = chan['plot']
        self.phase2_tdma = chan['phase2_tdma']
        self.trunk_conf_file = filename
        self._js_config = config

def http_main():
    global my_backend
    # command line argument parsing
    parser = OptionParser()
    parser.add_option("-c", "--config", type="string", default=None, help="config json name, without prefix/suffix")
    parser.add_option("-e", "--endpoint", type="string", default="127.0.0.1:8080", help="address:port to listen on (use addr 0.0.0.0 to enable external clients)")
    parser.add_option("-v", "--verbosity", type="int", default=0, help="message debug level")
    parser.add_option("-p", "--pause", action="store_true", default=False, help="block on startup")
    parser.add_option("-z", "--zmq-port", type="int", default=25000, help="backend sub port")
    (options, args) = parser.parse_args()

    # wait for gdb
    if options.pause:
        print ('Ready for GDB to attach (pid = %d)' % (os.getpid(),))
        raw_input("Press 'Enter' to continue...")

    input_q = gr.msg_queue(20)
    output_q = gr.msg_queue(20)
    backend_input_q = gr.msg_queue(20)
    backend_output_q = gr.msg_queue(20)

    my_backend = Backend(options, backend_input_q, backend_output_q, init_config=options.config)
    server = http_server(input_q, output_q, options.endpoint)
    q_watcher = queue_watcher(output_q, lambda msg : my_backend.publish(msg))
    backend_q_watcher = queue_watcher(backend_output_q, lambda msg : process_qmsg(msg))

    server.run()

if __name__ == '__main__':
    http_main()
