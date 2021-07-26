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

var lastUpdated = "15-Jul-2021";

var d_debug = 0;
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
var last_srctag = [];
var last_alg = [];
var last_algid = [];
var last_keyid = [];
var tgid_files = {};
var srcid_files = {};
var channel_id = {};
var event_source = null;  // must be in global scope for Babysitter to work.

window.g_change_freq = [];
window.g_cc_event = [];
window.src = [];

var intvAlias = null;
var intvCss = null;
localStorage.AliasTableUpdated == true;
localStorage.ColorsTableUpdated == true;

var encsym = "&#x2205;";

const zeroPad = (num, places) => String(num).padStart(places, '0');  	// leading zeros for single digit time values

function do_onload() {
    $('#div_status').show(window.animateSpeed);
    $('#babysitter').hide();
    $('#b1').addClass('nav-button-active');
    $('#uiupdated').html(lastUpdated);
    document.documentElement.setAttribute('data-theme', 'dark');
    window.siteAlias = null;
    getSiteAlias();
    intvAlias = setInterval(getSiteAlias, 5000);
	beginJsonSettings(); 
	generateCSS();
    intvCss = setInterval(generateCSS, 4000);
    resetFileReload = setInterval(rstFileReload, 12000)	
	connect();
	accColorSel();
	for (i = 1; i < 100; i ++) {
		$('#unk_default').append(new Option(i, i));
	}
	window.animateSpeed = $('#ani_speed').val();
}

// vars set when saving things...
// 	localStorage.AliasTableUpdated == true;
//  localStorage.ColorsTableUpdated == true;


$(document).ready(function() {
	// populate url into oplog url field
		var x = window.location.origin.split( ':' ); 
		var y = x[0] + ':' + x[1] + ':5000';
		$('#oplogUrl').val(y);
		loadHelp();
});

function connect() {
    event_source = new EventSource('/stream');
    event_source.addEventListener('message', eventsource_listener);
    event_source.onerror = function() {
    	event_source.close();
    	clearInterval(intvAlias);
    	clearInterval(intvCss);
    	clearInterval(resetFileReload);
    }
	setReconnect();
}

function eventsource_listener(event) {
    dispatch_commands(event.data);
}

// Babysitter - watches /stream, reacts when lost/restored
function setReconnect() {
	// readyState values: 0 = connecting, 1 = open, 2 = closed
	var reconnecting = false;
	setInterval(() => {
		if (event_source.readyState == 2) {
			reconnecting = true;
			$('#babysitter').show();
			$('#estat').html(event_source.readyState);
			connect();
		} else if (reconnecting) {
			reconnecting = false
			$('#estat').html(event_source.readyState);
			if (!event_source.readyState == 0)
				$('#estat').html('OK');
				$('#babysitter').hide();
			    intvCss = setInterval(generateCSS, 4000);
		        intvAlias = setInterval(getSiteAlias, 5000);
		        resetFileReload = setInterval(rstFileReload, 12000)
		}
	}, 3000);
}


function rstFileReload() {
	// forces the alias and colors info to reload in case user
	// makes changes to them from another browser.
	localStorage.AliasTableUpdated == true;
	localStorage.ColorsTableUpdated == true;
}


function navOplog() {
	window.open($('#oplogUrl').val());
}

function phaseType(nac) {
	// reset the UI to a Phase 1 display (untested)
	window[nac + 'flavor'] = null;
}

function nav_update(command) {
    var names = [
        'b1',
        'b2',
        'b3',
        'b4',
        'b5',
        'b7'
    ];
    var bmap = {
        'status': 'b1',
        'settings': 'b2',
        'rx': 'b3',
        'help': 'b4',
        'view': 'b5',
        'about': 'b7'
    };
    var id = bmap[command];
    for (var id1 in names) {
        b = document.getElementById(names[id1]);
        if (names[id1] == id) {
            b.className = 'nav-button-active';
        } else {
            b.className = 'nav-button';
        }
    }
}

function f_select(command) {
    var div_list = [
        'status',
        'settings',
        'rx',
        'help',
        'about'
    ];
    
    var orig_command = command;
    
    if (command == 'rx') {
    	$('#div_logs').show(window.animateSpeed);
        command = 'status';
        summary_mode = false;
    } else {
        summary_mode = true;
    	$('#div_logs').hide(window.animateSpeed);        
    }
    
    for (var i = 0; i < div_list.length; i++) {
    	(command == div_list[i]) ? $('#div_' + div_list[i]).show(window.animateSpeed) :	$('#div_' + div_list[i]).hide(window.animateSpeed);
    }
    
    (command == 'status' && summary_mode == true) ? $('#div_images').show(window.animateSpeed) : $('#div_images').hide(window.animateSpeed);
      
    (command == 'status') ? $('#controls').show() : $('#controls').hide();
        
    nav_update(orig_command);
    
    if (command == 'settings')
        f_list();
}

function rx_update(d) {
    if (d['files'].length > 0) {
        for (var i = 0; i < d['files'].length; i++) {
            var img = document.getElementById('img' + i);
            if (img['src'] != d['files'][i]) {
                img['src'] = d['files'][i];
                img.style['display'] = '';
            }
        }
    }
    error_val = d['error'];
    fine_tune = d['fine_tune'];
}

// frequency, system, and talkgroup display
function change_freq(d) {    // d json_type = change_freq
    t = 'TDMA';
    var t = 'FDMA';
    if ((d['tdma'] == 0) || (d['tdma'] == 1))
        t = 'TDMA ' + d['tdma'];
    $('#stx').html(t);

    var displayTgid = '&mdash;';
    var displayTag = '&nbsp;';
    var display_src = '&mdash;';
    var display_alg = '&mdash;';
    var display_keyid = '&mdash;';
    var display_srctag = '&mdash;';
    var e_class = 'value';
	var trunc = $('#valTruncate').val();

    last_srcaddr[d['nac']] = d['srcaddr'];
    last_alg[d['nac']] = d['alg'];
    last_algid[d['nac']] = d['algid'];
    last_keyid[d['nac']] = d['keyid'];
    last_srctag[d['nac']] = d['srcaddr.tag'];
    if (d['tgid'] != null) {
        displayTgid = d['tgid'];
        displayTag = d['tag'].substring(0, trunc);

        if (d['srcaddr'] != null && d['srcaddr'] > 0) {
            display_src = d['srcaddr'];
	        display_srctag = d['srcaddr_tag'];
	    }   
	    
        display_alg = d['alg'];

        if (d['algid'] != 128) {
            display_keyid = d['keyid'];
            e_class = 'red_value';
        }
    }
    
    // main display - system, talkgroup, encryption, keyid, source addr display
    
    var d_sys = 'system' in d ? d['system'].substring(0, trunc) : 'Undefined';
    
    var html = '<table style="width: 510px; height: 168px;">';
    html += '<tr>';

    html += '<td style="width: 422px;" colspan=2><span class="systgid" id="dSys">' + d_sys + '</span></td>';
    html += '<td align="center" style="width: 88px;">';
    html += '<span class="label-sm">Frequency</span><br><span class="value">' + freqDisplay(d['freq'] / 1000000) + '</span></td>';

    html += '</tr>';
    html += '<tr>';

    html += '<td style="width: 422px;" colspan=2><span class="systgid" id="dTag">' + displayTag + '</span></td>';
    html += '<td align="center" style="width: 88px;">';
    html += '<span class="label-sm">Talkgroup ID</span><br><span class="value" id="dTgid">' + displayTgid + '</span>';
    html += '</td>';

    html += '</tr>';
    html += '<tr>';

    html += '<td align="left">';
    html += '<span class="label-sm">Encryption</span><br><span class="' + e_class + '" id="dAlg">' + display_alg + '</span>';
    html += '</td>';
    html += '<td align="center" style="width: 88px;">';
    html += '<span class="label-sm">Key ID</span><br><span class="value" id="dKey">' + display_keyid + '</span>';
    html += '</td>';
    html += '<td align="center" style="width: 88px;">';
    html += '<span class="label-sm">Source Addr</span><br><span class="value" id="dSrc">' + display_src + '</span>';
    html += '</td>';

    html += '</tr>';
    html += '</table>';    
    
    $('#div_s2').html(html).show();
    
    active_nac = d['nac'];
    active_tgid = d['tgid'];
    if (d['tgid'] != null) {
        current_tgid = d['tgid'];
    }
  
  	// color/style for main display
  	
    var fontStyle = $('#valFontStyle').val();
    var tgSize = $('#valTagFont').val();
    var sysSize = $('#valSystemFont').val();    
	var defColor = $('#sysColor').val();
    var sysColor = "";
    var tagColor = "";  
	var clr = getProperty('.c' + d.tag_color, 'color', 'tgcolors');
	var ani = getProperty('.c' + d.tag_color, 'animation', 'tgcolors');
	var bg  = getProperty('.c' + d.tag_color, 'backgroundColor', 'tgcolors');
	
	sysColor = (cbState('color_main_sys') && d['tag_color']) ? clr : defColor;
	tagColor = (cbState('color_main_tag') && d['tag_color']) ? clr : defColor;
	
    $('#dSys').css({"color": sysColor, "font-size": tgSize, "font-weight": fontStyle});
    $('#dTag').css({"color": tagColor, "font-size": tgSize, "font-weight": fontStyle, "animation": ani, "background-color": bg});
    
} // end change_freq

function trunk_summary(d) {    // d json_type = trunk_update
    var nacs = [];
    for (var nac in d) {
        if (!is_digit(nac.charAt(0)))
            continue;
        nacs[nac] = 1;
    }
    var html = '';
    html += '<br><div class="summary">';
    html += '<form>';
    html += '<table border=1 width=732 border width=0 cellpadding=0 cellspacing=0>';
    html += '<tr><th>Enabled</th><th>NAC</th><th>System</th><th>Last TSBK</th><th>TSBK Count</th><th>Alias TSV</tr>';
    for (nac in d) {
        if (!is_digit(nac.charAt(0)))
            continue;
        last_srcaddr[nac] = d[nac]['srcaddr'];
        last_srctag[nac] = d[nac]['srcaddr_tag'];
        last_alg[nac] = d[nac]['alg'];
        last_algid[nac] = d[nac]['algid'];
        last_keyid[nac] = d[nac]['keyid'];
        if (!(nac in enable_status))
            enable_status[nac] = true;
        var times = [];
		var last_tsbk = d[nac]['last_tsbk'] * 1000;
        var display_last_tsbk = getTime(last_tsbk);
        times.push(display_last_tsbk);
        var min_t = 0;
        if (times.length) {
            for (var i = 0; i < times.length; i++) {
                if (i == 0 || times[i] < min_t)
                    min_t = times[i];
            }
            times = min_t;
        } else {
            times = '&nbsp;';
        }
        var ns = parseInt(nac).toString(16);
        html += '<tr>';
        var tf = d[nac]['tgid_tags_file'];
        var sf = d[nac]['unit_id_tags_file'];
        var sysid = d[nac]['sysid'];
        var checked = enable_status[nac] ? 'checked' : '';
        
        html += '<td align=center><span class="value"><input type="checkbox" id="enabled-' + nac + '" ' + checked + ' onchange="javascript: f_enable_changed(this, ' + nac + ');">';
        html += '<label for="enabled-' + nac + '"><span></span>  ' + '</label></span></td>';
        // checkbox styling nonsense above
        html += '<td align=center><span class="value">' + ns.toUpperCase() + '</span></td>';
        html += '<td align=center><span class="value">' + d[nac]['sysname'] + '</span></td>';
        html += '<td align=center><span class="value">' + times + '</span></td>';
        html += '<td align=center><span class="value">' + comma(d[nac]['tsbks']) + '</span></td>';  
        html += '<td align=center>&nbsp;';
        if (tf)        
			html +='<a title="Talkgroups" style="text-decoration: none;" href="tsv-edit.html?file=' + tf + '&mode=tg&css=' + displayMode() + '&nac=' + nac + '" target="_new">TG</a>';
		if (sf)
			html +='&nbsp;&nbsp<a title="Source IDs" style="text-decoration: none;" href="tsv-edit.html?file=' + sf + '&mode=src&css=' + displayMode() + '&nac=' + nac + '" target="_blank">SRC</a>';
		html += '&nbsp;&nbsp<a title="System Site Aliases" style="text-decoration: none;" href="alias-edit.html?file=site-alias.json&mode=alias&sys='+ (sysid) + '"&css=' + displayMode() +' target="_blank">SA</a>';
		html += '</td>'
        html += '</tr>';
    }
    var display = '';
    if (!enable_changed)
        display = 'none';
    html += '<tr id="save_list_row" style="display: ' + display + ';"><td colspan=99>';
    html += '<input type="button" name="save_list" value="Apply Settings" onclick="javascript:f_save_list(this);"></input>';
    html += '</td></tr>';
    html += '</table></form></div>';
    return html;
} // end trunk_summary()

