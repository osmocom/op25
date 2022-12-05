
% P25 H-CPM Demodulator (C) Copyright 2022 Max H. Parke KA1RBI
% % Experimental H-CPM Demodulator - Release 0 %
% 
% This file is part of OP25
% 
% OP25 is free software; you can redistribute it and/or modify it
% under the terms of the GNU General Public License as published by
% the Free Software Foundation; either version 3, or (at your option)
% any later version.
% 
% OP25 is distributed in the hope that it will be useful, but WITHOUT
% ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
% or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
% License for more details.
% 
% You should have received a copy of the GNU General Public License
% along with OP25; see the file COPYING. If not, write to the Free
% Software Foundation, Inc., 51 Franklin Street, Boston, MA
% 02110-1301, USA.
%
%
%
% Accepts input IF file in GR binary complex64 format;
% file must be at sample rate 24,000 samples/sec.
%
% this implementation has several simplifications, shortcuts,
% and pitfalls, some of which are:
%
% * input sample must be clean and error free, there is 
%   currently no tree search (viterbi) stage - decode errors
%   that should be recoverable are not autocorrected 
% * since the first and last one-quarter of the partial-response
%   period (in L=4) appear to contribute a negligible delta-phase,
%   this correlator ignores these intervals, using only the inner-
%   most two periods - accordingly, the value L=2 is assumed
% * the code is too slow to demod in real time and there are no claims
%   to efficiency
% * at each symbol period the received waveform vector is derotated.
%   this reduces the number of rows in the waveform matrix by a factor of
%   six (6); instead of derotating the samples, a correct correlator would
%   include these (approx. 80) additional rows
%

pkg load signal;

global WI0 = [
	1.000000, 0.999827, 0.998111, 0.963512, 0.819784, 0.500000,
	1.000000, 0.958473, 0.800512, 0.483695, 0.022053, -0.475169,
	1.000000, 0.978152, 0.913558, 0.808999, 0.669116, 0.500000,
	1.000000, 0.966921, 0.819689, 0.504702, 0.047650, -0.424375,
	1.000000, 0.984174, 0.926374, 0.822966, 0.687929, 0.548428,
	1.000000, 0.918644, 0.736098, 0.572238, 0.506066, 0.548428,
	1.000000, 0.995165, 0.986853, 0.986153, 0.994884, 0.999596,
	1.000000, 0.947207, 0.867963, 0.865831, 0.946296, 0.999596,
	1.000000, 0.869202, 0.540278, 0.146957, -0.204506, -0.475169,
	1.000000, 0.884236, 0.567518, 0.170815, -0.179370, -0.424375,
	1.000000, 0.827032, 0.340050, -0.286034, -0.793734, -0.998382,
	1.000000, 0.905842, 0.713560, 0.552256, 0.483811, 0.500000,
	1.000000, 0.936720, 0.851252, 0.853489, 0.937706, 0.999596,
	1.000000, 0.998757, 0.999587, 0.969698, 0.834181, 0.548428,
	1.000000, 0.844204, 0.370632, -0.262797, -0.777895, -0.993535,
	1.000000, 0.991608, 0.981038, 0.981858, 0.991970, 0.999596,
	 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
	 0.99179     0.98062998  0.95472002  0.92157     0.89235997  0.87256002];

global WQ0 = [
	0.000000, -0.018594, 0.061430, 0.267665, 0.572673, 0.866026,
	0.000000, 0.285183, 0.599317, 0.875237, 0.999757, 0.879895,
	0.000000, 0.207893, 0.406709, 0.587810, 0.743158, 0.866026,
	0.000000, -0.255075, -0.572808, -0.863294, -0.998864, -0.905486,
	0.000000, -0.177207, -0.376605, -0.568091, -0.725778, -0.836198,
	0.000000, -0.395087, -0.676875, -0.820088, -0.862495, -0.836198,
	0.000000, -0.098212, -0.161618, -0.165838, -0.101028, 0.028438,
	0.000000, -0.320622, -0.496628, -0.500337, -0.323300, 0.028438,
	0.000000, 0.494458, 0.841486, 0.989143, 0.978865, 0.879895,
	0.000000, -0.467040, -0.823361, -0.985303, -0.983782, -0.905486,
	0.000000, 0.562154, 0.940407, 0.958220, 0.608265, 0.056855,
	0.000000, 0.423616, 0.700594, 0.833674, 0.875173, 0.866025,
	0.000000, 0.350080, 0.524757, 0.521112, 0.347429, 0.028438,
	0.000000, 0.049845, -0.028745, -0.244306, -0.551491, -0.836198,
	0.000000, -0.536021, -0.928780, -0.964851, -0.628394, -0.113525,
	0.000000, 0.129280, 0.193816, 0.189618, 0.126474, 0.028438,
	0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
	 0.          0.13601001  0.26787999  0.37345001  0.44356     0.48087999];

