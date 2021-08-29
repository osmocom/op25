#! /usr/bin/env python

# Copyright 2021 Max H. Parke KA1RBI, Michael Rose
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

import time
from time import sleep
from time import gmtime, strftime
import os
from os import listdir
from os.path import isfile, join
import sys
import traceback
import math
import json
import click
import datetime
from datatables import ColumnDT, DataTables
from flask import Flask, jsonify, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, desc, and_, or_, case, delete, insert, update, exc
from sqlalchemy.orm import Query
from sqlalchemy.exc import OperationalError
import sqlalchemy.types as types
from shutil import copyfile

sys.path.append('..')   # for emap
from emap import oplog_map, cc_events, cc_desc

app = Flask(__name__)
app.config.from_pyfile("../app.cfg")
app.config['SQLALCHEMY_ECHO'] = False  # set to True to send sql statements to the console

# enables session variables to be used
app.secret_key = b'kH8HT0ucrh' # random bytes - this key not used anywhere else

db = SQLAlchemy(app)

try:
    db.reflect(app=app)
    db.init_app(app)
except OperationalError as e:
    raise(e) # database is locked by another process

class MyDateType(types.TypeDecorator):
    impl = types.REAL
    def process_result_value(self, value, dialect):
        return datetime.datetime.fromtimestamp(value).strftime('%Y-%m-%d %H:%M:%S')

class column_helper(object):
    # convenience class - enables columns to be referenced as
    # for example, Foo.bar instead of Foo['bar']
    def __init__(self, table):
        self.table_ = db.metadata.tables[table]
        cols = self.table_.columns
        for k in cols.keys():
            setattr(self, k, cols[k])

def dbstate():
    database = app.config['SQLALCHEMY_DATABASE_URI'][10:]
    if not os.path.isfile(database):
        return 1 # db file does not exist
    fs = os.path.getsize(database)  
    if fs < 1024:
        return 2 # file size too small
    DataStore = column_helper('data_store')
    rows = db.session.query(DataStore.id).count()
    if rows < 1:
        return 4 # no rows present
    return 0 

# clears the sm (successMessage) after being used in jinja
def clear_sm():
    session['sm'] = 0
    return '' #must be an empty string or 'None' is displayed in the template

def t_gmt():
    t = time.strftime("%a, %d %b %Y %H:%M:%S", time.gmtime())
    return t

def t_loc():
    t = strftime("%a, %d %b %Y %H:%M:%S %Z")
    return t

# make these functions available to jinja
app.jinja_env.globals.update(t_gmt=t_gmt)
app.jinja_env.globals.update(t_loc=t_loc)
app.jinja_env.globals.update(clear_sm=clear_sm)

# for displaying the db file size, shamelessly stolen from SO
def convert_size(size_bytes):
   if size_bytes == 0:
       return "0 B"
   size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
   i = int(math.floor(math.log(size_bytes, 1024)))
   p = math.pow(1024, i)
   s = round(size_bytes / p, 2)
   return "%s %s" % (s, size_name[i])

def dbStats():
    DataStore = column_helper('data_store')
    DataStore = column_helper('data_store')
    SysIDTags  = column_helper('sysid_tags')
    DataStore.time.type =  MyDateType()
    rows = db.session.query(func.count(DataStore.id)).scalar()    
    if rows == 0:
        return(0, 0, 0, 0, 0, 0, 0)

    sys_count = db.session.query(DataStore.sysid) \
       .distinct(DataStore.sysid) \
       .group_by(DataStore.sysid) \
       .filter(DataStore.sysid != 0) \
       .count()

    # TODO: talkgroups and subs should be distinct by system
    talkgroups = db.session.query(DataStore.tgid) \
        .distinct(DataStore.tgid) \
        .group_by(DataStore.tgid) \
        .count()

    subs = db.session.query(DataStore.suid) \
        .distinct(DataStore.suid) \
        .group_by(DataStore.suid) \
        .count()

    firstRec = db.session.query(DataStore.time, func.min(DataStore.time)).scalar()
    lastRec = db.session.query(DataStore.time, func.max(DataStore.time)).scalar()
    f = app.config['SQLALCHEMY_DATABASE_URI'][10:]  # db file name
    dbsize = convert_size(os.path.getsize(f))
    return(rows, sys_count, talkgroups, subs, firstRec, lastRec, dbsize, f)

