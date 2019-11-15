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

#include "ldu1.h"

#include <itpp/base/vec.h>
#include <itpp/base/converters.h>

#include <boost/format.hpp>
#include <iostream>

#include "pickle.h"
#include "value_string.h"

using std::string;

ldu1::ldu1(const_bit_queue& frame_body) :
   ldu(frame_body)
{
}

ldu1::~ldu1()
{
}

void ldu1::do_correct_errors(bit_vector& frame_body)
{
	ldu::do_correct_errors(frame_body);

	if (!process_meta_data(frame_body))
		return;

	const itpp::bvec& data = raw_meta_data();

	std::stringstream ss;

	m_meta_data.m.lcf = bin2dec(data.mid(0, 8));
	m_meta_data.m.mfid = bin2dec(data.mid(8, 8));
	ss << (boost::format("%s: LCF: 0x%02x, MFID: 0x%02x") % duid_str() % m_meta_data.m.lcf % m_meta_data.m.mfid);
   if (m_meta_data.m.lcf == 0x00)
   {
      m_meta_data.m0.emergency = data[16];
      m_meta_data.m0.reserved = bin2dec(data.mid(17, 15));
      m_meta_data.m0.tgid = bin2dec(data.mid(32, 16));
      m_meta_data.m0.source = bin2dec(data.mid(48, 24));
      ss << (boost::format(", Emergency: 0x%02x, Reserved: 0x%04x, TGID: 0x%04x, Source: 0x%06x") % m_meta_data.m0.emergency % m_meta_data.m0.reserved % m_meta_data.m0.tgid % m_meta_data.m0.source);
   }
   else if (m_meta_data.m.lcf == 0x03)
   {
      m_meta_data.m3.reserved = bin2dec(data.mid(16, 8));
      m_meta_data.m3.destination = bin2dec(data.mid(24, 24));
      m_meta_data.m3.source = bin2dec(data.mid(48, 24));
      ss << (boost::format(", Reserved: 0x%02x, Destination: 0x%06x, Source: 0x%06x") % m_meta_data.m3.reserved % m_meta_data.m3.destination % m_meta_data.m3.source);
   }
   else
   {
   		ss << " (unknown LCF)";
   }

   if (logging_enabled()) std::cerr << ss.str() << std::endl;
}

std::string
ldu1::snapshot() const
{
   pickle p;
   p.add("duid", duid_str());
   p.add("mfid", lookup(m_meta_data.m.mfid, MFIDS, MFIDS_SZ));
   if ((m_meta_data.m.lcf == 0x00) || (m_meta_data.m.lcf == 0x03))
   	p.add("source", (boost::format("0x%06x") % m_meta_data.m0.source).str());
   if (m_meta_data.m.lcf == 0x00)
   	p.add("tgid", (boost::format("0x%04x") % m_meta_data.m0.tgid).str());
   if (m_meta_data.m.lcf == 0x03)
   	p.add("dest", (boost::format("0x%06x") % m_meta_data.m3.destination).str());
   return p.to_string();
}

ldu1::combined_meta_data
ldu1::meta_data() const
{
	return m_meta_data;
}

string
ldu1::duid_str() const
{
   return string("LDU1");
}