global S_A = zeros(18,"int");
global S_B = zeros(18,"int");
S_A(1) = -1;
S_B(1) = 3;
S_A(2) = 1;
S_B(2) = 3;
S_A(3) = 1;
S_B(3) = 1;
S_A(4) = -1;
S_B(4) = -3;
S_A(5) = -1;
S_B(5) = -1;
S_A(6) = -3;
S_B(6) = 1;
S_A(7) = -1;
S_B(7) = 1;
S_A(8) = -3;
S_B(8) = 3;
S_A(9) = 3;
S_B(9) = 1;
S_A(10) = -3;
S_B(10) = -1;
S_A(11) = 3;
S_B(11) = 3;
S_A(12) = 3;
S_B(12) = -1;
S_A(13) = 3;
S_B(13) = -3;
S_A(14) = 1;
S_B(14) = -3;
S_A(15) = -3;
S_B(15) = -3;
S_A(16) = 1;
S_B(16) = -1;
S_A(17) = 0;
S_B(17) = 0;
S_A(18) = 1;
S_B(18) = 1;

global L = 4;	%sps
global M = 10 	% interp factor
global LM = L*M;
global Q = 8;	% decim amount
global NEWSPS = 5;	% after decimation
global K=360.0 / (2 * pi);	% radians -> degrees
global k = 6.0 / (2 * pi);

% change name of input data file
fname = 'if-24000-IQ.dat';

function samples = load_text(fname)
	fid = fopen(fname, 'r');
	nn = 0;
	while 1
		nn = nn+1;
		s = fgetl(fid);
		if s == -1
			break;
		endif
		res = sscanf(s, "%f\t%f");
		samples(nn) = res(1) + 1j*res(2);
	endwhile
	g = max(abs(samples));
	samples = samples / g;
endfunction

function amt_left = process_dat(dat)
	global L
	iq = dat(1:2:end-1) .+ 1j * dat(2:2:end);
	a = abs(iq);
	thresh = max(a) / 2.0;
	msk = a > thresh;
	m1 = msk(2:end) - msk(1:end-1);
	f = find(m1);
	m1f = m1(f)(end);
	lens = f(2:end) - f(1:end-1);
	l1 = (lens/L > 170 & lens/L < 180) | (lens/L > 350 & lens/L < 360);
	l2 = m1(f) == 1;
	l2 = l2(1:end-1);
	found = find(l1 & l2);
	if(length(found)) < 1
		amt_left = 0;
		return;
	endif
	for n = 1:length(found)
		valid = found(n);
		start1 = f(valid);
		len1 = lens(valid);
		demod_frag(iq(start1:start1+len1));
	end
	validn = found(end);
	startn = f(validn);
	lenn = lens(validn);
	datlen=length(dat);
	amt_left = length(dat) - (startn + lenn);
	if (amt_left < 0)
		amt_left = 0;
	endif
endfunction

function process_file(filename)
	global L
	bufsize = L * 180 * 12;
	fid = fopen(filename, 'r');
	save = [];
	while 1
		[dat, l] = fread(fid, bufsize, 'float32', 0);
		if l < 1
			break
		endif
		savel=size(save);
		datl=size(dat);
		concat = [save.' dat.'].';
		amt_left = process_dat(concat);
		if (amt_left > 0)
			save = concat(end-amt_left:end);
		else
			save = [];
		endif
	endwhile
endfunction

function large_frag(msg)
	msgl = length(msg);
	padsz = 360 - msgl;
	lenh = round(length(msg) / 2);
	fmsg1 = frame_msg(msg(1:lenh),1);
	decode_msg(fmsg1);
	fmsg2 = frame_msg(msg(lenh:end),2);
	decode_msg(fmsg2);