def sysList():
    DataStore = column_helper('data_store')
    rows = db.session.query(func.count(DataStore.id)).scalar()
    if rows == 0:
        return []
    SysIDTags  = column_helper('sysid_tags')
    sysList = db.session.query(DataStore.sysid, SysIDTags.tag.label('tag')) \
        .distinct(DataStore.sysid) \
        .outerjoin(SysIDTags.table_, SysIDTags.sysid == DataStore.sysid) \
        .filter(DataStore.sysid != 0)
    return sysList

def read_tsv(filename): # used by import_tsv and inspect_tsv, careful w/ changes
    rows = []
    with open(filename, 'r') as f:
        lines = f.read().rstrip().split('\n')
        for i in range(len(lines)):
            a = lines[i].split('\t')
            if i == 0:    # check hdr
                if not a[0].strip().isdigit():
                    continue
            if not a[0].strip().isdigit(): # check each a[0] for wildcards and skip (continue) if wildcards found
                continue
            rid = int(a[0])
            tag = a[1]
            priority = 0 if len(a) < 3 else int(a[2])
            s = (rid, tag, priority)
            rows.append(s)
    return rows

def import_tsv(argv):
    UnitIDTags = column_helper('unit_id_tags')
    TGIDTags   = column_helper('tgid_tags')
    cmd = argv[1]
    filename = argv[2]
    sysid = int(argv[3])
    if cmd == 'import_tgid':
        tbl = TGIDTags
    elif cmd == 'import_unit':
        tbl = UnitIDTags
    else:
        print('%s unsupported' % (cmd))
        return
    rows = read_tsv(filename)
    rm = 0  # records matched
    nr = 0  # new records
    dr = 0  # duplicate records
    if len(rows):
        for i in rows:
            recCount = db.session.query(tbl.table_).where(and_(tbl.rid == i[0], tbl.sysid == argv[3])).count()
            if recCount == 1:
                # update record
                q = update(tbl.table_) \
                    .where(and_(tbl.rid == i[0], tbl.sysid == argv[3])) \
                    .values(rid = int(i[0]), sysid = int(argv[3]), tag = i[1], priority = int(i[2]))
                db.session.execute(q)
                db.session.commit()
                rm +=1
            elif recCount == 0:
                # insert record
                q = insert(tbl.table_).values(rid = int(i[0]), sysid = int(argv[3]), tag = i[1], priority = int(i[2]))
                db.session.execute(q)
                db.session.commit()
                nr += 1
            else: 
                # delete all of the duplicates and insert new (duplicates break things)
                print('command %s - db error - %s records for %s %s' % (cmd, recCount, i[0], i[1]))
                delRec = delete(TGIDTags.table_).where(and_(tbl.rid == i[0], tbl.sysid == argv[3]))
                db.session.execute(delRec)
                db.session.commit()                
                q = insert(tbl.table_).values(rid = int(i[0]), sysid = int(argv[3]), tag = i[1], priority = int(i[2]))
                db.session.execute(q)
                db.session.commit()
                dr += 1
    return(rm, nr, dr)

@app.route("/")
def home():
    ds = dbstate()    
    if ds is not 0:
        return redirect('error?code=%s' % ds)
    params = request.args.to_dict()
    params['ekeys'] = sorted(oplog_map.keys())
    params['cc_desc'] = cc_desc
    return render_template("home.html", project="op25", params=params, dbstats=dbStats(), sysList=sysList())

@app.route("/about")
def about():
    ds = dbstate()
    if ds is not 0:
        return redirect('error?code=%s' % ds)
    params = request.args.to_dict()
    params['ekeys'] = sorted(oplog_map.keys())
    params['cc_desc'] = cc_desc
    return render_template("about.html", project="op25", params=params, sysList=sysList())

# error page for database errors
@app.route("/error")
def error_page():
    params = request.args.to_dict()
    params['file'] = app.config['SQLALCHEMY_DATABASE_URI'][10:]
    return render_template("error.html", params=params, file=params['file'], code=int(params['code']))

