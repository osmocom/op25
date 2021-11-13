/* -*- c++ -*- */
/* 
 * NXDN Encoder (C) Copyright 2017 Max H. Parke KA1RBI
 * 
 * This file is part of OP25
 * 
 * This is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3, or (at your option)
 * any later version.
 * 
 * This software is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the GNU General Public License
 * along with this software; see the file COPYING.  If not, write to
 * the Free Software Foundation, Inc., 51 Franklin Street,
 * Boston, MA 02110-1301, USA.
 */

#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include <gnuradio/io_signature.h>
#include "nxdn.h"
#include "mbelib.h"
#include "p25p2_vf.h"
#include "nxdn_tx_sb_impl.h"
#include "nxdn_const.h"
#include <op25_imbe_frame.h>

#include <vector>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <assert.h>

static const uint8_t nxdn_fs[] = {3, 0, 3, 1, 3, 3, 1, 1, 2, 1};

#if 0
static inline void print_result(char title[], const uint8_t r[], int len) {
	uint8_t buf[256];
	for (int i=0; i<len; i++){
		buf[i] = r[i] + '0';
	}
	buf[len] = 0;
	printf("%s: %s\n", title, buf);
}
#endif

static inline void store_i(int reg, uint8_t val[], int len) {
	for (int i=0; i<len; i++){
		val[i] = (reg >> (len-1-i)) & 1;
	}
}

static inline void bits_to_dibits(uint8_t* dest, const uint8_t* src, int n_dibits) {
	for (int i=0; i<n_dibits; i++) {
		dest[i] = src[i*2] * 2 + src[i*2+1];
	}
}

static inline void bool_to_dibits(uint8_t* dest, const std::vector<bool> src, int n_dibits) {
	for (int i=0; i<n_dibits; i++) {
		int l = src[i*2] ? 1 : 0;
		int r = src[i*2+1] ? 1 : 0;
		dest[i] = l * 2 + r;
	}
}

static inline int load_i(const uint8_t val[], int len) {
	int acc = 0;
	for (int i=0; i<len; i++){
		acc = (acc << 1) + (val[i] & 1);
	}
	return acc;
}

// unpacks bytes into bits, len is length of result
static inline void unpack_bytes(uint8_t result[], const char src[], int len) {
	static const int nbytes = len / 8;
	int outp = 0;
	for (int i=0; i < len; i++) {
		result[i] = (src[i>>3] >> (7-(i%8))) & 1;
	}
}

static inline int crc6(const uint8_t * bits, int len) {
	uint8_t s[6] = {1,1,1,1,1,1};
	for (int i=0; i<len; i++) {
		int bit = bits[i];
		int a = bit ^ s[0];
		s[0] = a ^ s[1];
		s[1] = s[2];
		s[2] = s[3];
		s[3] = a ^ s[4];
		s[4] = a ^ s[5];
		s[5] = a;
	}
	return (load_i(s, 6));
}

static inline int crc12(uint8_t bits[], int len) {
	uint8_t s[] = {1,1,1,1,1,1,1,1,1,1,1,1};
	for (int i=0; i<len; i++) {
		int bit = bits[i];
		int a = bit ^ s[0];
		s[0] = a ^ s[1];
		s[1] = s[2];
		s[2] = s[3];
		s[3] = s[4];
		s[4] = s[5];
		s[5] = s[6];
		s[6] = s[7];
		s[7] = s[8];
		s[8] = a ^ s[9];
		s[9] = a ^ s[10];
		s[10] = a ^ s[11];
		s[11] = a;
	}
	return (load_i(s, 12));
}

static const uint8_t trellis_PC[] = {0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1};
static inline void trellis_encode(const uint8_t src_bits[], uint8_t dest_bits[], const int dest_len) {
	int reg = 0;
	for (int i=0; i<dest_len/2; i++) {
		int bit = src_bits[i];
		reg = (reg << 1) | bit;
		dest_bits[i*2]   = trellis_PC[reg & 0x19];
		dest_bits[i*2+1] = trellis_PC[reg & 0x17];
	}
}

static inline uint16_t crc16(const uint8_t buf[], int len) {
        uint32_t poly = (1<<12) + (1<<5) + (1<<0);
        uint32_t crc = 0;
        for(int i=0; i<len; i++) {
                uint8_t bit = buf[i] & 1;
                crc = ((crc << 1) | bit) & 0x1ffff;
                if (crc & 0x10000)
                        crc = (crc & 0xffff) ^ poly;
	}
        crc = crc ^ 0xffff;
        return crc & 0xffff;
}