// additional system info: wacn, sysID, rfss, site id, freq table, adjc sites, secondary control channels, freq error
function trunk_detail(d) { // d json_type = trunk_update
    var html = '';
    var alias, sysid, rfss, site;
    var error_val = fine_tune = "&mdash;";
    for (var nac in d) {
        if (!is_digit(nac.charAt(0)))
            continue;
        var p2 = window[nac + 'flavor']; 				// if phase 2 was detected, add phase 2 layouts
        var flavor = "Phase 1";
        if (p2) 
        	flavor = "Phase 2";
        last_srcaddr[nac] = d[nac]['srcaddr'];
        last_srctag[nac] = d[nac]['srcaddr_tag'];        
        last_alg[nac] = d[nac]['alg'];
        last_algid[nac] = d[nac]['algid'];
        last_keyid[nac] = d[nac]['keyid'];        
 	    error_val = sessionStorage.errorVal;
        fine_tune = sessionStorage.fineTune;
        
        sysid = d[nac]['sysid'];
        rfss = d[nac]['rfid'];
        site = d[nac]['stid'];
        
        // use the Site Alias if defined, otherwise use d/nac/sysname
        if (window.siteAlias != null && window.siteAlias[sysid] && window.siteAlias[sysid][rfss] && window.siteAlias[sysid][rfss][site]) {
        	alias = window.siteAlias[sysid][rfss][site]['alias'];
        } else {
        	alias =  d[nac]['sysname'];
        }

        html += '<br><div>';
        html += '<table class="rxsys" border=1 border width=0 cellpadding=0 cellspacing=0 width=100%">';
        
        html += '<col width="120px">';  	// 1
        html += '<col width="120px">';  	// 2
 	    html += '<col width="120px">';  	// 3
        html += '<col width="120px">';  	// 4
        html += '<col width="120px">';  	// 5
        html += '<col width="120px">';  	// 6
             
        html += '<th colspan="6">' +  alias + '</th><tr>';     
        
        // 1
        html += '<td align="center">';
        html += 'System ID<br> <span class="value">' + '0x' + parseInt(d[nac]['sysid']).toString(16).toUpperCase();
        html += '</td>';
        
        // 2
        html += '<td align="center">';
        html += 'NAC<br> <span class="value">' + '0x' + parseInt(nac).toString(16).toUpperCase();
        html += '</td>';
        
        // 3
        html += '<td align="center">';
        html += 'WACN<br> <span class="value">' + '0x' + parseInt(d[nac]['wacn']).toString(16).toUpperCase();
        html += '</td>';

        // 4
        html += '<td align="center">';
        html += 'RFSS ID<br> <span class="value">' + d[nac]['rfid']
        html += '</td>';
        
        // 5
        html += '<td align="center">';
        html += 'Site ID<br> <span class="value">' + d[nac]['stid']
        html += '</td>';
        
        
        // 6
        html += '<td align="center" id="ptype" ondblclick="phaseType(' + nac + ')">';
        html += '<span>Type<br> <span class="value">' + flavor + '</span></span>';
        html += '</td>';

        html += '</tr>';     
           
 		// row 2
        html += '<tr>';
        
        // 1
        html += '<td align="center" style="white-space: nowrap;">';
        html += 'Control Channel<br> <span class="value">' + freqDisplay(d[nac]['rxchan'] / 1000000); 
        html += '</td>';
        
        // 2, 3, 4
        html += '<td colspan="3" align="center">';   
        
		if (d[nac]['secondary'].length) {
			html += 'Secondary Control Channels</span><br><span class="value"> ';
			for (i = 0; i < d[nac]['secondary'].length; i++) {
				html += freqDisplay(d[nac]['secondary'][i] / 1000000);
				html += '&nbsp;&nbsp;&nbsp;';
			}	
		} else {
			html += '<span class="value">None';			
		}
		
			html += '</td></span>';
        
        // 5
        html += '<td align="center">';
        html += 'TSBK<br><span class="value">' + comma(d[nac]['tsbks']);
        html += '</td>';
        
        // 6
        var last_tsbk = d[nac]['last_tsbk'] * 1000;
        var display_last_tsbk = getTime(last_tsbk);
    	html += '<td align="center">';
        html += 'Last TSBK<br> <span class="value">' + display_last_tsbk + '</span>';
        html += '</td>';
        
        html += '</tr>';
        
        if (cbState('showBandPlan')) {

			var zsys = d[nac]['sysid'];
			html += '<tr><td colspan="6">';
	
			html += '<table id="bandplan" title="Channel ID / Band Plan"><tr>';
			html += '<th>ID</th>';
			html += '<th>Type</th>';
			html += '<th>Base Frequency</th>';
			html += '<th>Tx Offset</th>';
			html += '<th>Spacing (kHz)</th>';
			html += '<th>Slots</th></tr>';
			for (p in channel_id[d[nac]['sysid']]) {
				html += '<tr>';
				html += '<td style="text-align: center;">' + channel_id[zsys][p]['iden'] + '</td>';
				html += '<td style="text-align: center;">' + channel_id[zsys][p]['type'] + '</td>';
				html += '<td style="text-align: center;">' + freqDisplay(channel_id[zsys][p]['freq']) + '</td>';
				html += '<td style="text-align: center;">' + freqDisplay(channel_id[zsys][p]['offset']) + '</td>';		
				html += '<td style="text-align: center;">' + (channel_id[zsys][p]['step'] * 100) + '</td>';
				html += '<td style="text-align: center;">' + channel_id[zsys][p]['slots'] + '</td>';
				html += '</tr>';
			}
			html += '</table>';
			
			html += '</td></tr>';
        } 
        
        html += '</table></div>';

        // system frequencies table  // d json_type = trunk_update
        html += '<br>';
        html += '<table class="fixed" id="sysfreq">';
        
        html += '<col width="100px">';  	// 1 Freq 
        html += '<col width=" 75px">';  	// 2 Last
        html += '<col width=" 80px">';  	// 3 tgid
        html += '<col width="175px">';  	// 4 tgtag
        html += '<col width=" 25px">';  	// 5 enc        
        html += '<col width=" 80px">';  	// 6 srcaddr
        html += '<col width="195px">';  	// 7 srctag

        html += '<tr>';
        html += '<th>Frequency </th>';      			// 1
        html += '<th>Last </th>';						// 2
        html += '<th colspan="3">Talkgroup</th>';       // 3 / 4 / 5
        html += '<th colspan="2">Source</th>';        	// 6 / 7
        html += '</tr>';

        var c, src_c, sc_src, sf_freq, sf_last, sf_hits, sf_timeout;
 
 		// save keystrokes!
		var fd = 'frequency_data';
		var ft = 'frequency_tracking';
		var td = 'talkgroup_data';
		var ts = 'time_slot';
		var calls = 'calls';
		
        sf_timeout = 0;		// delay before clearing the tg info
		
		// #frequency#
			var sf_tdma;

			//calls
				var sf_count = [];	// "count"
				var sf_lastactive = []; // "last_active"
				var sf_protected = []; // "protected"
				var sf_starttime = []; // "start_time"
				var sf_endtime = []; // "end_time"
				
				//tgid
					var sf_tgid = []; // "tg_id"
					var sf_tgtag = [];	// "tag"
					var sf_tgcolor = []; // "color"			
				
				//srcaddr
					var sf_srcaddr = [];  // "unit_id"
					var sf_srctag = [];	  // "tag"
					var sf_srccolor = []; // "color"
			
		var slot, tgid, x, y;
		var sf_enc = [];
		var sf_la = [];
		
		var sf_last = 0;
		
		    sf_tgid[0] = " ";
 		   sf_tgtag[0] = " ";
	 	 sf_srcaddr[0] = " ";
		  sf_srctag[0] = " ";
		     sf_enc[0] = " ";		  
		 sf_tgcolor[0] = 0;
		sf_srccolor[0] = 0;
		      sf_la[0] = 0;
		
		    sf_tgid[1] = " ";
 		   sf_tgtag[1] = " ";
	 	 sf_srcaddr[1] = " ";
		  sf_srctag[1] = " ";
		     sf_enc[1] = " ";	  
		 sf_tgcolor[1] = 0;
		sf_srccolor[1] = 0;
		      sf_la[1] = 0;		

        for (var freq in d[nac][ft]) {

		slot = 0;
						
			for (var call of d[nac][ft][freq][calls]) {

				if (call == null) {
				
						sf_tgid[slot] = " ";
					   sf_tgtag[slot] = " ";
					 sf_srcaddr[slot] = " ";
					  sf_srctag[slot] = " ";
						 sf_enc[slot] = " ";	
				
					slot++;
					continue;
				}
								
				if (call.end_time == 0) { // if end_time != 0 then the call is dead and should not be displayed in Active Freq table
			
					sf_tgid[slot] 		= call.tgid.tg_id;
					
					if (call.tgid.tag) {
						sf_tgtag[slot] = call.tgid.tag; 
					} else {
						sf_tgtag[slot] = "Talkgroup " + call.tgid.tg_id;
						call.tgid.color = $('#unk_default').val();
					}
					
					sf_tgcolor[slot] 	= call.tgid.color;
				
					sf_srcaddr[slot] 	= call.srcaddr.unit_id ? call.srcaddr.unit_id : " ";
					sf_srctag[slot] 	= call.srcaddr.tag ? call.srcaddr.tag : " ";
					sf_srccolor[slot] 	= call.srcaddr.color;
				
					sf_protected[slot]	= call['protected']; 		// protected is a reserved word in JS so can't use dot notation here	
					sf_enc[slot] = (sf_protected[slot] == true) ? encsym : " ";
							
				} // end if call.end_time
												
				sf_count[slot] 		= call.count;
				sf_lastactive[slot] = call.last_active;
				
				sf_la[slot] = parseInt(d.time - sf_lastactive[slot], 10);
				
				slot++;
				
			}  // end for var call in calls
				
            sf_freq = freqDisplay(parseInt(freq) / 1000000);
            
            sf_last = d[nac][ft][freq]['last_active'];                  
            	sf_last = parseFloat(sf_last).toFixed(0);
            
            if (sf_la[0] > sf_timeout) {         
				sf_tgid[0] = " ";
				sf_tgtag[0] = " ";
				sf_srcaddr[0] = " ";
				sf_srctag[0] = " ";
				sf_enc[0] = " ";
			}

            if (sf_la[1] > sf_timeout) {         
				sf_tgid[1] = " ";
				sf_tgtag[1] = " ";
				sf_srcaddr[1] = " ";
				sf_srctag[1] = " ";
				sf_enc[1] = " ";
			}
			
            for (slot = 0; slot < 2; slot++ ) {
            	            
            	var c = 0;
            	var src_c = 0;
            	
            	if (sf_tgcolor[slot]) {
            		c = sf_tgcolor[slot];
            	} else {
            		c = smartColor(sf_tgtag[slot])
            	}
            
              	if (sf_srccolor[slot]) {
            		src_c = sf_srccolor[slot];
            	} else {
            		src_c = smartColor(sf_srctag[slot])
            	}          

				sc_src = "<span class=\"c" + src_c + "\">";
				sc = "<span class=\"c" + c + "\">";
				
				var tfile = d[nac]['tgid_tags_file'];
				var sfile = d[nac]['unit_id_tags_file'];
					
				// Active Frequencies Table
						
				html += '<tr>';				
				if (slot == 0)
					html += '<td style="cursor: crosshair;" title="' + sf_freq + ' Hits: ' + sf_count[slot] + '">' + sf_freq + '</td>';    						// 1
				if (slot == 1)
					html += '<td align="right" style="cursor: crosshair;" title="' + sf_freq + ' Hits: ' + sf_count[slot] + '"> / 2 &nbsp;&nbsp;&nbsp; </td>';	// 1
				html += '<td>' + sf_la[slot] + '</td>';            																								// 2
				html += '<td name="tgid" ondblclick="editTsv(this, 1, \'' + tfile + '\', ' + nac +');">' + sc + sf_tgid[slot]  + '</td>';            			// 3 								
				html += '<td name="tag" ondblclick="editTsv(this, 1, \'' + tfile + '\', ' + nac +');">' + sc + sf_tgtag[slot] + '</td>';            			// 4
				html += '<td><span class="enc">' + sf_enc[slot] + '</span></td>';       																		// 5
				html += '<td name="srcid" ondblclick="editTsv(this, 1, \'' + sfile + '\', ' + nac +');">' + sc_src + sf_srcaddr[slot] + '</td>';            	// 6
				html += '<td name="srctag" ondblclick="editTsv(this, 1, \'' + sfile + '\', ' + nac +');">' + sc_src + sf_srctag[slot] + '</td>';          		// 7				
					
				html += '</tr>';

				if (!p2) break;
			} // end for slot
         } // end for freq
        
        html += '</table>';
        
        if (cbState('show_adj'))
	       html += adjacent_data(d[nac]['adjacent_data']);

    }   // end for nac in d
    
    return html;
    
} // end trunk_detail()