# Inspect TSV (import) - returns a table of the tsv for display in a div, accessed by ajax
@app.route("/inspect")
def inspect():
    params = request.args.to_dict()
    f = os.getcwd() + '/../' + params['file']
    i = read_tsv(f)
    return render_template("inspect.html", i=i)

# edit and import tags
@app.route("/edit_tags")
def edit_tags():
    UnitIDTags = column_helper('unit_id_tags')
    TGIDTags   = column_helper('tgid_tags')
    SysIDTags  = column_helper('sysid_tags')    
    params = request.args.to_dict()
    params['ekeys'] = sorted(oplog_map.keys())
    if 'cmd' not in params.keys(): # render talkgroup by default
        params['cmd'] = 'tgid'
    cmd = params['cmd']
    session['cmd'] = cmd
    systems = db.session.query(SysIDTags.sysid, SysIDTags.tag)
    p = os.getcwd() + '/..'
    tsvs = []
    for root, dirs, files in os.walk(p, topdown=True):
        for file in files:
            if file.endswith(".tsv") and not file.startswith("._"):
                 print(os.path.join(root, file))
                 tsvs.append(os.path.join(root, file))
    tsvs.sort()
    return render_template("edit_tags.html", params=params, systems=systems, sysList=sysList(), p=p, cmd=cmd, tsvs=tsvs)
    
# data for tags table editor
@app.route("/edittg")
def edittg():
    params = request.args.to_dict()
    params['ekeys'] = sorted(oplog_map.keys())
    cmd = params['cmd'] 
    sysid = int(params['sysid'])
    UnitIDTags = column_helper('unit_id_tags')
    TGIDTags   = column_helper('tgid_tags')
    SysIDTags  = column_helper('sysid_tags')
    if cmd == 'tgid':
        tbl = TGIDTags
    if cmd == 'unit':
        tbl = UnitIDTags
    column_d = {
        'tgid': [
            ColumnDT(TGIDTags.id),
            ColumnDT(TGIDTags.sysid),
            ColumnDT(TGIDTags.rid),
            ColumnDT(TGIDTags.tag),
            ColumnDT(TGIDTags.id)
        ],
        'unit': [
            ColumnDT(UnitIDTags.id),
            ColumnDT(UnitIDTags.sysid),
            ColumnDT(UnitIDTags.rid),
            ColumnDT(UnitIDTags.tag),
            ColumnDT(UnitIDTags.id)
        ]
    }
    q = db.session.query(tbl.id, tbl.sysid, tbl.rid, tbl.tag).order_by(tbl.rid)
    if sysid != 0:
        q = q.filter(tbl.sysid == sysid)   
    rowTable = DataTables(params, q, column_d[cmd])
    js = jsonify(rowTable.output_result())
    return js

#dtd = delete tag data
@app.route("/dtd")
def dtd():
    params = request.args.to_dict()
    params['ekeys'] = sorted(oplog_map.keys())    
    cmd = params['cmd']
    UnitIDTags = column_helper('unit_id_tags')
    TGIDTags   = column_helper('tgid_tags')
    SysIDTags  = column_helper('sysid_tags')   
    recId = params['id']
    if cmd == 'tgid':
        tbl = TGIDTags
    if cmd == 'unit':
        tbl = UnitIDTags
    delRec = delete(tbl.table_).where(tbl.id == recId)
    db.session.execute(delRec)
    db.session.commit()
    session['sm'] = 2
    return redirect('/edit_tags?cmd=' + cmd)

#utd = update tag data
@app.route("/utd")
def utd():
    params = request.args.to_dict()
    params['ekeys'] = sorted(oplog_map.keys())
    cmd = params['cmd']
    UnitIDTags = column_helper('unit_id_tags')
    TGIDTags   = column_helper('tgid_tags')
    SysIDTags  = column_helper('sysid_tags')
    recId = params['id']
    tag = params['tag']
    if cmd == 'tgid':
        tbl = TGIDTags
    if cmd == 'unit':
        tbl = UnitIDTags
    upRec = update(tbl.table_).where(tbl.id == recId).values(tag=tag)
    db.session.execute(upRec)
    db.session.commit()
    session['sm'] = 1
    return redirect('/edit_tags?cmd=' + cmd)

