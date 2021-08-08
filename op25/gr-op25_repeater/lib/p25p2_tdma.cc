// P25 TDMA Decoder (C) Copyright 2013, 2014 Max H. Parke KA1RBI
// Copyright 2017 Graham J. Norbury (modularization rewrite)
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

#include <stdint.h>
#include <map>
#include <string.h>
#include <string>
#include <iostream>
#include <assert.h>
#include <errno.h>
#include <sys/time.h>

#include "p25p2_duid.h"
#include "p25p2_sync.h"
#include "p25p2_tdma.h"
#include "p25p2_vf.h"
#include "mbelib.h"
#include "ambe.h"
#include "value_string.h"
#include "crc16.h"

static const int BURST_SIZE = 180;
static const int SUPERFRAME_SIZE = (12*BURST_SIZE);

static uint16_t crc12(const uint8_t bits[], unsigned int len) {
	uint16_t crc=0;
	static const unsigned int K = 12;
	static const uint8_t poly[K+1] = {1,1,0,0,0,1,0,0,1,0,1,1,1}; // p25 p2 crc 12 poly
	uint8_t buf[256];
	if (len+K > sizeof(buf)) {
		fprintf (stderr, "crc12: buffer length %u exceeds maximum %lu\n", len+K, sizeof(buf));
		return 0;
	}
	memset (buf, 0, sizeof(buf));
	for (int i=0; i<len; i++){
		buf[i] = bits[i];
	}
	for (int i=0; i<len; i++)
		if (buf[i])
			for (int j=0; j<K+1; j++)
				buf[i+j] ^= poly[j];
	for (int i=0; i<K; i++){
		crc = (crc << 1) + buf[len + i];
	}
	return crc ^ 0xfff;
}

static bool crc12_ok(const uint8_t bits[], unsigned int len) {
	uint16_t crc = 0;
	for (int i=0; i < 12; i++) {
		crc = (crc << 1) + bits[len+i];
	}
	return (crc == crc12(bits,len));
}

static const uint8_t mac_msg_len[256] = {
	 0,  7,  8,  7,  0, 16,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 
	 0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 
	 0, 14, 15,  0,  0, 15,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 
	 5,  7,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 
	 9,  7,  9,  0,  9,  8,  9,  0,  0,  0,  9,  0,  0,  0,  0,  0, 
	 0,  0,  0,  0,  9,  7,  0,  0,  0,  0,  7,  0,  0,  8, 14,  7, 
	 9,  9,  0,  0,  9,  0,  0,  9,  0,  0,  7,  0,  0,  7,  0,  0, 
	 0,  0,  0,  9,  9,  9,  0,  0,  9,  9,  9, 11,  9,  9,  0,  0, 
	 0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 
	 0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 
	 0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 
	 0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 
	11,  0,  0,  8, 15, 12, 15,  0,  0,  0,  0,  0,  0,  0,  0,  0, 
	 0,  0,  0,  0,  0,  0,  9,  0,  0,  0, 11,  0,  0,  0,  0, 11, 
	 0,  0,  0,  0,  0,  0,  0,  0,  0,  8, 11,  0,  0,  0,  0,  0, 
	 0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 11, 13, 11,  0,  0,  0 };

p25p2_tdma::p25p2_tdma(const op25_audio& udp, int slotid, int debug, bool do_msgq, gr::msg_queue::sptr queue, std::deque<int16_t> &qptr, bool do_audio_output, int msgq_id) :	// constructor
        op25audio(udp),
	write_bufp(0),
	tdma_xormask(new uint8_t[SUPERFRAME_SIZE]),
	symbols_received(0),
	packets(0),
	d_slotid(slotid),
	d_nac(0),
	d_do_msgq(do_msgq),
	d_msg_queue(queue),
	output_queue_decode(qptr),
	d_debug(debug),
	d_do_audio_output(do_audio_output),
        burst_id(-1),
        ESS_A(28,0),
        ESS_B(16,0),
        ess_algid(0x80),
        ess_keyid(0),
        d_msgq_id(msgq_id),
	p2framer()
{
	assert (slotid == 0 || slotid == 1);
	mbe_initMbeParms (&cur_mp, &prev_mp, &enh_mp);
}

