// Copyright 2017, 2018, 2019, 2020 Max H. Parke KA1RBI
// Copyright 2020, 2021 Michael Rose
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

// Last Update: 04-Jun-2021


var delay = 250;

const params = new URLSearchParams(window.location.search); // load query string from url

	window.file = params.get('file');
	window.mode = params.get('mode');
	window.nac  = params.get('nac');
	window.sys  = params.get('sys');
	var css = params.get('css') ? params.get('css') : 'dark';	

//		 file - the tsv filename to work with (only matters for tg, src, sa - hard coded in the python for color)
//		   id - the talkgroup or source ID to jump to upon load
//		  css - [ light | dark ] - the display mode
//		 mode - [ tg | src | color ]  what is being worked on

	window.imp = false;
	var unsaved = false;

var error1 = "ID and Tag fields are required. \n\n Error 1";
var error2 = "Talkgroup and Priority / Color fields must be an integer. \n\n Error 2";
var error3 = "Priority / Color field must be an integer. \n\n Error 3";
var error4 = "ID already exists and must be unique. \n\n Error 4";
var error5 = "Import file not specified. \n\n Error 5";
var error6 = "Editor table not present. \n\n Error 6";
var error7 = 'not supported. Expecting CSV or TSV. \n\n Error 7';
var error8 = 'Failed to load file: ';
var error9 = '';
var error10 = 'All fields are required. \n\n Error 10';
var error11 = 'Duplicate rffs/site entries not permitted. \n\n Error 11';
var error12 = 'Invalid system ID. Input out of range. \n\n Error 12';
var error13 = 'Duplicate System ID. \n\nError 13';

$(window).on('load', function() {
	document.documentElement.setAttribute('data-theme', css); 
	var tgid = params.get('id');
	if (tgid)
		var x = setTimeout(function(){ scrollToAnchor(tgid) }, 300);
	var oc = "this.blur(); command_reload_tsv(" + nac + ");";
	$('#btnReload').attr("onclick", oc);
	$('#searchInput').val(null);
	$('#csv-upload').hide();
	$('#loading').hide();
	$('#csvfile').val(null).on('change',readSingleFile);
	generateCSS();
	beginJsonSettings();
	accColorSel();
	uiColorRefresh();
	
	switch(mode) {
		case 'tg':
			window.modeTitle = "Talkgroup";
			$('#btnLoad').text('Load Talkgroups');	
			document.querySelectorAll('button.saveButton').forEach(elem => {
				elem.innerHTML = "Save Talkgroups";
			});
			$('#title').text('Talkgroup TSV Editor - OP25');
			break;
	
		case 'src':
			window.modeTitle = "Source";
			$('#btnLoad').text('Load Source IDs');				
			document.querySelectorAll('button.saveButton').forEach(elem => {
				elem.innerHTML = "Save Source IDs";
			});				
			$('#title').text('Source IDs TSV Editor - OP25');
			break;
		
		case 'alias':
			window.modeTitle = "Alias";
			$('#btnLoad').text('Load Aliases');				
			document.querySelectorAll('button.saveButton').forEach(elem => {
				elem.innerHTML = "Save Aliases";
			});				
			$('#title').text('System Site Alias Editor - OP25');
			break;
			
		case 'color':
			window.modeTitle = "Color";
			$('#btnLoad').text('Load Colors');				
			document.querySelectorAll('button.saveButton').forEach(elem => {
				elem.innerHTML = "Save Colors";
			});				
			$('#title').text('Colors Editor - OP25');
			$('#btnColorEditor').hide();
			$('.importExport').hide(); // hide these buttons -- import/export function not written yet
			break;
		} // end switch			
		
});

$(document).ready(function() {
	// nothing here right now
});

window.onbeforeunload = function(){
  if (unsaved == true)
	  return 'Are you sure you want to leave? Unsaved changes will be lost.';
};

// delete button
$('input[class="delbutton"]').click(function(e){
   $(this).closest('tr').remove();
})

function tsv_onload() {	
	switch(mode) {	
		case "alias":
			beginAlias();	
			break;
		case "color":
			beginColor();
			break;
		default:
			begin();
	}	
}

function begin() {
// 		console.log('begin() started...');
		$( "#loading" ).show();	
		if (begin.caller.name != "completeSave")
			$('#talkgroups').hide(250);	
		$("#message").text("Fetching TSV...");
		file = window.file;
	    $.ajax({
        url     : file,
        type    : 'GET',
        success : buildTable,
        error   : function(XMLHttpRequest, textStatus, errorThrown) {alert('File Acces Error: \n\nFile:' + file + '\n\n' + errorThrown + '\n\n');} 
    });
}

function beginAlias() {
// 		console.log('beginAlias() started...');
		$( "#loading" ).show();	
		if (beginAlias.caller.name != "completeSave")
			$('#talkgroups').hide(250);	
		$("#message").text("Fetching Info...");
		file = window.file;
	    $.ajax({
        url     : file,
        type    : 'GET',
        success : buildAliasTable,
        error   : function(XMLHttpRequest, textStatus, errorThrown) {alert('File Acces Error: \n\nFile:' + file + '\n\n' + errorThrown + '\n\n'); buildAliasTable();} 
    });
}