# import tags
@app.route("/itt")
def itt():
    params = request.args.to_dict()
    params['ekeys'] = sorted(oplog_map.keys())
    cmd = params['cmd']
    argv = [ None, 'import_' + cmd, os.getcwd() + '/../' + params['file'], params['sysid'] ]
    session['imp_results'] = import_tsv(argv)
    session['sm'] = 3
    return redirect('/edit_tags?cmd=' + cmd) 
    
# delete all talkgroup/subscriber tags
@app.route("/delTags")
def delTags():
    params = request.args.to_dict()
    params['ekeys'] = sorted(oplog_map.keys())
    cmd = params['cmd']
    UnitIDTags = column_helper('unit_id_tags')
    TGIDTags   = column_helper('tgid_tags')
    SysIDTags  = column_helper('sysid_tags')
    sysid = params['sysid']
    if cmd == 'tgid':
        tbl = TGIDTags
    if cmd == 'unit':
        tbl = UnitIDTags
    delRec = delete(tbl.table_).where(tbl.sysid == sysid)
    db.session.execute(delRec)
    db.session.commit()
    db.session.execute("VACUUM") # sqlite3 clean up -- reduces file size
    session['sm'] = 4
    return redirect('/edit_tags?cmd=' + cmd)

# system tag editor functions (entirely separate from the tags editor above)
@app.route("/editsys")
def editsys():
    params = request.args.to_dict()
    params['ekeys'] = sorted(oplog_map.keys())
    params['cc_desc'] = cc_desc
    SysIDTags  = column_helper('sysid_tags')
    systems = db.session.query(SysIDTags.sysid, SysIDTags.tag)
    return render_template("editsys.html", params=params, systems=systems, sysList=sysList())

#dsd = delete system data
@app.route("/dsd")
def dsd():
    params = request.args.to_dict()
    SysIDTags  = column_helper('sysid_tags')
    recId = params['id']
    delRec = delete(SysIDTags.table_).where(SysIDTags.id == recId)
    db.session.execute(delRec)
    db.session.commit()
    return redirect('/editsys')
    
#usd = update system data
@app.route("/usd")
def usd():
    params = request.args.to_dict()
    SysIDTags  = column_helper('sysid_tags')
    recId = params['id']
    tag = params['tag']    
    upRec = update(SysIDTags.table_).where(SysIDTags.id == recId).values(tag=tag)
    db.session.execute(upRec)
    db.session.commit()
    return redirect('/editsys')    

#esd = edit system data (system tags)
@app.route("/esd")
def esd():
    params = request.args.to_dict()
    SysIDTags  = column_helper('sysid_tags')
    column_d = {
        's': [
            ColumnDT(SysIDTags.id),
            ColumnDT(SysIDTags.sysid),
            ColumnDT(SysIDTags.tag),
            ColumnDT(SysIDTags.id)
        ]
    }
    q = db.session.query(SysIDTags.id, SysIDTags.sysid, SysIDTags.tag)
    rowTable = DataTables(params, q, column_d['s'])
    js = jsonify(rowTable.output_result())
    return js

#asd = add system data
@app.route("/asd")
def asd():
    params = request.args.to_dict()
    ns = params['id']
    nt = params['tag']
    #todo: validate input
    SysIDTags  = column_helper('sysid_tags')
    insRec = insert(SysIDTags.table_).values(sysid=ns, tag=nt)
    db.session.execute(insRec)
    db.session.commit()
    return redirect('/editsys')

