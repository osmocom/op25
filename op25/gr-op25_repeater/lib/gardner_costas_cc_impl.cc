/* -*- c++ -*- */
/* 
 * Copyright 2005,2006,2007 Free Software Foundation, Inc.
 *
 * Gardner symbol recovery block for GR - Copyright 2010, 2011, 2012, 2013, 2014, 2015 KA1RBI
 * 
 * This file is part of OP25 and part of GNU Radio
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
#include "gardner_costas_cc_impl.h"

#include <gnuradio/math.h>
#include <gnuradio/expj.h>
#include <gnuradio/filter/mmse_fir_interpolator_cc.h>
#include <stdexcept>
#include <cstdio>
#include <string.h>
#include <sys/time.h>

#include "p25_frame.h"
#include "p25p2_framer.h"
#include "check_frame_sync.h"

#define ENABLE_COSTAS_CQPSK_HACK 0

static const float M_TWOPI = 2 * M_PI;
#define VERBOSE_GARDNER 0    // Used for debugging symbol timing loop
#define VERBOSE_COSTAS 0     // Used for debugging phase and frequency tracking
static const gr_complex PT_45 = gr_expj( M_PI / 4.0 );
static const int NUM_COMPLEX=100;

static const int FM_COUNT=500;	// number of samples per measurement frame

static const int N_FILES = 4;	// number of filenames to cycle through

namespace gr {
  namespace op25_repeater {

static inline std::complex<float> sgn(std::complex<float>c) {
	if (c == std::complex<float>(0.0,0.0))
		return std::complex<float>(0.0, 0.0);
	return c/abs(c);
}

#define UPDATE_COUNT(c) if (d_event_type == c) {	\
				d_event_count ++;	\
			} else {			\
				d_event_count = 1;	\
				d_event_type = c;	\
			}

static int tuning_score(gr_complex buf[], int bufp, int bufl, int sync_l, int sps) {
	int n_scan_samples = sps * 6;
	float atan_prev = 0;
	float score = 0;
	int p = bufp - (n_scan_samples + 1);
	if (p < 0)
		p += bufl;
	int n_tests = 0;
	int n_plus = 0;
	// a series of N consecutive samples treated as N-1 connected line segments 
	// is evaluated to find the angle, in radians, at the junction of each pair
	// of lines.
	// when a frequency tuning error is present the algebraic sum of the angles
	// will contain a significant positive or negative bias.
	for (int i = 0; i < n_scan_samples; i++) {
		gr_complex sample1 = buf[ (p+i)   % bufl ];
		gr_complex sample2 = buf[ (p+i+1) % bufl ];
		gr_complex diff = sample2 - sample1;
		float atan = gr::fast_atan2f(diff.real(), diff.imag());
		if (i == 0) {
			atan_prev = atan;
			continue;
		}
		float atan_diff = atan - atan_prev;
		if (atan_diff > M_PI)
			atan_diff -= M_TWOPI;
		if (atan_diff < -M_PI)
			atan_diff += M_TWOPI;
		atan_prev = atan;
		score += atan_diff;
		n_tests += 1;
		if (atan_diff > 0)
			n_plus += 1;
	}
	float f1 = (score > 0) ? n_plus : n_tests - n_plus;
	float f2 = n_tests;
	int pct = (int) (100*f1/f2 + 0.5);
	if (score < 0)
		pct *= -1;
	return pct;
}

static inline bool is_future(struct timeval*t) {
	struct timeval current_t;
	gettimeofday(&current_t,0);
	if (t->tv_sec > current_t.tv_sec)
		return true;
	else if (t->tv_sec < current_t.tv_sec)
		return false;
	else if (t->tv_usec > current_t.tv_usec)
		return true;
	else
		return false;
}

void gardner_costas_cc_impl::dump_samples(int error_amt) {
	// TODO = disk I/O from inside a gr flow graph block work function (tsk tsk)
	char tmp_filename[256];
	char filename[256];
	char line[64];
	FILE *fp1;
	if (!d_enable_sync_plot)
		return;
	if (d_prev_sample == NULL)
		return;
	if (is_future(&d_next_sample_time))
		return;
	gettimeofday(&d_next_sample_time,0);
	d_next_sample_time.tv_sec += 1;
	sprintf(filename, "sample-%ld-%d.dat", unique_id(), d_sample_file_id);
	d_sample_file_id ++;
	d_sample_file_id = d_sample_file_id % N_FILES;
	sprintf(line, "%u %d %d %d\n", d_prev_sample_p, (d_is_tdma) ? 2 : 1, (int) (d_omega + 0.5), error_amt);
	strcpy(tmp_filename, filename);
	strcat(tmp_filename, ".tmp");
	fp1 = fopen(tmp_filename, "wb");
	if (!fp1)
		return;
	fwrite (line, 1, strlen(line), fp1);
	fwrite (d_prev_sample, 1, d_n_prev_sample * sizeof(gr_complex), fp1);
	fclose(fp1);

	rename(tmp_filename, filename);
}

uint8_t gardner_costas_cc_impl::slicer(float sym) {
    uint8_t dibit = 0;
    int sps = (int) (d_omega + 0.5);
    static const float PI_4 = M_PI / 4.0;
    static const float d_slice_levels[4] = {(float)-2.0*PI_4, (float)0.0*PI_4, (float)2.0*PI_4, (float)4.0*PI_4};
    if (d_slice_levels[3] < 0) {
      dibit = 1;
      if (d_slice_levels[3] <= sym && sym < d_slice_levels[0])
        dibit = 3;
    } else {
      dibit = 3;
      if (d_slice_levels[2] <= sym && sym < d_slice_levels[3])
        dibit = 1;
    }
    if (d_slice_levels[0] <= sym && sym < d_slice_levels[1])
      dibit = 2;
    if (d_slice_levels[1] <= sym && sym < d_slice_levels[2])
      dibit = 0;
    nid_accum <<= 2;
    nid_accum |= dibit;

	if(check_frame_sync((nid_accum & P25_FRAME_SYNC_MASK) ^ P25_FRAME_SYNC_MAGIC, 0, 48)) {
//		fprintf(stderr, "P25P1 Framing detect\n");
		UPDATE_COUNT(' ')
		d_sync_valid_until = d_sample_count + 2400 * sps;
		dump_samples(0);
	}
	else if(check_frame_sync((nid_accum & P25P2_FRAME_SYNC_MASK) ^ P25P2_FRAME_SYNC_MAGIC, 0, 40)) {
//		fprintf(stderr, "P25P2 Framing detect\n");
		UPDATE_COUNT(' ')
		d_sync_valid_until = d_sample_count + 2400 * sps;
		dump_samples(0);
	}
    if (d_is_tdma) {
	if(check_frame_sync((nid_accum & P25_FRAME_SYNC_MASK) ^ 0x000104015155LL, 0, 40)) {
		fprintf(stderr, "TDMA: channel %d tuning error -1200\n", -1);
		UPDATE_COUNT('-')
		d_sync_valid_until = d_sample_count + 2400 * sps;
		dump_samples(-1200);
	}
	else if(check_frame_sync((nid_accum & P25_FRAME_SYNC_MASK) ^ 0xfefbfeaeaaLL, 0, 40)) {
		fprintf(stderr, "TDMA: channel %d tuning error +1200\n", -1);
		UPDATE_COUNT('+')
		d_sync_valid_until = d_sample_count + 2400 * sps;
		dump_samples(1200);
	}
	else if(check_frame_sync((nid_accum & P25_FRAME_SYNC_MASK) ^ 0xa8a2a80800LL, 0, 40)) {
		int score = tuning_score(d_prev_sample, d_prev_sample_p, d_n_prev_sample, 20, sps);
		int error = 24;
		if (score == -100) {
			error = 2400;
			UPDATE_COUNT('>')
			fprintf(stderr, "TDMA: channel %d tuning error %d\n", -1, error);
		} else if (score == 100) {
			error = -2400;
			UPDATE_COUNT('<')
			fprintf(stderr, "TDMA: channel %d tuning error %d\n", -1, error);
		} else {
			fprintf(stderr, "TDMA: channel %d tuning error +/-2400, confidence %d\n", -1, score);
		}
		d_sync_valid_until = d_sample_count + 2400 * sps;
		dump_samples(error);
	}
    } else {
	if(check_frame_sync((nid_accum & P25_FRAME_SYNC_MASK) ^ 0x001050551155LL, 0, 48)) {
//		fprintf(stderr, "tuning error -1200\n");
		UPDATE_COUNT('-')
		d_sync_valid_until = d_sample_count + 2400 * sps;
		dump_samples(-1200);
	}
	else if(check_frame_sync((nid_accum & P25_FRAME_SYNC_MASK) ^ 0xFFEFAFAAEEAALL, 0, 48)) {
//		fprintf(stderr, "tuning error +1200\n");
		UPDATE_COUNT('+')
		d_sync_valid_until = d_sample_count + 2400 * sps;
		dump_samples(1200);
	}
	else if(check_frame_sync((nid_accum & P25_FRAME_SYNC_MASK) ^ 0xAA8A0A008800LL, 0, 48)) {
		int score = tuning_score(d_prev_sample, d_prev_sample_p, d_n_prev_sample, 24, sps);
		int error = 24;
		if (score == -100) {
			error = 2400;
			UPDATE_COUNT('>')
			fprintf(stderr, "channel %d block id %ld tuning error %d\n", -1, (long)unique_id(), error);
		} else if (score == 100) {
			error = -2400;
			UPDATE_COUNT('<')
			fprintf(stderr, "channel %d block id %ld tuning error %d\n", -1, (long)unique_id(), error);
		} else {
			fprintf(stderr, "channel %d block id %ld tuning error +/-2400, confidence %d\n", -1, (long)unique_id(), score);
		}
		d_sync_valid_until = d_sample_count + 2400 * sps;
		dump_samples(error);
	}
    }
    if (d_event_type == ' ' || d_event_count < 5) {
        d_update_request = 0;
    } else {
        if (d_event_type == '+' && d_fm > 0)
            d_update_request = -1;
        else if (d_event_type == '-' && d_fm < 0)
            d_update_request = 1;
        else if (d_event_type == '<')
            d_update_request = -2;
        else if (d_event_type == '>')
            d_update_request = 2;
        else d_update_request = 0;
    }
    return dibit;
}

    gardner_costas_cc::sptr
    gardner_costas_cc::make(float samples_per_symbol, float gain_mu, float gain_omega, float alpha, float beta, float max_freq, float min_freq)
    {
      return gnuradio::get_initial_sptr
        (new gardner_costas_cc_impl(samples_per_symbol, gain_mu, gain_omega, alpha, beta, max_freq, min_freq));
    }

    /*
     * The private constructor
     */
    gardner_costas_cc_impl::gardner_costas_cc_impl(float samples_per_symbol, float gain_mu, float gain_omega, float alpha, float beta, float max_freq, float min_freq)
      : gr::block("gardner_costas_cc",
              gr::io_signature::make(1, 1, sizeof(gr_complex)),
              gr::io_signature::make(1, 1, sizeof(gr_complex))),
    d_mu(0),
    d_gain_omega(gain_omega),
    d_omega_rel(0.005),
    d_gain_mu(gain_mu),
    d_last_sample(0), d_interp(new gr::filter::mmse_fir_interpolator_cc()),
    //d_verbose(gr::prefs::singleton()->get_bool("gardner_costas_cc", "verbose", false)),
    d_verbose(false),
    d_dl(new gr_complex[NUM_COMPLEX]),
    d_dl_index(0),
    d_alpha(alpha), d_beta(beta), 
    d_interp_counter(0),
    d_theta(M_PI / 4.0), d_phase(0), d_freq(0), d_max_freq(max_freq),
    nid_accum(0), d_prev(0),
    d_event_count(0), d_event_type(' '),
    d_symbol_seq(samples_per_symbol * 4800),
    d_update_request(0),
    d_fm(0), d_fm_accum(0), d_fm_count(0), d_muted(false), d_is_tdma(false),
    d_enable_sync_plot(false),
    d_prev_sample(NULL), d_n_prev_sample(0), d_prev_sample_p(0),
    d_sample_file_id(0),
    d_sample_count(0), d_sync_valid_until(0)
    {
  set_omega(samples_per_symbol);
  set_relative_rate (1.0 / d_omega);
  set_history(d_twice_sps);			// ensure extra input is available
  gettimeofday(&d_next_sample_time, 0);
    }

    /*
     * Our virtual destructor.
     */
    gardner_costas_cc_impl::~gardner_costas_cc_impl()
    {
  if (d_prev_sample != NULL) {
      free(d_prev_sample);
      d_prev_sample = NULL;
  }
  delete [] d_dl;
  delete d_interp;
    }