function editTsv(click, source, file, nac) { // dbl click the ui to access the TSV editor
	if (!click)
		return;
		
	// source
	// 1 = Active Frequencies
	// 2 = Call History

	window.getSelection().removeAllRanges();  // unselect the text that was double-clicked on
	var cname = click.attributes.name;
	cname = (cname.value);
	
	
	if (source == 2 && (cname == "tgid" || cname == "tag")) {  // Call History Talkground dbl clicked
		var sid = file;
		file = tgid_files[sid];
	}
	
	if (source == 2 && (cname == "srcid" || cname == "srctag")) {  // Call History Source dbl clicked
		var sid = file;
		file = srcid_files[sid];
	}	
	
	if ( (cname =="tgid" || cname == "tag") && (!file || file == "null"))  {  // null is being stored as a string in window.tgid_files
		jAlert ("Talkgroup tag TSV file not specified in config file. Cannot edit.", "Error");
		return;
	}
	
	if ( (cname =="srcid" || cname == "srctag") && (!file || file == "null")) {
		jAlert ("Source tag TSV file not specified in config file. Cannot edit.", "Error");
		return;
	}	
		
	var id = 0;
	var url, x, y, tsv;
	
	// Active Frequencies						// Call History
	// cellIndex[2] = Talkgroup ID				// cellIndex[3] = Talkgroup ID
	// cellIndex[3] = Talkgroup Tag				// cellIndex[4] = Talkgroup Tag
	// cellIndex[5] = Source ID					// cellIndex[5] = Source ID
	// cellIndex[6] = Source Tag				// cellIndex[6] = Source Tag
	
	switch (source) { 
		case 1: // sysfreq Table TD
			x = 2;  // the cell index of tgid
			y = 5;  // the cell index of srcid

			switch (cname) {
				case 'tgid':
					id = click.innerText;			
					url = 'tsv-edit.html?file=' + file + '&css=' + displayMode() + '&mode=tg&id=' + id + '&nac=' + nac;
					tsv = window.open(url, 'tsv');			
					break;

				case 'tag':
					id = click.parentElement.cells[x].innerText;
					url = 'tsv-edit.html?file=' + file + '&css=' + displayMode() + '&mode=tg&id=' + id + '&nac=' + nac;
					tsv = window.open(url, 'tsv');
					break;
			
				case 'srcid':
					id = click.innerText;			
					url = 'tsv-edit.html?file=' + file + '&css=' + displayMode() + '&mode=src&id=' + id + '&nac=' + nac;
					tsv = window.open(url, 'tsv');
					break;

				case 'srctag':
					id = click.parentElement.cells[y].innerText;
					url = 'tsv-edit.html?file=' + file + '&css=' + displayMode() + '&mode=src&id=' + id + '&&nac=' + nac;		
					tsv = window.open(url, 'tsv');						
					break;
			}
			break;
			
		case 2: // Call History Table SPAN
			x = 3;  // the cell index of tgid
			y = 5;  // the cell index of srcid
			
			switch (cname) {
				case 'tgid':
					id = click.parentElement.parentElement.cells[x].innerText;		
					url = 'tsv-edit.html?file=' + file + '&css=' + displayMode() + '&mode=tg&id=' + id + '&nac=' + nac;
					tsv = window.open(url, 'tsv');			
					break;

				case 'tag':
					id = click.parentElement.parentElement.cells[x].innerText;
					url = 'tsv-edit.html?file=' + file + '&css=' + displayMode() + '&mode=tg&id=' + id + '&nac=' + nac;;
					tsv = window.open(url, 'tsv');
					break;	
			
				case 'srcid':
					id = click.parentElement.parentElement.cells[y].innerText;		
					url = 'tsv-edit.html?file=' + file + '&css=' + displayMode() + '&mode=src&id=' + id + '&nac=' + nac;
					tsv = window.open(url, 'tsv');
					break;

				case 'srctag':
					id = click.parentElement.parentElement.cells[y].innerText;	
					url = 'tsv-edit.html?file=' + file + '&css=' + displayMode() + '&mode=src&id=' + id + '&nac=' + nac;		
					tsv = window.open(url, 'tsv');						
					break;
			} // end switch cname
			break;
	} // end switch source
} // end editTsv()

// adjacent sites table    
function adjacent_data(d) {
	// d json_type = trunk_update
	if (Object.keys(d).length < 1)
		return '';
	//     var html = "<div class=\"adjacent\">"; // open div-adjacent
	var html = '<br><table class="fixed" id="adjacent-sites" width=100%>';

        html += '<col width="220px">';
        html += '<col width="130px">';
		html += '<col width="100px">';
		html += '<col width=" 75px">';
		html += '<col width=" 75px">';
		html += '<col width="130px">';

	html += '<th>Adjacent Sites</th><th>Frequency</th><th>System ID</th><th>RFSS ID</th><th>Site ID</th><th>Uplink</th>';
	var ct = 0;
	var alias, sysid, rfss, site;
	for (var freq in d) {
		sysid = d[freq]['sysid'];
		rfss = d[freq]['rfid'];
		site = d[freq]['stid'];
		alias = "-";
        if (window.siteAlias != null && window.siteAlias[sysid] && window.siteAlias[sysid][rfss] && window.siteAlias[sysid][rfss][site]) {
        	alias = window.siteAlias[sysid][rfss][site]['alias'];
        } else {
        	alias =  'Site ' + d[freq]['stid'];
        }
		
		html += '<tr><td>' + alias + '</td><td align="center">'+ freqDisplay(freq / 1000000) + '</td><td align="center">' + d[freq]['sysid'].toString(16).toUpperCase() + '</td>';
		html += '<td  align="center">' + d[freq]['rfid'] + '</td><td  align="center">' + d[freq]['stid'] + '</td>';
		html += '<td align="center">' + freqDisplay(d[freq]['uplink'] / 1000000) + '</td></tr>';
	}
	html += '</table>';
	return html; // end adjacent sites table
} // end adjacent_data()

function trunk_update(d) {

    var html;
    if (summary_mode) {
        html = trunk_summary(d); // home screen
    } else {
        html = trunk_detail(d); // RX screen
        
    }
    
    $('#div_s1').html(html);
    
    if (!summary_mode)
    	sortTable('adjacent-sites', 4);
    	
    // display hold indicator 
    if (d['data']['hold_mode']) {
    	$('#holdIndicator').show();
    } else {
        $('#holdIndicator').hide();
    }
    
    // display last command unless it was more than 10 seconds ago
    x2 = d['data']['last_command'];
    if (x2 && d['data']['last_command_time'] > -10) {
        $('#lastCommand').html('Last Command<br><b>' + x2.toUpperCase() + '</b><br>' + ' ' + d['data']['last_command_time'] * -1 + ' secs ago');
    } else {
        $('#lastCommand').html('');
    }

    update_data(d);
} // end trunk_update()

function update_data(d) { // d json type = trunk_update
    if (active_nac == null || active_tgid == null)
        return;
        
    var    display_src = '&mdash;';
    var display_srctag = '&mdash;';    
    var    display_alg = '&mdash;';
    var  display_keyid = '&mdash;';
    
    var e_class = 'value';
    
    if (last_srcaddr[active_nac] != null) {
        display_src = last_srcaddr[active_nac];
        var ele = document.getElementById('dSrc');
        if (ele != null)
            ele.innerHTML = display_src;
    }
    
    if (last_srctag[active_nac] != null) {
        display_srctag = last_srctag[active_nac];
        var ele = document.getElementById('dSrctag');
        if (ele != null)
            ele.innerHTML = display_srctag;
    }   
    
    if (last_algid[active_nac] == null || last_alg[active_nac] == null || last_keyid[active_nac] == null)
        return;
    display_alg = last_alg[active_nac];
    if (last_algid[active_nac] != 128) {
        display_keyid = last_keyid[active_nac];
        e_class = 'red_value';
    }
    ele = document.getElementById('dAlg');
	if (ele != null) {
		ele.innerHTML = display_alg;
		ele.className = e_class;
	}
    ele = document.getElementById('dKey');
    if (ele != null)
        ele.innerHTML = display_keyid; 

}  // end update_data()

function error_tracking() {
	return;	// empty right now, handled in dispatch_commands switch block
} // end error_tracking

