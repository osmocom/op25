#ifndef INCLUDED_LDU_H
#define INCLUDED_LDU_H

#include "voice_data_unit.h"

class ldu : public voice_data_unit
{
private:

	size_t m_hamming_error_count;
	itpp::bvec m_raw_meta_data;

protected:

	virtual void do_correct_errors(bit_vector& frame_body);

	virtual bool process_meta_data(bit_vector& frame_body);

	virtual const itpp::bvec& raw_meta_data() const;

public:

	ldu(const_bit_queue& frame_body);

	virtual bool meta_data_valid() const;
};

#endif // INCLUDED_LDU_H
