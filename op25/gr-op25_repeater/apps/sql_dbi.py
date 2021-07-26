#!/usr/bin/env python

# Copyright 2021 Max H. Parke KA1RBI
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
import json
import threading
import traceback
import sqlite3

from gnuradio import gr

from emap import events_map, cc_events

_def_db_file = 'op25-data.db'
_def_msgq_size = 100
_def_uncommitted = 25

class du_queue_runner(threading.Thread):
	def __init__(self, msgq,  **kwds):
		threading.Thread.__init__ (self, **kwds)
		self.setDaemon(1)
		self.msgq = msgq
		self.db_filename = _def_db_file
		self.conn = None
		self.cursor = None
		self.failed = False
		self.keep_running = True
		self.uncommitted = 0
		self.max_q = 0
		self.start()
		self.next_t = time.time()

	def run(self):
		self.connect()
		while self.keep_running and not self.failed:
			self.max_q = max(self.max_q, self.msgq.count())
			if time.time() > self.next_t:
				self.next_t = time.time() + 2
			msg = self.msgq.delete_head()
			if self.failed or not self.keep_running:
				break
			self.insert_row(msg)

	def disconnect(self):
		self.conn.close()
		self.cursor = None
		self.conn = None

	def connect(self):
		self.conn = sqlite3.connect(self.db_filename)
		self.cursor = self.conn.cursor()

	def insert_row(self, msg):
		if self.cursor is None or self.conn is None:
			return
		d = json.loads(msg.to_string())
		try:
			self.cursor.execute(d['command'], d['row'])
			# optimization: only commit when no more msgs queued (or limit reached)
			if self.uncommitted < _def_uncommitted and self.msgq.count():
				self.uncommitted += 1
			else:
				self.conn.commit()
				self.uncommitted = 0
		except:
			self.failed = True
			traceback.print_exc(limit=None, file=sys.stdout)
			traceback.print_exc(limit=None, file=sys.stderr)
			sys.stderr.write('sql_dbi: db logging stopped due to error (or db not initialized)\n')
			# TODO - add error recovery?

