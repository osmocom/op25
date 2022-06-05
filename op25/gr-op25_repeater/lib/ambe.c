/*
 * Copyright (C) 2010 mbelib Author
 * GPG Key ID: 0xEA5EFE2C (9E7A 5527 9CDC EBF7 BF1B  D772 4F98 E863 EA5E FE2C)
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted, provided that the above
 * copyright notice and this permission notice appear in all copies.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND ISC DISCLAIMS ALL WARRANTIES WITH
 * REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
 * AND FITNESS.  IN NO EVENT SHALL ISC BE LIABLE FOR ANY SPECIAL, DIRECT,
 * INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
 * LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE
 * OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
 * PERFORMANCE OF THIS SOFTWARE.
 */

#include <stdlib.h>
#include "mbelib.h"
#include "ambe3600x2250_const.h"
#include "ambe3600x2400_const.h"

#ifndef M_PI
# define M_PI           3.14159265358979323846  /* pi */
#endif 

#ifndef M_E
# define M_E            2.7182818284590452354   /* e */
#endif 

#ifndef M_SQRT2
# define M_SQRT2        1.41421356237309504880  /* sqrt(2) */
#endif 

static int
mbe_dequantizeAmbeParms (mbe_parms * cur_mp, mbe_parms * prev_mp, const int *b, int dstar)
{

  int ji, i, j, k, l, L, L9, m, am, ak;
  int intkl[57];
  int b0, b1, b2, b3, b4, b5, b6, b7, b8;
  float f0, Cik[5][18], flokl[57], deltal[57];
  float Sum42, Sum43, Tl[57], Gm[9], Ri[9], sum, c1, c2;
  char tmpstr[13];
  int silence;
  int Ji[5], jl;
  float deltaGamma, BigGamma;
  float unvc, rconst;

  b0 = b[0];
  b1 = b[1];
  b2 = b[2];
  b3 = b[3];
  b4 = b[4];
  b5 = b[5];
  b6 = b[6];
  b7 = b[7];
  b8 = b[8];

  silence = 0;

#ifdef AMBE_DEBUG
  printf ("\n");
#endif

  // copy repeat from prev_mp
  cur_mp->repeat = prev_mp->repeat;

  if ((b0 >= 120) && (b0 <= 123))
    {
#ifdef AMBE_DEBUG
      printf ("Erasure Frame\n");
#endif
      return (2);
    }
  else if ((b0 == 124) || (b0 == 125))
    {
#ifdef AMBE_DEBUG
      printf ("Silence Frame\n");
#endif
      silence = 1;
      cur_mp->w0 = ((float) 2 * M_PI) / (float) 32;
      f0 = (float) 1 / (float) 32;
      L = 14;
      cur_mp->L = 14;
      for (l = 1; l <= L; l++)
        {
          cur_mp->Vl[l] = 0;
        }
    }
  else if ((b0 == 126) || (b0 == 127))
    {
#ifdef AMBE_DEBUG
      printf ("Tone Frame\n");
#endif
      return (3);
    }

  if (silence == 0)
    {
      if (dstar)
        f0 = powf(2, (-4.311767578125 - (2.1336e-2 * ((float)b0+0.5))));
      else
      // w0 from specification document
        f0 = AmbeW0table[b0];
      cur_mp->w0 = f0 * (float) 2 *M_PI;
      // w0 from patent filings
      //f0 = powf (2, ((float) b0 + (float) 195.626) / -(float) 45.368);
      //cur_mp->w0 = f0 * (float) 2 *M_PI;
    }

  unvc = (float) 0.2046 / sqrtf (cur_mp->w0);
  //unvc = (float) 1;
  //unvc = (float) 0.2046 / sqrtf (f0);

  // decode L
  if (silence == 0)
    {
      // L from specification document 
      // lookup L in tabl3
      if (dstar)
        L = AmbePlusLtable[b0];
      else
        L = AmbeLtable[b0];
      // L formula form patent filings
      //L=(int)((float)0.4627 / f0);
      cur_mp->L = L;
    }
  L9 = L - 9;

  // decode V/UV parameters
  for (l = 1; l <= L; l++)
    {
      // jl from specification document
      jl = (int) ((float) l * (float) 16.0 * f0);
      // jl from patent filings?
      //jl = (int)(((float)l * (float)16.0 * f0) + 0.25);

      if (silence == 0)
        {
          if (dstar)
            cur_mp->Vl[l] = AmbePlusVuv[b1][jl];
          else
            cur_mp->Vl[l] = AmbeVuv[b1][jl];
        }
#ifdef AMBE_DEBUG
      printf ("jl[%i]:%i Vl[%i]:%i\n", l, jl, l, cur_mp->Vl[l]);
#endif
    }
#ifdef AMBE_DEBUG
  printf ("\nb0:%i w0:%f L:%i b1:%i\n", b0, cur_mp->w0, L, b1);
#endif
  if (dstar) {
    deltaGamma = AmbePlusDg[b2];
    cur_mp->gamma = deltaGamma + ((float) 0.5 * prev_mp->gamma);
  } else {
    deltaGamma = AmbeDg[b2];
    cur_mp->gamma = deltaGamma + ((float) 0.5 * prev_mp->gamma);
  }
#ifdef AMBE_DEBUG
  printf ("b2: %i, deltaGamma: %f gamma: %f gamma-1: %f\n", b2, deltaGamma, cur_mp->gamma, prev_mp->gamma);
#endif


  // decode PRBA vectors
  Gm[1] = 0;

  if (dstar) {
    Gm[2] = AmbePlusPRBA24[b3][0];
    Gm[3] = AmbePlusPRBA24[b3][1];
    Gm[4] = AmbePlusPRBA24[b3][2];

    Gm[5] = AmbePlusPRBA58[b4][0];
    Gm[6] = AmbePlusPRBA58[b4][1];
    Gm[7] = AmbePlusPRBA58[b4][2];
    Gm[8] = AmbePlusPRBA58[b4][3];
  } else {
    Gm[2] = AmbePRBA24[b3][0];
    Gm[3] = AmbePRBA24[b3][1];
    Gm[4] = AmbePRBA24[b3][2];

    Gm[5] = AmbePRBA58[b4][0];
    Gm[6] = AmbePRBA58[b4][1];
    Gm[7] = AmbePRBA58[b4][2];
    Gm[8] = AmbePRBA58[b4][3];
  }

#ifdef AMBE_DEBUG
  printf ("b3: %i Gm[2]: %f Gm[3]: %f Gm[4]: %f b4: %i Gm[5]: %f Gm[6]: %f Gm[7]: %f Gm[8]: %f\n", b3, Gm[2], Gm[3], Gm[4], b4, Gm[5], Gm[6], Gm[7], Gm[8]);
#endif

  // compute Ri
  for (i = 1; i <= 8; i++)
    {
      sum = 0;
      for (m = 1; m <= 8; m++)
        {
          if (m == 1)
            {
              am = 1;
            }
          else
            {
              am = 2;
            }
          sum = sum + ((float) am * Gm[m] * cosf ((M_PI * (float) (m - 1) * ((float) i - (float) 0.5)) / (float) 8));
        }
      Ri[i] = sum;
#ifdef AMBE_DEBUG
      printf ("R%i: %f ", i, Ri[i]);
#endif
    }
#ifdef AMBE_DEBUG
  printf ("\n");
#endif

  // generate first to elements of each Ci,k block from PRBA vector
  rconst = ((float) 1 / ((float) 2 * M_SQRT2));
  Cik[1][1] = (float) 0.5 *(Ri[1] + Ri[2]);
  Cik[1][2] = rconst * (Ri[1] - Ri[2]);
  Cik[2][1] = (float) 0.5 *(Ri[3] + Ri[4]);
  Cik[2][2] = rconst * (Ri[3] - Ri[4]);
  Cik[3][1] = (float) 0.5 *(Ri[5] + Ri[6]);
  Cik[3][2] = rconst * (Ri[5] - Ri[6]);
  Cik[4][1] = (float) 0.5 *(Ri[7] + Ri[8]);
  Cik[4][2] = rconst * (Ri[7] - Ri[8]);

  // decode HOC

  // lookup Ji
  if (dstar) {
    Ji[1] = AmbePlusLmprbl[L][0];
    Ji[2] = AmbePlusLmprbl[L][1];
    Ji[3] = AmbePlusLmprbl[L][2];
    Ji[4] = AmbePlusLmprbl[L][3];
  } else {
    Ji[1] = AmbeLmprbl[L][0];
    Ji[2] = AmbeLmprbl[L][1];
    Ji[3] = AmbeLmprbl[L][2];
    Ji[4] = AmbeLmprbl[L][3];
  }
#ifdef AMBE_DEBUG
  printf ("Ji[1]: %i Ji[2]: %i Ji[3]: %i Ji[4]: %i\n", Ji[1], Ji[2], Ji[3], Ji[4]);
  printf ("b5: %i b6: %i b7: %i b8: %i\n", b5, b6, b7, b8);
#endif

  // Load Ci,k with the values from the HOC tables
  // there appear to be a couple typos in eq. 37 so we will just do what makes sense
  // (3 <= k <= Ji and k<=6)
  for (k = 3; k <= Ji[1]; k++)
    {
      if (k > 6)
        {
          Cik[1][k] = 0;
        }
      else
        {
          if (dstar)
            Cik[1][k] = AmbePlusHOCb5[b5][k - 3];
          else
            Cik[1][k] = AmbeHOCb5[b5][k - 3];
#ifdef AMBE_DEBUG
          printf ("C1,%i: %f ", k, Cik[1][k]);
#endif
        }
    }
  for (k = 3; k <= Ji[2]; k++)
    {
      if (k > 6)
        {
          Cik[2][k] = 0;
        }
      else
        {
          if (dstar)
            Cik[2][k] = AmbePlusHOCb6[b6][k - 3];
          else
            Cik[2][k] = AmbeHOCb6[b6][k - 3];
#ifdef AMBE_DEBUG
          printf ("C2,%i: %f ", k, Cik[2][k]);
#endif
        }
    }
  for (k = 3; k <= Ji[3]; k++)
    {
      if (k > 6)
        {
          Cik[3][k] = 0;
        }
      else
        {
          if (dstar)
            Cik[3][k] = AmbePlusHOCb7[b7][k - 3];
          else
            Cik[3][k] = AmbeHOCb7[b7][k - 3];
#ifdef AMBE_DEBUG
          printf ("C3,%i: %f ", k, Cik[3][k]);
#endif
        }
    }
  for (k = 3; k <= Ji[4]; k++)
    {
      if (k > 6)
        {
          Cik[4][k] = 0;
        }
      else
        {
          if (dstar)
            Cik[4][k] = AmbePlusHOCb8[b8][k - 3];
          else
            Cik[4][k] = AmbeHOCb8[b8][k - 3];
#ifdef AMBE_DEBUG
          printf ("C4,%i: %f ", k, Cik[4][k]);
#endif
        }
    }
#ifdef AMBE_DEBUG
  printf ("\n");
#endif

  // inverse DCT each Ci,k to give ci,j (Tl)
  l = 1;
  for (i = 1; i <= 4; i++)
    {
      ji = Ji[i];
      for (j = 1; j <= ji; j++)
        {
          sum = 0;
          for (k = 1; k <= ji; k++)
            {
              if (k == 1)
                {
                  ak = 1;
                }
              else
                {
                  ak = 2;
                }
#ifdef AMBE_DEBUG
              printf ("j: %i Cik[%i][%i]: %f ", j, i, k, Cik[i][k]);
#endif
              sum = sum + ((float) ak * Cik[i][k] * cosf ((M_PI * (float) (k - 1) * ((float) j - (float) 0.5)) / (float) ji));
            }
          Tl[l] = sum;
#ifdef AMBE_DEBUG
          printf ("Tl[%i]: %f\n", l, Tl[l]);
#endif
          l++;
        }
    }

  // determine log2Ml by applying ci,j to previous log2Ml

  // fix for when L > L(-1)
  if (cur_mp->L > prev_mp->L)
    {
      for (l = (prev_mp->L) + 1; l <= cur_mp->L; l++)
        {
          prev_mp->Ml[l] = prev_mp->Ml[prev_mp->L];
          prev_mp->log2Ml[l] = prev_mp->log2Ml[prev_mp->L];
        }
    }
  prev_mp->log2Ml[0] = prev_mp->log2Ml[1];
  prev_mp->Ml[0] = prev_mp->Ml[1];

  // Part 1
  Sum43 = 0;
  for (l = 1; l <= cur_mp->L; l++)
    {

      // eq. 40
      flokl[l] = ((float) prev_mp->L / (float) cur_mp->L) * (float) l;
      intkl[l] = (int) (flokl[l]);
#ifdef AMBE_DEBUG
      printf ("flok%i: %f, intk%i: %i ", l, flokl[l], l, intkl[l]);
#endif
      // eq. 41
      deltal[l] = flokl[l] - (float) intkl[l];
#ifdef AMBE_DEBUG
      printf ("delta%i: %f ", l, deltal[l]);
#endif
      // eq 43
      Sum43 = Sum43 + ((((float) 1 - deltal[l]) * prev_mp->log2Ml[intkl[l]]) + (deltal[l] * prev_mp->log2Ml[intkl[l] + 1]));
    }
  Sum43 = (((float) 0.65 / (float) cur_mp->L) * Sum43);
#ifdef AMBE_DEBUG
  printf ("\n");
  printf ("Sum43: %f\n", Sum43);
#endif

  // Part 2
  Sum42 = 0;
  for (l = 1; l <= cur_mp->L; l++)
    {
      Sum42 += Tl[l];
    }
  Sum42 = Sum42 / (float) cur_mp->L;
  BigGamma = cur_mp->gamma - ((float) 0.5 * (log ((float) cur_mp->L) / log ((float) 2))) - Sum42;
  //BigGamma=cur_mp->gamma - ((float)0.5 * log((float)cur_mp->L)) - Sum42;

  // Part 3
  for (l = 1; l <= cur_mp->L; l++)
    {
      c1 = ((float) 0.65 * ((float) 1 - deltal[l]) * prev_mp->log2Ml[intkl[l]]);
      c2 = ((float) 0.65 * deltal[l] * prev_mp->log2Ml[intkl[l] + 1]);
      cur_mp->log2Ml[l] = Tl[l] + c1 + c2 - Sum43 + BigGamma;
      // inverse log to generate spectral amplitudes
      if (cur_mp->Vl[l] == 1)
        {
          cur_mp->Ml[l] = exp ((float) 0.693 * cur_mp->log2Ml[l]);
        }
      else
        {
          cur_mp->Ml[l] = unvc * exp ((float) 0.693 * cur_mp->log2Ml[l]);
        }
#ifdef AMBE_DEBUG
      printf ("flokl[%i]: %f, intkl[%i]: %i ", l, flokl[l], l, intkl[l]);
      printf ("deltal[%i]: %f ", l, deltal[l]);
      printf ("prev_mp->log2Ml[%i]: %f\n", l, prev_mp->log2Ml[intkl[l]]);
      printf ("BigGamma: %f c1: %f c2: %f Sum43: %f Tl[%i]: %f log2Ml[%i]: %f Ml[%i]: %f\n", BigGamma, c1, c2, Sum43, l, Tl[l], l, cur_mp->log2Ml[l], l, cur_mp->Ml[l]);
#endif
    }

  return (0);
}

int
mbe_dequantizeAmbe2400Parms (mbe_parms * cur_mp, mbe_parms * prev_mp, const int *b){
	int dstar = 1;
	return (mbe_dequantizeAmbeParms (cur_mp, prev_mp, b, dstar));
}

int
mbe_dequantizeAmbe2250Parms (mbe_parms * cur_mp, mbe_parms * prev_mp, const int *b){
	int dstar = 0;
	return (mbe_dequantizeAmbeParms (cur_mp, prev_mp, b, dstar));
}