void gardner_costas_cc_impl::set_omega (float omega) {
    assert (omega >= 2.0);
    d_omega = omega;
    d_min_omega = omega*(1.0 - d_omega_rel);
    d_max_omega = omega*(1.0 + d_omega_rel);
    d_omega_mid = 0.5*(d_min_omega+d_max_omega);
    d_twice_sps = 2 * (int) ceilf(d_omega);
    int num_complex = std::max(d_twice_sps*2, 16);
    if (num_complex > NUM_COMPLEX)
        fprintf(stderr, "gardner_costas_cc: warning omega %f size %d exceeds NUM_COMPLEX %d\n", omega, num_complex, NUM_COMPLEX);
    memset(d_dl, 0, NUM_COMPLEX * sizeof(gr_complex));
}

float gardner_costas_cc_impl::get_freq_error (void) {
	if (!recent_sync())
		return 0.0;
	return (d_freq);
}

int gardner_costas_cc_impl::get_error_band (void) {
	if (!recent_sync())
		return 0;
	return (d_update_request);
}

void
gardner_costas_cc_impl::forecast(int noutput_items, gr_vector_int &ninput_items_required)
{
  unsigned ninputs = ninput_items_required.size();
  for (unsigned i=0; i < ninputs; i++)
    ninput_items_required[i] =
      (int) ceil((noutput_items * d_omega) + d_interp->ntaps());
}

