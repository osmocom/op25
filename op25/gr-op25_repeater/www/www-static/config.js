// Copyright 2017, 2018, 2019, 2020, 2021 Max H. Parke KA1RBI
// 
// This file is part of OP25
//
// OP25 is free software; you can redistribute it and/or modify it
// under the terms of the GNU General Public License as published by
// the Free Software Foundation; either version 3, or (at your option)
// any later version.
//
// OP25 is distributed in the hope that it will be useful, but WITHOUT
// ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
// or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
// License for more details.
//
// You should have received a copy of the GNU General Public License
// along with OP25; see the file COPYING. If not, write to the Free
// Software Foundation, Inc., 51 Franklin Street, Boston, MA
// 02110-1301, USA.


// Functions related to Online Config

function find_parent(ele, tagname) {
    while (ele) {
        if (ele.nodeName == tagname)
            return ele;
        else if (ele.nodeName == 'HTML')
            return null;
        ele = ele.parentNode;
    }
    return null;
}

function f_command(ele, command) {
    var myrow = find_parent(ele, 'TR');
    var mytbl = find_parent(ele, 'TABLE');
    amend_d(myrow, mytbl, command);
}

function edit_freq(freq, to_ui) {
    var MHZ = 1000000;
    if (to_ui) {
        var f = freq / MHZ + '';
        if (f.indexOf('.') == -1)
            f += '.0';
        return f;
    } else {
        var f = parseFloat(freq);
        if (freq.indexOf('.'))
            f *= MHZ;
        return Math.round(f);
    }
}


function edit_d(d, to_ui) {
    var new_d = {};
    var hexints = {
        'nac': 1
    };
    var ints = {
        'if_rate': 1,
        'ppm': 1,
        'rate': 1,
        'offset': 1,
        'nac': 1,
        'logfile-workers': 1,
        'decim-amt': 1,
        'seek': 1,
        'hamlib-model': 1
    };
    var bools = {
        'active': 1,
        'trunked': 1,
        'rate': 1,
        'offset': 1,
        'phase2_tdma': 1,
        'phase2-tdma': 1,
        'wireshark': 1,
        'udp-player': 1,
        'audio-if': 1,
        'tone-detect': 1,
        'vocoder': 1,
        'audio': 1,
        'pause': 1
    };
    var floats = {
        'costas-alpha': 1,
        'gain-mu': 1,
        'calibration': 1,
        'fine-tune': 1,
        'gain': 1,
        'excess-bw': 1,
        'offset': 1,
        'excess_bw': 1
    };
    var lists = {
        'blacklist': 1,
        'whitelist': 1,
        'cclist': 1
    };
    var freqs = {
        'frequency': 1,
        'cclist': 1
    };
    for (var k in d) {
        if (!to_ui) {
            if (d[k] == 'None')
                new_d[k] = '';
            else
                new_d[k] = d[k];
            if (k == 'plot' && !d[k].length)
                new_d[k] = null;
            if (k in ints) {
                new_d[k] = parseInt(new_d[k]);
            } else if (k in floats) {
                new_d[k] = parseFloat(new_d[k]);
            } else if (k in lists) {
                var l = [];
                if (new_d[k].length)
                    l = new_d[k].split(',');
                if (k in freqs && new_d[k].length) {
                    var new_l = [];
                    for (var i in l)
                        new_l.push(edit_freq(l[i], to_ui));
                    new_d[k] = new_l;
                } else {
                    new_d[k] = l;
                }
            } else if (k in freqs) {
                new_d[k] = edit_freq(new_d[k], to_ui);
            }
        } else {
            if (k in hexints) {
                if (d[k] == null)
                    new_d[k] = '0x0';
                else
                    new_d[k] = '0x' + d[k].toString(16);
            } else if (k in ints) {
                if (d[k] == null)
                    new_d[k] = '';
                else
                    new_d[k] = d[k].toString(10);
            } else if (k in lists) {
                if (k in freqs) {
                    var new_l = [];
                    for (var i in d[k]) {
                        new_l.push(edit_freq(d[k][i], to_ui));
                    }
                    new_d[k] = new_l.join(',');
                } else {
                    if (!d[k] || !d[k].length)
                        new_d[k] = [];
                    else
                        new_d[k] = d[k].join(',');
                }
            } else if (k in freqs) {
                new_d[k] = edit_freq(d[k], to_ui);
            } else {
                new_d[k] = d[k];
            }
        }
    }
    return new_d;
}