bool p25p2_tdma::rx_sym(uint8_t sym)
{
	symbols_received++;
	return p2framer.rx_sym(sym);
}

void p25p2_tdma::set_slotid(int slotid)
{
	assert (slotid == 0 || slotid == 1);
	d_slotid = slotid;
}

p25p2_tdma::~p25p2_tdma()	// destructor
{
	delete[](tdma_xormask);
}

void
p25p2_tdma::set_xormask(const char*p) {
	for (int i=0; i<SUPERFRAME_SIZE; i++)
		tdma_xormask[i] = p[i] & 3;
}

int p25p2_tdma::process_mac_pdu(const uint8_t byte_buf[], const unsigned int len) 
{
	unsigned int opcode = (byte_buf[0] >> 5) & 0x7;
	unsigned int offset = (byte_buf[0] >> 2) & 0x7;

        if (d_debug >= 10) {
                fprintf(stderr, "%s process_mac_pdu: opcode %d len %d\n", logts.get(), opcode, len);
        }

        switch (opcode)
        {
                case 0: // MAC_SIGNAL
                        handle_mac_signal(byte_buf, len);
                        break;

                case 1: // MAC_PTT
                        handle_mac_ptt(byte_buf, len);
                        break;

                case 2: // MAC_END_PTT
                        handle_mac_end_ptt(byte_buf, len);
                        break;

                case 3: // MAC_IDLE
                        handle_mac_idle(byte_buf, len);
                        break;

                case 4: // MAC_ACTIVE
                        handle_mac_active(byte_buf, len);
                        break;

                case 6: // MAC_HANGTIME
                        handle_mac_hangtime(byte_buf, len);
                        op25audio.send_audio_flag(op25_audio::DRAIN);
                        break;
        }
	// maps sacch opcodes into phase I duid values 
	static const int opcode_map[8] = {3, 5, 15, 15, 5, 3, 3, 3};
	return opcode_map[opcode];
}

void p25p2_tdma::handle_mac_signal(const uint8_t byte_buf[], const unsigned int len) 
{
	char nac_color[2];
	int i;
        i = (byte_buf[19] << 4) + ((byte_buf[20] >> 4) & 0xf);
	nac_color[0] = i >> 8;
	nac_color[1] = i & 0xff;
	send_msg(std::string(nac_color, 2) + std::string((const char *)byte_buf, len), -6);
}

void p25p2_tdma::handle_mac_ptt(const uint8_t byte_buf[], const unsigned int len) 
{
        uint32_t srcaddr = (byte_buf[13] << 16) + (byte_buf[14] << 8) + byte_buf[15];
        uint16_t grpaddr = (byte_buf[16] << 8) + byte_buf[17];
        std::string s = "{\"srcaddr\" : " + std::to_string(srcaddr) + ", \"grpaddr\": " + std::to_string(grpaddr) + ", \"nac\" : " + std::to_string(d_nac) + "}";
        send_msg(s, -3);

        if (d_debug >= 10) {
                fprintf(stderr, "%s MAC_PTT: srcaddr=%u, grpaddr=%u", logts.get(), srcaddr, grpaddr);
        }
        for (int i = 0; i < 9; i++) {
                ess_mi[i] = byte_buf[i+1];
        }
        ess_algid = byte_buf[10];
        ess_keyid = (byte_buf[11] << 8) + byte_buf[12];
        if (d_debug >= 10) {
                fprintf(stderr, ", algid=%x, keyid=%x, mi=", ess_algid, ess_keyid);
                for (int i = 0; i < 9; i++) {
                        fprintf(stderr,"%02x ", ess_mi[i]);
                }
        }
	s = "{\"nac\" : " + std::to_string(d_nac) + ", \"algid\" : " + std::to_string(ess_algid) + ", \"alg\" : \"" + lookup(ess_algid, ALGIDS, ALGIDS_SZ) + "\", \"keyid\": " + std::to_string(ess_keyid) + "}";
	send_msg(s, -3);

        if (d_debug >= 10) {
                fprintf(stderr, "\n");
        }

        reset_vb();
}

