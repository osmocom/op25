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
//
// OP25 Logs

$(window).load(function() {
    $('#loading').hide();
});
  
$(document).ready(function() {
	$('#startDate').val(localStorage.logStart);
	$('#endDate').val(localStorage.logEnd);	
	randCss(); // force css reload each time for dev
	$('#records').text(comma(parseInt(($('#records').text()))));
	$('#systems').text(comma(parseInt(($('#systems').text()))));
	$('#talkgroups').text(comma(parseInt(($('#talkgroups').text()))));	
	$('#subs').text(comma(parseInt(($('#subs').text()))));
	if (localStorage.systemSelect) {
		$('#systemSelect').val(localStorage.systemSelect);
	}
	if (localStorage.systemSelect4) {
		$('#systemSelect4').val(localStorage.systemSelect4);
	}	
});

$(window).load(function() {
    $('#loading').hide();
});
  
function resetDates() {
	$('#startDate').val('');
	$('#endDate').val('');
	$('#systemSelect').val('0');		
	window.localStorage.removeItem('logStart');
	window.localStorage.removeItem('logEnd');
	window.localStorage.removeItem('systemSelect');		
}

$('#navSelect').change(function(){
	console.log("shit");
	var ns = $('#navSelect').val();
	if (ns == '0')
		return;
	console.log(ns);
	load_new_page1(ns);		
});

// forces css to reload - helpful during dev
function randCss() {
  var h, a, f;
  a = document.getElementsByTagName('link');
  for (h = 0; h < a.length; h++) {
    f = a[h];
    if (f.rel.toLowerCase().match(/stylesheet/) && f.href) {
      var g = f.href.replace(/(&|\?)rnd=\d+/, '');
      f.href = g + (g.match(/\?/) ? '&' : '?');
      f.href += 'rnd=' + (new Date().valueOf());
    }
  }
}


function load_new_page1(request,param) {
  var v1 = $('#resource_id').val();
  tgid = $('#cc_filter_tgid').val();
  suid = $('#cc_filter_suid').val();
  tgid = (Number.isInteger(parseInt(tgid)) == true) ? parseInt(tgid) : 0;
  suid = (Number.isInteger(parseInt(suid)) == true) ? parseInt(suid) : 0;
  load_new_page('/logs', 'q=' + v1 + '&r=' + request + '&p=' + param + '&tgid=' + tgid + '&suid=' + suid);
}


//SUID and TGID 'specified' buttons!
function load_new_page0(request) {
  var v1 = $('#resource_id').val();
  var sysid = $('#systemSelect').val();
  if (v1 == '') {
  	alert("Subscriber unit ID or talkgroup ID is required!");
  	return;
  }
  if (v1.split('-').length > 2) {
    	alert("Too many values for a range.");
	  	return;
  }
  
  load_new_page('/logs', 'q=' + v1 + '&r=' + request + '&sysid=' + sysid);
}

function load_new_page(url, arg) {
  var u = url;
  if (arg)
     u = u + "?" + arg;
  window.open(u, "_self", "resizable,location,menubar,toolbar,scrollbars,status")
}

function sdate() {
	var s = $('#startDate').val() ? new Date($('#startDate').val()) : new Date("2001/01/01 01:00");
	var stime = s.getTime() / 1000;
	return stime | 0;
}

function edate() {
	var e = $('#endDate').val() ? new Date($('#endDate').val()) : new Date();
	var etime =  e.getTime() / 1000;
	return etime | 0;
}

function comma(x) {
    // add comma formatting to whatever you give it (xx,xxxx,xxxx)
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function doPurge(sim) {
	var kv = $('#keepVoice').prop('checked');
	var bu = $('#createBackup').prop('checked');	
	if ($('#startDate').val() == '' || $('#endDate').val() == '') {
			alert('Start date and end date are required.');
		return;
	}
	var sd = sdate();
	var ed = edate();
	var sysid = $('#systemSelect').val();
 	window.location.href='/purge?action=purge&sd=' + sd + '&ed=' + ed + '&sysid=' + sysid + '&simulate=' + sim + '&kv=' + kv + '&bu=' + bu;
 	
}

function addNewSystemTag() {
	if ($('#newSysId').val() == '' || $('#newSysTag').val() == '') {
			alert('System ID (dec) and System Tag are required.');
		return;
	}
	var hexId = $('#newSysId').val();
	var newId = parseInt(dec(hexId));
	var newTag = $('#newSysTag').val()
	if (! Number.isInteger(newId)) {
		alert('Invalid system ID.');
		return;
	}
	window.location.href='/asd?id=' + newId + '&tag=' + newTag;
}

function importTalkgroupTsv(cmd) {
	$('#impProc').show()
	if ($('#selTsv').val() == '0' || $('#systemSelect2').val() == '0') {
			alert('TSV file selection and System selection are required.');
				$('#impProc').hide()
		return;
	}
	
	if ($('#invtsv').length){
		$('#impProc').hide()
		alert('The TSV is invalid!');
		return;
	}
	
	var sysid = $('#systemSelect2').val();
	var tsvfile = $('#selTsv').val();	
	window.location.href='/itt?sysid=' + sysid + '&file=' + tsvfile + '&cmd=' + cmd;
}

function deleteTags(cmd) {
	if ($('#systemSelect3').val() == '0') {
			alert('System selection is required.');
		return;
	}
	sysid = $('#systemSelect3').val();	
	window.location.href='/delTags?sysid=' + sysid + '&cmd=' + cmd;
}

function hex(dec) {
	if (!dec) return;
    return dec.toString(16);
}

function dec(hex) {
	if (!hex) return;
    return parseInt(hex, 16);
}

function csvTable(table_id, separator = ',') {       // Quick and simple export target #table_id into a csv
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



