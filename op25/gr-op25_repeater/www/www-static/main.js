
// Copyright 2017, 2018 Max H. Parke KA1RBI
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

var d_debug = 0;
var update_interval = 500;              // UI update interval, ms (default=1000)

var http_req = new XMLHttpRequest();
var counter1 = 0;
var error_val = null;
var current_tgid = null;
var active_tgid = null;
var active_nac = null;
var send_busy = 0;
var send_qfull = 0;
var send_queue = [];
var req_cb_count = 0;
var request_count = 0;
var nfinal_count = 0;
var n200_count = 0;
var r200_count = 0;
var SEND_QLIMIT = 5;
var summary_mode = true;
var enable_changed = false;
var enable_status = [];
var last_srcaddr = [];
var last_alg = [];
var last_algid = [];
var last_keyid = [];

function find_parent(ele, tagname) {
    while (ele) {
        if (ele.nodeName == tagname)
            return (ele);
        else if (ele.nodeName == "HTML")
            return null;
        ele = ele.parentNode;
    }
    return null;
}

function f_command(ele, command) {
    var myrow = find_parent(ele, "TR");
    var mytbl = find_parent(ele, "TABLE");
    amend_d(myrow, mytbl, command);
}

function edit_freq(freq, to_ui) {
	var MHZ = 1000000.0;
	if (to_ui) {
		var f = (freq / MHZ) + "";
		if (f.indexOf(".") == -1)
			f += ".0";
		return f;
	} else {
		var f = parseFloat(freq);
		if (freq.indexOf("."))
			f *= MHZ;
		return Math.round(f);
	}
}