function beginColor() {
		console.log('beginColor started...');
		$('#searchInput').hide();
		$("#main").html('Loading...');
		$(".saveButton").attr("onclick", "this.blur(); saveColorTable();");
		$("#btnLoad").attr("onclick", "this.blur(); beginColor();");
		$( "#loading" ).show();	
		generateCSS();			
		colorFile = 'color-map.json';
	    $.ajax({
        url     : colorFile,
        type    : 'GET',
        success : buildColorTable,
        error   : function(XMLHttpRequest, textStatus, errorThrown) {alert('File Acces Error: \n\nFile:' + colorFile + '\n\n' + errorThrown + '\n\n');} 
    	});
}


function buildTable(d) {
// 	console.log('build table started... ~207');
		if (!d) {
			location.reload();
		}
			
		$("#message").text("Building table...");
		
		var x = "";
		lines = [];
		
		data = d.split(/\r?\n/); 					// split by newline
		
		for(var i = 0; i < data.length; i++){
			lines.push(data[i].split(/['\t']+/));  	// split by tab \t
		}	

		i = 0;
													// TODO split priority and color into 2 fields?
		aLen = lines.length;
		
			var html = '<div id="editor">';
			html += '<table class="editor" id="tsv-editor">';
			html += '<th>New ' + window.modeTitle + ' ID</th>';
			html += '<th>New ' + window.modeTitle + ' Tag</th>';
			html += '<th class="pricol">Priority / Color</th>';
			html += '<th>Actions</th>';
			
			html += '<tr><td><input type="text" id="newtg"></td>';
			html += '    <td><input type="text" id="newtag"></td>';
			html += '    <td><input type="text" id="newcol"></td>';
			html += '    <td align="center"><button id="btnAddNew" onclick="this.blur; addNew();"> Add New </button></td></tr>';					
			html += '</table><br>';

			html += '<span class="label">Editing TSV: </span><span class="value">' + file + '</span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;';
			html += '<span id="records">&nbsp;</span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;';
			html += '<span class="label">NAC: </span><span class="value">' + (nac) + ' - 0x' + (hex(parseInt(nac)).toUpperCase()) + '</span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;';
			html += '<span class="value" id="unsaved" style="display: none;">Unsaved Changes</span>';
			html += '<br><br>';
			
			html += '<table class="editor" id="talkgroups">';
			html += '<th>Row</th>';
			html += '<th>' + window.modeTitle + ' ID</th>';
			html += '<th>' + window.modeTitle + ' Tag</th>';
			html += '<th class="pricol" >Priority / Color</th>';
			html += '<th>Actions</th>';
			
		for (var i = 0; i < aLen - 1; i++) {
		
			x = i;
			var id = lines[i][0];
			var tag = lines[i][1];
			var col = lines[i][2]; // ? lines[i][2] : 0;
			
			var eleid_id   = 'ID' + i + id + parseInt(Math.random() * 10000000);		// unique IDs for each td, not used for anything right now.
			var eleid_tag  = 'ID' + i + id +  parseInt(Math.random() * 10000000);
			var eleid_col  = 'ID' + i + col +  parseInt(Math.random() * 10000000);
			
			html += '<tr>';
			html += '<td id="">' + (i + 1) + '<a href="#" name="'+ id + '"></a></td>';
			
			html += '<td id="' + (eleid_id) + '" style="width: 150px;"><input type="text"    id="' + x + '" value="' + id  + '" class="tg  tedit"></td>';
			html += '<td id="' + (eleid_tag) + '"><input type="text" id="tag' + x + '" value="' + tag + '" class="tag tedit"></td>';
			html += '<td id="' + (eleid_col) + '" style="width: 150px;"><input maxlength="4" type="text" id="col' + x + '" value="' + col + '" class="col tedit"></td>';

			html += '<td align="center">';						
			html += '<button title="Delete" class="delbutton" onclick="this.blur; deleteRow(\'' + id + '\', \'' + tag +'\');">&#x2718;</button></td>';
			
			html += '</tr>';
		}

		html += '</table></div><br><br><br><br>';

		var s = document.getElementById("main");  // todo - use jQ attri() method to assign custom attributes.
		s.innerHTML = html;
		s.content = 'editor';
		
		$('#main').data('content', 'editor');
		
		$("#main").html(html);
		$('#talkgroups').show(150);	
		
		$('#records').html('<span class="label">Records: </span><span class="value">' + (getHigh() + 1) + ' </span>');
		
		$('#message').text('Ready');

		if (mode == 'src') $('.pricol').text('Color');

		document.querySelectorAll(".tedit").forEach(item => {
		  item.addEventListener('change', event => {
			isUnsaved();
		  });
		});
		
		// enter key behavior (clicks Add New button)
		$('#newtg').on('keypress', function(e) {
			if(e.which == 13) {
				$('#btnAddNew').trigger('click');
			}
		});
		
		$('#newtag').on('keypress', function(e) {
			if(e.which == 13) {
				$('#btnAddNew').trigger('click');
			}
		});
		
		$('#newcol').on('keypress', function(e) {
			if(e.which == 13) {
				$('#btnAddNew').trigger('click');
				$('#newtg').focus();
			}
		});	
		
		$( "#loading" ).hide();	
		if (window.imp == true)  //only flag as unsaved if buildTable was used after import
			isUnsaved();
}