void p25p2_tdma::handle_mac_end_ptt(const uint8_t byte_buf[], const unsigned int len) 
{
        uint16_t colorcd = ((byte_buf[1] & 0x0f) << 8) + byte_buf[2];
        uint32_t srcaddr = (byte_buf[13] << 16) + (byte_buf[14] << 8) + byte_buf[15];
        uint16_t grpaddr = (byte_buf[16] << 8) + byte_buf[17];

        if (d_debug >= 10)
                fprintf(stderr, "%s MAC_END_PTT: colorcd=0x%03x, srcaddr=%u, grpaddr=%u\n", logts.get(), colorcd, srcaddr, grpaddr);

        //std::string s = "{\"srcaddr\" : " + std::to_string(srcaddr) + ", \"grpaddr\": " + std::to_string(grpaddr) + "}";
        //send_msg(s, -3);	// can cause data display issues if this message is processed after the DUID15
        op25audio.send_audio_flag(op25_audio::DRAIN);
}

void p25p2_tdma::handle_mac_idle(const uint8_t byte_buf[], const unsigned int len) 
{
        if (d_debug >= 10)
                fprintf(stderr, "%s MAC_IDLE: ", logts.get());

        decode_mac_msg(byte_buf, len);
        op25audio.send_audio_flag(op25_audio::DRAIN);

        if (d_debug >= 10)
                fprintf(stderr, "\n");
}

void p25p2_tdma::handle_mac_active(const uint8_t byte_buf[], const unsigned int len) 
{
        if (d_debug >= 10)
                fprintf(stderr, "%s MAC_ACTIVE: ", logts.get());

        decode_mac_msg(byte_buf, len);

        if (d_debug >= 10)
                fprintf(stderr, "\n");
}

void p25p2_tdma::handle_mac_hangtime(const uint8_t byte_buf[], const unsigned int len) 
{
        if (d_debug >= 10)
                fprintf(stderr, "%s MAC_HANGTIME: ", logts.get());

        decode_mac_msg(byte_buf, len);
        op25audio.send_audio_flag(op25_audio::DRAIN);

        if (d_debug >= 10)
                fprintf(stderr, "\n");
}


