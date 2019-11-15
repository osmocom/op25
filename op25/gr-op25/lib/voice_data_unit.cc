/* -*- C++ -*- */

/*
 * Copyright 2008 Steve Glass
 * 
 * This file is part of OP25.
 * 
 * OP25 is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3, or (at your option)
 * any later version.
 * 
 * OP25 is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
 * or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
 * License for more details.
 * 
 * You should have received a copy of the GNU General Public License
 * along with OP25; see the file COPYING.  If not, write to the Free
 * Software Foundation, Inc., 51 Franklin Street, Boston, MA
 * 02110-1301, USA.
 */

#include "voice_data_unit.h"
#include "op25_imbe_frame.h"

#include <map>
#include <iostream>
#include <boost/format.hpp>
#include <stdio.h>

#include <itpp/base/vec.h>
#include <itpp/base/mat.h>
#include <itpp/base/binary.h>
#include <itpp/base/converters.h>

using namespace std;

static void vec_mod(itpp::ivec& vec, int modulus = 2)
{
   for (int i = 0; i < vec.length(); ++i)
      vec[i] = vec[i] % modulus;
}

class cyclic_16_8_5_syndromes
{
public:
   typedef map<unsigned char,unsigned short> SyndromeTableMap;

   const static itpp::imat cyclic_16_8_5;
private:
   SyndromeTableMap m_syndrome_table;
public:
   inline const SyndromeTableMap table() const
   {
      return m_syndrome_table;
   }

   cyclic_16_8_5_syndromes(bool generate_now = false)
   {
      if (generate_now)
         generate();
   }

   int generate()
   {
      if (m_syndrome_table.empty() == false)
         return -1;
      
      // n=16, k=8
      
      // E1
      itpp::ivec v("1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0");
      itpp::ivec r(cyclic_16_8_5 * v);
      vec_mod(r);
      itpp::bvec b(to_bvec(r));
      unsigned char ch = (unsigned char)bin2dec(b);
      itpp::bvec bV(to_bvec(v));
      unsigned short us = (unsigned short)bin2dec(bV);
      m_syndrome_table.insert(make_pair(ch, us));
      
      // E2
      for (int i = 0; i <= (16 - 2); ++i)
      {
         itpp::ivec v2(v);
         v2[15-i] = 1;
         r = cyclic_16_8_5 * v2;
         bV = itpp::to_bvec(v2);
         
         vec_mod(r);
         b = itpp::to_bvec(r);
         unsigned char ch = (unsigned char)itpp::bin2dec(b);
         unsigned short us = (unsigned short)itpp::bin2dec(bV);
         m_syndrome_table.insert(make_pair(ch, us));
      }
      
      // E3 - disabled: min.d = 5, t=floor(5/2)=2
      /*for (int i = 0; i <= (16 - 2); ++i)
      {
         for (int j = 0; j < i; ++j)
         {
            ivec v3(v);
            v3[15-i] = 1;
            v3[15-j] = 1;
            r = cyclic_16_8_5 * v3;
            bV = to_bvec(v3);
            
            vec_mod(r);
            b = to_bvec(r);
            unsigned char ch = (unsigned char)bin2dec(b);
            unsigned short us = (unsigned short)bin2dec(bV);
            m_syndrome_table.insert(make_pair(ch, us));
         }
      }*/

      return m_syndrome_table.size();
   }
};

const itpp::imat cyclic_16_8_5_syndromes::cyclic_16_8_5(
"0 0 1 1 1 1 0 0 1 0 0 0 0 0 0 0;"
"1 0 0 1 1 1 1 0 0 1 0 0 0 0 0 0;"
"0 1 0 0 1 1 1 1 0 0 1 0 0 0 0 0;"
"0 0 0 1 1 0 1 1 0 0 0 1 0 0 0 0;"
"1 0 1 1 0 0 0 1 0 0 0 0 1 0 0 0;"
"1 1 1 0 0 1 0 0 0 0 0 0 0 1 0 0;"
"1 1 1 1 0 0 1 0 0 0 0 0 0 0 1 0;"
"0 1 1 1 1 0 0 1 0 0 0 0 0 0 0 1"
);

static cyclic_16_8_5_syndromes g_cyclic_16_8_5_syndromes(true);

static int decode_cyclic_16_8_5(const itpp::ivec& vec, itpp::ivec& out)
{   
   itpp::ivec vc(cyclic_16_8_5_syndromes::cyclic_16_8_5 * vec);
   vec_mod(vc);
   itpp::bvec vb(to_bvec(vc));
   
   unsigned char ch = (unsigned char)itpp::bin2dec(vb);
   if (ch == 0x00)
      return 0;
   
   const cyclic_16_8_5_syndromes::SyndromeTableMap& syndrome_table = g_cyclic_16_8_5_syndromes.table();
   cyclic_16_8_5_syndromes::SyndromeTableMap::const_iterator it = syndrome_table.find(ch);
   int j = 0;
   while (it == syndrome_table.end())
   {
      ++j;
      vc = itpp::concat(itpp::ivec("0 0 0 0 0 0 0 0"), vc); // Restore to 16 bits
      vc.shift_left(vc[0]);   // Rotate (s * x)
      vc = cyclic_16_8_5_syndromes::cyclic_16_8_5 * vc;
      vec_mod(vc);
      vb = itpp::to_bvec(vc);
      ch = (unsigned char)itpp::bin2dec(vb);
      it = syndrome_table.find(ch);
      
      if (j >= 15)
         break;
   }
   
   if (it == syndrome_table.end())
   {
      return -1;
   }
   
   unsigned short us = it->second;
   itpp::bvec es(itpp::dec2bin(16, us));
   if (j > 0)
      es.shift_right(es.mid(16-j, j)); // e
   vb = itpp::to_bvec(vec);
   vb -= es;
   out = itpp::to_ivec(vb);
   
   vc = cyclic_16_8_5_syndromes::cyclic_16_8_5 * out;
   vec_mod(vc);
   vb = itpp::to_bvec(vc);
   if (itpp::bin2dec(vb) != 0x00)
   {
      return -1;
   }
   
   return 1;
}