function edit_l(cfg, to_ui) {
    var new_d = {
        'devices': [],
        'channels': []
    };
    for (var device in cfg['devices'])
        new_d['devices'].push(edit_d(cfg['devices'][device], to_ui));
    for (var channel in cfg['channels'])
        new_d['channels'].push(edit_d(cfg['channels'][channel], to_ui));
    new_d['backend-rx'] = edit_d(cfg['backend-rx'], to_ui);
    return new_d;
}

function amend_d(myrow, mytbl, command) {
    var trunk_row = null;
    if (mytbl.id == 'chtable')
        trunk_row = find_next(myrow, 'TR');
    if (command == 'delete') {
        var ok = confirm('Confirm delete');
        if (ok) {
            myrow.parentNode.removeChild(myrow);
            if (mytbl.id == 'chtable')
                trunk_row.parentNode.removeChild(trunk_row);
        }
    } else if (command == 'clone') {
        var newrow = myrow.cloneNode(true);
        newrow.id = find_free_id('id_');
        if (mytbl.id == 'chtable') {
            var newrow2 = trunk_row.cloneNode(true);
            newrow2.id = 'tr_' + newrow.id.substring(3);
            if (trunk_row.nextSibling) {
                myrow.parentNode.insertBefore(newrow2, trunk_row.nextSibling);
                myrow.parentNode.insertBefore(newrow, trunk_row.nextSibling);
            } else {
                myrow.parentNode.appendChild(newrow);
                myrow.parentNode.appendChild(newrow2);
            }
        } else {
            if (myrow.nextSibling)
                myrow.parentNode.insertBefore(newrow, myrow.nextSibling);
            else
                myrow.parentNode.appendChild(newrow);
        }
    } else if (command == 'new') {
        var newrow = null;
        var parent = null;
        var pfx = 'id_';
        if (mytbl.id == 'chtable') {
            newrow = document.getElementById('chrow').cloneNode(true);
            parent = document.getElementById('chrow').parentNode;
        } else if (mytbl.id == 'devtable') {
            newrow = document.getElementById('devrow').cloneNode(true);
            parent = document.getElementById('devrow').parentNode;
        } else if (mytbl.className == 'tgtable') {
            newrow = mytbl.querySelector('.tgrow').cloneNode(true);
            parent = mytbl.querySelector('.tgrow').parentNode;
            pfx = 'tg_';
        } else {
            return null;
        }
        newrow.style['display'] = '';
        newrow.id = find_free_id(pfx);
        parent.appendChild(newrow);
        if (mytbl.id == 'chtable') {
            var newrow2 = document.getElementById('trrow').cloneNode(true);
            newrow2.id = 'tr_' + newrow.id.substring(3);
            parent.appendChild(newrow2);
        }
        return newrow;
    }
}

function f_save_list(ele) {
    var flist = [];
    for (var nac in enable_status) {
        if (enable_status[nac])
            flist.push(nac.toString(10));
    }

    if (flist.length == 0) {
	    jAlert('Cannot disable all NACs - request ignored.', 'Warning');
    }
    document.getElementById('save_list_row').style['display'] = 'none';
    enable_changed = false;
    send_command('settings-enable', flist.join(','));
}

function f_enable_changed(ele, nac) {
    enable_status[nac] = ele.checked;
    enable_changed = true;
    document.getElementById('save_list_row').style['display'] = '';
}


function config_list(d) {
    var html = '';
    html += '<select id="config_select" name="cfg-list">';
    for (var file in d['data']) {
        html += '<option value="' + d['data'][file] + '">' + d['data'][file] + '</option>';
    }
    html += '<option value="New Configuration">New Configuration</option>';
    html += '</select>';
    document.getElementById('cfg_list_area').innerHTML = html;
}

function config_data(d) {
    var cfg = edit_l(d['data'], true);
    open_editor();
    var chtable = document.getElementById('chtable');
    var devtable = document.getElementById('devtable');
    var chrow = document.getElementById('chrow');
    var devrow = document.getElementById('devrow');
    for (var device in cfg['devices'])
        rollup_row('dev', amend_d(devrow, devtable, 'new'), cfg['devices'][device]);
    for (var channel in cfg['channels'])
        rollup_row('ch', amend_d(chrow, chtable, 'new'), cfg['channels'][channel]);
    rollup_rx_rows(cfg['backend-rx']);
}