void p25p2_tdma::decode_mac_msg(const uint8_t byte_buf[], const unsigned int len) 
{
	std::string s;
	uint8_t b1b2, cfva, mco, lra, rfss, site_id, ssc, svcopts[3], msg_ptr, msg_len;
        uint16_t chan[3], ch_t[2], ch_r[2], colorcd, grpaddr[3], sys_id;
        uint32_t srcaddr, wacn_id;

	for (msg_ptr = 1; msg_ptr < len; )
	{
               	b1b2 = byte_buf[msg_ptr] >> 6;
               	mco  = byte_buf[msg_ptr] & 0x3f;
		msg_len = mac_msg_len[(b1b2 << 6) + mco];
		if (d_debug >= 10)
               		fprintf(stderr, "mco=%01x/%02x", b1b2, mco);

		switch(byte_buf[msg_ptr])
                {
			case 0x00: // Null message
				break;
			case 0x40: // Group Voice Channel Grant Abbreviated
				svcopts[0] = (byte_buf[msg_ptr+1]     )                      ;
				chan[0]    = (byte_buf[msg_ptr+2] << 8) + byte_buf[msg_ptr+3];
				grpaddr[0] = (byte_buf[msg_ptr+4] << 8) + byte_buf[msg_ptr+5];
				srcaddr    = (byte_buf[msg_ptr+6] << 16) + (byte_buf[msg_ptr+7] << 8) + byte_buf[msg_ptr+8];
				if (d_debug >= 10)
					fprintf(stderr, ", svcopts=0x%02x, ch=%u, grpaddr=%u, srcaddr=%u", svcopts[0], chan[0], grpaddr[0], srcaddr);
				break;
			case 0xc0: // Group Voice Channel Grant Extended
				svcopts[0] = (byte_buf[msg_ptr+1]     )                      ;
				ch_t[0]    = (byte_buf[msg_ptr+2] << 8) + byte_buf[msg_ptr+3];
				ch_r[0]    = (byte_buf[msg_ptr+4] << 8) + byte_buf[msg_ptr+5];
				grpaddr[0] = (byte_buf[msg_ptr+6] << 8) + byte_buf[msg_ptr+7];
				srcaddr    = (byte_buf[msg_ptr+8] << 16) + (byte_buf[msg_ptr+9] << 8) + byte_buf[msg_ptr+10];
				if (d_debug >= 10)
					fprintf(stderr, ", svcopts=0x%02x, ch_t=%u, ch_t=%u, grpaddr=%u, srcaddr=%u", svcopts[0], ch_t[0], ch_r[0], grpaddr[0], srcaddr);
				break;
                        case 0x01: // Group Voice Channel User Message Abbreviated
                                grpaddr[0] = (byte_buf[msg_ptr+2] << 8) + byte_buf[msg_ptr+3];
                                srcaddr    = (byte_buf[msg_ptr+4] << 16) + (byte_buf[msg_ptr+5] << 8) + byte_buf[msg_ptr+6];
                                if (d_debug >= 10)
                              	        fprintf(stderr, ", grpaddr=%u, srcaddr=%u", grpaddr[0], srcaddr);
                                s = "{\"srcaddr\" : " + std::to_string(srcaddr) + ", \"grpaddr\": " + std::to_string(grpaddr[0]) + ", \"nac\" : " + std::to_string(d_nac) + "}";
				send_msg(s, -3);
                                break;
			case 0x42: // Group Voice Channel Grant Update
				chan[0]    = (byte_buf[msg_ptr+1] << 8) + byte_buf[msg_ptr+2];
				grpaddr[0] = (byte_buf[msg_ptr+3] << 8) + byte_buf[msg_ptr+4];
				chan[1]    = (byte_buf[msg_ptr+5] << 8) + byte_buf[msg_ptr+6];
				grpaddr[1] = (byte_buf[msg_ptr+7] << 8) + byte_buf[msg_ptr+8];
				if (d_debug >= 10)
					fprintf(stderr, ", ch_1=%u, grpaddr1=%u, ch_2=%u, grpaddr2=%u", chan[0], grpaddr[0], chan[1], grpaddr[1]);
				break;
			case 0xc3: // Group Voice Channel Grant Update Explicit
				svcopts[0] = (byte_buf[msg_ptr+1]     )                      ;
				ch_t[0]    = (byte_buf[msg_ptr+2] << 8) + byte_buf[msg_ptr+3];
				ch_r[0]    = (byte_buf[msg_ptr+4] << 8) + byte_buf[msg_ptr+5];
				grpaddr[0] = (byte_buf[msg_ptr+6] << 8) + byte_buf[msg_ptr+7];
				if (d_debug >= 10)
					fprintf(stderr, ", svcopts=0x%02x, ch_t=%u, ch_r=%u, grpaddr=%u", svcopts[0], ch_t[0], ch_r[0], grpaddr[0]);
				break;
			case 0x05: // Group Voice Channel Grant Update Multiple
				svcopts[0] = (byte_buf[msg_ptr+ 1]     )                       ;
				chan[0]    = (byte_buf[msg_ptr+ 2] << 8) + byte_buf[msg_ptr+ 3];
				grpaddr[0] = (byte_buf[msg_ptr+ 4] << 8) + byte_buf[msg_ptr+ 5];
				svcopts[1] = (byte_buf[msg_ptr+ 6]     )                       ;
				chan[1]    = (byte_buf[msg_ptr+ 7] << 8) + byte_buf[msg_ptr+ 8];
				grpaddr[1] = (byte_buf[msg_ptr+ 9] << 8) + byte_buf[msg_ptr+10];
				svcopts[2] = (byte_buf[msg_ptr+11]     )                       ;
				chan[2]    = (byte_buf[msg_ptr+12] << 8) + byte_buf[msg_ptr+13];
				grpaddr[2] = (byte_buf[msg_ptr+14] << 8) + byte_buf[msg_ptr+15];
				if (d_debug >= 10)
					fprintf(stderr, ", svcopt1=0x%02x, ch_1=%u, grpaddr1=%u, svcopt2=0x%02x, ch_2=%u, grpaddr2=%u, svcopt3=0x%02x, ch_3=%u, grpaddr3=%u", svcopts[0], chan[0], grpaddr[0], svcopts[1], chan[1], grpaddr[1], svcopts[2], chan[2], grpaddr[2]);
				break;
			case 0x25: // Group Voice Channel Grant Update Multiple Explicit
				svcopts[0] = (byte_buf[msg_ptr+ 1]     )                       ;
				ch_t[0]    = (byte_buf[msg_ptr+ 2] << 8) + byte_buf[msg_ptr+ 3];
				ch_r[0]    = (byte_buf[msg_ptr+ 4] << 8) + byte_buf[msg_ptr+ 5];
				grpaddr[0] = (byte_buf[msg_ptr+ 6] << 8) + byte_buf[msg_ptr+ 7];
				svcopts[1] = (byte_buf[msg_ptr+ 8]     )                       ;
				ch_t[1]    = (byte_buf[msg_ptr+ 9] << 8) + byte_buf[msg_ptr+10];
				ch_r[1]    = (byte_buf[msg_ptr+11] << 8) + byte_buf[msg_ptr+12];
				grpaddr[1] = (byte_buf[msg_ptr+13] << 8) + byte_buf[msg_ptr+14];
				if (d_debug >= 10)
					fprintf(stderr, ", svcopt1=0x%02x, ch_t1=%u, ch_r1=%u, grpaddr1=%u, svcopt2=0x%02x, ch_t2=%u, ch_r2=%u, grpaddr2=%u", svcopts[0], ch_t[0], ch_r[0], grpaddr[0], svcopts[1], ch_t[1], ch_r[1], grpaddr[1]);
				break;
			case 0x7b: // Network Status Broadcast Abbreviated
				lra     =   byte_buf[msg_ptr+1];
				wacn_id =  (byte_buf[msg_ptr+2] << 12) + (byte_buf[msg_ptr+3] << 4) + (byte_buf[msg_ptr+4] >> 4);
				sys_id  = ((byte_buf[msg_ptr+4] & 0x0f) << 8) + byte_buf[msg_ptr+5];
				chan[0] =  (byte_buf[msg_ptr+6] << 8) + byte_buf[msg_ptr+7];
				ssc     =   byte_buf[msg_ptr+8];
				colorcd = ((byte_buf[msg_ptr+9] & 0x0f) << 8) + byte_buf[msg_ptr+10];
				if (d_debug >= 10)
					fprintf(stderr, ", lra=0x%02x, wacn_id=0x%05x, sys_id=0x%03x, ch=%u, ssc=0x%02x, colorcd=%03x", lra, wacn_id, sys_id, chan[0], ssc, colorcd);
				break;
			case 0x7c: // Adjacent Status Broadcast Abbreviated
				lra     =   byte_buf[msg_ptr+1];
				cfva    =  (byte_buf[msg_ptr+2] >> 4);
				sys_id  = ((byte_buf[msg_ptr+2] & 0x0f) << 8) + byte_buf[msg_ptr+3];
				rfss    =   byte_buf[msg_ptr+4];
				site_id =   byte_buf[msg_ptr+5];
				chan[0] =  (byte_buf[msg_ptr+6] << 8) + byte_buf[msg_ptr+7];
				ssc     =   byte_buf[msg_ptr+8];
				if (d_debug >= 10)
					fprintf(stderr, ", lra=0x%02x, cfva=0x%01x, sys_id=0x%03x, rfss=%u, site=%u, ch=%u, ssc=0x%02x", lra, cfva, sys_id, rfss, site_id, chan[0], ssc);
				break;
			case 0xfc: // Adjacent Status Broadcast Extended
				break;
			case 0xfb: // Network Status Broadcast Extended
				colorcd = ((byte_buf[msg_ptr+11] & 0x0f) << 8) + byte_buf[msg_ptr+12];
				if (d_debug >= 10)
					fprintf(stderr, ", colorcd=%03x", colorcd);
				break;
               	}
		msg_ptr = (msg_len == 0) ? len : (msg_ptr + msg_len); // TODO: handle variable length messages
		if ((d_debug >= 10) && (msg_ptr < len))
			fprintf(stderr,", ");
	}
}