class sql_dbi:
	def __init__(self, db_filename=_def_db_file):
		self.conn = None
		self.cursor = None
		self.db_filename = db_filename
		self.db_msgq = gr.msg_queue(_def_msgq_size)
		self.q_runner = du_queue_runner(self.db_msgq)
		self.db_msgq_overflow = 0

		self.sql_commands = {
			'calls': 'INSERT INTO calls(time, sysid, options, tgid, srcid)',
			'joins': 'INSERT INTO joins(time, sysid, rv, tgid, srcid)',
			'create_data_store': '''CREATE TABLE data_store (
						id INTEGER PRIMARY KEY,
						time REAL NOT NULL,
						cc_event INTEGER NOT NULL,
						opcode INTEGER NOT NULL,
						sysid INTEGER NOT NULL,
						mfrid INTEGER NULL,
						p INTEGER NULL,
						p2 INTEGER NULL,
						p3 INTEGER NULL,
						wacn INTEGER NULL,
						frequency INTEGER NULL,
						tgid INTEGER NULL,
						tgid2 INTEGER NULL,
						suid INTEGER NULL,
						suid2 INTEGER NULL,
						tsbk_sysid INTEGER NULL,
						FOREIGN KEY(cc_event) REFERENCES event_keys (id))''',
			'create_event_keys': '''CREATE TABLE event_keys (
						id INTEGER PRIMARY KEY,
						tag TEXT NOT NULL )''',
			'create_sysid': '''CREATE TABLE sysid_tags (
						id INTEGER PRIMARY KEY,
						sysid INTEGER NOT NULL,
						tag TEXT)''',
			'create_tgid': '''CREATE TABLE tgid_tags (
						id INTEGER PRIMARY KEY,
						rid INTEGER NOT NULL,
						sysid INTEGER NOT NULL,
						tag TEXT,
						priority INTEGER)''',
			'create_unit_id': '''CREATE TABLE unit_id_tags (
						id INTEGER PRIMARY KEY,
						rid INTEGER NOT NULL,
						sysid INTEGER NOT NULL,
						tag TEXT,
						priority INTEGER)''',
			'create_2b_rv': '''CREATE TABLE loc_reg_resp_rv (
						rv INTEGER NOT NULL,
						tag TEXT NOT NULL)''',
			'populate_2b_rv': '''INSERT INTO loc_reg_resp_rv(rv, tag) VALUES(0, "join")
						INSERT INTO loc_reg_resp_rv(rv, tag) VALUES(1, "fail")
						INSERT INTO loc_reg_resp_rv(rv, tag) VALUES(2, "deny")
						INSERT INTO loc_reg_resp_rv(rv, tag) VALUES(3, "refuse")''',
			'create_index': '''CREATE INDEX tgid_idx ON data_store(tgid)
						CREATE INDEX tgid2_idx ON data_store(tgid2)
						CREATE INDEX suid_idx ON data_store(suid)
						CREATE INDEX suid2_idx ON data_store(suid2)
						CREATE INDEX t_tgid_idx ON tgid_tags(rid)
						CREATE INDEX t_unit_id_idx ON unit_id_tags(rid)'''
			}

	def disconnect(self):
		self.conn.close()
		self.cursor = None
		self.conn = None

	def connect(self):
		self.conn = sqlite3.connect(self.db_filename)
		self.cursor = self.conn.cursor()

	def reset_db(self):	# any data in db will be destroyed!
		if os.access(self.db_filename, os.W_OK):
			os.remove(self.db_filename)
		self.conn = sqlite3.connect(self.db_filename)
		self.cursor = self.conn.cursor()
		self.execute('create_sysid')
		self.execute('create_2b_rv')
		self.execute_lines('populate_2b_rv')
		self.execute('create_tgid')
		self.execute('create_unit_id')
		self.execute('create_event_keys')
		self.execute('create_data_store')
		self.execute_lines('create_index')
		self.conn.commit()
		self.populate_event_keys()
		self.conn.close()

	def execute(self, q):
		self.cursor.execute(self.sql_commands[q])
		self.conn.commit()

	def execute_lines(self,q):
		for line in self.sql_commands[q].split('\n'):
			self.cursor.execute(line)
		self.conn.commit()

	def q(self, query):
		if query != '-':
			return self.cursor.execute(query)
		lines = sys.stdin.read().strip().split('\n')
		for query in lines:
			self.cursor.execute(query)
		self.conn.commit()
		return None

	def write(self, table_name, row):
		# the number of elements in tuple 'row' must be two less than the number of table columns
		curr_time = time.time()
		row = (curr_time,) + row
		qs = ['?'] * len(row)
		command = self.sql_commands[table_name] + ' VALUES (' + ','.join(qs) + ')'
		self.cursor.execute(command, row)
		self.conn.commit()

	def event(self, d):
		if d['cc_event'] not in events_map:
			return
		if not os.access(_def_db_file, os.W_OK):	# if DB not (yet) set up or not writable
			return
		mapl = events_map[d['cc_event']]
		row = []
		column_names = []
		for col in mapl:
			colname = col[0]
			k = col[1]
			# special mappings: unwrap tgid and srcid objects
			if colname.startswith('tgid') and type(d[k]) is dict:
				val = d[k]['tg_id']
			elif colname.startswith('suid') and type(d[k]) is dict:
				val = d[k]['unit_id']
			elif type(d[k]) is not dict:
				val = d[k]
			else:
				sys.stderr.write('value retrieval error %s %s %s\n' % (d['cc_event'], type(d[k]) is dict, k))
				val = -1
			# special mappings: map cc_event tag to an int
			if colname == 'cc_event':
				val = cc_events[d[k]]
			# special mappings: map affiliation to int
			if k == 'affiliation':
				if d[k] == 'global':
					val = 1
				elif d[k] == 'local':
					val = 0
				else:
					val = -1
			# special mappings: map duration to int(msec).
			if k == 'duration':
				val = int(d[k] * 1000)
			row.append(val)
			column_names.append(colname)
		command = "INSERT INTO data_store(%s) VALUES(%s)" % (','.join(column_names), ','.join(['?'] * len(row)))
		js = json.dumps({'command': command, 'row': row})
		if not self.db_msgq.full_p():
			msg = gr.message().make_from_string(js, 0, 0, 0)
			self.db_msgq.insert_tail(msg)
		else:
			self.db_msgq_overflow += 1

	def import_tsv(self, argv):
		cmd = argv[1]
		filename = argv[2]
		sysid = int(argv[3])
		if cmd == 'import_tgid':
			table = 'tgid_tags'
		elif cmd == 'import_unit':
			table = 'unit_id_tags'
		elif cmd == 'import_sysid':
			table = 'sysid_tags'
		else:
			print('%s unsupported' % (cmd))
			return
		q = 'INSERT INTO ' + table + '(rid, sysid, tag, priority) VALUES(?,?,?,?)'
		if table == 'sysid_tags':
			q = 'INSERT INTO ' + table + '(sysid, tag) VALUES(?,?)'
		rows = []
		with open(filename, 'r') as f:
			lines = f.read().rstrip().split('\n')
			for i in range(len(lines)):
				a = lines[i].split('\t')
				if i == 0:	# check hdr
					if not a[0].strip().isdigit():
						continue
				rid = int(a[0])
				tag = a[1]
				priority = 0 if len(a) < 3 else int(a[2])
				s = (rid, sysid, tag, priority)
				if table == 'sysid_tags':
					s = (rid, tag)
				rows.append(s)
		if len(rows):
			self.cursor.executemany(q, rows)
			self.conn.commit()

	def populate_event_keys(self):
		d = {cc_events[k]:k for k in cc_events}
		query = 'INSERT INTO event_keys(id, tag) VALUES(?, ?)'
		for k in sorted(d.keys()):
			self.cursor.execute(query, [k, d[k]])
		self.conn.commit()

def main():
	if len(sys.argv) > 1 and sys.argv[1] == 'reset_db':
		sql_dbi().reset_db()
		return

	db1 = sql_dbi()
	db1.connect()

	if len(sys.argv) > 1 and sys.argv[1] == 'setup':
		db1.cursor.execute(db1.sql_commands['create_tgid'])
		db1.cursor.execute(db1.sql_commands['create_unit_id'])
		db1.conn.commit()
		db1.conn.close()
		return

	if len(sys.argv) > 1 and sys.argv[1] == 'execute_lines':
		db1.execute_lines(sys.argv[2])
		return

	if len(sys.argv) > 1 and sys.argv[1] == 'execute':
		db1.execute(sys.argv[2])
		return

	if len(sys.argv) > 1 and sys.argv[1] == 'insert':
		db1.write('joins', (555, 5555, 5555555))
		return

	if len(sys.argv) > 3 and sys.argv[1].startswith('import_'):
		db1.import_tsv(sys.argv)
		return

	if len(sys.argv) < 3 or sys.argv[1] != 'query':
		print('nothing done')
		return

	result = db1.q(sys.argv[2])
	if result:
		for row in result:
			print ('%s' % ('\t'.join([str(x) for x in row])))

if __name__ == '__main__':
	main()