endfunction

function msg=demod_frag(frag)
	global L
	global NEWSPS
	global M
	amt_trim = mod(length(frag), L);
	frag = frag(1:end-amt_trim);
	g = max(abs(frag));
	frag = frag / g;
	nsyms = length(frag) / L;
	intrp0 = interp(frag, M);
	resampq=timing_sync(intrp0);
	nsyms = length(resampq) / NEWSPS;
	resamp1=frequency_sync(resampq);
	msg=correlation(resamp1);
	if length(msg) > 270
		large_frag(msg);
	else
		fmsg=frame_msg(msg,1);
		decode_msg(fmsg);
		lfmsg=length(fmsg);
	endif
endfunction

function decode_msg(msg)
	if length(msg) != 160
		return
	endif
	DMAP = [3 2 0 1];
	duid = msg([37,74,123,160]) + 3;
	duid = (duid / 2) + 1;
	dibits = DMAP(duid);
	duidx = dibits(1) * 64 + dibits(2) * 16 + dibits(3) * 4 + dibits(4);
	printf ('hex %x\n' , duidx);
endfunction

function resampq=timing_sync(intrp0)
	global LM
	global NEWSPS
	global Q
	nsyms = length(intrp0) / LM;
	fmd = angle(intrp0(2:end) .* conj(intrp0(1:end-1)));
	fmx = mod(LM*6* ([fmd' 0] / (2*pi) + 0.5) + 0.5, 1);
	matx= reshape(fmx, LM, nsyms );
	res = std(matx');
	[m, amin] = min(res);
	amin = amin + 0 + (LM/2);
	if amin > LM
		amin = amin - LM;
	endif
	resampq = intrp0(amin:Q:end);	# decim by Q
	amt_trim = mod(length(resampq), NEWSPS);
	resampq = resampq(1:end-amt_trim);
endfunction

function resamp1=frequency_sync(resampq)
	global NEWSPS
	global k
	F = 0;
	sz1 = length(resampq);
	for iter = 1:4
		osc = [0:sz1-1] * (F / 30000);
		osc = exp(j*2*pi*osc);
		resamp1 = resampq .* osc.';
		row = resamp1(1:NEWSPS:end);
		rowz = mod(k*angle(row)+0.5, 1);
		rowz = unwrap((rowz-0.5) * 2*pi);
		meanr = mean(rowz(5:15)) - mean(rowz(end-15:end-5));
		F = F + meanr;
	end
	nsyms = length(resamp1) / NEWSPS;
	rfm = angle(resamp1(2:end) .* conj(resamp1(1:end-1)));
	afm = angle(resamp1);
endfunction

function eye_plot(dat, sps)
	hold on
	for nn = 1:sps:length(dat)-sps*2
		sl = dat(nn:nn+sps);
		plot(sl);
	end
	hold off
	pause
endfunction

function msg=correlation(resamp1)
	global NEWSPS
	global WI0
	global WQ0
	global S_A
	global S_B
	global K
	nsyms = length(resamp1) / NEWSPS;
	for n= 1 : NEWSPS : length(resamp1) - NEWSPS
		stepn=(n-1)/NEWSPS;
		idx = ((n-1) / NEWSPS) + 1;
		sl=resamp1(n:n+NEWSPS);
		sl = sl * conj(sl(1));
		sl_i = real(sl);
		sl_q = imag(sl);
		corr2 = sl_i' * WI0' + sl_q' * WQ0';
		[m,am] = max(corr2);
		msga(idx) = S_A(am);
		msgb(idx) = S_B(am);
	end
	msgok=msga(2:end) == msgb(1:end-1);
	ok=sum(msgok) / length(msga);
	msg=msgb;
endfunction

function msg=frame_msg(imsg, fcode)
	if (fcode == 1)
		pilots = [1 -1 -1 1];
	else
		pilots = [-3 -3 -1 1];
	endif
	fml = length(imsg);
	msg = [];
	excess=length(imsg) - 160;
	for n=1:excess
		if n+163 > length(imsg)
			break
		endif
		slx = [imsg(n:n+1), imsg(n+162:n+163)];
		if sum(slx == pilots) == 4
			msg = imsg(n+2:n+161);
			return;
		endif
	end
	return;
endfunction

process_file(fname);