int p25p2_tdma::handle_acch_frame(const uint8_t dibits[], bool fast, bool is_lcch) 
{
	int i, j, rc;
	uint8_t bits[512];
	std::vector<uint8_t> HB(63,0);
	std::vector<int> Erasures;
	uint8_t byte_buf[32];
	unsigned int bufl=0;
	unsigned int len=0;
	if (fast) {
		for (i=11; i < 11+36; i++) {
			bits[bufl++] = (dibits[i] >> 1) & 1;
			bits[bufl++] = dibits[i] & 1;
		}
		for (i=48; i < 48+31; i++) {
			bits[bufl++] = (dibits[i] >> 1) & 1;
			bits[bufl++] = dibits[i] & 1;
		}
		for (i=100; i < 100+32; i++) {
			bits[bufl++] = (dibits[i] >> 1) & 1;
			bits[bufl++] = dibits[i] & 1;
		}
		for (i=133; i < 133+36; i++) {
			bits[bufl++] = (dibits[i] >> 1) & 1;
			bits[bufl++] = dibits[i] & 1;
		}
	} else {
		for (i=11; i < 11+36; i++) {
			bits[bufl++] = (dibits[i] >> 1) & 1;
			bits[bufl++] = dibits[i] & 1;
		}
		for (i=48; i < 48+84; i++) {
			bits[bufl++] = (dibits[i] >> 1) & 1;
			bits[bufl++] = dibits[i] & 1;
		}
		for (i=133; i < 133+36; i++) {
			bits[bufl++] = (dibits[i] >> 1) & 1;
			bits[bufl++] = dibits[i] & 1;
		}
	}

	// Reed-Solomon
	if (fast) {
		j = 9;
		len = 270;
		Erasures = {0,1,2,3,4,5,6,7,8,54,55,56,57,58,59,60,61,62};
	}
	else {
		j = 5;
		len = 312;
		Erasures = {0,1,2,3,4,57,58,59,60,61,62};
	}

	for (i = 0; i < len; i += 6) { // convert bits to hexbits
		HB[j] = (bits[i] << 5) + (bits[i+1] << 4) + (bits[i+2] << 3) + (bits[i+3] << 2) + (bits[i+4] << 1) + bits[i+5];
		j++;
	}
	rc = rs28.decode(HB, Erasures);
//	if (d_debug >= 10)
//		fprintf(stderr, "p25p2_tdma: rc28: rc %d\n", rc);
	if (rc < 0)
		return -1;

	if (fast) {
		j = 9;
		len = 144;
	}
	else {
		j = 5;
		len = (is_lcch) ? 180 : 168;
	}
	for (i = 0; i < len; i += 6) { // convert hexbits back to bits
		bits[i]   = (HB[j] & 0x20) >> 5;
		bits[i+1] = (HB[j] & 0x10) >> 4;
		bits[i+2] = (HB[j] & 0x08) >> 3;
		bits[i+3] = (HB[j] & 0x04) >> 2;
		bits[i+4] = (HB[j] & 0x02) >> 1;
		bits[i+5] = (HB[j] & 0x01);
		j++;
	}

	bool crc_ok = (is_lcch) ? (crc16(bits, len) == 0) : crc12_ok(bits, len);
	int olen = (is_lcch) ? 23 : len/8;
	rc = -1;
	if (crc_ok) { // TODO: rewrite crc12 so we don't have to do so much bit manipulation
		// fprintf(stderr, "crc12 ok\n");
		for (int i=0; i<olen; i++) {
			byte_buf[i] = (bits[i*8 + 0] << 7) + (bits[i*8 + 1] << 6) + (bits[i*8 + 2] << 5) + (bits[i*8 + 3] << 4) + (bits[i*8 + 4] << 3) + (bits[i*8 + 5] << 2) + (bits[i*8 + 6] << 1) + (bits[i*8 + 7] << 0);
		}
		rc = process_mac_pdu(byte_buf, olen);
	} else {
		// fprintf(stderr, "crc12 failed\n");
	}
	return rc;
}