function dispatch_commands(txt) {
    if (txt == '[]') {
        return;
    }

    var dl = JSON.parse(txt);

    var dispatch = {
        'trunk_update': trunk_update,
        'change_freq': change_freq,
        'rx_update': rx_update,
        'config_data': config_data,
        'config_list': config_list,
        'cc_event': cc_event,
        'freq_error_tracking': error_tracking
    };
    
    for (var i = 0; i < dl.length; i++) {
        var d = dl[i];
        if (!('json_type' in d))
            continue;
        if (!(d['json_type'] in dispatch))
            continue;
        var j_type = d['json_type'];
        var time = getTime(new Date());
        if (d.time)
            time = getTime(d.time * 1000); 
        
        switch (j_type) {
        
        	case 'freq_error_tracking':
        		var ele, bx, cx, dx, ex, fx, gx;
        		$('#error_tracking').show();
        		bx = d.device;
        		cx = d.name;
        		dx = d.error_band;
        		ex = d.freq_correction;
        		fx = d.freq_error;
        		gx = d.tuning_error;
        		appendErrorTable (time, bx, cx, dx, ex, fx, gx, 'errors');
        		break;
        
            case 'change_freq':
                cb = cbState('log_cf');
                time = getTime(d['effective_time'] * 1000);
                if (d.tgid && !d.tag) {
                    d.tag = 'Talkgroup ' + d.tgid + ''; // talkgroup tag isn't in the tsv
                    d.tag_color = $('#unk_default').val();
                }
                sysid = d.sysid ? hex(d.sysid).toUpperCase() : "&mdash;"
                var freq = d['freq'] / 1000000; 
                var srctag = "&mdash;";
                var color, srccolor, srcaddr;
                
                
                if (d['tag_color']) {
                    color = d['tag_color'];
                } else {
                    color = smartColor(d.tag);
                    d['tag_color'] = color;
                }

                if (d['srcaddr_color']) {
                    srccolor = d['srcaddr_color'];
                } else {
                    srccolor = smartColor(d.tag);
                }
                        
                var tag = '<span class="c' + color + '">' + d.tag + '</span>';
                var tgid = '<span class="c' + color + '">' + d.tgid + '</span>';
                
                // TODO - cb not defined keeps coming up a couple times in the console, right at start up.
                if (cb && d.tgid) {
	                appendJsonTable(time, j_type, sysid, tag, tgid, freq, '--', '--', 'history');
                }
                
                if (d.tgid) {
                    srctag = (window['srct' + d.srcaddr]) ? '<span class="c' + srccolor + '">' + window['srct' + d.srcaddr] : "&mdash;";
                    srcaddr = '<span class="c' + srccolor + '">' + d.srcaddr;
                }
                window.g_change_freq = d;
                break;
                
            case 'trunk_update':
                cb = cbState('log_tu');
                	var tf, sf, sid, a, z;
					var sysid, site, rfid, color;
					var grpaddr, c_grpaddr, srcaddr, c_srcaddr, talkgroup, c_talkgroup, srctag, c_srctag;
				    for (nac in d) {
				        if (Number.isInteger(parseInt(nac))) {  
				        	sysid = d[nac]['sysid'];
				        	sid = sysid;
			        		sysid = hex(sysid).toUpperCase();
				        	site = d[nac]['stid'];
				        	rfid = d[nac]['rfid'];
				        	grpaddr = d[nac]['grpaddr'];
				        	srcaddr = d[nac]['srcaddr'];
	
							tf = d[nac]['tgid_tags_file'];
							tgid_files[sid] = tf;

							sf = d[nac]['unit_id_tags_file'];
							srcid_files[sid] = sf;

							if (window['tgidt' + grpaddr]) 
								talkgroup = window['tgidt' + grpaddr]; 
					        
					        srctag = (window['srct' + srcaddr]) ? (window['srct' + srcaddr]) : "&nbsp;";
				    
				    		color = smartColor(talkgroup);
				    		srccolor = smartColor(talkgroup);
				    		
				    		if (window['tgidc' + grpaddr])
				    			color = window['tgidc' + grpaddr];
				    		
		                    c_grpaddr = '<span class="c' + color + '">' + grpaddr + '</span>';
		                    c_talkgroup = '<span class="c' + color + '">' + talkgroup + '</span>';
	
		                    color = (window['srcc' + srcaddr]) ? window['srcc' + srcaddr] : "0";
   		                    c_srcaddr = '<span class="c' + srccolor + '">' + srcaddr + '</span>';
		                    c_srctag  = '<span class="c' + srccolor + '">' + srctag + '</span>';
		                    
		                    var sr = "Site: " + site + "  &nbsp;&nbsp;&nbsp; RFID: " + rfid;
		                    
		                    var col_f = "&mdash;"; // empty for now
                    
           				if (cb) {
		                    if (grpaddr) {  // do not append the table if no grpaddr is present - TU into Events table is pretty much useless anyway
					        	appendJsonTable(time, j_type, sysid, sr, c_grpaddr,  col_f, "--", "--", "history");
							}
						} //end if cb
				      } // end if nac is number	
					} // end for nac in d
                sources(d);
                window.g_trunk_update = d;      
                break;
                
            case 'rx_update':
                cb = cbState('log_rx');
				if (d['files'][0]) {
                	var ps = "Plots present";            	
                	} else {
						// do nothing
                	}                
                if (cb) {       
                    appendJsonTable(time, j_type, ps, 'Fine Tune: ' + d['fine_tune'], 'Error: ' + d['error'], '-', '-', '--', 'history');
                }  // this Events table entry doesn't add much value either.

//                 window.g_rx_update = d;
                sessionStorage.fineTune = d['fine_tune'] ? d['fine_tune'] : "&mdash;";
                sessionStorage.errorVal = d['error'] ? d['error'] : "&mdash;";
                break;
                
            case 'cc_event':
            	time = getTime(d['time'] * 1000);
                cb = cbState('log_cc');
                var opcode, n_opcode, sysid, tag, target, source, srctag, src_c, color;
                var logCall = 0;
                var noLog = 0;
                var xp = 0;
                
                if (d.opcode !== null) {
                    opcode = d['opcode'].toString(16);
                    if (g_opcode[opcode]) {
                        n_opcode = g_opcode[opcode];
                    } else {
                        n_opcode = 'Opcode Not Found: ' + opcode;
                    }
                }
                
                tag = target = source = '&mdash;';
                srctag = "&nbsp;";   // used           
                
                // [group] does not appear in every cc_event!
                if (d.group) {

              		if (d.group && d.group.tag) {
							tag = d.group.tag;
					} else {
						d.group.tag = 'Talkgroup ' + d.group.tg_id;
						d.group.color = $('#unk_default').val();			
					}

                }  // end if d.group
                
                if (d.reason) {
                    tag = getReason(hex(d.reason));
                }
                   
                n_opcode = g_opcode[opcode] ? g_opcode[opcode] : opcode;	
				
				if (d['srcaddr']) {
                	source = (d.srcaddr.unit_id) ? d.srcaddr.unit_id : "&mdash; No ID";	// This condition is reached when there is traffic
                																		// but no source unit id is present. on ebrcs, this
                																		// happens when an old u/vhf system is patched onto ebrcs.
                	srctag = (d.srcaddr.tag) ? d.srcaddr.tag : "&nbsp;";
                }
				
            	// handle manufacturer opcodes:   
				// 		   0x10 = Relm/BK
				//		   0x68 = Kenwood	
            	// 144(10) 0x90 = Motorola
            	// 164(10) 0xA4 = Harris 
            	//		   0xD8 = Tait
            	//		   0xF8 = Vertex Standard
            	//   trunking.py sends the following opcodes:
            	//   -1, 0x00, 01, 02, 03, 09, 20, 27, 28, 2a, 2b, 2c, 2d, 2f, 33, 34, 3d
            	
            	switch (opcode) {
            	
            		case "-1": // end call (not a P25 standard)
            			tag = d.tgid.tag;
            			target = d.tgid.tg_id;
						n_opcode = "End Call";
						noLog = 1; // Events
						// TODO - maybe nothing?
            			break;
            	
					case "0":
						if (d.mfrid != null) {
							switch (d.mfrid) {
								case 0:						
									n_opcode = "Call";		// GRP_V_CH_GRANT
									target = d['group']['tg_id'];
									srctag = d['srcaddr']['tag'];
									noLog = cbState('je_calls') ? 0 : 1;  //events
									logCall = 1; // callHistory
									break;
								case 144: // MOTOROLA
									n_opcode = "XP Adds";  //mot_grg_add_cmd 0x00"
									tag = d.sg.tag;
									target = d.sg.tg_id;	
									noLog = 1; // chatty af		
									logCall = 0; // callHistory
									break;
								case "default":
									n_opcode = "Call";
									target = d['group']['tg_id'];
									srctag = d['srcaddr']['tag'];									
									noLog = cbState('je_calls') ? 0 : 1;
									logCall = 1; // callHistory
									break;
							} // end switch
						} // end if
						break;
				
					case "1": // 0x01 - RESERVED
						if (d.mfrid != null) {
							switch (d.mfrid) {
								case 0:
									n_opcode = "Reserved 0x01";
									break;
								case 144: // MOTOROLA
									n_opcode = "XP Drops";
									tag = d.sg.tag;
									target = d.sg.tg_id;
									break;
							} // end switch
						} // end if
						break;            		
				
					case "2": // 0x02 - grp_v_ch_grant_updt
						if (d.mfrid != null) {
							switch (d.mfrid) {
								case 0:
									n_opcode = "grp_v_ch_grant_updt 0x02";
									noLog = cbState('je_calls') ? 0 : 1;										
									break;
								case 144: // MOTOROLA
									d['group'] = d['sg'];
									d['srcaddr'] = d['sa'];
									srctag = d.sa.tag;									
									n_opcode = "XP Call"; // MOT XP Call  mot_grg_cn_grant 0x02
									tag = d.sg.tag;
									target = d.sg.tg_id;
									source = d.sa.unit_id;			
									noLog = cbState('je_calls') ? 0 : 1;
									logCall = 1; // callHistory	
									xp = 1;								
									break;        				            		
							} // end switch
						} // end if
						break;				

					case "3": // 0x03 - GRP_V_CH_GRANT_UPDT_EXP
						if (d.mfrid != null) {
							switch (d.mfrid) {
								case 0:
									n_opcode = "grp_v_ch_grant_updt_exp 0x03";
									break;
								case 144: // MOTOROLA
									n_opcode = "mot_grg_cn_grant_updt 0x03"; 
									tag = d.sg1.tag;
									target = d.sg1.tg_id;
									noLog = 1;  // used for late entry, very chatty, probably should not log to JSON Events
									break;
							} // end switch
						} // end if
						break;
						
					case "9": // MOT System Load ? Could be "Motorola Scan Marker"
						if (d.mfrid != null) {
							switch (d.mfrid) {
								case 0:
									n_opcode = "Opcode 0x03";
									break;
								case 144: // MOTOROLA
									n_opcode = "System Load " + d.test1;
 									noLog = 1;
									break;
							} // end switch
						} // end if
						break;

					case "20":  // 0x20 - ACK_RSP_FNE
						noLog = 1;
						break;
						
					case "24":  // 0x24 - Extended Function Command (inhibit)  TODO: get reason code, log it
						var efclass = d.efclass;
						var efoperand = d.efoperand;
						var efargs = d.efargs;
						var target = d.target;
						n_opcode = "Ext Fnct Cmd: " + efoperand;
						source = efargs;	
						noLog = 0;
						break;							
	
					case "27":  // 0x27 - DENY_RSP
						source = d.target.unit_id;
						srctag = d.target.tag;
						noLog = cbState('je_deny') ? 0 : 1;
						break;		
						
					case "28":  // 0x28 - GRP_AFF_RSP
						source = d.target.unit_id;
						target = d.group.tg_id;
						noLog = cbState('je_joins') ? 0 : 1;
						break;		
						
					case "2a": // 0x2A - GRP_AFF_Q - Group Affiliate Query
						noLog = 1;
						break;
						
					case "2b": // 0x2B - LOC_REG_RSP - Location Registration Response
						if (d['rv'] != null) {
							switch (d['rv']) {
								case 0:
									n_opcode = "Joins";
									target = d.group.tg_id;
									source = d.target.unit_id;
									srctag = d.target.tag;
									noLog = cbState('je_joins') ? 0 : 1;
									break;
								case 1:
									n_opcode = "Reg Fail";
									target = d.group.tg_id;
									source = d.target.unit_id;
									srctag = d.target.tag;									
									noLog = cbState('je_deny') ? 0 : 1;	
									break;
								case 2:
									n_opcode = "Reg Denied";
									target = d.group.tg_id;
									source = d.target.unit_id;
									srctag = d.target.tag;									
									noLog = cbState('je_deny') ? 0 : 1;
									break;
								case 3:
									n_opcode = "Reg Refused";
									target = d.group.tg_id;
									source = d.target.unit_id;
									srctag = d.target.tag;								
									noLog = cbState('je_deny') ? 0 : 1;
									break;
							} // end rv switch
						} // end if
						break;	

					case "2c":  // 0x2C - U_REG_RSP - Login	TODO: source and target are the same from the json
						source = d.source.unit_id;
						srctag = d.source.tag;
 						// target = d.target.unit_id;
 						// tag = d.target.tag;
						noLog = cbState('je_log') ? 0 : 1;
						break;	

					case "2d":  // 0x2D - U_REG_CMD - Force SU Registration
						source = d.source.unit_id;
						srctag = d.source.tag;
						target = d.target.unit_id;
						tag = d.target.tag;						
						noLog = cbState('je_log') ? 0 : 1;
						break;	
						
					case "2f":  // 0x2F - U_DE_REG_ACK - Logout
						source = d.source.unit_id;
						srctag = d.source.tag;						
						noLog = cbState('je_log') ? 0 : 1;	
						break;

					case "33": // 0x33 - iden up tdma
						var sysid 	= d.sysid;
						var type	= 'TDMA';						
						var iden 	= d.iden;
						var freq 	= d.freq / 1000000;
						var offset 	= d.offset / 1000000;
						var step 	= d.step/100000;
						var slots 	= d.slots;
						channelId (sysid, iden, type, freq, offset, step, slots);
						noLog = 1;
						break;

					case "34": // 0x34 - iden up vhf/uhf
						// TODO - test this
						var sysid 	= d.sysid;
						var type	= 'FDMA';
						var iden 	= d.iden;
						var freq 	= d.freq / 1000000;
						var offset 	= d.offset / 1000000;
						var step 	= d.step/100000;
						var slots 	= 1;
						channelId (sysid, iden, type, freq, offset, step, slots);
						noLog = 1;
						break;
					
					case "3d": // 0x3D - iden up (7/800)
						var sysid 	= d.sysid;
						var type	= 'FDMA';
						var iden 	= d.iden;
						var freq 	= d.freq / 1000000;
						var offset 	= d.offset / 1000000;
						var step 	= d.step/100000;
						var slots 	= 1;
						channelId (sysid, iden, type, freq, offset, step, slots);
						noLog = 1;
						break;
	
				} // end switch - end handle manf opcodes

                if (d.options) {
                	n_opcode = ( (d.options >> 6) & 1 ) ? n_opcode = n_opcode + "&nbsp;&nbsp;&nbsp;&#x2205;" : n_opcode;  //encrypted
                }

				c = smartColor(tag);
				src_c = 0;
	
				if (d['group']) 
					c = (d['group']['color']) ? d['group']['color'] : c;
				
				if (d['sg']) 
					c = (d['sg']['color']) ? d['sg']['color'] : c;
				
				tag = "<span class=\"c" + c + "\">" + tag;
				target = "<span class=\"c" + c + "\">" + target;              
				
				if (d['srcaddr']) 
					src_c = (d['srcaddr']['color']) ? d['srcaddr']['color'] : src_c;               	

				source = "<span class=\"c" + src_c + "\">" + source;                
				srctag = "<span class=\"c" + src_c + "\">" + srctag;                     		

				if (cb && noLog == 0) {            	                	
					appendJsonTable(time, j_type, n_opcode, tag, target, source, srctag, opcode, 'history');
				}

				if (target != "&mdash;" && logCall) {

					target = "<span name=\"tgid\"  ondblclick=\"editTsv(this, 2, " + d.sysid + ", " + d.nac + ");\" class=\"c" + c + "\">" + target;    
					   tag = "<span name=\"tag\"   ondblclick=\"editTsv(this, 2, " + d.sysid + ", " + d.nac + ");\" class=\"c" + c + "\">" + tag;

					source = "<span name=\"srcid\"  ondblclick=\"editTsv(this, 2, " + d.sysid + ", " + d.nac + ");\" class=\"c" + src_c + "\">" + source;                
					srctag = "<span name=\"srctag\" ondblclick=\"editTsv(this, 2, " + d.sysid + ", " + d.nac + ");\" class=\"c" + src_c + "\">" + srctag;   
			
					var tdma_slot = d.tdma_slot; // s/b null if not running tdma

					appendCallHistory(time, "--", target, tag, source, srctag, 'callHistory', d.options, xp, d.sysid, d.nac, tdma_slot);
				}

                window.g_cc_event = d;
                break;
        } // end switch
        
        dispatch[d['json_type']](d); // correct function is called based on json type in the dataset
    } // end for
  f_debug(d);
} // end dispatch_commands()

