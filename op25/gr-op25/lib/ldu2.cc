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

#include "ldu2.h"

#include <itpp/base/vec.h>
#include <itpp/base/converters.h>

#include <boost/format.hpp>

#include "pickle.h"
#include "value_string.h"

using std::string;

ldu2::ldu2(const_bit_queue& frame_body) :
   ldu(frame_body)
{
}

ldu2::~ldu2()
{
}

string
ldu2::duid_str() const
{
   return string("LDU2");
}

std::string
ldu2::snapshot() const
{
   pickle p;
   p.add("duid", duid_str());
   std::stringstream ss;
   ss << "0x";
	for (size_t n = 0; n < m_crypto_state.mi.size(); ++n)
		ss << (boost::format("%02x") % (int)m_crypto_state.mi[n]);
   p.add("mi", ss.str());
   p.add("algid", lookup(m_crypto_state.algid, ALGIDS, ALGIDS_SZ));
   p.add("kid", (boost::format("0x%04x") % m_crypto_state.kid).str());
   return p.to_string();
}

void
ldu2::do_correct_errors(bit_vector& frame_body)
{
	ldu::do_correct_errors(frame_body);

	if (!process_meta_data(frame_body))
		return;

	const itpp::bvec& data = raw_meta_data();

	for (int i = 0; i < 72; i += 8)
	{
	  m_crypto_state.mi[i/8] = bin2dec(data.mid(i, 8));
	}

	m_crypto_state.algid = bin2dec(data.mid(72, 8));
	m_crypto_state.kid = bin2dec(data.mid(80, 16));
}

struct CryptoState
ldu2::crypto_state() const
{
	return m_crypto_state;
}