static int decode_cyclic_16_8_5(itpp::ivec& vec)
{
   return decode_cyclic_16_8_5(vec, vec);
}

////////////////////////////////////////////////////////////////////////////////////

voice_data_unit::voice_data_unit(const_bit_queue& frame_body) :
   abstract_data_unit(frame_body),
   d_lsdw(0),
   d_lsdw_valid(false)
{
   memset(d_lsd_byte_valid, 0x00, sizeof(d_lsd_byte_valid));
}

voice_data_unit::~voice_data_unit()
{
}

void
voice_data_unit::do_correct_errors(bit_vector& frame_body)
{
   if (logging_enabled()) fprintf(stderr, "\n");

   d_lsd_byte_valid[0] = d_lsd_byte_valid[1] = false;
   d_lsdw_valid = false;

   itpp::ivec lsd1(16), lsd2(16);
   
   for (int i = 0; i < 32; ++i)
   {
      int x = 1504 + i;
      x = x + ((x / 70) * 2); // Adjust bit index for status
      if (i < 16)
         lsd1[i] = frame_body[x];
      else
         lsd2[i-16] = frame_body[x];
   }
   
   int iDecode1 = decode_cyclic_16_8_5(lsd1);
   if (iDecode1 >= 0)
   {
      d_lsd_byte_valid[0] = true;
   }
   else if (iDecode1 == -1)
   {
         // Error
   }
   int iDecode2 = decode_cyclic_16_8_5(lsd2);
   if (iDecode2 >= 0)
   {
      d_lsd_byte_valid[1] = true;
   }
   else
   {
         // Error
   }

   d_lsdw = 0;
   for (int i = 0; i < 8; ++i)
      d_lsdw = d_lsdw | (lsd1[i] << (7 - i));  // Little-endian byte swap
   for (int i = 0; i < 8; ++i)
      d_lsdw = d_lsdw | (lsd2[i] << (15 - i)); // Little-endian byte swap
   
   if (d_lsd_byte_valid[0] && d_lsd_byte_valid[1])
      d_lsdw_valid = true;
}

uint16_t
voice_data_unit::lsdw() const
{
   return d_lsdw;
}

bool
voice_data_unit::lsdw_valid() const
{
   return d_lsdw_valid;
}

static void extract(unsigned int u, size_t n, std::vector<bool>& out)
{
   for (size_t i = 0; i < n; ++i)
      out.push_back(((u & (1 << (n-1-i))) != 0));
}

void
voice_data_unit::do_decode_audio(const_bit_vector& frame_body, imbe_decoder& imbe, crypto_module::sptr crypto_mod)
{
   voice_codeword cw(voice_codeword_sz);
   for(size_t i = 0; i < nof_voice_codewords; ++i) {
      imbe_deinterleave(frame_body, cw, i);

      unsigned int u0 = 0;
      unsigned int u1,u2,u3,u4,u5,u6,u7;
      unsigned int E0 = 0;
      unsigned int ET = 0;

      // PN/Hamming/Golay - etc.
      size_t errs = imbe_header_decode(cw, u0, u1, u2, u3, u4, u5, u6, u7, E0, ET, false);   // E0 & ET are not used, and are always returned as 0

      crypto_algorithm::sptr algorithm;
      if (crypto_mod)
         algorithm = crypto_mod->current_algorithm();

      if (algorithm)
      {
         if (i == 8)
         {
            d_lsdw ^= algorithm->generate(16);  // LSDW
         }

         u0 ^= (int)algorithm->generate(12);
         u1 ^= (int)algorithm->generate(12);
         u2 ^= (int)algorithm->generate(12);
         u3 ^= (int)algorithm->generate(12);
         
         u4 ^= (int)algorithm->generate(11);
         u5 ^= (int)algorithm->generate(11);
         u6 ^= (int)algorithm->generate(11);
         
         u7 ^= (int)algorithm->generate(7);

         imbe_header_encode(cw, u0, u1, u2, u3, u4, u5, u6, (u7 << 1));
      }

      std::vector<bool> cw_raw;
      extract(u0, 12, cw_raw);
      extract(u1, 12, cw_raw);
      extract(u2, 12, cw_raw);
      extract(u3, 12, cw_raw);
      extract(u4, 11, cw_raw);
      extract(u5, 11, cw_raw);
      extract(u6, 11, cw_raw);
      extract(u7, 7, cw_raw);

      const int cw_octets = 11;

      std::vector<uint8_t> cw_vector(cw_octets);
      extract(cw_raw, 0, (cw_octets * 8), &cw_vector[0]);

      if (logging_enabled())
      {
         std::stringstream ss;
         for (size_t n = 0; n < cw_vector.size(); ++n)
         {
            ss << (boost::format("%02x") % (int)cw_vector[n]);
            if (n < (cw_vector.size() - 1))
               ss << " ";
         }

         if (errs > 0)
            ss << (boost::format(" (%llu errors)") % errs);

         std:cerr << (boost::format("%s:\t%s") % duid_str() % ss.str()) << std::endl;
      }

      imbe.decode(cw);
   }

   if (logging_enabled()) fprintf(stderr, "%s: LSDW: 0x%04x, %s\n", duid_str().c_str(), d_lsdw, (d_lsdw_valid ? "valid" : "invalid"));
}

uint16_t
voice_data_unit::frame_size_max() const
{
   return 1728;
}
