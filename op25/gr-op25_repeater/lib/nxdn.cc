/* -*- c++ -*- */
/* 
 * NXDN Encoder/Decoder (C) Copyright 2019 Max H. Parke KA1RBI
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

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include "bit_utils.h"

#include "nxdn.h"
#include "nxdn_const.h"

static const uint8_t scramble_t[] = {
	2, 5, 6, 7, 10, 12, 14, 16, 17, 22, 23, 25, 26, 27, 28, 30, 33, 34, 36, 37, 38, 41, 45, 47,
	52, 54, 56, 57, 59, 62, 63, 64, 65, 66, 67, 69, 70, 73, 76, 79, 81, 82, 84, 85, 86, 87, 88,
	89, 92, 95, 96, 98, 100, 103, 104, 107, 108, 116, 117, 121, 122, 125, 127, 131, 132, 134,
	137, 139, 140, 141, 142, 143, 144, 145, 147, 151, 153, 154, 158, 159, 160, 162, 164, 165,
	168, 170, 171, 174, 175, 176, 177, 181};

static const int PARITY[] = {0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1};

static inline uint16_t crc16(const uint8_t buf[], int len, uint32_t crc) {
        uint32_t poly = (1<<12) + (1<<5) + (1<<0);
        for(int i=0; i<len; i++) {
                uint8_t bit = buf[i] & 1;
                crc = ((crc << 1) | bit) & 0x1ffff;
                if (crc & 0x10000)
                        crc = (crc & 0xffff) ^ poly;
	}
        crc = crc ^ 0xffff;
        return crc & 0xffff;
}

static uint16_t crc15(const uint8_t buf[], int len) {
	uint8_t s[15];
	uint8_t a;
	for (int i=0;i<15;i++)
		s[i] = 1;
	for (int i=0;i<len;i++) {
		a = buf[i] ^ s[0];
		s[0] = a ^ s[1];
		s[1] = s[2];
		s[2] = s[3];
		s[3] = a ^ s[4];
		s[4] = a ^ s[5];
		s[5] = s[6];
		s[6] = s[7];
		s[7] = a ^ s[8];
		s[8] = a ^ s[9];
		s[9] = s[10];
		s[10] = s[11];
		s[11] = s[12];
		s[12] = a ^ s[13];
		s[13] = s[14];
		s[14] = a;
	}
	return load_i(s, 15);
}

static uint16_t crc16(const uint8_t buf[], int len) {
	int crc = 0xc3ee;
        int poly = (1<<12) + (1<<5) + 1;
	for (int i=0;i<len;i++) {
                crc = ((crc << 1) | buf[i]) & 0x1ffff;
                if(crc & 0x10000)
                        crc = (crc & 0xffff) ^ poly;
	}
        crc = crc ^ 0xffff;
        return crc & 0xffff;
}

static uint8_t crc6(const uint8_t buf[], int len) {
	uint8_t s[6];
	uint8_t a;
	for (int i=0;i<6;i++)
		s[i] = 1;
	for (int i=0;i<len;i++) {
		a = buf[i] ^ s[0];
		s[0] = a ^ s[1];
		s[1] = s[2];
		s[2] = s[3];
		s[3] = a ^ s[4];
		s[4] = a ^ s[5];
		s[5] = a;
	}
	return load_i(s, 6);
}

static uint16_t crc12(const uint8_t buf[], int len) {
	uint8_t s[12];
	uint8_t a;
	for (int i=0;i<12;i++)
		s[i] = 1;
	for (int i=0;i<len;i++) {
		a = buf[i] ^ s[0];
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
	return load_i(s, 12);
}

// trellis_1_2 encode: source is in bits, result in bits
static inline void trellis_encode(uint8_t result[], const uint8_t source[], int result_len, int reg)
{
	for (int i=0; i<result_len; i+=2) {
		reg = (reg << 1) | source[i>>1];
		result[i] = PARITY[reg & 0x19];
		result[i+1] = PARITY[reg & 0x17];
	}
}

// simplified trellis 2:1 decode; source and result in bits
// assumes that encoding was done with NTEST trailing zero bits
// result_len should be set to the actual number of data bits
// in the original unencoded message (excl. these trailing bits)
static inline void trellis_decode(uint8_t result[], const uint8_t source[], int result_len)
{
	int reg = 0;
	int min_d;
	int min_bt;
	static const int NTEST = 4;
	static const int NTESTC = 1 << NTEST;
	uint8_t bt[NTEST];
	uint8_t tt[NTEST*2];
	int dstats[4];
	int sum;
	for (int p=0; p < 4; p++)
		dstats[p] = 0;
	for (int p=0; p < result_len; p++) {
		for (int i=0; i<NTESTC; i++) {
			bt[0] = (i&8)>>3;
			bt[1] = (i&4)>>2;
			bt[2] = (i&2)>>1;
			bt[3] = (i&1);
			trellis_encode(tt, bt, NTEST*2, reg);
			sum=0;
			for (int j=0; j<NTEST*2; j++) {
				sum += tt[j] ^ source[p*2+j];
			}
			if (i == 0 || sum < min_d) {
				min_d = sum;
				min_bt = bt[0];
			}
		}
		result[p] = min_bt;
		reg = (reg << 1) | min_bt;
		dstats[(min_d > 3) ? 3 : min_d] += 1;
	}
	// fprintf (stderr, "stats\t%d %d %d %d\n", dstats[0], dstats[1], dstats[2], dstats[3]);
}

void nxdn_descramble(uint8_t dibits[], int len) {
	for (int i=0; i<sizeof(scramble_t); i++) {
		if (scramble_t[i] >= len)
			break;
		dibits[scramble_t[i]] ^= 0x2;	// invert sign of scrambled dibits
	}
}

static inline void cfill(uint8_t result[], const uint8_t src[], int len) {
	for (int i=0; i<len; i++)
		result[i] = load_i(src+i*8, 8);
}

void nxdn_decode_cac(const uint8_t dibits[], int len, uint8_t answer[], int& answer_len) {
	uint8_t cacbits[300];
	uint8_t deperm[300];
	uint8_t depunc[350];
	uint8_t decode[171];
	int id=0;
	uint16_t crc;

	assert (len == 150);
	if (answer_len < 19) {
		answer_len = -1;
		return;
	}
	dibits_to_bits(cacbits, dibits, 150);
	for (int i=0; i<300; i++) {
		deperm[PERM_12_25[i]] = cacbits[i];
	}
	for (int i=0; i<25; i++) {
		depunc[id++] = deperm[i*12];
		depunc[id++] = deperm[i*12+1];
		depunc[id++] = deperm[i*12+2];
		depunc[id++] = 0;
		depunc[id++] = deperm[i*12+3];
		depunc[id++] = deperm[i*12+4];
		depunc[id++] = deperm[i*12+5];
		depunc[id++] = deperm[i*12+6];
		depunc[id++] = deperm[i*12+7];
		depunc[id++] = deperm[i*12+8];
		depunc[id++] = deperm[i*12+9];
		depunc[id++] = 0;
		depunc[id++] = deperm[i*12+10];
		depunc[id++] = deperm[i*12+11];
	}
	trellis_decode(decode, depunc, 171);
	crc = crc16(decode, 171, 0xc3ee);
	if (crc != 0) {
		answer_len = -1;
		return;		// ignore msg if crc failed
	}
	// result length after crc and 3 zero bits removed = 152 = 19 bytes
	cfill(answer, decode, 19);
	answer_len = 19;	/* return 19 bytes */
}