function deleteRow(id, tag) {
	var r = confirm(id + ' - ' + tag + '\n\nConfirm delete.');
	if (r == true) {
      var td = event.target.parentNode; 
      var tr = td.parentNode; // the row to be removed
      tr.parentNode.removeChild(tr);
      isUnsaved();
    }
}

function saveTable() {
// 	console.log('saveTable()');
	if (!document.getElementById("talkgroups")) {
		jAlert(error6, 'Error');
		return 0;
	}
	
	$( "#loading" ).show();	
	window.location.href = "#top";
	// $('#talkgroups').hide(250);
	$('#message').text('Saving...');
	disableSave(); // disable save buttons momentarily 

	var tgs, tag, col;
	data = [];
		
	table = document.getElementById("talkgroups");
	rows = table.rows.length;
	
	var els = document.getElementsByClassName("tg"); // only the ID field is "tg"
	
	for(var i = 0; i < els.length; i++) {
		
		x = els[i].id;
		
			tgs = document.getElementById(x).value;
			tag = document.getElementById("tag" + (x)).value;
			col = document.getElementById("col" + (x)).value;
			
			if (tgs == "" || tag == "") {
				jAlert(error1 + '\n\nEmpty fields on Row ' + (i + 1) + '\n\n', 'Error');
				enableSave();
				return;	
			}		
			
			if (!Number.isInteger(Number(tgs)) && mode=='tg') {
				jAlert(error2 + ' \n\n' + tgs + ' looks like a ' + (typeof tgs) + ' on Row ' + (i + 1) + '.', 'Error');
				enableSave();				
				return;
			}
	
			if (!Number.isInteger(Number(col))) {
				jAlert(error3 + ' \n\n' + col + ' looks like a ' + (typeof col) + ' on Row ' + (i + 1) + '.', 'Error');
				enableSave();				
				return;
			}	
		
			data[i] = new Array(tgs, tag, col);

	}

	if (mode == "tg") {
		data.sort(function(a, b) {
			return a[0] - b[0];
		});
	}
	
	// have to sort Source IDs differently because there could be wildcards/strings in there.
	if (mode == "src") {		
		data.sort(function( a , b){
			if(a[0] > b[0]) return 1;
			if(a[0] < b[0]) return -1;
			return 0;
		});
	
		data.sort(function(a, b){
		  return a[0].length - b[0].length;
		});
	}
	
	//json output - not currently used here
	var jsonOutput = JSON.stringify(data, undefined, 2);
	
	var textOutput = "";
	for(var i = 0; i < data.length; i++) {
		textOutput += (data[i][0] + '\t' + data[i][1] + '\t' + data[i][2] + '\n');
	}

	save_tsv('config-tsvsave', textOutput, window.file);    // send data to server

	setTimeout(completeSave, delay);   // artificial delays to allow http_server.py time to process things
	setTimeout(function(){ command_reload_tsv(nac); }, delay); // tell OP25 to reload the TSVs
	setTimeout(enableSave, delay);
	$('#talkgroups').show(delay);
	$( "#loading" ).hide();	
	isSaved();

}

function addNew() {
	var id = getHigh() + 1;
	var table = document.getElementById("talkgroups");
	var x;

	var  newtg = $('#newtg').val();		// we're re-using the same AddNew code in Alias editor as well, hence the variable names.
	var newtag = $('#newtag').val();
	var newcol = $('#newcol').val();
		
	var alias = newtg;
	var r = newtag;
	var s = newcol;		
			
	if (mode=="tg" || mode == "src") {
		if (newtg == "" || newtag == "" ) {   // || newcol == "") {
			jAlert(error1, 'Error');			
			return;	
		}
	
		if (!Number.isInteger(Number(newtg)) && mode=='tg') {
			jAlert(error2 + ' \n\n<b>' + newtg + '</b> looks like a ' + (typeof newtg) + '.', 'Error');
			return;
		}
	
		if (!Number.isInteger(Number(newcol))) {
			jAlert(error3 + ' \n\n<b>' + newcol + '</b> looks like a ' + (typeof newtg) + '.', 'Error');
			return;
		}	
	
		var els = document.getElementsByClassName("tg");
		for(var i = 0; i < els.length; i++) {
			x = parseInt(els[i].value);
			if (newtg == x) {
				jAlert(error4, 'Error');				
				return;
			}
		}
	}
	
	if (mode=="alias") {
			if (alias == "" || r == "" || s == "") {
				jAlert(error10, 'Error');
				return;	
			}	
	}
	
	var row = table.insertRow(1); 
	var cell0 = row.insertCell(0);
	var cell1 = row.insertCell(1);
	var cell2 = row.insertCell(2);
	var cell3 = row.insertCell(3);
	var cell4 = row.insertCell(4);

	if (mode == "tg" || mode == "src") { 

		cell0.innerHTML = '<span class="newtg">New</span>';
		cell1.innerHTML = '<td><span class="newtg"><input type="text"    id="' + id + '" value="' + newtg + '" class="tg"></td>';
		cell2.innerHTML = '<td><span class="newtg"><td><input type="text" id="tag' + id + '" value="' + newtag + '"></td>';
		cell3.innerHTML = '<td style="width: 100px;"><span class="newtg"><input type="text" id="col' + id + '" value="' + newcol + '"></td>';
		cell4.innerHTML = '<td align="center"><button class="saveButton" id="btnSave3" onclick="this.blur; saveTable();"> Save </button>&nbsp;&nbsp;';
		cell4.style = "text-align:center";
		cell4.innerHTML += '<button title="Delete" class="delbutton" onclick="this.blur; deleteRow();">&#x2718;</button></td>';
	}
	
	if (mode == "alias") { 
	
		cell0.innerHTML = '<span class="newtg">New</span>';
		cell1.innerHTML = '<td><span class="newtg"><input type="text"    id="' + id + '" value="' + alias + '" class="tg"></td>';
		cell2.innerHTML = '<td><span class="newtg"><td><input type="text" id="rfss' + id + '" value="' + r + '"></td>';
		cell3.innerHTML = '<td style="width: 100px;"><span class="newtg"><input type="text" id="site' + id + '" value="' + s + '"></td>';
		cell4.innerHTML = '';
		cell4.style = "text-align:center";
		cell4.innerHTML += '<button title="Delete" class="delbutton" onclick="this.blur; deleteRow();">&#x2718;</button></td>';
	}

		
	 $('#newtg').val('');
	$('#newtag').val('');
	$('#newcol').val('');		
	
	isUnsaved();
}