# purge database functions
@app.route("/purge")
def purge():
    params = request.args.to_dict()
    params['ekeys'] = sorted(oplog_map.keys())
    DataStore  = column_helper('data_store')
    destfile = ''
    b = False
    if 'bu' in params.keys():
        if params['bu'] == 'true':
            b = True
            t = strftime("%Y%m%d_%H%M%S")
            destfile = 'op25-backup-%s.db' % t
            src = app.config['SQLALCHEMY_DATABASE_URI'][10:]
            s = src.split('/')
            f = s[-1]
            dst = src.replace(f, destfile)
    if 'simulate' in params.keys():
        simulate = params['simulate']
    if 'action' in params.keys():
        if params['action'] == 'purge':
            sd = params['sd']
            ed = params['ed']
            sysid = int(params['sysid'])
            delRec = delete(DataStore.table_).where(DataStore.time >= int(sd), DataStore.time <= int(ed))
            recCount = db.session.query(DataStore.id).filter(and_(DataStore.time >= int(sd), DataStore.time <= int(ed)))
            if sysid != 0:
                recCount = recCount.filter(DataStore.sysid == sysid)
                delRec = delRec.where(DataStore.sysid == sysid)
            if 'kv' in params.keys(): # keep voice calls
                if params['kv'] == 'true':
                    recCount = recCount.where(and_(DataStore.opcode != 0, DataStore.opcode != 2))
                    delRec = delRec.where(and_(DataStore.opcode != 0, DataStore.opcode != 2))
            recCount = recCount.count()
            dispQuery = delRec.compile(compile_kwargs={"literal_binds": True})
            if simulate == 'false':
                if b == True:
                    copyfile(src, dst)
                db.session.execute(delRec)
                db.session.commit()
                db.session.execute("VACUUM") # sqlite3 clean up -- reduces file size
                successMessage = 1
            else:
                successMessage = 2
    else:
        recCount = 0
        successMessage = 0
        dispQuery = ''
        
    return render_template("purge.html", \
        project="op25", \
        params=params, \
        dbstats=dbStats(), \
        sysList=sysList(), \
        successMessage=successMessage, \
        recCount=recCount, \
        dispQuery=dispQuery, \
        destfile=destfile )

# displays all logs w/ datatables
@app.route("/logs")
def logs():
    UnitIDTags = column_helper('unit_id_tags')
    TGIDTags   = column_helper('tgid_tags')
    tag = ''
    params = request.args.to_dict()
    params['ekeys'] = oplog_map.keys()
    params['cc_desc'] = cc_desc
    t = None if 'q' not in params.keys() else params['q']
    sysid = 0 if 'sysid' not in params.keys() else int(params['sysid'])
    if sysid != 0:
        if t is not None and params['r'] == 'tgid':
            q = db.session.query(TGIDTags.tag).where(and_(TGIDTags.rid == t, TGIDTags.sysid == sysid))
        if t is not None and params['r'] == 'su':
            q = db.session.query(UnitIDTags.tag).where(and_(UnitIDTags.rid == t, UnitIDTags.sysid == sysid))
        if q.count() > 0:
            tg = (db.session.execute(q).one())
            tag = (' - %s' % tg.tag)
    if params['r'] == 'cc_event':
        mapl = oplog_map[params['p'].strip()]
        params['ckeys'] = [s[1] for s in mapl if s[0] != 'opcode' and s[0] != 'cc_event']
        
    return render_template("logs.html", \
        project="logs", \
        params=params, \
        sysList=sysList(), \
        tag=tag )

