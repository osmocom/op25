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

static const uint16_t perm_25_12[300] = {	// perumtation schedule for 25x12
	0,12,24,36,48,60,72,84,96,108,120,132,144,156,168,180,192,204,216,228,240,252,264,276,288,
	1,13,25,37,49,61,73,85,97,109,121,133,145,157,169,181,193,205,217,229,241,253,265,277,289,
	2,14,26,38,50,62,74,86,98,110,122,134,146,158,170,182,194,206,218,230,242,254,266,278,290,
	3,15,27,39,51,63,75,87,99,111,123,135,147,159,171,183,195,207,219,231,243,255,267,279,291,
	4,16,28,40,52,64,76,88,100,112,124,136,148,160,172,184,196,208,220,232,244,256,268,280,292,
	5,17,29,41,53,65,77,89,101,113,125,137,149,161,173,185,197,209,221,233,245,257,269,281,293,
	6,18,30,42,54,66,78,90,102,114,126,138,150,162,174,186,198,210,222,234,246,258,270,282,294,
	7,19,31,43,55,67,79,91,103,115,127,139,151,163,175,187,199,211,223,235,247,259,271,283,295,
	8,20,32,44,56,68,80,92,104,116,128,140,152,164,176,188,200,212,224,236,248,260,272,284,296,
	9,21,33,45,57,69,81,93,105,117,129,141,153,165,177,189,201,213,225,237,249,261,273,285,297,
	10,22,34,46,58,70,82,94,106,118,130,142,154,166,178,190,202,214,226,238,250,262,274,286,298,
	11,23,35,47,59,71,83,95,107,119,131,143,155,167,179,191,203,215,227,239,251,263,275,287,299};

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

static inline void decode_cac(const uint8_t dibits[], int len) {
	uint8_t cacbits[300];
	uint8_t deperm[300];
	uint8_t depunc[350];
	uint8_t decode[171];
	int id=0;
	uint16_t crc;

	dibits_to_bits(cacbits, dibits, 150);
	for (int i=0; i<300; i++) {
		deperm[perm_25_12[i]] = cacbits[i];
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
	if (crc != 0)
		return;		// ignore msg if crc failed
	uint8_t msg_type = load_i(decode+8, 8) & 0x3f;
	// todo: forward CAC message
}

void nxdn_frame(const uint8_t dibits[], int ndibits) {
	uint8_t descrambled[182];
	uint8_t lich;
	uint8_t lich_test;
	uint8_t bit72[72];

	assert (ndibits >= 170);
	memcpy(descrambled, dibits, ndibits);
	nxdn_descramble(descrambled, ndibits);
	lich = 0;
	for (int i=0; i<8; i++)
		lich |= (descrambled[i] >> 1) << (7-i);
	/* todo: parity check & process LICH */
	if (lich >> 1 == 0x01)
		decode_cac(descrambled+8, 150);
	/* todo: process E: 12 dibits at descrambed+158; */
}