function getHigh() {
	var x = [];
	var els = document.getElementsByClassName("tg");
	for(var i = 0; i < els.length; i++) {
		x[i] = (parseInt(els[i].id));
	}
	x = Math.max(...x);
// 	console.log(x);
	if (x == -Infinity) x = -1;
	return x;
}

function scrollToAnchor(a){
	var f;
	var els = document.getElementsByClassName("tg");
	for(var i = 0; i < els.length; i++) {
		if (a ==  (parseInt(els[i].value))) {
			var x = document.getElementById(i);
			x.focus();
			x.scrollIntoView({
            behavior : 'smooth',
            block    : 'center',
            inline   : 'center'
        });
		return;
		}
	}
	
	jAlert (modeTitle + ' ' + a + ' not found. There may be wildcard matches. \n\n Creating new. ', 'Add New');
	$('#newtg').val(a);
	$('#newtg').focus();
}

function tsv_csv() {  // export to CSV file
	var filetag = 'op25_tsv_' + mode;
    var csv = "";
    var separator = ",";
    var rows = [];
	var tgs = $('.tg');
	var tag = $('.tag');
	var col = $('.col');		
	
	for(var i = 0; i < tgs.length; i++) {
		rows.push ( [ tgs[i].value, tag[i].value, col[i].value ] );	
	}

	var filename = 'export_' + filetag + '_' + new Date().toLocaleDateString() + '.csv';
	$("#unsaved").show();
	exportToCsv(filename, rows); // in main.js

}

function clearMessage() {
	$('#message').text('');
}

function refresh() {
	location.reload();
}

function up() {
	window.location.href = '#top';
}

function completeSave() {
	switch(mode) {
	case "alias":
		beginAlias();	
		break;
	case "color":
		beginColor();
		break;
	default:
// 		console.log('executing default...');
		begin();
	}	
}

function disableSave() {
	$('.saveButton').prop('disabled', true);
// 	document.querySelectorAll('button.saveButton').forEach(elem => {
// 		elem.disabled = true;
// 	});
}

function enableSave(){     
	$('.saveButton').prop('disabled', false); 
// 	document.querySelectorAll('button.saveButton').forEach(elem => {
// 		elem.disabled = false;
// 	});
}

function help(){
	    $.ajax({
        url     : 'tsv-help.html',
        type    : 'GET',
        success : dispHelp
    });
}

function dispHelp(h) {
	var s = document.getElementById("main");
// 	if (s.content == 'help')
// 		return;
	
	if ($('#main').data('content') == 'help')
		return;
		
// 	window.editorTable = s.innerHTML;
// 	s.innerHTML = h;
	window.editorTable = $('#main').html();
	$('#main').html(h);
	s.content = 'help';
	$('#main').data('content', 'help');
}

function closeHelp() {
	var s = document.getElementById("main");
	s.innerHTML = window.editorTable;
	s.content = 'editor';
	$('#main').data('content', 'editor');			
}

function isNum(x) {
	if (!x) return;
	y = Number.isInteger(x);
	return y;
}

function command_reload_tsv(nac) {
	$('#message').text('Sending command...');
	reload_tsv(parseInt(nac));
	$('#message').text('Command Sent');
}

function dispImport() {
	$('#csv-upload').show();
}

function hideImport() {
	$('#csv-upload').hide();
}

function isUnsaved() {
      unsaved = true;
	  $( "#unsaved" ).show();
}

function isSaved() {
	  $( "#unsaved" ).hide();
      unsaved = false;
}

