// P25 Decoder (C) Copyright 2013, 2014, 2015, 2016, 2017 Max H. Parke KA1RBI
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

#ifndef INCLUDED_RX_SYNC_H
#define INCLUDED_RX_SYNC_H

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <string>
#include <iostream>
#include <deque>
#include <assert.h>
#include <gnuradio/msg_queue.h>

#include "bit_utils.h"
#include "check_frame_sync.h"

#include "p25p2_vf.h"
#include "mbelib.h"
#include "ambe.h"

#include "ysf_const.h"
#include "dmr_const.h"
#include "p25_frame.h"
#include "op25_imbe_frame.h"
#include "software_imbe_decoder.h"
#include "op25_audio.h"
#include "nxdn_const.h"
#include "nxdn.h"

namespace gr{
    namespace op25_repeater{

static const uint64_t DSTAR_FRAME_SYNC_MAGIC = 0x444445101440LL;  // expanded into dibits

enum rx_types {
	RX_TYPE_NONE=0,
	RX_TYPE_P25,
	RX_TYPE_DMR,
	RX_TYPE_DSTAR,
	RX_TYPE_YSF,
	RX_TYPE_NXDN,
	RX_N_TYPES
};   // also used as array index

static const struct _mode_data {
	const char * type;
	int sync_len;
	int sync_offset;
	int fragment_len;   // symbols
	int expiration;
	uint64_t sync;
} MODE_DATA[RX_N_TYPES] = {
	{"NONE",   0,0,0,0,0},
	{"P25",    48,0,864,1728,   P25_FRAME_SYNC_MAGIC},
	{"DMR",    48,66,144,1728,  DMR_VOICE_SYNC_MAGIC},
	{"DSTAR",  48,72,96,2016*2, DSTAR_FRAME_SYNC_MAGIC},
	{"YSF",    40,0,480,480*2,  YSF_FRAME_SYNC_MAGIC},
	{"NXDN",   20,0,192,192*2, NXDN_SYNC_MAGIC}
};   // index order must match rx_types enum

enum codeword_types {
	CODEWORD_P25P1,
	CODEWORD_P25P2,
	CODEWORD_DMR,
	CODEWORD_DSTAR,
	CODEWORD_YSF_FULLRATE,
	CODEWORD_YSF_HALFRATE,
	CODEWORD_NXDN_EHR
};

#define XLIST_SIZE 256

class rx_sync {
public:
	void rx_sym(const uint8_t sym);
	void sync_reset(void);
	rx_sync(const char * options, int debug, gr::msg_queue::sptr queue, int msgq_id);
	~rx_sync();
        void insert_whitelist(int grpaddr);
        void insert_blacklist(int grpaddr);
private:
	void cbuf_insert(const uint8_t c);
	void dmr_sync(const uint8_t bitbuf[], int& current_slot, bool& unmute);
	void ysf_sync(const uint8_t dibitbuf[], bool& ysf_fullrate, bool& unmute);
	void codeword(const uint8_t* cw, const enum codeword_types codeword_type, int slot_id);
	void output(int16_t * samp_buf, const ssize_t slot_id);
	bool nxdn_gate(enum rx_types sync_detected);
	void nxdn_frame(const uint8_t symbol_ptr[]);
	static const int CBUF_SIZE=864;
	static const int NSAMP_OUTPUT = 160;

	unsigned int d_symbol_count;
	uint64_t d_sync_reg;
	uint8_t d_cbuf[CBUF_SIZE*2];
	unsigned int d_cbuf_idx;
	enum rx_types d_current_type;
	int d_threshold;
	int d_rx_count;
	unsigned int d_expires;
	int d_shift_reg;
	unsigned int d_unmute_until[2];
	p25p2_vf interleaver;
	mbe_parms cur_mp[2];
	mbe_parms prev_mp[2];
	mbe_parms enh_mp[2];
	software_imbe_decoder d_software_decoder[2];
	std::deque<int16_t> d_output_queue[2];
	bool d_stereo;
	int d_debug;
	op25_audio d_audio;
	uint8_t d_burstb[2][32*4];
	int d_burstl[2];	// in units of bits
	int d_groupid[2];
	unsigned int d_groupid_valid[2];
	int d_whitelist[XLIST_SIZE];
	int d_blacklist[XLIST_SIZE];
	gr::msg_queue::sptr d_msg_queue;
	int d_previous_nxdn_sync;
	int d_previous_nxdn_sr_structure;
	int d_previous_nxdn_sr_ran;
	uint8_t d_sacch_buf[72];
	int d_msgq_id;
};

    } // end namespace op25_repeater
} // end namespace gr
#endif // INCLUDED_RX_SYNC_H
