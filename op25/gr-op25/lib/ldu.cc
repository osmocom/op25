#include "ldu.h"

#include <stdio.h>

#include <itpp/base/vec.h>
#include <itpp/base/mat.h>
#include <itpp/base/binary.h>
#include <itpp/base/converters.h>

const static itpp::Mat<int> ham_10_6_3_6("1 1 1 0 0 1 1 0 0 0; 1 1 0 1 0 1 0 1 0 0; 1 0 1 1 1 0 0 0 1 0; 0 1 1 1 1 0 0 0 0 1");

typedef std::vector<itpp::Vec<int> > VecArray;

ldu::ldu(const_bit_queue& frame_body) :
   voice_data_unit(frame_body),
   m_hamming_error_count(0)
{
}

void
ldu::do_correct_errors(bit_vector& frame_body)
{
   voice_data_unit::do_correct_errors(frame_body);
}

bool
ldu::process_meta_data(bit_vector& frame_body)
{
   m_hamming_error_count = 0;

   //std::vector<uint8_t> lc(30);
   //std::vector<uint16_t> ham(24);
   int lc_bit_idx = 0;
   VecArray arrayVec;
   itpp::Vec<int> vecRaw(10); // First 6 bits contain data
   
   for (int i = 400; i < 1360; i += 184)
   {
      for (int j = 0; j < 40; j++)
      {
         int x = (i + j) + (((i + j) / 70) * 2);	// Adjust bit index for status
         unsigned char ch = frame_body[x];
         
         //lc[lc_bit_idx / 8]  |= (ch << (7 - (lc_bit_idx % 8)));
         //ham[lc_bit_idx / 10] = ((ham[lc_bit_idx / 10]) << 1) | ch;
         vecRaw(lc_bit_idx % 10) = ch;
         
         ++lc_bit_idx;
         
         if ((lc_bit_idx % 10) == 0)
            arrayVec.push_back(vecRaw);
      }
   }
   
   if (lc_bit_idx != 240)	// Not enough bits
   {
      return false;
   }
   
   if (arrayVec.size() != 24)	// Not enough vectors
   {
      return false;
   }
   
   itpp::Vec<int> vecZero(4);
   vecZero.zeros();

   m_raw_meta_data.clear();
   
   for (int i = 0; i < arrayVec.size(); ++i)
   {
      itpp::Vec<int>& vec = arrayVec[i];
      itpp::bvec vB(itpp::to_bvec(vec));
      
      itpp::Vec<int> vS = ham_10_6_3_6 * vec;
      for (int i = 0; i < vS.length(); ++i)
         vS[i] = vS[i] % 2;
      itpp::bvec vb(to_bvec(vS));
      if (itpp::bin2dec(vb) != 0)
      {
         ++m_hamming_error_count;
      }
      
      m_raw_meta_data = concat(m_raw_meta_data, vB.mid(0, 6));  // Includes RS for last 72 bits
   }

   if (logging_enabled()) fprintf(stderr, "%s: %lu hamming errors, %s\n", duid_str().c_str(), m_hamming_error_count, (meta_data_valid() ? "valid" : "invalid"));
   
   return meta_data_valid();
}

const itpp::bvec&
ldu::raw_meta_data() const
{
   return m_raw_meta_data;
}

bool
ldu::meta_data_valid() const
{
   return (m_raw_meta_data.length() == 144); // Not enough bits after Hamming(10,6,3)
}