function readSingleFile(evt) {
	if (!evt.target.files) {
		alert(error5);
		return;
	}

    var f = evt.target.files[0]; 
    if (f) {
		isUnsaved();
    	var ftype = (evt.target.value).substr((evt.target.value).length - 3).toUpperCase();
    
    switch (ftype) {
    	case 'CSV':
    		var sep = ",";
    		break;
    	case 'TSV':
    		var sep = "\t";
    		break;	
    	default:
    		jAlert('File type ' + ftype + ' ' + error7, 'Error');
    		return;
    }
    
      var r = new FileReader();
      if (!r) return;
      r.onload = function(e) { 
          var contents = e.target.result;
//          document.write("File Uploaded! <br />" + "name: " + f.name + "<br />" + "content: " + 'contents hidden' + "<br />" + "type: " + f.type + "<br />" + "size: " + f.size + " bytes <hr />");
          var lines = contents.split("\n"), output = [];
          for (var i=0; i<lines.length; i++){
          	if (lines[i].length > 0)
	            output.push(lines[i].split(sep).join("\t") + "\n");
          }
          output = "" + output.join("") + "";
          isUnsaved();
          window.imp = true;
          buildTable(output);
     }
       r.readAsText(f);
       isUnsaved();
    } else { 
      jAlert(error8 + evt.target.value, 'Error');
    }
}

function buildAliasTable(d) {  // geting JSON with this one

		if (!d) {
			location.reload();
		}
		var lines = [];
		var i = 0;
		var sysid = window.sys;
		var alias;
		var systems = [];
		window.aliasData = d;

		for (r in d) {
			systems.push(r);
		}

		for (r in d[sysid]) {
			for (s in d[sys][r]) {
				alias = d[sys][r][s]['alias'];
// 					console.log (sysid + ' / '  + hex(parseInt(sysid)).toUpperCase() + ' - ' + alias + ' - R=' + r + ' - S=' + s);
				lines.push([alias, r, s]);
			}
		}

		$("#message").text("Building table...");
		aLen = lines.length;
		
			var html = '<div id="editor">';
			html += '<table class="editor" id="tsv-editor">';
			html += '<th>New ' + window.modeTitle + '</th>';
			html += '<th>RFSS ID (dec)</th>';
			html += '<th>Site ID (dec)</th>';
			html += '<th>Actions</th>';
			
			html += '<tr><td><input type="text" id="newtg"></td>';
			html += '    <td><input type="text" id="newtag"></td>';
			html += '    <td><input type="text" id="newcol"></td>';
			html += '    <td align="center"><button id="btnAddNew" onclick="this.blur; addNew();"> Add New </button></td></tr>';					
			html += '</table><br>';

			html += '<span class="label">Editing: </span><span class="value">' + file + '</span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;';
			html += '<span id="records">&nbsp;</span>&nbsp;&nbsp;&nbsp;&nbsp;';
			html += '<span class="label">System: </span><span class="value">' + (sysid) + ' - 0x' + (hex(parseInt(sysid)).toUpperCase()) + '</span>&nbsp;&nbsp;&nbsp;&nbsp;';
			html += '<span class="label">Change: </span>';
			html += '<span><select name="selSystem" id="selSystem" style="width: 100px;"></select></span>';
			html += '<span class="value" id="unsaved" style="display: none;">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Unsaved</span>';
			html += '<br><br>';
			
			html += '<table class="editor" id="talkgroups">';
			
			html += '<th width="">Row</th>';
			html += '<th width="300">' + window.modeTitle + '</th>';
			html += '<th width="">RFSS ID<br>(dec)</th>';
			html += '<th width="">Site ID<br>(dec)</th>';
			html += '<th wifth="120">Actions</th>';
			
			if (aLen == 0) {
				jAlert('No Site Aliases found for System ' + sysid + '. Try creating some.', 'Create New');
			}
			
		for (var i = 0; i < aLen; i++) {
		
			x = i;
			var alias = lines[i][0];
			var rfss = lines[i][1];
			var site = lines[i][2];  
			
			var eleid_alias = 'ID' + i + site + parseInt(Math.random() * 10000000);		// unique IDs for each td, not used for anything right now.
			var eleid_rfss  = 'ID' + i + site + parseInt(Math.random() * 10000000);
			var eleid_site  = 'ID' + i + site + parseInt(Math.random() * 10000000);
			
			html += '<tr>';
			html += '<td id="">' + (i + 1) + '<a href="#" name="'+ alias + '"></a></td>';
			
			html += '<td id="' + (eleid_alias) + '" style="width: 150px;"><input type="text"    id="' + x + '" value="' + alias  + '" class="tg  tedit"></td>';
			html += '<td id="' + (eleid_rfss) + '"><input type="text" id="rfss' + x + '" value="' + rfss + '" class="rfss tedit"></td>';
			html += '<td id="' + (eleid_site) + '" style="width: 150px;"><input maxlength="4" type="text" id="site' + x + '" value="' + site + '" class="site tedit"></td>';

			html += '<td align="center">';						
			html += '<button title="Delete" class="delbutton" onclick="this.blur; deleteRow(\'' + alias + '\', \'' + site +'\');">&#x2718;</button></td>';
			
			html += '</tr>';
		}

		html += '</table></div><br><br><br><br>';

		var s = document.getElementById("main");  // todo - use jQ attri() method to assign custom attributes.
		s.innerHTML = html;
		s.content = 'editor';
		
		$('#main').data('content', 'editor');
		
		$("#main").html(html);
		$('#talkgroups').show(150);	
		
		$('#records').html('<span class="label">Records: </span><span class="value">' + (getHigh() + 1) + ' </span>');
		
		$('#message').text('Ready');

		if (mode == 'src') $('.pricol').text('Color');

		document.querySelectorAll(".tedit").forEach(item => {
		  item.addEventListener('change', event => {
			isUnsaved();
		  });
		});
		
		$( "#loading" ).hide();	
		if (window.imp == true)  //only flag as unsaved if buildTable was used after import
			isUnsaved();
			
		// enter key behavior (clicks Add New button)
		$('#newtg').on('keypress', function(e) {
			if(e.which == 13) {
				$('#btnAddNew').trigger('click');
			}
		});
		
		$('#newtag').on('keypress', function(e) {
			if(e.which == 13) {
				$('#btnAddNew').trigger('click');
			}
		});
		
		$('#newcol').on('keypress', function(e) {
			if(e.which == 13) {
				$('#btnAddNew').trigger('click');
				$('#newtg').focus();
			}
		});				
			
		populateChange(systems);	

}

