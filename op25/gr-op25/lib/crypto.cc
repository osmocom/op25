#include "crypto.h"

#include <sstream>
#include <boost/format.hpp>
#include <iostream>
#include <stdio.h>
#include <memory.h>

extern "C" {
#include "des.h"
}

static unsigned long long swap_bytes(uint64_t l)
{
	unsigned long long r;
	unsigned char* pL = (unsigned char*)&l;
	unsigned char* pR = (unsigned char*)&r;
	for (int i = 0; i < sizeof(l); ++i)
		pR[i] = pL[(sizeof(l) - 1) - i];
	return r;
}

///////////////////////////////////////////////////////////////////////////////
/*
class null_algorithm : public crypto_algorithm	// This is an algorithm skeleton (can be used for no encryption as pass-through)
{
private:
	size_t m_generated_bits;
public:
	null_algorithm()
		: m_generated_bits(0)
	{
	}
	const type_id id() const
	{
		return crypto_algorithm::NONE;
	}
	bool update(const struct CryptoState& state)
	{
		fprintf(stderr, "NULL:\t%d bits generated\n", m_generated_bits);

		m_generated_bits = 0;

		return true;
	}
	bool set_key(const crypto_algorithm::key_type& key)
	{
		return true;
	}
	uint64_t generate(size_t n)
	{
		m_generated_bits += n;
		return 0;
	}
};
*/
///////////////////////////////////////////////////////////////////////////////

class des_ofb : public crypto_algorithm
{
public:
	unsigned long long m_key_des, m_next_iv, m_ks;
	int m_ks_idx;
	DES_KS m_ksDES;
    int m_iterations;
    uint16_t m_current_kid;
    key_type m_default_key;
    key_map_type m_key_map;
    bool m_verbose;
public:
	des_ofb()
		: m_current_kid(-1)
	{
	    memset(&m_ksDES, 0, sizeof(m_ksDES));
	    m_key_des = 0;
	    m_next_iv = 0;
	    m_ks_idx = 0;
	    m_ks = 0;
	    m_iterations = 0;
	}

	void set_logging(bool on)
	{
		m_verbose = on;
	}

	const type_id id() const
	{
		return crypto_algorithm::DES_OFB;
	}

	bool update(const struct CryptoState& state)
	{
		if (m_current_kid != state.kid)
		{
			if (m_key_map.empty())
			{
				// Nothing to do
			}
			else
			{
				key_map_type::iterator it = m_key_map.find(state.kid);
				if (it != m_key_map.end())
				{
					set_key(it->second);
				}
				else if (!m_default_key.empty())
				{
					/*if (m_verbose) */fprintf(stderr, "Key 0x%04x not found in key map - using default key\n", state.kid);

					set_key(m_default_key);
				}
				else
				{
					/*if (m_verbose) */fprintf(stderr, "Key 0x%04x not found in key map and no default key\n", state.kid);
				}
			}

			m_current_kid = state.kid;
		}

		uint64_t iv = 0;
		size_t n = std::min(sizeof(iv), state.mi.size());
		memcpy(&iv, &state.mi[0], n);
		set_iv(iv);

		return (n == 8);
	}

	void set_key_map(const key_map_type& key_map)
	{
		m_key_map = key_map;

		m_current_kid = -1;	// To refresh on next update if it has changed
	}

	bool set_key(const crypto_algorithm::key_type& key)
	{
		const size_t valid_key_length = 8;

		if (key.size() != valid_key_length)
		{
			if (m_verbose) fprintf(stderr, "DES:\tIncorrect key length of %lu (should be %lu)\n", key.size(), valid_key_length);
			return false;
		}

		m_default_key = key;

		memcpy(&m_key_des, &key[0], std::min(key.size(), sizeof(m_key_des)));
		
		if (m_verbose)
		{
			std::stringstream ss;
			for (int i = 0; i < valid_key_length; ++i)
				ss << boost::format("%02X") % (int)key[i];
			std::cerr << "DES:\tKey: " << ss.str() << std::endl;
		}
		
		deskey(m_ksDES, (unsigned char*)&m_key_des, 0);	// 0: encrypt (for OFB mode)

		return true;
	}