# data for /logs
@app.route("/data")
def data():
    """Return server side data."""
    # GET parameters
    params = request.args.to_dict()

    host_rid = None if 'host_rid' not in params.keys() else params['host_rid']
    host_function_type = None if 'host_function_type' not in params.keys() else params['host_function_type']
    host_function_param = None if 'host_function_param' not in params.keys() else params['host_function_param'].strip()

    filter_tgid = None if 'tgid' not in params.keys() else int(params['tgid'].strip())
    filter_suid = None if 'suid' not in params.keys() else int(params['suid'].strip())
    
    start_time = None if 'sdate' not in params.keys() else datetime.datetime.utcfromtimestamp(float(params['sdate']))
    end_time = None if 'edate' not in params.keys() else datetime.datetime.utcfromtimestamp(float(params['edate']))
    print(params)
    sysid = None if 'sysid' not in params.keys() else int(params['sysid'])
    
    stime = int(params['sdate']) #used in the queries
    etime = int(params['edate']) #used in the queries

    DataStore  = column_helper('data_store')
    EventKeys  = column_helper('event_keys')
    SysIDTags  = column_helper('sysid_tags')
    UnitIDTags = column_helper('unit_id_tags')
    TGIDTags   = column_helper('tgid_tags')
    LocRegResp = column_helper('loc_reg_resp_rv')

    DataStore.time.type = MyDateType()

    k = 'logs'
    if host_function_type:
        k = '%s_%s' % (k, host_function_type)

    column_d = {
        'logs_su': [
            ColumnDT(TGIDTags.tag),
            ColumnDT(DataStore.tgid),
            ColumnDT(DataStore.tgid),
        ],
        'logs_tgid': [
            ColumnDT(DataStore.suid),
            ColumnDT(UnitIDTags.tag),
            ColumnDT(DataStore.suid),
            ColumnDT(DataStore.time)
        ],

        'logs_calls': [
            ColumnDT(DataStore.time),
            ColumnDT(SysIDTags.tag),
            ColumnDT(DataStore.tgid),
            ColumnDT(TGIDTags.tag),
            ColumnDT(DataStore.frequency),
            ColumnDT(DataStore.suid)
        ],
        'logs_joins': [
            ColumnDT(DataStore.time),
            ColumnDT(DataStore.opcode),
            ColumnDT(DataStore.sysid),
            ColumnDT(SysIDTags.tag),
            ColumnDT(LocRegResp.tag),
            ColumnDT(DataStore.tgid),
            ColumnDT(TGIDTags.tag),
            ColumnDT(DataStore.suid),
            ColumnDT(UnitIDTags.tag)
        ],
        'logs_total_tgid': [
            ColumnDT(DataStore.sysid),
            ColumnDT(SysIDTags.tag),
            ColumnDT(DataStore.tgid),
            ColumnDT(TGIDTags.tag),
            ColumnDT(DataStore.tgid)
        ],
        'logs_call_detail': [
            ColumnDT(DataStore.time),
            ColumnDT(DataStore.opcode),
            ColumnDT(SysIDTags.sysid),
            ColumnDT(SysIDTags.tag),
            ColumnDT(DataStore.tgid),
            ColumnDT(TGIDTags.tag),
            ColumnDT(DataStore.suid),
            ColumnDT(UnitIDTags.tag),
            ColumnDT(DataStore.frequency)
        ]        
    }

    """or_( EventKeys.tag == 'grp_v_ch_grant', EventKeys.tag == 'grp_v_ch_grant_exp'),"""
    
    query_d = {
        'logs_total_tgid': db.session.query(DataStore.sysid, \
                                            SysIDTags.tag, \
                                            DataStore.tgid, \
                                            TGIDTags.tag, \
                                            func.count(DataStore.tgid).label('count'))
            .group_by(DataStore.tgid)
            .outerjoin(SysIDTags.table_, DataStore.sysid == SysIDTags.sysid)
            .outerjoin(TGIDTags.table_, DataStore.tgid == TGIDTags.rid)
            .filter(and_(DataStore.tgid != 0), (DataStore.frequency != None) ),
            
        'logs_call_detail': db.session.query(DataStore.time, \
                                             DataStore.opcode, \
                                             DataStore.sysid, \
                                             SysIDTags.tag, \
                                             DataStore.tgid, \
                                             TGIDTags.tag, \
                                             DataStore.suid, \
                                             UnitIDTags.tag, \
                                             DataStore.frequency )
            .outerjoin(SysIDTags.table_, DataStore.sysid == SysIDTags.sysid)
            .outerjoin(TGIDTags.table_, and_(DataStore.tgid == TGIDTags.rid, DataStore.sysid == TGIDTags.sysid))
            .outerjoin(UnitIDTags.table_, and_(DataStore.suid == UnitIDTags.rid, DataStore.sysid == UnitIDTags.sysid))
            .filter(and_(DataStore.tgid != 0), (DataStore.frequency != None) )
            .filter(or_(DataStore.opcode == 0, and_(DataStore.opcode == 2, DataStore.mfrid == 144)) ),

            
        'logs_tgid': db.session.query(DataStore.suid, \
                                      UnitIDTags.tag, \
                                      func.count(DataStore.suid).label('count'), func.max(DataStore.time).label('last') )
            .outerjoin(UnitIDTags.table_, and_(DataStore.suid == UnitIDTags.rid, DataStore.sysid == UnitIDTags.sysid)),

        'logs_su': db.session.query(TGIDTags.tag, \
                                    DataStore.tgid, \
                                    func.count(DataStore.tgid).label('count') )
            .outerjoin(TGIDTags.table_, DataStore.tgid == TGIDTags.rid), 

        'logs_calls': db.session.query(DataStore.time, \
                                       SysIDTags.tag, \
                                       DataStore.tgid, \
                                       TGIDTags.tag, \
                                       DataStore.frequency, \
                                       DataStore.suid )
            .join(EventKeys.table_, and_(or_( EventKeys.tag == 'grp_v_ch_grant', EventKeys.tag == 'grp_v_ch_grant_mbt'),EventKeys.id == DataStore.cc_event))
            .outerjoin(TGIDTags.table_, and_(TGIDTags.rid == DataStore.tgid, TGIDTags.sysid == DataStore.sysid))
            .outerjoin(SysIDTags.table_, DataStore.sysid == SysIDTags.sysid),

        'logs_joins': db.session.query(DataStore.time, \
                                       DataStore.opcode, \
                                       DataStore.sysid, \
                                       SysIDTags.tag, \
                                       LocRegResp.tag, \
                                       DataStore.tgid, \
                                       TGIDTags.tag, \
                                       DataStore.suid, \
                                       UnitIDTags.tag )
            .join(LocRegResp.table_, DataStore.p == LocRegResp.rv)
            .outerjoin(SysIDTags.table_, DataStore.sysid == SysIDTags.sysid)
            .outerjoin(TGIDTags.table_, and_(DataStore.tgid == TGIDTags.rid, DataStore.sysid == TGIDTags.sysid))
            .outerjoin(UnitIDTags.table_, and_(DataStore.suid == UnitIDTags.rid, DataStore.sysid == UnitIDTags.sysid))
            .filter(or_(DataStore.opcode == 40, DataStore.opcode == 43)) # joins
    } # end query_d

    if host_function_type != 'cc_event':
        q = query_d[k]

    if host_function_type in 'su tgid'.split():    
        filter_col = {'su': DataStore.suid, 'tgid': DataStore.tgid}
        group_col = {'su': DataStore.tgid, 'tgid': DataStore.suid}
        if '?' in host_rid:
            id_start = int(host_rid.replace('?', '0'))
            id_end = int(host_rid.replace('?', '9'))
            q = q.filter(filter_col[host_function_type] >= id_start, filter_col[host_function_type] <= id_end)
        elif '-' in host_rid:
            id_start, id_end = host_rid.split('-')
            id_start = int(id_start)
            id_end = int(id_end)
            q = q.filter(filter_col[host_function_type] >= id_start, filter_col[host_function_type] <= id_end)
        else:
            q = q.filter(filter_col[host_function_type] == int(host_rid))
        q = q.group_by(group_col[host_function_type])
        q = q.filter(DataStore.suid != None)

    dt_cols = {
        'logs_tgid'       : [ DataStore.suid, UnitIDTags.tag, 'count' ],
        'logs_su'         : [ TGIDTags.tag, DataStore.tgid, 'count' ],
        'logs_calls'      : [ DataStore.time, SysIDTags.tag, DataStore.tgid, TGIDTags.tag, DataStore.frequency, DataStore.suid ],
        'logs_joins'      : [ DataStore.time, SysIDTags.tag, LocRegResp.tag, TGIDTags.tag, DataStore.suid ],
        'logs_total_tgid' : [ DataStore.sysid, SysIDTags.tag, DataStore.tgid, TGIDTags.tag, 'count' ]
    }

    if host_function_type == 'cc_event':
        mapl = oplog_map[host_function_param]
        columns = []
        for row in mapl:
            col = getattr(DataStore, row[0])
            if row[0] == 'sysid':
                col = SysIDTags.tag
            elif row[1] == 'Talkgroup':
                col = TGIDTags.tag
            elif row[1] == 'Source' or row[1] == 'Target':
                col = UnitIDTags.tag
            elif row[0] == 'cc_event':
                continue
                #col = EventKeys.tag
            elif row[0] == 'opcode':
                continue
            elif host_function_param == 'loc_reg_resp' and row[0] == 'p':
                col = LocRegResp.tag
            columns.append(col)

        column_dt = [ColumnDT(s) for s in columns]

        q = db.session.query(*columns
            ).join(
                EventKeys.table_, and_( EventKeys.tag == host_function_param, EventKeys.id == DataStore.cc_event)
            ).outerjoin(
                SysIDTags.table_, DataStore.sysid == SysIDTags.sysid
            )
        if host_function_param == 'grp_aff_resp':
            q = q.outerjoin(
                TGIDTags.table_, and_(DataStore.tgid2 == TGIDTags.rid, DataStore.sysid == TGIDTags.sysid)
            ).outerjoin(
                UnitIDTags.table_, and_(DataStore.suid == UnitIDTags.rid, DataStore.sysid == UnitIDTags.sysid)
            )

        elif host_function_param == 'ack_resp_fne' or host_function_param == 'grp_aff_q'  or host_function_param == 'u_reg_cmd':
            q = q.outerjoin(
                TGIDTags.table_, and_(DataStore.tgid2 == TGIDTags.rid, DataStore.sysid == TGIDTags.sysid)
            ).outerjoin(
                UnitIDTags.table_, and_(DataStore.suid2 == UnitIDTags.rid, DataStore.sysid == UnitIDTags.sysid)
            )
        else:
            q = q.outerjoin(
                TGIDTags.table_, and_(DataStore.tgid == TGIDTags.rid, DataStore.sysid == TGIDTags.sysid)
            ).outerjoin(
                UnitIDTags.table_, and_(DataStore.suid == UnitIDTags.rid, DataStore.sysid == UnitIDTags.sysid)
            )

        if host_function_param == 'loc_reg_resp':
            q = q.join(LocRegResp.table_, LocRegResp.rv == DataStore.p)

    if host_function_type == 'cc_event':
        cl = columns
    elif k in dt_cols:
        cl = dt_cols[k]
    else:
        cl = None

    # apply tgid and suid filters if present
    if host_function_type == 'cc_event':
        if filter_tgid is not None and int(filter_tgid) != 0:
            q = q.filter(DataStore.tgid == filter_tgid)
        if filter_suid is not None and int(filter_suid) != 0:
            q = q.filter(DataStore.suid == filter_suid)

    if cl:
        c = int(params['order[0][column]'])
        d = params['order[0][dir]']	# asc or desc
        if d == 'asc':
            q = q.order_by(cl[c])
        else:
            q = q.order_by(desc(cl[c]))
    
    q = q.filter(and_(DataStore.time >= int(stime), DataStore.time <= int(etime)))

    if sysid != 0:
        q = q.filter(DataStore.sysid == sysid)

    if host_function_type == 'cc_event':
        rowTable = DataTables(params, q, column_dt)
    else:
        rowTable = DataTables(params, q, column_d[k])

    js = jsonify(rowTable.output_result())