static inline void encode_sacch_chunk(const uint8_t src_bits[18], uint8_t dest_dibits[30], int structure, int ran) {
	uint8_t buf1[60];
	uint8_t buf2[72];
	uint8_t str_field[8];
	int str;

	str = (structure & 3) << 6;
	str |= ran & 0x3f;
	store_i(str, str_field, 8);

	memcpy(buf1, str_field, 8);
	memcpy(buf1+8, src_bits, 18);

	int crc = crc6(buf1, 26);
	store_i(crc, buf1+26, 6);
	store_i(0, buf1+32, 4);
	trellis_encode(buf1, buf2, sizeof(buf2));
	for (int i=0, op=0; i<sizeof(buf2); i += 12) {
		buf1[op++] = buf2[i+0];
		buf1[op++] = buf2[i+1];
		buf1[op++] = buf2[i+2];
		buf1[op++] = buf2[i+3];
		buf1[op++] = buf2[i+4];
		buf1[op++] = buf2[i+6];
		buf1[op++] = buf2[i+7];
		buf1[op++] = buf2[i+8];
		buf1[op++] = buf2[i+9];
		buf1[op++] = buf2[i+10];
	}
	for (int i=0; i<60; i++) {
		buf2[i] = buf1[PERM_12_5[i]];
	}
	bits_to_dibits(dest_dibits, buf2, 30);
}

static inline void encode_facch(const uint8_t src_bits[80], uint8_t dest_dibits[72]) {
	uint8_t buf1[144];
	uint8_t buf2[192];
	memcpy(buf1, src_bits, 80);
	int crc = crc12(buf1, 80);
	store_i(crc, buf1+80, 12);
	store_i(0, buf1+92, 4);
	trellis_encode(buf1, buf2, sizeof(buf2));
	for (int i=0, op=0; i<sizeof(buf2); i += 4) {
		buf1[op++] = buf2[i+0];
		buf1[op++] = buf2[i+2];
		buf1[op++] = buf2[i+3];
	}
	for (int i=0; i<144; i++) {
		buf2[i] = buf1[PERM_16_9[i]];
	}
	bits_to_dibits(dest_dibits, buf2, 72);
}

static inline void encode_lich(const int lich, uint8_t lich_dibits[8]) {
	uint8_t b[8];
	store_i(lich & 0x7f, b, 7);
	b[8] = (b[0] + b[1] + b[2] + b[3]) & 1;
	for (int i=0; i<8; i++)
		lich_dibits[i] = (b[i]) ? 3 : 1;
}

namespace gr {
  namespace op25_repeater {

    nxdn_tx_sb::sptr
    nxdn_tx_sb::make(int verbose_flag, const char * config_file, bool nxdn96_mode)
    {
      return gnuradio::get_initial_sptr
        (new nxdn_tx_sb_impl(verbose_flag, config_file, nxdn96_mode));
    }

//////////////////////////////////////////////////////////////////////////

static const int MIN_IN = 1;
static const int MAX_IN = 1;

static const int MIN_OUT = 1;
static const int MAX_OUT = 1;

    /*
     * The private constructor
     */
    nxdn_tx_sb_impl::nxdn_tx_sb_impl(int verbose_flag, const char * config_file, bool nxdn96_mode)
      : gr::block("nxdn_tx_sb",
              gr::io_signature::make (MIN_IN, MAX_IN, sizeof(short)),
              gr::io_signature::make (MIN_OUT, MAX_OUT, sizeof(char))),
              d_verbose_flag(verbose_flag),
              d_config_file(config_file),
              d_nxdn96_mode(nxdn96_mode),
              d_output_amount((nxdn96_mode) ? 384 : 192),
              d_sacch_seq(0),
              d_lich(0),
              d_ran(0)
    {
      set_output_multiple(d_output_amount);
      memset(d_acch, 0, sizeof(d_acch));
      config();
    }