float   // for QPSK
gardner_costas_cc_impl::phase_error_detector_qpsk(gr_complex sample)
{
  float phase_error = 0;
  if(fabsf(sample.real()) > fabsf(sample.imag())) {
    if(sample.real() > 0)
      phase_error = -sample.imag();
    else
      phase_error = sample.imag();
  }
  else {
    if(sample.imag() > 0)
      phase_error = sample.real();
    else
      phase_error = -sample.real();
  }
  
  return phase_error;
}

void
gardner_costas_cc_impl::phase_error_tracking(gr_complex sample)
{
  float phase_error = 0;
#if ENABLE_COSTAS_CQPSK_HACK
  if (d_interp_counter & 1)    // every other symbol
    sample = sample * PT_45;    // rotate by +45 deg
  d_interp_counter++;
#endif /* ENABLE_COSTAS_CQPSK_HACK */

  // Make phase and frequency corrections based on sampled value
  phase_error =  phase_error_detector_qpsk(sample);
    
  d_freq += d_beta*phase_error*abs(sample);             // adjust frequency based on error
  d_phase += d_alpha*phase_error*abs(sample);  // adjust phase based on error

  // Make sure we stay within +-pi
  while(d_phase > M_PI)
    d_phase -= M_TWOPI;
  while(d_phase < -M_PI)
    d_phase += M_TWOPI;
  
  // Limit the frequency range
  d_freq = gr::branchless_clip(d_freq, d_max_freq);
  
#if VERBOSE_COSTAS
  fprintf(stderr, "COSTAS\t%f\t%f\t%f\t%f+j%f\n",
	 phase_error, d_phase, d_freq, sample.real(), sample.imag());
#endif
}