function cc_event(d) {
	// does nothing right now
    return;
} // end cc_event()

function do_update() {
    f_debug();
} // do_update()

function f_scan_button(command) {
    if (current_tgid == null)
        send_command(command, -1);
    else
        send_command(command, current_tgid);
}

function f_goto_button(command) {
    var _tgid = 0;
    if (command == 'goto') {
        command = 'hold';
        if (current_tgid != null)
            _tgid = current_tgid;
        _tgid = parseInt(prompt('Enter TGID to hold.', _tgid));
        if (isNaN(_tgid) || _tgid < 0 || _tgid > 65535)
            _tgid = 0;
        send_command(command, _tgid);
    }
}

function f_debug(d) {
    if (!d_debug)
        return;

    var html = "<div class='label'>Debug:<br>";
//     html += 'window.g_nac = ' + window.g_nac;
    html += '<br>';    
    html += 'json type: ' + d['json_type'];
    html += '<br>';
 	html += "busy " + send_busy;
	html += " qfull " + send_qfull;
	html += " sendq size " + send_queue.length;
	html += " requests " + request_count;
	html += " <br>callbacks: ";
	html += " total=" + req_cb_count;
	html += " incomplete=" + nfinal_count;
	html += " error=" + n200_count;
	html += " OK=" + r200_count;
	html += "</div>";   
    
    $('#div_debug').html(html);
}

function popOut() { 
    var myWindow = window.open(window.location.href, '', 'width=760,height=400');
}

function toggleCSS() {
	$(document.documentElement).attr('data-theme') == 'light' ? 
		$(document.documentElement).attr('data-theme', 'dark') : 
			$(document.documentElement).attr('data-theme', 'light');
	sdmode();
}