    /*
     * Our virtual destructor.
     */
    nxdn_tx_sb_impl::~nxdn_tx_sb_impl()
    {
    }

void
nxdn_tx_sb_impl::config()
{
	FILE * fp1 = fopen(d_config_file, "r");
	char line[256];
	char * cp;
	unsigned int li[9];
	long int ran;
	long int lich, lich2;
	if (!fp1) {
		fprintf(stderr, "nxdn_tx_sb_impl:config: failed to open %s\n", d_config_file);
		return;
	}
	for (;;) {
		cp = fgets(line, sizeof(line) - 2, fp1);
		if (!cp) break;
		if (line[0] == '#') continue;
		if (memcmp(line, "ran=", 4) == 0) {
			ran = strtol(line+4, 0, 0);
			d_ran = ran;
		} else if (memcmp(line, "lich=", 5) == 0) {
			lich = strtol(line+5, 0, 0);
			d_lich = lich;
		} else if (memcmp(line, "lich2=", 6) == 0) {
			lich2 = strtol(line+6, 0, 0);
			d_lich2 = lich2;
		} else if (memcmp(line, "acch=", 5) == 0) {
			sscanf(&line[5], "%x %x %x %x %x %x %x %x %x %x", &li[0], &li[1], &li[2], &li[3], &li[4], &li[5], &li[6], &li[7], &li[8], &li[9]);
			for (int i=0; i<10; i++) {
				store_i(li[i], d_acch+i*8, 8);
			}
		}
	}
	encode_lich(d_lich, d_lich_x1);
	encode_lich(d_lich2, d_lich_x2);
	encode_facch(d_acch, d_facch1);
	for (int i=0; i<4; i++)
		encode_sacch_chunk(d_acch+18*i, d_sacch[i], 3-i, d_ran);
	fclose(fp1);
}

void
nxdn_tx_sb_impl::forecast(int nof_output_items, gr_vector_int &nof_input_items_reqd)
{
   // each 192-dibit output frame contains four voice code words=640 samples
   // for nxdn96 we output 384 dibits per four voice code words
   const size_t nof_inputs = nof_input_items_reqd.size();
   const int nof_vcw = nof_output_items / d_output_amount;
   const int nof_samples_reqd = nof_vcw * 4 * 160;
   std::fill(&nof_input_items_reqd[0], &nof_input_items_reqd[nof_inputs], nof_samples_reqd);
}

int 
nxdn_tx_sb_impl::general_work (int noutput_items,
			       gr_vector_int &ninput_items,
			       gr_vector_const_void_star &input_items,
			       gr_vector_void_star &output_items)
{

  int nconsumed = 0;
  int16_t *in;
  in = (int16_t *) input_items[0];
  uint8_t *out = reinterpret_cast<uint8_t*>(output_items[0]);
  int nframes=0;
  int16_t frame_vector[8];
  voice_codeword cw(voice_codeword_sz);
  uint8_t ambe_codeword[36];	// dibits
  std::vector <bool> interleaved_buf(144);

  for (int n=0;n < (noutput_items/d_output_amount);n++) {
    // need (at least) four voice codewords worth of samples
    if (ninput_items[0] - nconsumed < 4*160) break;
    memcpy(out, nxdn_fs, sizeof(nxdn_fs));
    memcpy(out+10, d_lich_x1, 8);
    memcpy(out+18, d_sacch[d_sacch_seq++ % 4], 30);
    // TODO: would be nice to multithread these
    for (int vcw = 0; vcw < 4; vcw++) {
      d_halfrate_encoder.encode(in, ambe_codeword);
      memcpy(out+48+36*vcw, ambe_codeword, sizeof(ambe_codeword));
      in += 160;
      nconsumed += 160;
    }
    nxdn_descramble(out+10, 182);
    if (d_nxdn96_mode) {
       memcpy(out+192, nxdn_fs, sizeof(nxdn_fs));
       memcpy(out+192+10, d_lich_x2, 8);
       memcpy(out+192+18, d_sacch[d_sacch_seq++ % 4], 30);
       memcpy(out+192+48, d_facch1, 72);
       memcpy(out+192+120, d_facch1, 72);
       nxdn_descramble(out+192+10, 182);
    }
    nframes += 1;
    out += d_output_amount;
  }

  // Tell runtime system how many input items we consumed on
  // each input stream.

  if (nconsumed)
    consume_each(nconsumed);

  // Tell runtime system how many output items we produced.
  return (nframes * d_output_amount);
}

void
nxdn_tx_sb_impl::set_gain_adjust(float gain_adjust) {
	d_halfrate_encoder.set_gain_adjust(gain_adjust);
}

  } /* namespace op25_repeater */
} /* namespace gr */