int
gardner_costas_cc_impl::general_work (int noutput_items,
				   gr_vector_int &ninput_items,
				   gr_vector_const_void_star &input_items,
				   gr_vector_void_star &output_items)
{
  const gr_complex *in = (const gr_complex *) input_items[0];
  gr_complex *out = (gr_complex *) output_items[0];

  int i=0, o=0;
  gr_complex symbol, sample, nco;
  gr_complex interp_samp, interp_samp_mid, diffdec;
  float error_real, error_imag, symbol_error;

  if (d_prev_sample == NULL) {
      d_n_prev_sample = (int) (d_omega + 0.5);	// sps
      d_n_prev_sample *= (d_is_tdma) ? 32 : 25;	// enough for p25p1 or p25p2 sync
      d_prev_sample = (gr_complex *) calloc(d_n_prev_sample, sizeof(gr_complex));
  }

  while((o < noutput_items) && (i < ninput_items[0])) {
    while((d_mu > 1.0) && (i < ninput_items[0]))  {
	d_mu --;

        d_phase += d_freq;
  // Keep phase clamped and not walk to infinity
  while(d_phase > M_PI)
    d_phase -= M_TWOPI;
  while(d_phase < -M_PI)
    d_phase += M_TWOPI;
  
        nco = gr_expj(d_phase+d_theta);   // get the NCO value for derotating the curr
        symbol = in[i];
        sample = nco*symbol;      // get the downconverted symbol

        if (d_enable_sync_plot && d_prev_sample != NULL) {
            d_prev_sample[d_prev_sample_p] = sample;
            d_prev_sample_p ++;
            d_prev_sample_p %= d_n_prev_sample;
        }

	d_dl[d_dl_index] = sample;
	d_dl[d_dl_index + d_twice_sps] = sample;
	d_dl_index ++;
	d_dl_index = d_dl_index % d_twice_sps;

	i++;
	d_sample_count++;
	gr_complex df = symbol * conj(d_prev);
	float fmd = atan2f(df.imag(), df.real());
	d_fm_accum += fmd;
        d_fm_count ++;
	if (d_fm_count % FM_COUNT == 0) {
	d_fm = d_fm_accum / FM_COUNT;
	d_fm_accum = 0;
	}
	d_prev = symbol;
    }
    
    if(i < ninput_items[0]) {
	// to mitigate tracking drift in the event of no input signal
	// skip tracking on muted channel
	if (!d_muted) {
		float half_omega = d_omega / 2.0;
		int half_sps = (int) floorf(half_omega);
		float half_mu = d_mu + half_omega - (float) half_sps;
		if (half_mu > 1.0) {
			half_mu -= 1.0;
			half_sps += 1;
		}
		// at this point half_sps represents the whole part, and
		// half_mu the fractional part, of the halfway mark.
		// locate two points, separated by half of one symbol time
		// interp_samp is (we hope) at the optimum sampling point 
		interp_samp_mid = d_interp->interpolate(&d_dl[ d_dl_index ], d_mu);
		interp_samp = d_interp->interpolate(&d_dl[ d_dl_index + half_sps], half_mu);

		error_real = (d_last_sample.real() - interp_samp.real()) * interp_samp_mid.real();
		error_imag = (d_last_sample.imag() - interp_samp.imag()) * interp_samp_mid.imag();
		diffdec = interp_samp * conj(d_last_sample);
		if (!d_muted)	// if muted, assume channel idle (suspend tuning error checks)
			(void)slicer(std::arg(diffdec));
		d_last_sample = interp_samp;	// save for next time
#if 1
		symbol_error = error_real + error_imag; // Gardner loop error
#else
		symbol_error = ((sgn(interp_samp) - sgn(d_last_sample)) * conj(interp_samp_mid)).real();
#endif
		if (std::isnan(symbol_error)) symbol_error = 0.0;
		if (symbol_error < -1.0) symbol_error = -1.0;
		if (symbol_error >  1.0) symbol_error =  1.0;

		d_omega = d_omega + d_gain_omega * symbol_error * abs(interp_samp);  // update omega based on loop error
		d_omega = d_omega_mid + gr::branchless_clip(d_omega-d_omega_mid, d_omega_rel);   // make sure we don't walk away
#if VERBOSE_GARDNER
		fprintf(stderr, "%f\t%f\t%f\t%f\t%f\n", symbol_error, d_mu, d_omega, error_real, error_imag);
#endif
        } else {
		symbol_error = 0;
	} /* end of if (!d_muted) */
		d_mu += d_omega + d_gain_mu * symbol_error;   // update mu based on loop error

	if (!d_muted) {
		phase_error_tracking(diffdec * PT_45);
	} /* end of if (!d_muted) */

      if (d_muted)  
          out[o++] = 0.0;
      else
          out[o++] = interp_samp;
    }
  }

  #if 0
  printf("ninput_items: %d   noutput_items: %d   consuming: %d   returning: %d\n",
	 ninput_items[0], noutput_items, i, o);
  #endif

  consume_each(i);
  return o;
}

  } /* namespace op25_repeater */
} /* namespace gr */