void p25p2_tdma::handle_voice_frame(const uint8_t dibits[]) 
{
	static const int NSAMP_OUTPUT=160;
	int b[9];
	int16_t snd;
	int K;
	int rc = -1;

	vf.process_vcw(dibits, b);
	if (b[0] < 120) // anything above 120 is an erasure or special frame
		rc = mbe_dequantizeAmbe2250Parms (&cur_mp, &prev_mp, b);
	/* FIXME: check RC */
	K = 12;
	if (cur_mp.L <= 36)
		K = int(float(cur_mp.L + 2.0) / 3.0);
	if (rc == 0)
		software_decoder.decode_tap(cur_mp.L, K, cur_mp.w0, &cur_mp.Vl[1], &cur_mp.Ml[1]);
	audio_samples *samples = software_decoder.audio();
	write_bufp = 0;
	for (int i=0; i < NSAMP_OUTPUT; i++) {
		if (samples->size() > 0) {
			snd = (int16_t)(samples->front());
			samples->pop_front();
		} else {
			snd = 0;
		}
		write_buf[write_bufp++] = snd & 0xFF ;
		write_buf[write_bufp++] = snd >> 8;
	}
	if (d_do_audio_output && (write_bufp >= 0)) { 
		op25audio.send_audio(write_buf, write_bufp);
		write_bufp = 0;
	}

	mbe_moveMbeParms (&cur_mp, &prev_mp);
	mbe_moveMbeParms (&cur_mp, &enh_mp);
}

