typedef unsigned long DES_KS[16][2];	/* Single-key DES key schedule */
typedef unsigned long DES3_KS[48][2];	/* Triple-DES key schedule */

/* In deskey.c: */
void deskey(DES_KS,unsigned char *,int);
void des3key(DES3_KS,unsigned char *,int);

/* In desport.c, desborl.cas or desgnu.s: */
void des(DES_KS,unsigned char *);
/* In des3port.c, des3borl.cas or des3gnu.s: */
void des3(DES3_KS,unsigned char *);

extern int Asmversion;	/* 1 if we're linked with an asm version, 0 if C */