function populateChange(sys) {
	var s, h;
	$('#selSystem').append('<option value="' + 0 + '">' + 'Select...' + '</option>');
	for (i in sys) {
		s = sys[i];
		h = hex(parseInt(s));
		$('#selSystem').append('<option value="' + s + '">' + s + ' - 0x' + h.toUpperCase() + '</option>');
	}
	$('#selSystem').append('<option value="' + 'new' + '">' + 'Add New...' + '</option>');
	$('#selSystem').on('change', function() {
		  changeSys(sys);
		});
}

function changeSys(sys) {

		if (sys == 0) 
			return;
		
		var sel	= $('#selSystem').val();
		
		var sysd = 0;
		
		if (sel == 'new') {
			var p = prompt('Enter new System ID in hex.\n\n');

			if (!p) { // Cancel btn
				$('#selSystem').val(0);
				return;
			}

			if (!(p.match("^[0-9a-fA-F]+$") !== null)) { // valid hex?
				jAlert(error12, 'Invalid Entry');
				$('#selSystem').val(0);
				return;
			}

			sysd = dec(p);
	
			if (sysd < 1 || sysd > 4095) {
				jAlert(error12, 'Invalid Entry');
				$('#selSystem').val(0);
				return;	
			}

			if (sys.includes( sysd.toString())) {
				jAlert(error13, 'Invalid Entry');
				$('#selSystem').val(0);
				return;
			}
			
			$('#selSystem').val(0);
			
			sel = sysd;
			
		} // end if new
			
		var url = 'alias-edit.html?file=site-alias.json&mode=alias&sys=' + sel;
		window.sys = sel;
		beginAlias();
}

function deleteSys() {
	system = window.sys;

	if (Object.keys(aliasData).length == 1) {
// 		console.log('cannot delete last system');
		return;
	}

	var r = confirm("Confirm: Delete site aliases for System " + system + ' - 0x' + hex(parseInt(sys)).toUpperCase() + '\n\nWARNING: This action cannot be reversed.\n\n');
	if (r == true) {
		delete window.aliasData[system.toString()];		
		$('#selSystem option[value="' + system + '"]').remove();
		var jsonOutput = JSON.stringify(aliasData, undefined, 2);
		$( "#loading" ).show();			
		save_tsv('config-tsvsave', jsonOutput, window.file);    // send data to server
		$('#selSystem :nth-child(1)').prop('selected', true); // select first option (below Select...)
		var newSys = $('#selSystem option').eq(1).val();
		window.sys = newSys;
		$('#loading').hide();	
		beginAlias();
	} else {
		// cancel
		return;
	}
}

function saveAliasTable() {                    							
	if (!document.getElementById("talkgroups")) {
		jAlert(error6, 'Error');
		return 0;
	}
	
	d = window.aliasData;
	var sysid = window.sys;

	$( "#loading" ).show();	
	window.location.href = "#top";
	// $('#talkgroups').hide(250);
	$('#message').text('Saving...');

	disableSave(); // disable save buttons momentarily 

	var tgs, tag, col;
	data = [];
	out = [];
	rs = [];
	
	table = document.getElementById("talkgroups");
	rows = table.rows.length;
	
	// check for dupe rfss/site combos
	var els = document.getElementsByClassName("tg");
 			for(var y = 0; y < els.length; y++) {
				rfss = document.getElementById("rfss" + (y)).value;
				site = document.getElementById("site" + (y)).value;
				rs.push([rfss, site]);
			}			
		var arr = rs.map(JSON.stringify);
		rl = arr.length;
		var sar = new Set(arr);
		sl = sar.size;
		if (rl != sl ) {
			jAlert(error11, 'Error');
			$('#message').text('Ready');
			$( "#loading" ).hide();	
			enableSave();			
			return;
		}
			
	for(var i = 0; i < els.length; i++) {
		
		x = els[i].id;
		
		alias = document.getElementById(x).value;
		rfss = document.getElementById("rfss" + (x)).value;
		site = document.getElementById("site" + (x)).value;
				
		if (alias == "" || rfss == "" || site == "") {
			jAlert(error10 + '\n\nEmpty fields on Row ' + (i + 1) + '\n\n', 'Error');
			enableSave();
			return;	
		}		
		
		data[i] = new Array(alias, rfss, site);

	}

	data.sort(function(a, b) {
		return a[2] - b[2];
	});

	// these get added to site-alias.json when no data is present initially - just delete them.
	delete d['readyState'];
	delete d['responseText'];
	delete d['status'];
	delete d['statusText'];
	
	delete d[sys];
	
	for(var i = 0; i < data.length; i++) {
		alias = data[i][0];
		r = data[i][1];
		s = data[i][2];	
		d[sys] = d[sys] || {};
		d[sys][r] = d[sys][r] || {};
		d[sys][r][s] = d[sys][r][s] || {};
		d[sys][r][s]['alias'] = alias;
	}	
	
	//json output
	var jsonOutput = JSON.stringify(d, undefined, 2);
	save_tsv('config-tsvsave', jsonOutput, window.file);    // send data to server

	setTimeout(completeSave, delay);   // artificial delays to allow http_server.py time to process things
	setTimeout(enableSave, delay);
	$('#talkgroups').show(delay);
	$('#loading').hide();	
	localStorage.AliasTableUpdated == true;
	isSaved();

}