int p25p2_tdma::handle_frame(void)
{
	uint8_t dibits[180];
	int rc;
	for (int i=0; i<sizeof(dibits); i++)
		dibits[i] = p2framer.d_frame_body[i*2+1] + (p2framer.d_frame_body[i*2] << 1);
	rc = handle_packet(dibits);
	return rc;
}

/* returns true if in sync and slot matches current active slot d_slotid */
int p25p2_tdma::handle_packet(const uint8_t dibits[]) 
{
	int rc = -1;
	static const int which_slot[] = {0,1,0,1,0,1,0,1,0,1,1,0};
	packets++;
	sync.check_confidence(dibits);
	if (!sync.in_sync())
		return -1;
	const uint8_t* burstp = &dibits[10];
	uint8_t xored_burst[BURST_SIZE - 10];
	int burst_type = duid.duid_lookup(duid.extract_duid(burstp));
	if (which_slot[sync.tdma_slotid()] != d_slotid && burst_type != 13) // ignore if on oppo. slot and not CC
		return -1;
	for (int i=0; i<BURST_SIZE - 10; i++) {
		xored_burst[i] = burstp[i] ^ tdma_xormask[sync.tdma_slotid() * BURST_SIZE + i];
	}
        if (d_debug >= 10) {
		fprintf(stderr, "%s TDMA burst type=%d\n", logts.get(), burst_type);
	}
	if (burst_type == 0 || burst_type == 6)	{       // 4V or 2V burst
                track_vb(burst_type);
                handle_4V2V_ess(&xored_burst[84]);
                if ( !encrypted() ) {
                        handle_voice_frame(&xored_burst[11]);
                        handle_voice_frame(&xored_burst[48]);
                        if (burst_type == 0) {
                                handle_voice_frame(&xored_burst[96]);
                                handle_voice_frame(&xored_burst[133]);
                        }
                }
		return -1;
	} else if (burst_type == 3) {                   // scrambled sacch
		rc = handle_acch_frame(xored_burst, 0, false);
	} else if (burst_type == 9) {                   // scrambled facch
		rc = handle_acch_frame(xored_burst, 1, false);
	} else if (burst_type == 12) {                  // unscrambled sacch
		rc = handle_acch_frame(burstp, 0, false);
	} else if (burst_type == 13) {                  // TDMA CC OECI
		rc = handle_acch_frame(burstp, 0, true);
	} else if (burst_type == 15) {                  // unscrambled facch
		rc = handle_acch_frame(burstp, 1, false);
	} else {
		// unsupported type duid
		return -1;
	}
	return rc;
}