void nxdn_decode_facch(const uint8_t dibits[], int len, uint8_t answer[], int& answer_len) {
	uint8_t bits[144];
	uint8_t deperm[144];
	uint8_t depunc[192];
	uint8_t trellis_buf[92];
	uint16_t crc;
	uint16_t crc2;
	int out;
	char buf[128];
	assert (len == 72);
	if (answer_len < 10) {
		answer_len = -1;
		return;
	}
	dibits_to_bits(bits, dibits, 72);
	for (int i=0; i<144; i++) 
		deperm[PERM_16_9[i]] = bits[i];
	out = 0;
	for (int i=0; i<144; i+=3) {
		depunc[out++] = deperm[i+0];
		depunc[out++] = 0;
		depunc[out++] = deperm[i+1];
		depunc[out++] = deperm[i+2];
	}
	trellis_decode(trellis_buf, depunc, 92);
	crc = crc12(trellis_buf, 92);
	if (crc) {
		answer_len = -1;
		return;
	}
	cfill(answer, trellis_buf, 10);
	answer_len = 10;
}

void nxdn_decode_facch2_udch(const uint8_t dibits[], int len, uint8_t answer[], int& answer_len) {
	uint8_t bits[348];
	uint8_t deperm[348];
	uint8_t depunc[406];
	uint8_t trellis_buf[199];
	int id=0;
	uint16_t crc;
	assert (len == 174);
	if (answer_len < 23) {
		answer_len = -1;
		return;
	}
	dibits_to_bits(bits, dibits, 174);
	for (int i=0; i<348; i++) {
		deperm[PERM_12_29[i]] = bits[i];
	}
	for (int i=0; i<29; i++) {
		depunc[id++] = deperm[i*12];
		depunc[id++] = deperm[i*12+1];
		depunc[id++] = deperm[i*12+2];
		depunc[id++] = 0;
		depunc[id++] = deperm[i*12+3];
		depunc[id++] = deperm[i*12+4];
		depunc[id++] = deperm[i*12+5];
		depunc[id++] = deperm[i*12+6];
		depunc[id++] = deperm[i*12+7];
		depunc[id++] = deperm[i*12+8];
		depunc[id++] = deperm[i*12+9];
		depunc[id++] = 0;
		depunc[id++] = deperm[i*12+10];
		depunc[id++] = deperm[i*12+11];
	}
	trellis_decode(trellis_buf, depunc, 199);
	crc = crc15(trellis_buf, 199);
	if (crc != 0) {
		answer_len = -1;
		return;		// ignore msg if crc failed
	}
	// pack 184 bits in 23 bytes
	cfill(answer, trellis_buf, 23);
	answer_len = 23;
}