#   j= 'skipped' # json.dumps(rowTable.output_result(), indent=4, separators=[',', ':'], sort_keys=True)
#   with open('data-log', 'a') as logf:
#       s = '\n\t'.join(['%s:%s' % (k, params[k]) for k in params.keys()])
#       logf.write('keys: %s\n' % (' '.join(params.keys())))
#       logf.write('params:\n\t%s\nrequest: %s\n' % (s, function_req))
#       logf.write('%s\n' % j)
    return js

# switch and backup database file
@app.route("/switch_db")
def switch_db(): 
    params = request.args.to_dict()
    params['ekeys'] = sorted(oplog_map.keys())
    p = os.getcwd() + '/..'
    files = [f for f in listdir(p) if isfile(join(p, f))]
    files.sort()    
    if 'cmd' not in params.keys(): 
        curr_file = app.config['SQLALCHEMY_DATABASE_URI'].split('/')[-1]
        return render_template("switch_db.html", params=params, files=files, curr_file=curr_file)
    if params['cmd'] == 'backup':
        t = strftime("%Y-%m-%d_%H%M%S")
        destfile = 'op25-backup-%s.db' % t
        src = app.config['SQLALCHEMY_DATABASE_URI'][10:]
        s = src.split('/')
        curr_file = s[-1]
        dst = src.replace(curr_file, destfile)
        copyfile(src, dst)
        return render_template("switch_db.html", params=params, destfile=destfile, curr_file=curr_file, files=files, sm=1)
    if params['cmd'] == 'switch':
        new_f = params['file']
        database = app.config['SQLALCHEMY_DATABASE_URI']
        f = database.split('/')[-1]
        new_db = database.replace(f, new_f)
        print('switching database to: %s' % new_db)
        app.config['SQLALCHEMY_DATABASE_URI'] = new_db
        return redirect('/')