	void set_iv(uint64_t iv)
	{
		if (m_iterations > 0)
		{
			if (m_verbose) fprintf(stderr, "DES:\t%i bits used from %i iterations\n", m_ks_idx, m_iterations);
		}
		
		m_next_iv = iv;
		
		m_ks_idx = 0;
		m_iterations = 0;
		
		m_ks = m_next_iv;
		des(m_ksDES, (unsigned char*)&m_ks);	// First initialisation
		++m_iterations;
		
		des(m_ksDES, (unsigned char*)&m_ks);	// Throw out first iteration & prepare for second
		++m_iterations;
		
		generate(64);		// Reserved 3 + first 5 of LC (3 left)
		generate(3 * 8);	// Use remaining 3 bytes for LC
	}

	uint64_t generate(size_t count)	// 1..64
	{
		unsigned long long ullCurrent = swap_bytes(m_ks);
		const int max_len = 64;
		int pos = m_ks_idx % max_len;
		
		m_ks_idx += count;
		
		if ((pos + count) <= max_len)	// Up to 64
		{
			if ((m_ks_idx % max_len) == 0)
			{
				des(m_ksDES, (unsigned char*)&m_ks);	// Prepare for next iteration
				++m_iterations;
			}
			
			unsigned long long result = (ullCurrent >> (((max_len - 1) - pos) - (count-1))) & ((count == max_len) ? (unsigned long long)-1 : ((1ULL << count) - 1));
			
			return result;
		}
		
		// Over-flow 64-bit boundary (so all of rest of current will be used)
		
		des(m_ksDES, (unsigned char*)&m_ks);	// Compute second part
		++m_iterations;
		
		unsigned long long first = ullCurrent << pos;	// RHS will be zeros
		
		ullCurrent = swap_bytes(m_ks);
		int remainder = count - (max_len - pos);
		first >>= (((max_len - 1) - remainder) - ((max_len - 1) - pos));
		unsigned long long next = (ullCurrent >> (((max_len - 1) - 0) - (remainder-1))) & ((1ULL << remainder) - 1);
		
		return (first | next);
	}

};

///////////////////////////////////////////////////////////////////////////////

crypto_module::crypto_module(bool verbose/* = true*/)
	: d_verbose(verbose)
{
}

crypto_algorithm::sptr crypto_module::algorithm(crypto_algorithm::type_id algid)
{
	if ((!d_current_algorithm && (algid == crypto_algorithm::NONE)) ||	// This line should be commented out if 'null_algorithm' is to be tested
		(d_current_algorithm && (algid == d_current_algorithm->id())))
		return d_current_algorithm;

	switch (algid)
	{
		case crypto_algorithm::DES_OFB:
			d_current_algorithm = crypto_algorithm::sptr(new des_ofb());
			break;
		//case crypto_algorithm::NONE:
		//	d_current_algorithm = crypto_algorithm::sptr(new null_algorithm());
		//	break;
		default:
			d_current_algorithm = crypto_algorithm::sptr();
	};

	if (d_current_algorithm)
	{
		d_current_algorithm->set_logging(logging_enabled());

		if (!d_persistent_key_map.empty())
			d_current_algorithm->set_key_map(d_persistent_key_map);

		if (!d_persistent_key.empty())
			d_current_algorithm->set_key(d_persistent_key);
	}

	return d_current_algorithm;
}

void crypto_module::set_key(const crypto_algorithm::key_type& key)
{
	d_persistent_key = key;

	if (d_current_algorithm)
		d_current_algorithm->set_key(d_persistent_key);
}

void crypto_module::set_key_map(const crypto_algorithm::key_map_type& keys)
{
	d_persistent_key_map = keys;

	if (d_current_algorithm)
		d_current_algorithm->set_key_map(d_persistent_key_map);
}

void crypto_module::set_logging(bool on/* = true*/)
{
	d_verbose = on;

	if (d_current_algorithm)
		d_current_algorithm->set_logging(on);
}