function comma(x) {
    // add comma formatting to whatever you give it (xx,xxxx,xxxx)
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

document.onkeydown = function(evt) {
	// keyboard shortcuts
    evt = evt || window.event;
    var x = document.activeElement.tagName;
 	if (x == "INPUT") 
 		return; // don't do anything if user is typing in an input field

    switch (evt.keyCode) {
        case 71:
            // 'g' key - GOTO
        	$('#lastCommand').html('G - GOTO<br><br>').show();            
            f_goto_button('goto');
            break;
        case 76:
            // 'l' key - LOCKOUT
        	$('#lastCommand').html('L - LOCKOUT<br><br>').show();               
            f_goto_button('lockout');
            break;
        case 72:
            // 'h' key - HOLD
        	$('#lastCommand').html('H - HOLD<br><br>').show();                 
            f_goto_button('hold');
            break;
        case 80:
            // 'p' show/hide plots
        	$('#lastCommand').html('P - Plots<br><br>').show();                
             minify('div_images');
            break;            
        case 83:
            //  's' key - SKIP
        	$('#lastCommand').html('S - Skip<br><br>').show();                   
            f_goto_button('skip');
            break;
        case 86:
            //  'v' key - VIEW (light/dark)
        	$('#lastCommand').html('V - View<br><br>').show();                 
            toggleCSS();
            break;
        case 82:
            //  'r' key - RX screen
            f_select('rx');
            break;
        case 74:
            //  'j' key - HOME screen
            f_select('status');
            break;
        case 77:
            //  'm' key - MINIFY
            minify('nav-bar');
            minify('div_images');
            minify('div_s1');
            break;
        case 48: // '0' key - show/hide Main Display
        	minify('controlsDisplay');
        	break;
        case 49:
        	$('#lastCommand').html('1 - Calls<br><br>').show();             
            //  '1' key - show/hide callHistory
            minify('log_container_1');
            break;
        case 50:
        	$('#lastCommand').html('2 - Events<br><br>').show();            
            //  '2' key - show/hide history (json log)
            minify('log_container_2');
            break;
        case 51:
            //  '3' key - show/hide logs block
        	$('#lastCommand').html('3 - Logs<br><br>').show();                   
			if ( $('#div_logs').is(":hidden") ) {
				 $('#div_logs').show(window.animateSpeed);
			} else {
				$('#div_logs').hide(window.animateSpeed);
			}
            break;        // showBandPlan
        case 52:
        	//  '4' key - show/hide Band Plan
        	$('#lastCommand').html('4 - Bandplan<br><br>').show();
        	$('#showBandPlan').trigger('click');
        	setTimeout(function() {$('#lastCommand').html('').hide();}, 2000);
            break;
        case 65:
        	$('#lastCommand').html('A - Neighbors<br><br>').show();        
        	$('#show_adj').trigger('click');	        
            break;
        case 66:
            //  'b' key - bold
             $('#valFontStyle').val('bold');
            break;
        case 78:
            //  'n' key - normal
             $('#valFontStyle').val('normal');
            break;
    } // end switch
}; // end onkeydown

function minify(div) {
	$('#' + div).toggle(window.animateSpeed);
}

function appendJsonTable(a, b, c, d, e, f, srctag, opcode, target) {
    var numRows = document.getElementById(target).rows.length;
    var size = document.getElementById('log_len').value;
    if (!Number.isInteger(size))
        // entry in Config / Display Options must be a number
        size = 1500;
    
	// shorter friendly view
    var fv = {
        'cc_event': "<font color='#ff3300'>CC</font>",    
        'rx_update': 'RX',
        'change_freq': 'CF',
        'trunk_update': 'TU'
    };
    
    if (numRows > size)
        document.getElementById(target).deleteRow(-1);
    var table = document.getElementById(target);
    var lastRowIndex = table.rows.length - 1;
    var skip = 0;

    var prevTime = nohtml(table.rows[1].cells[0].innerHTML);	// time

    // do not duplicate history enteries - uses window object to store previous enteries and compares them with current data
    // seems to work... 
    
    if (target == 'history' && b == 'trunk_update' && window.g_trunk_update_c && window.g_trunk_update_d) {
        if (c == window.g_trunk_update_c && d == window.g_trunk_update_d && a == prevTime) {
//             console.log('skip cond 1');
            skip = 1;
        }
    }
    if (target == 'history' && b.includes('cc_event') && window.g_cc_event_c && window.g_cc_event_e) {
        if (c == window.g_cc_event_c && (e == window.g_cc_event_e || f == window.g_cc_event_f) && a == prevTime) {
            skip = 1;
// 			     console.log('skip cond 2');       
        }

    }
    if (target == 'history' && b.includes('change_freq') && window.g_change_freq_c && window.g_change_freq_e) {
        if (c == window.g_change_freq_c && e == window.g_change_freq_e && a == prevTime) {
//             console.log('skip cond 3');
            skip = 1;
        }
    }
    
    if (!skip) {
        var row = table.insertRow(1);        // 2nd row insert        
        
        var cell0 = row.insertCell(0);
        var cell1 = row.insertCell(1);
        var cell2 = row.insertCell(2);
        var cell3 = row.insertCell(3);        
        var cell4 = row.insertCell(4);
        var cell5 = row.insertCell(5);
        var cell6 = row.insertCell(6);
        var cell7 = row.insertCell(7);
        
        opcode = opcode.toString();
        opcode = opcode.length == 1 ? "0" + opcode : opcode;
        
        cell0.innerHTML = a;  //time
        cell1.innerHTML = (target == 'history') ? '<div align="center">' + fv[b] + '</div>' : '<div align="center">' + b + '</div>'; // type
        cell2.innerHTML = f; // source id
        cell3.innerHTML = srctag;
        cell4.innerHTML = '<div align="center">' + opcode.toUpperCase() + '</div>'; // opcode
        cell5.innerHTML = c;  // n_coode (event)
        cell6.innerHTML = e;  // target
        cell7.innerHTML = d; // tag
        
        // only update the window globals if we haven't skipped, so do this inside if !skip
        if (target == 'history' && b == 'trunk_update') {
            window.g_trunk_update_c = c;
            window.g_trunk_update_d = d;
        }
        if (target == 'history' && b.includes('cc_event')) {
            window.g_cc_event_c = c;
            window.g_cc_event_e = e;
            window.g_cc_event_f = f;            
        }
        
        if (target == 'history' && b.includes('change_freq')) {
            window.g_change_freq_c = c;
            window.g_change_freq_e = e;
        }
        
    } // end if !skip
} // end appendJsonTable

function appendCallHistory(a, b, c, d, e, f, target, options, xp, sysid, nac, tdma_slot) {
    var numRows = document.getElementById(target).rows.length;
//     var size = document.getElementById('log_len').value;
    var size = $('#log_len').val();
    if (!Number.isInteger(size))
        // entry in Config / Display Options must be a number
        size = 1500;
    if (numRows > size)
        $('#' + target + ' tr:last').remove();
    var table = document.getElementById(target);
    var lastRowIndex = table.rows.length - 1;
    var skip = 0;
    var pri, enc, xpatch, x, y;
    
    
    b = (options) ? options : "&nbsp;";
	enc = ((b >> 6) & 1 ) ? "&#x2205; " : "";
	pri = ((b >> 2) & 1).toString() + ((b >> 1) & 1).toString() + ((b >> 0) & 1).toString();
	pri = parseInt(pri, 2);	
    pri = (xp) ? "XP " : pri;
    
	var prevTime, prevTg, prevSrc;

	// avoid duplicate channel grant enteries into Call History table.
	// Search previous 9 rows, compares current data with existing tgid, srcaddr, and time
	// if tgid and srcaddr are equal and time is within 2 seconds, skip the entry,
	search: {

		for (x = 1; x < 8; x++) {
			if (!table.rows[x]) {
				break search;
			}	
			prevTime = nohtml(table.rows[x].cells[0].innerHTML);	// time
			prevTg   = nohtml(table.rows[x].cells[3].innerHTML); 	// tgid
			prevSrc  = nohtml(table.rows[x].cells[5].innerHTML);	// source addr
			
			var psec = prevTime.slice(-1);
			var asec = a.slice(-1);
			var diff = Math.abs(psec - asec);		
			if (nohtml(c) == prevTg && nohtml(e) == prevSrc && (a == prevTime || diff <= 2)) {
				skip = 1;
			} // end if		
		} // end for
	} // end search
	
	if (((b >> 6) & 1) && cbState('hide_enc')) { 	// hide encrypted calls if selected in Config
		skip = 1;
	}
	
	// do not append the Call History table if not enabled on Home tab
	if (enable_status[nac] == false)
		skip = 1;
	
// 	console.log('callHistory slot=' + slot);
	
	var tslot = '';
	if (cbState('showSlot') == true && tdma_slot != null) {
		tslot = 'S' + ( tdma_slot +1 ) + ' ';
	}
	
    if (!skip) {

        var row = table.insertRow(1);        // 2nd row insert
        
        var cell0 = row.insertCell(0);
        var cell1 = row.insertCell(1);
        var cell2 = row.insertCell(2);
        var cell3 = row.insertCell(3);
        var cell4 = row.insertCell(4);
        var cell5 = row.insertCell(5);
        var cell6 = row.insertCell(6);        
        
        cell0.innerHTML = a;
        cell1.innerHTML = '<div align="center">' + hex(sysid).toUpperCase() + '</div>';
        cell2.innerHTML = '<div align="center">' + tslot + enc + pri + '</div>';
			cell3.innerHTML = c;
        cell4.innerHTML = d;
        cell5.innerHTML = e;
        cell6.innerHTML = f;
         
    } // end if !skip
} // end appendCallHistory

function appendErrorTable(ax, bx, cx, dx, ex, fx, gx, target) {

    var numRows = document.getElementById(target).rows.length;
    var size = document.getElementById('log_len').value;
    if (!Number.isInteger(size))
        // entry in Config / Display Options must be a number
        size = 500;
    
    if (numRows > size)
        document.getElementById(target).deleteRow(-1);
    var table = document.getElementById(target);
    var lastRowIndex = table.rows.length - 1;
    var skip = 0;

    if (!skip) {
        var row = table.insertRow(1);        // 2nd row insert        
        var cell0 = row.insertCell(0);
        var cell1 = row.insertCell(1);
        var cell2 = row.insertCell(2);
        var cell3 = row.insertCell(3);        
        var cell4 = row.insertCell(4);
        var cell5 = row.insertCell(5);
        var cell6 = row.insertCell(6);
        
        cell0.innerHTML = ax;  //time
        cell1.innerHTML = bx;
        cell2.innerHTML = cx;
        cell3.innerHTML = dx;
        cell4.innerHTML = ex;
        cell5.innerHTML = fx;
        cell6.innerHTML = gx;
        
    } // end if !skip
} // end appendErrorTable

function update_freq(d) {
    return; // not currently used		
}

function channelId (sysid, iden, type, freq, offset, step, slots) {
	!(sysid in channel_id) && (channel_id[sysid] = {});
	!(iden in channel_id[sysid]) && (channel_id[sysid][iden] = {});
	channel_id[sysid][iden] = {
		 'iden': iden, 'type': type, 'freq': freq, 'offset': offset, 'step': step, 'slots': slots 
	};
}

function smartColor(t) {
	// searches string t for items in sc1 and sc2, returns a color if found.
		
    var z = 4; // number of smart colors - TOTO add the UI elements in index.html
	
    if (!t || !cbState('smartcolors'))
        return 0;    // do nothing if there is no talkgroup name passed, or if the box is not checked (cb default is false!) 	
    var tag = t.toString().toUpperCase(); // throws an error if t is an int
    var color = 0;
    var ele, x, i, sc, alen;
    
    for (i = 1; i < (z+1); i++) {
    	ele = document.getElementById('sc'+i).value;
    	sc = ele.split(" ");
		for (var x = 0; x < sc.length; x++) {
  			if (tag.includes(sc[x].toUpperCase())) {
				color = i;
				return color;
			}
    	}
    }
    return color;
} // end smartColor()
            
function divExpand(div) {
	switch ($('#' + div).height()) {
		case 1:
			$('#' + div).height(301);
			$('#' + div).show();			
			break;		
		case 301:
			$('#' + div).height(702);
			break;
		case 702:
			$('#' + div).height(1);
			$('#' + div).hide();
			break;			
	}
}

function openTable(div, ref) {
	// popout window for review/search of log tables
    var divText = $('#' + div).prop('outerHTML');
    divText = divText.replace('table id="history"', 'table id="searchTable"');
    divText = divText.replace('table id="callHistory"', 'table id="searchTable"');
    divText = divText.replace('table id="errors"', 'table id="searchTable"');
    
    var myWindow = window.open('', '', 'width=900,height=600');
    var view = document.documentElement.getAttribute('data-theme');
    var doc = myWindow.document;
    
    doc.open();
    doc.write('<script src="main.js"></script>');
    doc.write('<script src="jquery.js"></script>');
    doc.write('<script src="editor.js"></script>');    
    doc.write('<script>window.tgid_files = window.opener.tgid_files;</script>');
    doc.write('<script>window.srcid_files = window.opener.srcid_files;</script>');
    doc.write('<script>generateCSS();</script>');
    // search icon &#x1F50E
    doc.write('<span class="nac">' + ref.id + '</span><br><br>');
    doc.write('<input type="text" id="searchInput" onkeyup="searchTable()" placeholder="Search" title="Search">');
    doc.write('<div align="right"><a href="#" style="text-decoration: none;" onclick="csvTable(\'searchTable\');">');
    doc.write('<img src="csv.png" width="30" title="Download CSV"></a></div><br>');
    doc.write('<script>document.getElementById("searchInput").focus();</script>');
    doc.write('<link rel="stylesheet" type="text/css" id="style" href="main.css">');
    if (view == 'dark')
        doc.documentElement.setAttribute('data-theme', 'dark');
    doc.write(divText);
    doc.close();
}

function searchTable() {
    var input, filter, table, tr, i, x, s, cols;
    var td = [];
    cols = document.getElementById('searchTable').rows[1].cells.length;
    input = document.getElementById('searchInput');
    filter = input.value.toUpperCase();
    table = document.getElementById('searchTable');
    tr = table.getElementsByTagName('tr');
    for (i = 1; i < tr.length; i++) {
		var s = undefined;
    	for (x = 0; x < cols; x++) {
    		td[x] = tr[i].getElementsByTagName('td')[x];
    		s = s + ' ' + nohtml(td[x].innerHTML).toUpperCase();
    	}	
    	if ( s.includes(filter)) {
    		tr[i].style.display = '';
    	} else {
    		tr[i].style.display = 'none'
    	}
    } // end for
} // end function

function searchTsvTable() {
    var input, filter, table, tr, i, x, s, y, cols;
    var td = [];
    table = document.getElementById('talkgroups');
    cols = table.rows[1].cells.length;
    input = document.getElementById('searchInput');
    filter = input.value.toUpperCase();
    tr = table.getElementsByTagName('tr');
    for (i = 1; i < tr.length; i++) {    
		var s = undefined;
    	for (x = 1; x < cols; x++) {         // don't search the first column [0]
    		td[x] = tr[i].getElementsByTagName('td')[x];
			s += ' ' + td[x].firstChild.value.toUpperCase();
    	}	
    	if ( s.includes(filter)) {
    		tr[i].style.display = '';
    	} else {
    		tr[i].style.display = 'none'
    	}
    } // end for
} // end function

function hex(dec) {
	if (!dec) return;
    return dec.toString(16);
}

function dec(hex) {
	if (!hex) return;
    return parseInt(hex, 16);
}

function nohtml(str) {
	if (typeof str != 'string') return str;
	var x = str.replace(/(<([^>]+)>)/gi, "");
	return x;
}

function freqDisplay(f) {
	var freq;
	if (!f) return;
	if (cbState('trailing_zeros')) {
		freq = f.toFixed(5);
	} else {
		if (Number.isInteger(f)) {
			freq = f + ".0";
		} else {
			freq = f;
		}
	}
	return freq;
}

function displayMode() { // just returns the display mode
	var x,y;
	x = document.documentElement.getAttribute('data-theme');
	y = (x == "dark") ? "dark" : "light";
	return y;
}

function sdmode() {
	 $('#selDispMode').val(displayMode());
}

function sdmodeChange() {
	var y = document.getElementById('selDispMode');
	document.documentElement.setAttribute('data-theme', y.value);
}

function is_digit(s) {
	return ((s >= '0' && s <= '9'));
}

function getTime(x) {
    //expects Unix timestamp, returns 24 hour time, hrs:min:sec
    date = new Date(x);
    var time = zeroPad(date.getHours(), 2) + ':' + zeroPad(date.getMinutes(), 2) + ':' + zeroPad(date.getSeconds(), 2);
    return time;
}

function cbState(x) {
    // returns the state (true / false) of whatever checkbox you ask it to
    return $('#' + x).is(':checked');
}

function csvTable(table_id, separator = ',') {       // Quick and simple export target #table_id into a csv
    // console.log('trying CSV table...');
    // Select rows from table_id
    var rows = document.querySelectorAll('table#' + table_id + ' tr');
    // Construct csv
    var csv = [];
    for (var i = 0; i < rows.length; i++) {
        var row = [],
            cols = rows[i].querySelectorAll('td, th');
        for (var j = 0; j < cols.length; j++) {
            // Clean innertext to remove multiple spaces and jumpline (break csv)
            var data = cols[j].innerText.replace(/(\r\n|\n|\r)/gm, '').replace(/(\s\s)/gm, ' ');
            // Escape double-quote with double-double-quote
            data = data.replace(/"/g, '""');
            // Push escaped string
            row.push('"' + data + '"');
        }
        csv.push(row.join(separator));
    }
    var csv_string = csv.join('\n');
    // Download it
    var filename = 'export_' + table_id + '_' + new Date().toLocaleDateString() + '.csv';
    var link = document.createElement('a');
    link.style.display = 'none';
    link.setAttribute('target', '_blank');
    link.setAttribute('href', 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv_string));
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function exportToCsv(filename, rows) {   // another csv export tool, but this one accepts an array.
    var processRow = function (row) {
        var finalVal = '';
        for (var j = 0; j < row.length; j++) {
            var innerValue = row[j] === null ? '' : row[j].toString();
            if (row[j] instanceof Date) {
                innerValue = row[j].toLocaleString();
            };
            var result = innerValue.replace(/"/g, '""');
            if (result.search(/("|,|\n)/g) >= 0)
                result = '"' + result + '"';
            if (j > 0)
                finalVal += ',';
            finalVal += result;
        }
        return finalVal + '\n';
    };

    var csvFile = '';
    for (var i = 0; i < rows.length; i++) {
        csvFile += processRow(rows[i]);
    }

    var blob = new Blob([csvFile], { type: 'text/csv;charset=utf-8;' });
    if (navigator.msSaveBlob) { // IE 10+
        navigator.msSaveBlob(blob, filename);
    } else {
        var link = document.createElement("a");
        if (link.download !== undefined) { // feature detection
            // Browsers that support HTML5 download attribute
            var url = URL.createObjectURL(blob);
            link.setAttribute("href", url);
            link.setAttribute("download", filename);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
    }
}

function sortTable(t, c) { // table id, column index
	if (!cbState('show_adj'))
		return;
	if (!t) return;
  var table, rows, switching, i, x, y, shouldSwitch;
  table = document.getElementById(t);
  switching = true;
  while (switching) {
    switching = false;
    rows = table.rows;
	// (skip the first row (0), which contains table headers)
    for (i = 1; i < (rows.length - 1); i++) {
      shouldSwitch = false;
      x = rows[i].getElementsByTagName("TD")[c];
      y = rows[i + 1].getElementsByTagName("TD")[c];
      if (x.innerHTML.toLowerCase() > y.innerHTML.toLowerCase()) {
        shouldSwitch = true;
        break;
      }
    }
    if (shouldSwitch) {
      rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
      switching = true;
    }
  }
} // end sort table

function sources(d) {  // d json type = trunk_update
				
	// stores source IDs and tags and colors in a global object

		// USAGE:

		// window['tgidc' + tgid] = tgid color
		// window['tgidt' + tgid] = tgid tag "talkgroup"
		
		// window['srct' + srcaddr] = srcaddr tag
		// window['srcc' + srcaddr] = srcaddr color
	
    if (Object.keys(d).length < 1)
        return;
    var f, nac, srcaddr, srcaddr_tag;
    var ft = 'frequency_tracking';
    var calls = 'calls';
    for (nac in d) {
        if (Number.isInteger(parseInt(nac))) { 
            for (f in d[nac][ft]) {

                srcaddr_tag = d[nac][ft][f]['calls'][0]['srcaddr']['tag'] ?     d[nac][ft][f]['calls'][0]['srcaddr'] : null;
                srcaddr =     d[nac][ft][f]['calls'][0]['srcaddr']['unit_id'] ? d[nac][ft][f]['calls'][0]['srcaddr'] : null;

                if (srcaddr && srcaddr_tag) {
                    window['tgidc' + d[nac][ft][f]['calls'][0]['tgid']['tg_id']] = d[nac][ft][f]['calls'][0]['tgid']['color'];
	                window['tgidt' + d[nac][ft][f]['calls'][0]['tgid']['tg_id']] = d[nac][ft][f]['calls'][0]['tgid']['tag'];
	                
                	window['srct' + d[nac][ft][f]['calls'][0]['srcaddr']['unit_id']] = d[nac][ft][f]['calls'][0]['srcaddr']['tag'];
                  	window['srcc' + d[nac][ft][f]['calls'][0]['srcaddr']['unit_id']] = d[nac][ft][f]['calls'][0]['srcaddr']['color'];              
                }
                
				if (d[nac][ft][f]['tdma'] == true ) {
					window[nac + 'flavor'] = "2"; // set it as p2 and leave it that way for the duration
				}   
            } // end for f
        } // end if number
    } // end for x
} // end function

function getReason(r) {
	// denial reason lookup
    if (g_reason[r]) {
        result = '0x' + r + ' - ' + g_reason[r];
    } else {
        result = '0x' + r;
    }
    return result;
}

function saveDisplaySettings() {
	var settings = {};
	$('#saveSettings').html('Saved');
	setTimeout(() => {  $('#saveSettings').html('Save Display Settings');}, 2000);

	var s = [
		"valSystemFont",
		"valTagFont",
		"valTruncate",
		"valFontStyle",
		"sc1",
		"sc2", 
		"sc3",
		"sc4",		
		"log_len",
		"color_main_tag",
		"color_main_sys",
		"smartcolors",
		"log_cc",
		"log_cf", 
		"log_tu",
		"log_rx", 
		"show_adj",
		"je_joins", 
		"je_calls",
		"je_deny", 
		"je_log", 
		"hide_enc", 
		"trailing_zeros", 
		"selDispMode",
		"acc1",
		"acc2",
		"sysColor",
		"valColor",
		"sysColor",
		"btnColor",
		"unk_default",
		"ani_speed",
		"showBandPlan",
		"showSlot" ];
	
	for (r in s) {
		if ($('#' + s[r]).attr('type') == "checkbox") {				
				settings[s[r]] = $('#' + s[r]).is(':checked') ? true : false;
		} else {
			settings[s[r]] = $('#' + s[r]).val();
		}	
	} // end for
	
	var settingsJSON = JSON.stringify(settings, null, 2);	
	send_command('config-savesettings', settingsJSON);
}


function loadHelp(){  // this is also called from editor.js

	f = 'help.html';
	$.ajax({
		url     : f,
		type    : 'GET',
		success : popHelp,
		error   : function(XMLHttpRequest, textStatus, errorThrown) {alert('Settings File Acces Error: \n\nFile:' + f + '\n\n' + errorThrown + '\n\n');} 
	});
}

function popHelp(h){
	$('#div_help').html(h)
}


function beginJsonSettings(){  // this is also called from editor.js

	f = 'ui-settings.json';
	$.ajax({
		url     : f,
		type    : 'GET',
		success : loadJsonDisplaySettings,
		error   : function(XMLHttpRequest, textStatus, errorThrown) {alert('Settings File Acces Error: \n\nFile:' + f + '\n\n' + errorThrown + '\n\n');} 
	});
}

function loadJsonDisplaySettings(settings) { 
	$('#loadSettings').html('Loaded');	
	setTimeout(() => { $('#loadSettings').html('Load Display Settings'); }, 2000);

	var ele, m;
	for (item in settings) {
		ele = document.getElementById(item);
		if (ele) {
			if (ele.type == "checkbox") {
				ele.checked = settings[item] == true ? true : false;
				continue;
			}

			if (ele.type == "select") {
				ele.value = settings[item];
				continue;		
			}
		
			ele.value = settings[item];
		}		
		
		if (item == "selDispMode") {
		   m = settings[item];
	       document.documentElement.setAttribute('data-theme', m);
	       sdmode();
		}
	
	} // end for item	
	
	uiColorRefresh();
	
}

function uiColorRefresh() { // this is also called from editor.js
	$('#acc1').trigger('change');
	$('#valColor').trigger('change');
	$('#sysColor').trigger('change');
	$('#btnColor').trigger('change');
	$('#ani_speed').trigger('change');		
}

function changeCss(className, classValue) {

    // we need invisible container to store additional css definitions
    var cssMainContainer = $('#css-modifier-container');
    if (cssMainContainer.length == 0) {
        cssMainContainer = $('<div id="css-modifier-container"></div>');
        cssMainContainer.hide();
        cssMainContainer.appendTo($('body'));
    }

    // and we need one div for each class
    var classContainer = cssMainContainer.find('div[data-class="' + className + '"]');
    if (classContainer.length == 0) {
        classContainer = $('<div data-class="' + className + '"></div>');
        classContainer.appendTo(cssMainContainer);
    }

    // append additional style
    classContainer.html('<style>' + className + ' {' + classValue + '}</style>');
}

function getSiteAlias() {
		if (localStorage.AliasTableUpdated == false)
			return;
	    $.ajax({
        url     : 'site-alias.json',
        type    : 'GET',
        success : loadSiteAlias,
        error   : function(XMLHttpRequest, textStatus, errorThrown) {console.log('site_alias.json file not found. \n\nFile:' + f + '\n\n' + errorThrown + '\n\n');} 
	    });
}

function loadSiteAlias(json) {
	window.siteAlias = json;
	localStorage.AliasTableUpdated == false;
}

function accColorSel() {  // this is also called from editor.js
	
	$('.accColor').on('change', function() { 
		this.blur();
		var c1 = $('#acc1').val();
		var c2 = $('#acc2').val();
		var z = 'linear-gradient(' + c1 + ', ' + c2 +')';
		$('.controlsDisplay').css('background', z);
	});

	$('#valColor').on('change', function() { 
		this.blur();
		var c1 = $('#valColor').val();
		changeCss('.value', 'color: ' + c1 + ';');
		changeCss('.nac', 'color: ' + c1 + ';');		
	});
	
	$('#sysColor').on('change', function() { 
		this.blur();
		var c1 = $('#sysColor').val();
		changeCss('.systgid', 'color: ' + c1 + ';');
	});	

	$('#btnColor').on('change', function() { 
		this.blur();
		var c1 = $('#btnColor').val();
		changeCss('button', 'color: ' + c1 + ';');
		changeCss('.nav-button-active', 'color: ' + c1 + ';');
		changeCss('.nav-button:hover', 'color: ' + c1 + ';');		
		changeCss('.nav-button-active:hover', 'color: ' + c1 + ';');
		changeCss('.btn', 'color: ' + c1 + ';');
		changeCss('.control-button', 'color: ' + c1 + ';');
		changeCss('.control-button:hover', 'color: ' + c1 + ';');		
	});			
		
	$('#ani_speed').on('change', function() { 
		this.blur();
		window.animateSpeed = parseInt(this.value);
	});	
	
}

// color, animation, backgroundColor - used for main talkgroup/system display
// returns the property value of the selector supplied. sheet is document.styleSheets[index].title
function getProperty(selector, property, sheet) { 
	for (y in document.styleSheets) {
		if (document.styleSheets[y].title == sheet) // this title is set in the json color map builder func
			break;
	}
    rules = document.styleSheets[y].cssRules;
    for(i in rules) {
        if(rules[i].selectorText == selector) 
            return rules[i]['style'][property];
    }
    return false;
}

function getStyle(className) {        //test, not used
    var cssText = "";
    var classes = document.styleSheets[1].rules || document.styleSheets[0].cssRules;
    for (var x = 0; x < classes.length; x++) {        
        if (classes[x].selectorText == className) {
            cssText += classes[x].cssText || classes[x].style.cssText;
        }         
    }
    return cssText;
}

var g_opcode = {  // global opcodes
    '0': 'Call', 						// Group Voice Grant grp_v_ch_grant dec=0
    '1': 'Reserved', // REserved 0x01
    '2': 'Update 0x02', 				
    '3': 'Update 0x03',
    '4': 'UnitVoiceGrant',
    '5': 'UU_ANS_RSP', 					// unit to unit answer response
    '6': 'UnitVoiceUpdate',
    '8': 'PhoneGrant',
    '9': 'TELE_INT_PSTN_AEQ',
    '0a': 'Phone Alert',				// tele interconnect
    '0b': 'Reserved',
    '10': 'UnitDataGrant',
    '11': 'GroupDataGrant',
    '12': 'GroupDataUpdate',
    '13': 'GroupDataUpdateExplicit',
    '18': 'UnitStatusUpdate',
    '1a': 'UnitStatusQuery',
    '1c': 'UnitShortMessage',
    '1d': 'UnitMonitor',
    '1f': 'UnitCallAlert',    			// Call Alert
    '20': 'Ack Response',    		// AckResponse - ACK_RESP_U - This is the generic response supplied by a unit to acknowledge an action when there is no other expected response. Response from radio to system poll ("are you still there?")
    '21': 'QueuedResponse',
    '24': 'ExtFunctionCommand',
    '27': 'Denied',    					// DenyResponse
    '28': 'Joins', 		// GroupAffiliationResponse - GRP_AFF_RSP - This is the response to the request for group affiliation by a unit. This will present the necessary information to the requesting unit to allow it to perform group operations for the indicated group identity.
    '29': 'Ack Response FNE',    		// This is the generic response supplied to a unit to acknowledge an action when there is no other expected response. This response is sent to a subscriber unit in response to an earlier action or service request.
    '2a': 'Group Aff Q',    	// GRP_AFF_Q - This transaction is to be used to determine what a targeted subscriber unit maintains as the group affiliation data for the unit. The Query will usually originate in the system, but the standard enables other originators.
    '2b': 'Joins',    	// LocRegResponse - This transaction is to be used to respond to a Location Registration Request. The response indicates that the subscriber is registered in the new location area.
    '2c': 'Login',		// UnitRegResponse
    '2d': 'Force SU Reg',    			// UnitRegCommand - U_REG_CMD - This transaction is to be used to force an SU to initiate Unit Registration
    '2e': 'UnitAuthCommand',
    '2f': 'Logout',    					// UnitDeregAck
    '36': 'RoamingAddrCommand',
    '37': 'RoamingAddrUpdate',
    '38': 'SystemServiceBroadcast',    	// This broadcast will inform the subscriber units of the current system services supported and currently offered on the Primary control channel of this site. 
    '39': 'AltControlChannel',
    '3a': 'RfssStatusBroadcast',
    '3b': 'NetworkStatusBroadcast',
    '3c': 'AdjacentSite',			    // Adjacent Site Broadcast
    '3d': 'ChannelParamsUpdate',	    // IDEN_UP
    '3e': 'ProtectionParamBroadcast',
    '3f': 'ProtectionParamUpdate'
};

var g_reason = {    // TIA-10.AABC-B Annex B Deny Response Reason Codes
    '10': 'Unit not valid',
    '11': 'Unit not authoirized',
    '20': 'Target unit not valid',
    '21': 'Target unit not authorized',
    '2f': 'Target unit refused',
    '30': 'Target group invalid',
    '31': 'Target group not authoirzed',
    '40': 'Invalid dialing',
    '41': 'Telephone number not authroized',
    '42': 'PSTN address invalid',
    '50': 'Call time-out',
    '51': 'Call terminated by landline',
    '52': 'Call terminated by subscriber',
    '5f': 'Call pre-empted',
    '60': 'Site access denial',
    '61': 'User/system def', // 0x61 - 0xEF per standard
    '67': 'User/sys def', 
    '77': 'User/sys def',
    'c0': 'User/sys def',  // seen on MOT system
    'f0': 'Call options invalid',
    'f1': 'Protection service option invalid',
    'f2': 'Duples service option invalid',
    'f3': 'circuit/packet mode service option invalid',
    'ff': 'Service not supported by system'
};

var g_moto_opcode = {    // opcodes when mfrid is MOT (0x90, 144)
    '0': 'MOT Add Patch Group',
    '1': 'MOT Del Patch Group',
    '3': 'MOT Patch Voice Channel Grant Update',
	'4': 'MOT Unknown',
	'5': 'MOT Traffic Chan Stn ID',
	'6': 'MOT Unknown',
	'7': 'MOT Unknown',
	'8': 'MOT Unknown',
	'9': 'MOT System Load',	
	'0a': 'MOT Unknown',
	'0b': 'MOT Control Chan Base Stn ID',
	'0c': 'MOT Unknown',	
	'0d': 'MOT Unknown',	
	'0e': 'MOT Planned Control Channel Shutdown',
	// 0f through 3f = unknown
};

var g_serviceOption = { 
	// TODO - populate this, not used currently.
	// bits 0-2 priority
    '0': 'reserved',
    '1': 'Lowest',
    '2': 'User/system def',
	'3': 'User/system def',
	'4': 'Default',
    '5': 'User/system def',
	'6': 'User/system def',
	'7': 'Highest',

	// bit 3 - reserved
	// bit 4 - mode

};

 
// const value_string MFIDS[] = {
//    { 0x00, "Standard MFID (pre-2001)" },
//    { 0x01, "Standard MFID (post-2001)" },
//    { 0x09, "Aselsan Inc." },
//    { 0x10, "Relm / BK Radio" },
//    { 0x18, "EADS Public Safety Inc." },
//    { 0x20, "Cycomm" },
//    { 0x28, "Efratom Time and Frequency Products, Inc" },
//    { 0x30, "Com-Net Ericsson" },
//    { 0x34, "Etherstack" },
//    { 0x38, "Datron" },
//    { 0x40, "Icom" },
//    { 0x48, "Garmin" },
//    { 0x50, "GTE" },
//    { 0x55, "IFR Systems" },
//    { 0x5A, "INIT Innovations in Transportation, Inc" },
//    { 0x60, "GEC-Marconi" },
//    { 0x64, "Harris Corp." },
//    { 0x68, "Kenwood Communications" },
//    { 0x70, "Glenayre Electronics" },
//    { 0x74, "Japan Radio Co." },
//    { 0x78, "Kokusai" },
//    { 0x7C, "Maxon" },
//    { 0x80, "Midland" },
//    { 0x86, "Daniels Electronics Ltd." },
//    { 0x90, "Motorola" },
//    { 0xA0, "Thales" },
//    { 0xA4, "M/A-COM" },
//    { 0xB0, "Raytheon" },
//    { 0xC0, "SEA" },
//    { 0xC8, "Securicor" },
//    { 0xD0, "ADI" },
//    { 0xD8, "Tait Electronics" },
//    { 0xE0, "Teletec" },
//    { 0xF0, "Transcrypt International" },
//    { 0xF8, "Vertex Standard" },
//    { 0xFC, "Zetron, Inc" },
// };


// const value_string ALGIDS[] = {
//    /* Type I */
//    { 0x00, "ACCORDION 1.3" },
//    { 0x01, "BATON (Auto Even)" },
//    { 0x02, "FIREFLY Type 1" },
//    { 0x03, "MAYFLY Type 1" },
//    { 0x04, "SAVILLE" },
//    { 0x05, "Motorola Assigned - PADSTONE" },
//    { 0x41, "BATON (Auto Odd)" },
//    /* Type III */
//    { 0x80, "Unencrypted" },
//    { 0x81, "DES-OFB, 56 bit key" },
//    { 0x83, "3 key Triple DES, 168 bit key" },
//    { 0x84, "AES-256-OFB" },
//    { 0x85, "AES-128-ECB"},
//    { 0x88, "AES-CBC"},
//    { 0x89, "AES-128-OFB"},
//    /* Motorola proprietary - some of these have been observed over the air,
//       some have been taken from firmware dumps on various devices, others
//       have come from the TIA's FTP website while it was still public,
//       from document "ALGID Guide 2015-04-15.pdf", and others have been
//       have been worked out with a little bit of "guesswork" ;) */
//    { 0x9F, "Motorola DES-XL 56-bit key" },
//    { 0xA0, "Motorola DVI-XL" },
//    { 0xA1, "Motorola DVP-XL" },
//    { 0xA2, "Motorola DVI-SPFL"},
//    { 0xA3, "Motorola HAYSTACK" },
//    { 0xA4, "Motorola Assigned - Unknown" },
//    { 0xA5, "Motorola Assigned - Unknown" },
//    { 0xA6, "Motorola Assigned - Unknown" },
//    { 0xA7, "Motorola Assigned - Unknown" },
//    { 0xA8, "Motorola Assigned - Unknown" },
//    { 0xA9, "Motorola Assigned - Unknown" },
//    { 0xAA, "Motorola ADP (40 bit RC4)" },
//    { 0xAB, "Motorola CFX-256" },
//    { 0xAC, "Motorola Assigned - Unknown" },
//    { 0xAD, "Motorola Assigned - Unknown" },
//    { 0xAE, "Motorola Assigned - Unknown" },
//    { 0xAF, "Motorola AES-256-GCM (possibly)" },
//    { 0xB0, "Motorola DVP"},
// };