function open_editor() {
    document.getElementById('edit_settings').style['display'] = '';
    var rows = document.querySelectorAll('.dynrow');
    var ct = 0;
    for (var r in rows) {
        var row = rows[r];
        ct += 1;
        if (row.id && (row.id.substring(0, 3) == 'id_' || row.id.substring(0, 3) == 'tr_')) {
            row.parentNode.removeChild(row);
        }
    }
    var oldtbl = document.getElementById('rt_1');
    if (oldtbl)
        oldtbl.parentNode.removeChild(oldtbl);
    var tbl = document.getElementById('rxopt-table');
    var newtbl = tbl.cloneNode(true);
    newtbl.id = 'rt_1';
    newtbl.style['display'] = '';
    var rxrow = newtbl.querySelector('.rxrow');
    var advrow = newtbl.querySelector('.advrow');
    rxrow.id = 'rx_1';
    advrow.id = 'rx_2';
    if (tbl.nextSibling)
        tbl.parentNode.insertBefore(newtbl, tbl.nextSibling);
    else
        tbl.parentNode.appendChild(newtbl);
}

function find_next(e, tag) {
    var n = e.nextSibling;
    for (var i = 0; i < 25; i++) {
        if (n == null)
            return null;
        if (n.nodeName == tag)
            return n;
        n = n.nextSibling;
    }
    return null;
}

function find_free_id(pfx) {
    for (var seq = 1; seq < 5000; seq++) {
        var test_id = pfx + seq;
        var ele = document.getElementById(test_id);
        if (!ele)
            return test_id;
    }
    return null;
}

function f_trunked(e) {
    var row = find_parent(e, 'TR');
    var trrow = document.getElementById('tr_' + row.id.substring(3));
    trrow['style']['display'] = e.checked ? '' : 'none';
}

function read_write_sel(sel_node, def) {
    var result = [];
    var elist = sel_node.querySelectorAll('option');
    for (var e in elist) {
        var ele = elist[e];
        if (def) {
            if (!def[sel_node.name])
                return;
            var options = def[sel_node.name].split(',');
            var opts = {};
            for (var o in options)
                opts[options[o]] = 1;
            if (ele.value in opts)
                ele.selected = true;
            else
                ele.selected = false;
        } else {
            if (ele.selected)
                result.push(ele.value);
        }
    }
    if (!def)
        return result.join();
}

function read_write(elist, def) {
    var result = {};
    for (var e in elist) {
        var ele = elist[e];
        if (ele.nodeName == 'INPUT') {
            if (ele.type == 'text')
                if (def)
                    ele.value = def[ele.name];
                else
                    result[ele.name] = ele.value;
            else if (ele.type == 'checkbox')
                if (def)
                    ele.checked = def[ele.name];
                else
                    result[ele.name] = ele.checked;
        } else if (ele.nodeName == 'SELECT') {
            if (def)
                read_write_sel(ele, def);
            else
                result[ele.name] = read_write_sel(ele, def);
        }
    }
    if (!def)
        return result;
}

function rollup_row(which, row, def) {
    var elements = Array.from(row.querySelectorAll('input,select'));
    if (which == 'ch') {
        var trrow = document.getElementById('tr_' + row.id.substring(3));
        var trtable = trrow.querySelector('table.trtable');
        elements = elements.concat(Array.from(trtable.querySelectorAll('input,select')));
        if (def)
            trrow.style['display'] = def['trunked'] ? '' : 'none';
    } else if (which == 'rx') {
        var advrow = document.getElementById('rx_2');
        elements = elements.concat(Array.from(advrow.querySelectorAll('input,select')));
    }
    var result = read_write(elements, def);
    if (which == 'ch') {
        var tgtable = trrow.querySelector('table.tgtable');
        var tgrow = trrow.querySelector('tr.tgrow');
        if (def) {
            for (var k in def['tgids']) {
                var val = def['tgids'][k];
                var newrow = amend_d(tgrow, tgtable, 'new');
                var inputs = newrow.querySelectorAll('input');
                read_write(inputs, {
                    'tg_id': k,
                    'tg_tag': val
                });
            }
        } else {
            var tgids = {};
            var rows = tgtable.querySelectorAll('tr.tgrow');
            for (var i = 0; i < rows.length; i++) {
                if (rows[i].id == null || rows[i].id.substring(0, 3) != 'tg_')
                    continue;
                var inputs = rows[i].querySelectorAll('input');
                var vals = read_write(inputs, null);
                tgids[vals['tg_id']] = vals['tg_tag'];
            }
            result['tgids'] = tgids;
        }
    }
    if (!def)
        return result;
}

