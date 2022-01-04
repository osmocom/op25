// P25 TDMA Decoder (C) Copyright 2013, 2014, 2021 Max H. Parke KA1RBI
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
static const int which_slot[] = {0,1,0,1,0,1,0,1,0,1,1,0};

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
	memset(tdma_xormask, 0, SUPERFRAME_SIZE);
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
	memset(tdma_xormask, 0, SUPERFRAME_SIZE);
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
	bool my_slot = (which_slot[sync.tdma_slotid()] == d_slotid);

        if (d_debug >= 10) {
                fprintf(stderr, "%s process_mac_pdu: opcode %d len %d buf %02x %02x %02x\n", logts.get(), opcode, len, byte_buf[0], byte_buf[1], byte_buf[2]);
        }

        if (opcode == 2) {		// MAC_END_PTT
                uint16_t colorcd = ((byte_buf[1] & 0x0f) << 8) + byte_buf[2];
                if (colorcd != d_nac && d_debug > 0)
                        fprintf(stderr, "p25p2_tdma_ process_mac_pdu: MAC_END_PTT color code 0x%x does not match d_nac 0x%x channel %d\n", colorcd, d_nac, d_msgq_id);
	}

        if (opcode == 3 || opcode == 4 || opcode == 6) {	// send msg for MAC_IDLE, MAC_ACTIVE, MAC_HANGTIME
                char nac_color[2];
                nac_color[0] = d_nac >> 8;
                nac_color[1] = d_nac & 0xff;
                send_msg(std::string(nac_color, 2) + std::string((const char *)byte_buf, len), -6);
        }

        if (opcode != 0 && !my_slot)		// for all except MAC_SIGNAL, ignore if on oppo. slot
                return -1;

        switch (opcode)
        {
                case 0: // MAC_SIGNAL
                        handle_mac_signal(byte_buf, len);
                        return -1;
                        break;

                case 1: // MAC_PTT
                        handle_mac_ptt(byte_buf, len);
                        break;

                case 2: // MAC_END_PTT
                        handle_mac_end_ptt(byte_buf, len);
                        break;

                case 3: // MAC_IDLE
                        op25audio.send_audio_flag(op25_audio::DRAIN);
                        break;

                case 4: // MAC_ACTIVE
                        break;

                case 6: // MAC_HANGTIME
                        op25audio.send_audio_flag(op25_audio::DRAIN);
                        break;
                default:
                        if (d_debug > 0)
                                fprintf(stderr, "p25p2_tdma_ process_mac_pdu: unrecognized opcode 0x%x channel %d\n", opcode, d_msgq_id);
                        break;
        }
	// maps sacch opcodes into phase I duid values 
	static const int opcode_map[8] = {7, 5, 15, 15, 5, 3, 3, 3};
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
	if (d_debug >= 1)
		fprintf(stderr, "p25p2_tdma: crc%d result: %s, length %d\n", (is_lcch) ? 16 : 12, (crc_ok) ? "ok" : "failed", olen);
	rc = -1;
	if (crc_ok) { // TODO: rewrite crc12 so we don't have to do so much bit manipulation
		for (int i=0; i<olen; i++) {
			byte_buf[i] = (bits[i*8 + 0] << 7) + (bits[i*8 + 1] << 6) + (bits[i*8 + 2] << 5) + (bits[i*8 + 3] << 4) + (bits[i*8 + 4] << 3) + (bits[i*8 + 5] << 2) + (bits[i*8 + 6] << 1) + (bits[i*8 + 7] << 0);
		}
		rc = process_mac_pdu(byte_buf, olen);
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
	packets++;
	sync.check_confidence(dibits);
	if (!sync.in_sync())
		return -1;
	const uint8_t* burstp = &dibits[10];
	uint8_t xored_burst[BURST_SIZE - 10];
	bool my_slot = (which_slot[sync.tdma_slotid()] == d_slotid);
	int burst_type = duid.duid_lookup(duid.extract_duid(burstp));
	for (int i=0; i<BURST_SIZE - 10; i++) {
		xored_burst[i] = burstp[i] ^ tdma_xormask[sync.tdma_slotid() * BURST_SIZE + i];
	}
        if (d_debug >= 10) {
		fprintf(stderr, "%s TDMA burst type=%d\n", logts.get(), burst_type);
	}
	if (burst_type == 0 || burst_type == 6)	{       // 4V or 2V burst
		if (!my_slot) // ignore if on oppo. slot
			return -1;
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