void p25p2_tdma::handle_4V2V_ess(const uint8_t dibits[])
{
	std::string s = "";
        if (d_debug >= 10) {
		fprintf(stderr, "%s %s_BURST ", logts.get(), (burst_id < 4) ? "4V" : "2V");
	}

        if (burst_id < 4) {
                for (int i=0; i < 12; i += 3) { // ESS-B is 4 hexbits / 12 dibits
                        ESS_B[(4 * burst_id) + (i / 3)] = (uint8_t) ((dibits[i] << 4) + (dibits[i+1] << 2) + dibits[i+2]);
                }
        }
        else {
                int i, j, k, ec;

                j = 0;
                for (i = 0; i < 28; i++) { // ESS-A is 28 hexbits / 84 dibits
                        ESS_A[i] = (uint8_t) ((dibits[j] << 4) + (dibits[j+1] << 2) + dibits[j+2]);
                        j = (i == 15) ? (j + 4) : (j + 3);  // skip dibit containing DUID#3
                }

                ec = rs28.decode(ESS_B, ESS_A);

                if (ec >= 0) { // save info if good decode
                        ess_algid = (ESS_B[0] << 2) + (ESS_B[1] >> 4);
                        ess_keyid = ((ESS_B[1] & 15) << 12) + (ESS_B[2] << 6) + ESS_B[3]; 

                        j = 0;
                        for (i = 0; i < 9;) {
                                 ess_mi[i++] = (uint8_t)  (ESS_B[j+4]         << 2) + (ESS_B[j+5] >> 4);
                                 ess_mi[i++] = (uint8_t) ((ESS_B[j+5] & 0x0f) << 4) + (ESS_B[j+6] >> 2);
                                 ess_mi[i++] = (uint8_t) ((ESS_B[j+6] & 0x03) << 6) +  ESS_B[j+7];
                                 j += 4;
                        }
			s = "{\"nac\" : " + std::to_string(d_nac) + ", \"algid\" : " + std::to_string(ess_algid) + ", \"alg\" : \"" + lookup(ess_algid, ALGIDS, ALGIDS_SZ) + "\", \"keyid\": " + std::to_string(ess_keyid) + "}";
			send_msg(s, -3);
                }
        }     

        if (d_debug >= 10) {
                fprintf(stderr, "ESS: algid=%x, keyid=%x, mi=", ess_algid, ess_keyid);        
                for (int i = 0; i < 9; i++) {
                        fprintf(stderr,"%02x ", ess_mi[i]);
                }
		fprintf(stderr, "\n");
        }
}

void p25p2_tdma::send_msg(const std::string msg_str, long msg_type)
{
        unsigned char hdr[4] = {0xaa, 0x55, (unsigned char)((d_msgq_id >> 8) & 0xff), (unsigned char)(d_msgq_id & 0xff)};
	if (!d_do_msgq || d_msg_queue->full_p())
		return;

	gr::message::sptr msg = gr::message::make_from_string(std::string((char*)hdr, 4) + msg_str, msg_type, 0, 0);
	d_msg_queue->insert_tail(msg);
}