function edit_d(d, to_ui) {
	var new_d = {};
	var hexints = {"nac":1};
	var ints = {"if_rate":1, "ppm":1, "rate":1, "offset":1, "nac":1, "logfile-workers":1, "decim-amt":1, "seek":1, "hamlib-model":1 };
	var bools = {"active":1, "trunked":1, "rate":1, "offset":1, "phase2_tdma": 1, "phase2-tdma":1, "wireshark":1, "udp-player":1, "audio-if":1, "tone-detect":1, "vocoder":1, "audio":1, "pause":1 };
	var floats = {"costas-alpha":1, "gain-mu":1, "calibration":1, "fine-tune":1, "gain":1, "excess-bw":1, "offset":1, "excess_bw":1};
	var lists = {"blacklist":1, "whitelist":1, "cclist":1};
	var freqs = {"frequency":1, "cclist":1};


	for (var k in d) {
		if (!to_ui) {
			if (d[k] == "None")
				new_d[k] = "";
			else
				new_d[k] = d[k];
			if (k == "plot" && !d[k].length)
				new_d[k] = null;
			if (k in ints) {
				new_d[k] = parseInt(new_d[k]);
			} else if (k in floats) {
				new_d[k] = parseFloat(new_d[k]);
			} else if (k in lists) {
				var l = [];
				if (new_d[k].length)
					l = new_d[k].split(",");
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
					new_d[k] = "0x0";
				else
					new_d[k] = "0x" + d[k].toString(16);
			} else if (k in ints) {
				if (d[k] == null)
					new_d[k] = "";
				else
					new_d[k] = d[k].toString(10);
			} else if (k in lists) {
				if (k in freqs) {
					var new_l = [];
					for (var i in d[k]) {
						new_l.push(edit_freq(d[k][i], to_ui));
					}
					new_d[k] = new_l.join(",");
				} else {
					if ((!d[k]) || (!d[k].length))
						new_d[k] = [];
					else
						new_d[k] = d[k].join(",");
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
	var new_d = {"devices": [], "channels": []};
	for (var device in cfg['devices'])
		new_d["devices"].push(edit_d(cfg['devices'][device], to_ui));
	for (var channel in cfg['channels'])
		new_d["channels"].push(edit_d(cfg['channels'][channel], to_ui));
	new_d["backend-rx"] = edit_d(cfg['backend-rx'], to_ui);
	return new_d;
}

function amend_d(myrow, mytbl, command) {
    var trunk_row = null;
    if (mytbl.id == "chtable")
        trunk_row = find_next(myrow, "TR");
    if (command == "delete") {
        var ok = confirm ("Confirm delete");
        if (ok) {
            myrow.parentNode.removeChild(myrow);
            if (mytbl.id == "chtable")
                trunk_row.parentNode.removeChild(trunk_row);
        }
    } else if (command == "clone") {
        var newrow = myrow.cloneNode(true);
	newrow.id = find_free_id("id_");
        if (mytbl.id == "chtable") {
            var newrow2 = trunk_row.cloneNode(true);
	    newrow2.id = "tr_" + newrow.id.substring(3);
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
    } else if (command == "new") {
        var newrow = null;
        var parent = null;
        var pfx = "id_";
        if (mytbl.id == "chtable") {
            newrow = document.getElementById("chrow").cloneNode(true);
            parent = document.getElementById("chrow").parentNode;
        } else if (mytbl.id == "devtable") {
            newrow = document.getElementById("devrow").cloneNode(true);
            parent = document.getElementById("devrow").parentNode;
        } else if (mytbl.className == "tgtable") {
            newrow = mytbl.querySelector(".tgrow").cloneNode(true);
            parent = mytbl.querySelector(".tgrow").parentNode;
            pfx = "tg_";
        } else {
            return null;
        }
        newrow.style['display'] = '';
	newrow.id = find_free_id(pfx);
        parent.appendChild(newrow);
        if (mytbl.id == "chtable") {
            var newrow2 = document.getElementById("trrow").cloneNode(true);
	    newrow2.id = "tr_" + newrow.id.substring(3);
            parent.appendChild(newrow2);
        }
        return newrow;
    }
}

function nav_update(command) {
	var names = ["b1", "b2", "b3", "b4", "b5", "b7"];
	var bmap = { "status": "b1", "settings": "b2", "rx": "b3", "help": "b4", "view": "b5", "about": "b7" };
	var id = bmap[command];
	for (var id1 in names) {
		b = document.getElementById(names[id1]);
		if (names[id1] == id) {
			b.className = "nav-button-active";
		} else {
			b.className = "nav-button";
		}
	}
}

function f_select(command) {
    var div_list = ["status", "settings", "rx", "help", "about"];
    var orig_command = command;
    if (command == "rx") {
        command = "status";     //hack
        summary_mode = false;
    } else {
        summary_mode = true;
    }
    for (var i=0; i<div_list.length; i++) {
        var ele = document.getElementById("div_" + div_list[i]);
        if (command == div_list[i])
            ele.style['display'] = "";
        else
            ele.style['display'] = "none";
    }
    if (command == "status" && summary_mode == true)
        document.getElementById("div_images").style["display"] = "";
    else
        document.getElementById("div_images").style["display"] = "none";
    var ctl = document.getElementById("controls");
    if (command == "status")
        ctl.style['display'] = "";
    else
        ctl.style['display'] = "none";
    nav_update(orig_command);
    if (command == "settings")
        f_list();
}

function is_digit(s) {
    if (s >= "0" && s <= "9")
        return true;
    else
        return false;
}

function rx_update(d) {
    if (d["files"].length > 0) {
        for (var i=0; i<d["files"].length; i++) {
            var img = document.getElementById("img" + i);
            if (img['src'] != d["files"][i]) {
                img['src'] = d["files"][i];
                img.style["display"] = "";
            }
        }
    }
    error_val = d["error"];
    fine_tune = d["fine_tune"]; // displays Fine Tune value as supplied in the command line arguments
}

// frequency, system, and talkgroup display

function change_freq(d) {

	var xj = document.getElementById("stx");	    // display FDMA or TDMA (untested, no P2 system here)
	xj.innerHTML = " $nbsp; ";						// trip 01/2021
	t = "TDMA";										// 
	if (!d['tdma'])									// 
	t = "FDMA";										// 
	xj.innerHTML = t;								// 
	
	var displayTgid = "&mdash;";
	var displayTag = "&nbsp;";
	var display_src = "&mdash;";
	var display_alg = "&mdash;";
	var display_keyid = "&mdash;";
	var e_class = "value";

	var doTruncate = document.getElementById("valTruncate").value; // get truncate value from Configuration

	last_srcaddr[d['nac']] = d['srcaddr'];
	last_alg[d['nac']] = d['alg'];
	last_algid[d['nac']] = d['algid'];
	last_keyid[d['nac']] = d['keyid'];

	if (d['tgid'] != null) {
		displayTgid = d['tgid'];
		displayTag = d['tag'].substring(0,doTruncate); 
		if (d['srcaddr'] != null && d['srcaddr'] > 0)
			display_src = d['srcaddr'];
		display_alg = d['alg'];
		if (d['algid'] != 128) {
			display_keyid = d['keyid'];
			e_class = "red_value";
		}
	}

	var html = "<table style=\"width: 512px; height: 168px;\">";
	var d_sys = ("system" in d) ? d['system'].substring(0,doTruncate) : "Undefined";
	html += "<tr>";
	html += "<td style=\"width: 422px;\" colspan=2><span class=\"systgid\" id=\"dSys\">" + d_sys + "</span></td>";
	html += "<td align=\"center\" style=\"width: 88px;\">";
        html += "<span class=\"label-sm\">Frequency</span><br><span class=\"value\">" + d['freq'] / 1000000.0 + "</span></td>";
	html += "</tr>";
	html += "<tr>";
	html += "<td style=\"width: 422px;\" colspan=2><span class=\"systgid\" id=\"dTag\">" + displayTag + "</span></td>";
	html += "<td align=\"center\" style=\"width: 88px;\">";
        html += "<span class=\"label-sm\">Talkgroup ID</span><br><span class=\"value\">" + displayTgid + "</span>";
	html += "</td>";
	html += "</tr>";
	html += "<tr>";
	html += "<td align=\"left\">";
        html += "<span class=\"label-sm\">Encryption</span><br><span class=\"" + e_class + "\" id=\"dAlg\">" + display_alg + "</span>";
	html += "</td>";
	html += "<td align=\"center\" style=\"width: 88px;\">";
        html += "<span class=\"label-sm\">Key ID</span><br><span class=\"value\" id=\"dKey\">" + display_keyid + "</span>";
	html += "</td>";
	html += "<td align=\"center\" style=\"width: 88px;\">";
        html += "<span class=\"label-sm\">Source Addr</span><br><span class=\"value\" id=\"dSrc\">" + display_src + "</span>";
	html += "</td>";
	html += "</tr>";
	html += "</table>";

	var div_s2 = document.getElementById("div_s2");
	div_s2.innerHTML = html;
	div_s2.style["display"] = "";

	active_nac = d['nac'];
	active_tgid = d['tgid'];
	if (d['tgid'] != null) {
		current_tgid = d['tgid'];
	}
	var fstyle = document.getElementById("valFontStyle").value;
	var z1 = document.getElementById("valTagFont").value;       // set font size of TG Tag
	var z = document.getElementById("dTag");
	z.style = "font-size: " + z1 + "px; " + "font-weight: " + fstyle + ";";

	var z1 = document.getElementById("valSystemFont").value;    // set font size of System
	var z = document.getElementById("dSys");
	z.style = "font-size: " + z1 + "px; " + "font-weight: " + fstyle + ";";

}
	

// adjacent sites table

function adjacent_data(d) {
    if (Object.keys(d).length < 1)
        return "";
    var html = "<div class=\"adjacent\">"; // open div-adjacent
    html += "<table border=1 borderwidth=0 cellpadding=0 cellspacing=0 width=100%>";
    html += "<tr><th colspan=99 style=\"align: center\">Adjacent Sites</th></tr>";
    html += "<tr><th>Frequency</th><th>Sys ID</th><th>RFSS</th><th>Site</th><th>Uplink</th></tr>";
    var ct = 0;
    for (var freq in d) {
        var color = "#d0d0d0";
        if ((ct & 1) == 0)
            color = "#c0c0c0";
        ct += 1;
        html += "<tr style=\"background-color: " + color + ";\"><td>" + freq / 1000000.0 + "</td><td>" + d[freq]['sysid'].toString(16) + "</td><td>" + d[freq]["rfid"] + "</td><td>" + d[freq]["stid"] + "</td><td>" + (d[freq]["uplink"] / 1000000.0) + "</td></tr>";
    }
    html += "</table></div>"; // close div-adjacent

// end adjacent sites table

    return html;
}

function trunk_summary(d) {
    var nacs = [];
    for (var nac in d) {
        if (!is_digit(nac.charAt(0)))
            continue;
        nacs[nac] = 1;
    }
    var html = "";
    html += "<br><div class=\"summary\">";
    html += "<form>";
    html += "<table border=1 width=732 borderwidth=0 cellpadding=0 cellspacing=0>"; 
    html += "<tr><th>Enabled</th><th>NAC</th><th>System</th><th>Last Active</th><th>TSBK Count</th></tr>";
    for (nac in d) {
        if (!is_digit(nac.charAt(0)))
            continue;
        last_srcaddr[nac] = d[nac]['srcaddr'];
        last_alg[nac] = d[nac]['alg'];
        last_algid[nac] = d[nac]['algid'];
        last_keyid[nac] = d[nac]['keyid'];
        if (!(nac in enable_status))
            enable_status[nac] = true;
        var times = [];
        for (var freq in d[nac]['frequency_data']) {
            times.push(parseInt(d[nac]['frequency_data'][freq]['last_activity']));
        }
        var min_t = 0;
        if (times.length) {
            for (var i=0; i<times.length; i++) {
                if (i == 0 || times[i] < min_t)
                    min_t = times[i];
            }
            times = min_t;
        } else {
            times = "&nbsp;";
        }
        var ns = parseInt(nac).toString(16);
        html += "<tr>";
	var checked = enable_status[nac] ? "checked" : "";
        html += "<td align=center><span class=\"value\"><input type=\"checkbox\" id=\"enabled-" + nac + "\" " + checked + " onchange=\"javascript: f_enable_changed(this, " + nac + ");\"></input></span></td>";

        html += "<td align=center><span class=\"value\">" + ns + "</span></td>";
        html += "<td align=center><span class=\"value\">" + d[nac]['sysname'] + "</span></td>";
        html += "<td align=center><span class=\"value\">" + times + "</span></td>";
        html += "<td align=center><span class=\"value\">" + comma(d[nac]['tsbks']) + "</span></td>";
        html += "</tr>";
    }
    var display = "";
    if (!enable_changed)
        display = "none";
    html += "<tr id=\"save_list_row\" style=\"display: " + display + ";\"><td colspan=99>";
    html += "<input type=\"button\" name=\"save_list\" value=\"Apply Settings\" onclick=\"javascript:f_save_list(this);\"></input>";
    html += "</td></tr>";
    html += "</table></form></div>";
    return html;
}

function f_save_list(ele) {
    var flist = [];
    for (var nac in enable_status) {
        if (enable_status[nac])
            flist.push(nac.toString(10));
    }
    document.getElementById("save_list_row").style["display"] = "none";
    enable_changed = false;
    send_command("settings-enable", flist.join(","));
}

function f_enable_changed(ele, nac) {
    enable_status[nac] = ele.checked;
    enable_changed = true;
    document.getElementById("save_list_row").style["display"] = "";
}

// additional system info: wacn, sysID, rfss, site id, secondary control channels, freq error

function trunk_detail(d) {
    var html = "";
    for (var nac in d) {
        if (!is_digit(nac.charAt(0)))
            continue;
        last_srcaddr[nac] = d[nac]['srcaddr'];
        last_alg[nac] = d[nac]['alg'];
        last_algid[nac] = d[nac]['algid'];
        last_keyid[nac] = d[nac]['keyid'];
	    html += "<div class=\"content\">";     // open div-content
        html += "<span class=\"nac\">";
        html += "<br>" + d[nac]["sysname"] + " <br> ";
        html += "NAC " + "0x" + parseInt(nac).toString(16) + " &nbsp; &nbsp; &nbsp; ";
        html += d[nac]['rxchan'] / 1000000.0;
        html += " / ";
        html += d[nac]['txchan'] / 1000000.0;
        html += " &nbsp; &nbsp; &nbsp; tsbks " + comma(d[nac]['tsbks']);
        html += "</span><br>";

        html += "<span class=\"label\">WACN: </span>" + "<span class=\"value\">0x" + parseInt(d[nac]['wacn']).toString(16) + " </span>";
        html += "<span class=\"label\">System ID: </span>" + "<span class=\"value\">0x" + parseInt(d[nac]['sysid']).toString(16) + " </span>";
        html += "<span class=\"label\">RFSS ID: </span><span class=\"value\">" + d[nac]['rfid'] + " </span>";
        html += "<span class=\"label\">Site ID: </span><span class=\"value\">" + d[nac]['stid'] + "</span><br>";
        if (d[nac]["secondary"].length) {
            html += "<span class=\"label\">Secondary control channel(s): </span><span class=\"value\"> ";
            for (i=0; i<d[nac]["secondary"].length; i++) {
                html += d[nac]["secondary"][i] / 1000000.0;
                html += "&nbsp;&nbsp;&nbsp;";
            }
            html += "</span><br>";
        }
        if (error_val != null) {
            html += "<span class=\"label\">Frequency error: </span><span class=\"value\">" + error_val + " Hz. </span> &nbsp; ";
            html += "<span class=\"label\">Fine tune: </span><span class=\"value\">" + fine_tune + "</span><br>";
        }

// system frequencies table

        html += "<br><div class=\"info\"><div class=\"system\">"; //    open div-info  open div-system
        html += "<table border=1 borderwidth=0 cellpadding=0 cellspacing=0 width=100%>"; 
        html += "<tr><th colspan=99 style=\"align: center\">System Frequencies</th></tr>";
        html += "<tr><th>Frequency</th><th>Last Seen</th><th colspan=2>Talkgoup ID</th><th>Count</th></tr>";
        var ct = 0;
        for (var freq in d[nac]['frequency_data']) {
            tg2 = d[nac]['frequency_data'][freq]['tgids'][1];
            if (tg2 == null)
                tg2 = "&nbsp;";
            var color = "#d0d0d0";
            if ((ct & 1) == 0)
                color = "#c0c0c0";
            ct += 1;
            html += "<tr style=\"background-color: " + color + ";\"><td>" + parseInt(freq) / 1000000.0 + "</td><td>" + d[nac]['frequency_data'][freq]['last_activity'] + "</td><td>" + d[nac]['frequency_data'][freq]['tgids'][0] + "</td><td>" + tg2 + "</td><td>" + d[nac]['frequency_data'][freq]['counter'] + "</td></tr>";
        }
        html += "</table></div>"; // close div-system    // end system freqencies table

        html += adjacent_data(d[nac]['adjacent_data']);
        html += "</div><br></div><hr><br>";   // close div-content  close div-info  box-br  hr-separating each NAC
    }
    return html;
}

function update_data(d) {
	if (active_nac == null || active_tgid == null)
		return;
	var display_src = "&mdash;";
	var display_alg = "&mdash;";
	var display_keyid = "&mdash;";
	var e_class = "value";
	if (last_srcaddr[active_nac] != null) {
		display_src = last_srcaddr[active_nac];
		var ele = document.getElementById("dSrc");
		if (ele != null)
			ele.innerHTML = display_src;
	}
	if (last_algid[active_nac] == null || last_alg[active_nac] == null || last_keyid[active_nac] == null)
		return;
	display_alg = last_alg[active_nac];
	if (last_algid[active_nac] != 128) {
		display_keyid = last_keyid[active_nac];
		e_class = "red_value";
	}
	ele = document.getElementById("dAlg");
	if (ele != null) {
		ele.innerHTML = display_alg;
		ele.className = e_class;
	}
	ele = document.getElementById("dKey");
	if (ele != null)
		ele.innerHTML = display_keyid;
}

function trunk_update(d) {
    var div_s1 = document.getElementById("div_s1");
    var html;
    if (summary_mode)
        html = trunk_summary(d);
    else
        html = trunk_detail(d);
    div_s1.innerHTML = html;

	// disply hold indicator  
	var x = document.getElementById("holdIndicator");
	if (d['data']['hold_mode']) {
	         x.style.display = "block";
	}				  
	else {
	        x.style.display = "none";
	}

	// display last command unless it was more than 10 seconds ago
	x2 = d['data']['last_command'];
	if (x2 && d['data']['last_command_time'] > -10) {
	document.getElementById("lastCommand").innerHTML = "Last Command<br><b>" + x2.toUpperCase() + "</b><br>" + " " + (d['data']['last_command_time'] * -1) + " secs ago";
	}
	else {
		document.getElementById("lastCommand").innerHTML = "";	
	}
	update_data(d);
}

function config_list(d) {
    var html = "";
    html += "<select id=\"config_select\" name=\"cfg-list\" size=5>";
    for (var file in d["data"]) {
        html += "<option value=\"" + d["data"][file] + "\">" + d["data"][file] + "</option>";
    }
    html += "<option value=\"New Configuration\">New Configuration</option>";
    html += "</select>";
    document.getElementById("cfg_list_area").innerHTML = html;
}

function config_data(d) {
    var cfg = edit_l(d['data'], true);
    open_editor();
    var chtable = document.getElementById("chtable");
    var devtable = document.getElementById("devtable");
    var chrow = document.getElementById("chrow");
    var devrow = document.getElementById("devrow");
    for (var device in cfg['devices'])
        rollup_row("dev", amend_d(devrow, devtable, "new"), cfg['devices'][device]);
    for (var channel in cfg['channels'])
        rollup_row("ch", amend_d(chrow, chtable, "new"), cfg['channels'][channel]);
    rollup_rx_rows(cfg['backend-rx']);
}

function open_editor() {
    document.getElementById("edit_settings").style["display"] = "";
    var rows = document.querySelectorAll(".dynrow");
    var ct = 0;
    for (var r in rows) {
        var row = rows[r];
        ct += 1;
        if (row.id && (row.id.substring(0,3) == "id_" || row.id.substring(0,3) == "tr_")) {
            row.parentNode.removeChild(row);
        }
    }
    var oldtbl = document.getElementById("rt_1");
    if (oldtbl)
        oldtbl.parentNode.removeChild(oldtbl);
    var tbl = document.getElementById("rxopt-table");
    var newtbl = tbl.cloneNode(true);
    newtbl.id = "rt_1";
    newtbl.style["display"] = "";
    var rxrow = newtbl.querySelector(".rxrow");
    var advrow = newtbl.querySelector(".advrow");
    rxrow.id = "rx_1";
    advrow.id = "rx_2";
    if (tbl.nextSibling)
        tbl.parentNode.insertBefore(newtbl, tbl.nextSibling);
    else
        tbl.parentNode.appendChild(newtbl);
}

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
    var dl = JSON.parse(http_req.responseText);
    var dispatch = {'trunk_update': trunk_update, 'change_freq': change_freq, 'rx_update': rx_update, 'config_data': config_data, 'config_list': config_list}
    for (var i=0; i<dl.length; i++) {
        var d = dl[i];
        if (!("json_type" in d))
            continue;
        if (!(d["json_type"] in dispatch))
            continue;
        dispatch[d["json_type"]](d);
    }
}

function do_onload() {
    var ele = document.getElementById("div_status");
    ele.style["display"] = "";
    var intv = setInterval(do_update, update_interval);              // UI update interval
    b = document.getElementById("b1");
    b.className = "nav-button-active";
}

function do_update() {
    send_command("update", 0);
    f_debug();
}

function send_command(command, data) {
    var d = {"command": command, "data": data};
    send(d);
}

function send(d) {
    request_count += 1;
    if (send_queue.length >= SEND_QLIMIT) {
        send_qfull += 1;
        send_queue.unshift();
    }
    send_queue.push( d );
    send_process();
}

function send_process() {
    s = http_req.readyState;
    if (s != 0 && s != 4) {
        send_busy += 1;
        return;
    }
    http_req.open("POST", "/");
    http_req.onreadystatechange = http_req_cb;
    http_req.setRequestHeader("Content-type", "application/json");
    cmd = JSON.stringify( send_queue );
    send_queue = [];
    http_req.send(cmd);
}

function f_scan_button(command) {
    if (current_tgid == null)
        send_command(command, -1);
    else
        send_command(command, current_tgid);
}

function f_goto_button(command) {
	var _tgid = 0;

	if (command == "goto") {
		command = "hold"
		if (current_tgid != null)
		   _tgid = current_tgid;
		_tgid = parseInt(prompt("Enter tgid to hold.", _tgid));

		if (isNaN(_tgid) || (_tgid < 0) || (_tgid > 65535)) 
			_tgid = 0;
		send_command(command, _tgid);									
	}
}

function f_debug() {
	if (!d_debug) return;
	var html = "<div class='label'><br>";
	html += "busy " + send_busy;
	html += " qfull " + send_qfull;
	html += " sendq size " + send_queue.length;
	html += " requests " + request_count;
	html += " update int=" + update_interval;
	html += " <br>callbacks: ";
	html += " total=" + req_cb_count;
	html += " incomplete=" + nfinal_count;
	html += " error=" + n200_count;
	html += " OK=" + r200_count;
	html += "</div>";
	var div_debug = document.getElementById("div_debug");
	div_debug.innerHTML = html;
}

function find_next(e, tag) {
	var n = e.nextSibling;
	for (var i=0; i<25; i++) {
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
	var row = find_parent(e, "TR");
	var trrow = document.getElementById("tr_" + row.id.substring(3));
	trrow['style']["display"] = (e.checked) ? "" : "none";
}

function read_write_sel(sel_node, def) {
	var result = [];
	var elist = sel_node.querySelectorAll("option");
	for (var e in elist) {
		var ele = elist[e];
		if (def) {
			if (!def[sel_node.name])
				return;
			var options = def[sel_node.name].split(",");
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
	var elements = Array.from(row.querySelectorAll("input,select"));
	if (which == "ch") {
		var trrow = document.getElementById("tr_" + row.id.substring(3));
		var trtable = trrow.querySelector("table.trtable");
		elements = elements.concat(Array.from(trtable.querySelectorAll("input,select")));
		if (def)
			trrow.style["display"] = (def["trunked"]) ? "" : "none";
	}
	else if (which == "rx") {
		var advrow = document.getElementById("rx_2");
		elements = elements.concat(Array.from(advrow.querySelectorAll("input,select")));
	}
	var result = read_write(elements, def);
	if (which == "ch") {
		var tgtable = trrow.querySelector("table.tgtable");
		var tgrow = trrow.querySelector("tr.tgrow");
		if (def) {
			for (var k in def["tgids"]) {
				var val = def["tgids"][k];
				var newrow = amend_d(tgrow, tgtable, "new");
				var inputs = newrow.querySelectorAll("input");
				read_write(inputs, {"tg_id": k, "tg_tag": val});
			}
		} else {
			var tgids = {};
			var rows = tgtable.querySelectorAll("tr.tgrow");
			for (var i=0; i<rows.length; i++) {
				if (rows[i].id == null || rows[i].id.substring(0,3) != "tg_")
					continue;
				var inputs = rows[i].querySelectorAll("input");
				var vals = read_write(inputs, null);
				tgids[vals["tg_id"]] = vals["tg_tag"];
			}
			result['tgids'] = tgids;
		}
	}
	if (!def)
		return result;
}

function rollup(which, def) {
	var result = [];
	var mytbl = document.getElementById(which + "table");
	var elements = mytbl.querySelectorAll(".dynrow");
	for (var e in elements) {
		var row = elements[e];
		if (row.id != null && row.id.substring(0,3) == "id_")
			result.push(rollup_row(which, row, def));
	}
	if (!def)
		return result;
}

function rollup_rx_rows(def) {
	return rollup_row("rx", document.getElementById("rx_1"), def);
}

function f_save() {
	var name = document.getElementById("config_name");
	if (!name.value) {
		alert("Name is required");
		name.focus();
		return;
	}
	if (name.value == "New Configuration") {
		alert ("'" + name.value + "' is a reserved name, please retry");
		name.value = "";
		name.focus();
		return;
	}
	var cfg = { "devices": rollup("dev", null), "channels": rollup("ch", null), "backend-rx": rollup_rx_rows(null) };
	cfg = edit_l(cfg, false);
	var request = {"name": name.value, "value": cfg};
	send_command("config-save", request);
	f_list();
}

function f_list() {
	var inp = document.getElementById("include_tsv");
	send_command("config-list", (inp.checked) ? "tsv" : "");
}

function f_stop() {
	send_command("rx-stop", "");
}

function f_start() {
	var sel = document.getElementById("config_select");
	if (!sel) return;
	var val = read_write_sel(sel, null);
	if ((!val) || val == "New Configuration") {
		alert ("You must select a valid configuration to start");
		return;
	}
	if (val.indexOf("[TSV]") >= 0) {
		alert ("TSV files not supported. First, invoke \"Edit\"; inspect the resulting configuration; then click \"Save\".");
		return;
	}
	send_command("rx-start", val);
}

function f_load() {
	var sel = document.getElementById("config_select");
	if (!sel) return;
	var val = read_write_sel(sel, null);
	if (!val) {
		alert ("You must select a configuration to edit");
		return;
	}
	if (val == "New Configuration") {
		open_editor();
	} else {
		send_command('config-load', val);
		var ele = document.getElementById("config_name");
		ele.value = val;
	}
}

function show_advanced(o) {
    var tbl = find_parent(o, "TABLE");
    var row = tbl.querySelector(".advrow");
    toggle_show_hide(o, row);

}

function toggle_show_hide(o, ele) {
    if (o.value == "Show") {
        o.value = "Hide";
        ele.style["display"] = "";
    } else {
        o.value = "Show";
        ele.style["display"] = "none";
    }
}

function f_tags(o) {
    var mydiv = find_parent(o, "DIV");
    var tbl = mydiv.querySelector(".tgtable");
    toggle_show_hide(o, tbl);
}

// added UI functions - triptolemus

// popout the UI to a minimal browser window 
function popOut() {
  var myWindow = window.open(window.location.href, "", "width=760,height=400");
}

// toggle dark/light mode
function toggleCSS() {
  var a = document.getElementById("style");
  a.x = 'dark' == a.x ? 'main' : 'dark'; // short if
  a.href = a.x + '.css';
}

// add comma formatting to number (tsbk)
function comma(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// keyboard shortcuts

document.onkeydown = function(evt) {
    evt = evt || window.event;
    if (evt.keyCode == 71) {	// 'g' key - GOTO
        f_goto_button("goto");
    }
    
    if (evt.keyCode == 76) {	// 'l' key - LOCKOUT
        f_scan_button("lockout");
    }    

    if (evt.keyCode == 72) {	// 'h' key - HOLD
        f_scan_button("hold");
    } 

    if (evt.keyCode == 83) {	// 's' key - SKIP
        f_scan_button("skip");
    } 

    if (evt.keyCode == 86) {	// 'v' key - VIEW (light/dark)
        toggleCSS();
    }  
    
    if (evt.keyCode == 82) {	// 'r' key - RX screen
       f_select("rx");
    }
    
    if (evt.keyCode == 74) {	// 'j' key - HOME screen
       f_select("status");
    }

    if (evt.keyCode == 77) {	// 'm' key - MINIFY
        minify("nav-bar");
        minify("div_images");
        minify("div_s1");
    } 
    
    if (evt.keyCode == 66) {	// 'b' key - bold
        document.getElementById("valFontStyle").value="bold"
    } 

    if (evt.keyCode == 78) {	// 'n' key - normal
        document.getElementById("valFontStyle").value="normal"
    } 
}

function minify(div) {
  var x = document.getElementById(div);
  if (x.style.display === "none") {
    x.style.display = "block";
  } else {
    x.style.display = "none";
  }
}