function buildColorTable(d) {

// 	console.log('build color table started...');

			var html = '<span class="value" id="unsaved" style="display: none;">Unsaved Changes</span>';
			html += '<br><br>';
						
			html += '<div id="editor">';
			html += '<table class="editor" id="tsv-editor">';
			
			html += '<th>Color</th>';
			html += '<th>Font Color</th>';
			html += '<th>Background</th>';
			html += '<th title="thank Max for this...">Blink</th>';
			html += '<th>Sample Text</th>';						

		for (i in d) {
			if (!d[i])
				continue;
			if (d[i][0] > 99)
				continue;
			
			var x = i;
			
			var color = d[i][1];
			var backg = d[i][2];
			var blink = d[i][3];
			
			var blinkOpt = (d[i][3] == true) ? "Yes" : "No";
			
			html += '<tr>';
			
			html += '<td style="text-align: center;" id=""><b>' + (parseInt(x)) + '</b></td>';
			
			html += '<td style="width: 150px; text-align: center;"><input title="' + x + '" type="text"    id="' + (x + 'color') + '" value="' + color  + '" class="tg  tedit coloredit"></td>';
			
			html += '<td style="width: 150px; text-align: center;"><input title="' + x + '" type="text"    id="' + (x + 'backg') + '" value="' + backg  + '" class="tg  tedit bgedit"></td>';

			html += '<td style="width: 150px; text-align: center;">';
			html += '<input type="checkbox" title="' + x + '" id="' + (x + 'blink') + '" class="tg  tedit blinkedit">';
			html += '<label for="' + (x + 'blink') + '"><span></span></label>';
			html +='</td>';

			html += '<td style="text-align: center;"><span id="s' + x + '" class="c' + parseInt(x)  + '">Sample Text 12345 </span>';

			html += '</tr>';
		
		}

		html += '</table></div><br><br><br><br>';
		generateCSS();
		var s = document.getElementById("main");  // todo - use jQ attri() method to assign custom attributes.
		s.innerHTML = html;
		s.content = 'editor';
		
		$('#main').data('content', 'editor');
		
		$("#main").html(html);
		$('#talkgroups').show(150);	

		for (i in d) {
			if (!d[i])
				continue;
			if (d[i][0] > 99)
				continue;
			$('#' + (i) + 'blink').prop('checked', d[i][3]);
		}

		// color picker: Spectrum - https://github.com/bgrins/spectrum
		// Copyright (c) Brian Grinstead
		// 
		// Permission is hereby granted, free of charge, to any person obtaining
		// a copy of this software and associated documentation files (the
		// "Software"), to deal in the Software without restriction, including
		// without limitation the rights to use, copy, modify, merge, publish,
		// distribute, sublicense, and/or sell copies of the Software, and to
		// permit persons to whom the Software is furnished to do so, subject to
		// the following conditions...
		// ** see complete license in source css & js
		
		$(".coloredit").spectrum({
		    preferredFormat: "hex",	
		    localStorageKey: "spectrum.homepage",
		    chooseText: "Select",
		    clickoutFiresChange: false,		
		    containerClassName: 'colorPicker',
		    replacerClassName: 'colorReplacer',
		    showInput: true,
		    showPalette: true,
		    showInitial: true,
 	        allowEmpty: false,
 	            palette: [
				["#000","#444","#666","#999","#ccc","#eee","#f3f3f3","#fff"],
				["#f00","#f90","#ff0","#0f0","#0ff","#00f","#90f","#f0f"],
				["#f4cccc","#fce5cd","#fff2cc","#d9ead3","#d0e0e3","#cfe2f3","#d9d2e9","#ead1dc"],
				["#ea9999","#f9cb9c","#ffe599","#b6d7a8","#a2c4c9","#9fc5e8","#b4a7d6","#d5a6bd"],
				["#e06666","#f6b26b","#ffd966","#93c47d","#76a5af","#6fa8dc","#8e7cc3","#c27ba0"],
				["#c00","#e69138","#f1c232","#6aa84f","#45818e","#3d85c6","#674ea7","#a64d79"],
				["#900","#b45f06","#bf9000","#38761d","#134f5c","#0b5394","#351c75","#741b47"],
				["#600","#783f04","#7f6000","#274e13","#0c343d","#073763","#20124d","#4c1130"]
    		    ]
		});
		
		$(".bgedit").spectrum({
		    preferredFormat: "hex",	
		    localStorageKey: "spectrum.homepage",
		    clickoutFiresChange: false,
		    containerClassName: 'colorPicker',
		    replacerClassName: 'colorReplacer',		    
		    chooseText: "Select",		    
		    showInput: true,
		    showPalette: true,
		    showInitial: true,
 	        allowEmpty: true,
 	            palette: [
				["#000","#444","#666","#999","#ccc","#eee","#f3f3f3","#fff"],
				["#f00","#f90","#ff0","#0f0","#0ff","#00f","#90f","#f0f"],
				["#f4cccc","#fce5cd","#fff2cc","#d9ead3","#d0e0e3","#cfe2f3","#d9d2e9","#ead1dc"],
				["#ea9999","#f9cb9c","#ffe599","#b6d7a8","#a2c4c9","#9fc5e8","#b4a7d6","#d5a6bd"],
				["#e06666","#f6b26b","#ffd966","#93c47d","#76a5af","#6fa8dc","#8e7cc3","#c27ba0"],
				["#c00","#e69138","#f1c232","#6aa84f","#45818e","#3d85c6","#674ea7","#a64d79"],
				["#900","#b45f06","#bf9000","#38761d","#134f5c","#0b5394","#351c75","#741b47"],
				["#600","#783f04","#7f6000","#274e13","#0c343d","#073763","#20124d","#4c1130"]
    		    ]
		});	
		
		$('.coloredit').on('change', function(){ 
			var v = this.value ? this.value : "initial";		
			var target = '#s' + (this.title);
			$(target).css('color', v);
			isUnsaved();
		});
		
		$('.bgedit').on('change', function(){
			var v = this.value ? this.value : "initial";
			var target = '#s' + (this.title);
			$(target).css('background-color', v);
			isUnsaved();
		});		
		
		$('.blinkedit').on('change', function(){ 
			var target = '#s' + (this.title);
			var z = this.checked == true ? "blinker 1s linear infinite" : "none";
			$(target).css('animation', z);		
			isUnsaved();
		});		
		
		$('#loading').hide();	
		$('#message').text('Ready');
}