void nxdn_decode_sacch(const uint8_t dibits[], int len, uint8_t answer[], int& answer_len) {
	// global NEXT_S, SACCH
	uint8_t bits[60];
	uint8_t deperm[60];
	uint8_t depunc[72];
	uint8_t trellis_buf[32];
	int o=0;
	uint8_t crc;

	assert (len == 30);
	if (answer_len < 26) {
		answer_len = -1;
		return;
	}
	dibits_to_bits(bits, dibits, 30);
	for (int i=0; i<60; i++) 
		deperm[PERM_12_5[i]] = bits[i];
	for (int p=0; p<60; p+= 10) {
		depunc[o++] = deperm[p+0];
		depunc[o++] = deperm[p+1];
		depunc[o++] = deperm[p+2];
		depunc[o++] = deperm[p+3];
		depunc[o++] = deperm[p+4];
		depunc[o++] = 0;
		depunc[o++] = deperm[p+5];
		depunc[o++] = deperm[p+6];
		depunc[o++] = deperm[p+7];
		depunc[o++] = deperm[p+8];
		depunc[o++] = deperm[p+9];
		depunc[o++] = 0;
	}
	trellis_decode(trellis_buf, depunc, 32);
	crc = crc6(trellis_buf, 32);
	if (crc) {
		answer_len = -1;
		return;
	}
	memcpy(answer, trellis_buf, 26);
	answer_len = 26;		// answer is 26 bits, not packed
}