function rollup(which, def) {
    var result = [];
    var mytbl = document.getElementById(which + 'table');
    var elements = mytbl.querySelectorAll('.dynrow');
    for (var e in elements) {
        var row = elements[e];
        if (row.id != null && row.id.substring(0, 3) == 'id_')
            result.push(rollup_row(which, row, def));
    }
    if (!def)
        return result;
}

function rollup_rx_rows(def) {
    return rollup_row('rx', document.getElementById('rx_1'), def);
}

function f_save() {
    var name = document.getElementById('config_name');
    if (!name.value) {
        alert('Name is required');
        name.focus();
        return;
    }
    if (name.value == 'New Configuration') {
        alert("'" + name.value + "' is a reserved name, please retry");
        name.value = '';
        name.focus();
        return;
    }
    var cfg = {
        'devices': rollup('dev', null),
        'channels': rollup('ch', null),
        'backend-rx': rollup_rx_rows(null)
    };
    cfg = edit_l(cfg, false);
    var request = {
        'name': name.value,
        'value': cfg
    };
    send_command('config-save', request);
    f_list();
}

function f_list() {
    var inp = document.getElementById('include_tsv');
    send_command('config-list', inp.checked ? 'tsv' : '');
}

function f_start() {
    var sel = document.getElementById('config_select');
    if (!sel)
        return;
    var val = read_write_sel(sel, null);
    if (!val || val == 'New Configuration') {
        alert('You must select a valid configuration to start');
        return;
    }
    if (val.indexOf('[TSV]') >= 0) {
        alert('TSV files not supported. First, invoke "Edit"; inspect the resulting configuration; then click "Save".');
        return;
    }
    send_command('rx-start', val);
}


function f_stop() {
    send_command('rx-stop', '');
}

function f_load() {
    var sel = document.getElementById('config_select');
    if (!sel)
        return;
    var val = read_write_sel(sel, null);
    if (!val) {
        alert('You must select a configuration to edit');
        return;
    }
    if (val == 'New Configuration') {
        open_editor();
    } else {
        send_command('config-load', val);
        var ele = document.getElementById('config_name');
        ele.value = val;
    }
}

function show_advanced(o) {
    var tbl = find_parent(o, 'TABLE');
    var row = tbl.querySelector('.advrow');
    toggle_show_hide(o, row);
}

function toggle_show_hide(o, ele) {
    if (o.value == 'Show') {
        o.value = 'Hide';
        ele.style['display'] = '';
    } else {
        o.value = 'Show';
        ele.style['display'] = 'none';
    }
}

function f_tags(o) {
    var mydiv = find_parent(o, 'DIV');
    var tbl = mydiv.querySelector('.tgtable');
    toggle_show_hide(o, tbl);
}

// communicate w/ HTTP server functions

function http_req_cb() {
    req_cb_count += 1;
    s = http_req.readyState;
    if (s != 4) {
        nfinal_count += 1;
        return;
    }
    if (http_req.status != 200) {
        n200_count += 1;
        return;
    }
    r200_count += 1;
    dispatch_commands(http_req.responseText);
}

function send_command(command, data) {
    var d = {
        'command': command,
        'data': data
    };
    send(d);
}

function send(d) {
    request_count += 1;
    if (send_queue.length >= SEND_QLIMIT) {
        send_qfull += 1;
        send_queue.unshift();
    }
    send_queue.push(d);
    send_process();
}

function send_process() {
    s = http_req.readyState;
    if (s != 0 && s != 4) {
        send_busy += 1;
        return;
    }
    http_req.open('POST', '/');
    http_req.onreadystatechange = http_req_cb;
    http_req.setRequestHeader('Content-type', 'application/json');
    cmd = JSON.stringify(send_queue);
    send_queue = [];
    http_req.send(cmd);
}


function save_tsv(command, data, file) {
    var d = {
        'command': command,
        'data': data,
        'file': file
    };
	send(d);
}
				// command, data
				
function reload_tsv(data) { // commands OP25 to reload the tsv talkgroup/source tag data
	console.log('sending reload command...');
	var command = "reload_tags";
    var d = {
        'command': command,
        'data': data
    };
    send(d);
}