function saveColorTable() {

	$( "#loading" ).show();	
	window.location.href = "#top";
	$('#message').text('Saving...');
		
	var i = null;
	var c = null;
	var b = null;
	var blink = null;
	var css = [];
	css[0] = new Array (500,"placeholder","do-not-use",false); // hack shack :( avoids a NULL at [0] in the resulting json
	for (i = 1; i < 100; i++){			
		c = $('#' + (i) + 'color').val();
		b = $('#' + (i) + 'backg').val();
		blink = $('#' + (i) + 'blink').is(':checked') ? true : false;
		css[i] = new Array(i, c, b, blink);
	}
	
	var jsonOutput = JSON.stringify(css, undefined, 2);
	
 	save_tsv('config-tsvsave', jsonOutput, 'color-map.json'); 	
	$('#message').text('Colors saved. Ready.');
	setTimeout(function() { $( "#loading" ).hide(); }, 250);  	// a little delay for the UI's benefit.
	localStorage.ColorsTableUpdated == true;	
	isSaved();
}

function generateCSS() {
// 		console.log('generateCSS started...');
		if (localStorage.ColorsTableUpdated == false)
			return;
		colorFile = 'color-map.json';
	    $.ajax({
        url     : colorFile,
        type    : 'GET',
        success : applyCSS,
//        error   : function(XMLHttpRequest, textStatus, errorThrown) { alert('File Acces Error: \n\nFile:' + colorFile + '\n\n' + errorThrown + '\n\n'); } 
    	});

}
	
function applyCSS(d) {
	var sheet = (function() {
		var sheets = document.styleSheets,
		stylesheet = sheets[(sheets.length - 1)];

		for(var i in document.styleSheets ){
			if( sheets[i].title == 'tgcolors') { 	
			for (var y=0; y<sheets[i].cssRules.length; y++) {
				sheets[i].deleteRule (y);
			}
				return sheets[i];	// re-use the same inline style sheet
			}
		}
		var style = document.createElement("style");
		style.title = 'tgcolors';
		// WebKit hack :(
		style.appendChild(document.createTextNode(""));
		// Add the <style> element to the page
		document.head.appendChild(style);
		localStorage.ColorsTableUpdated == false;		
		return style.sheet;
		
	})();
		
	for (i in d) {
		if (d[i]) {
			w = ' .c' + d[i][0] + ' { ';
			x = 'color: ' + d[i][1] + '; ';
			y = 'background-color: ' + d[i][2] + '; ';
			z = 'animation: ' + (d[i][3] == true ? "blinker 1s linear infinite;" : "none;") + '} \n';
			sheet.insertRule(  (w + x + y + z)    );	
		}
	}

	setTimeout(enableSave, delay);
	$('#talkgroups').show(delay);
	$( "#loading" ).hide();	
}

function reloadCss() {  // not used right now
    var links = document.getElementsByTagName("link");
    for (var cl in links)
    {
        var link = links[cl];
        if (link.rel === "stylesheet")
            link.href += "";
    }
}
