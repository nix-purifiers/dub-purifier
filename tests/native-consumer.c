// SPDX-License-Identifier: MIT
#define _GNU_SOURCE
#include <dlfcn.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv) {
  assert(argc==2);
  void *lib=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL); if(!lib){puts(dlerror());return 1;}
  int (*init)(void)=dlsym(lib,"purifier_init");
  int (*term)(void)=dlsym(lib,"purifier_term");
  int (*answer)(void)=dlsym(lib,"purifier_answer");
  assert(init && term && answer && init()==1);
  assert(answer()==42 && answer()==43);
  Dl_info info; assert(dladdr(answer,&info));
  char *actual=realpath(info.dli_fname,NULL), *expected=realpath(argv[1],NULL);
  assert(actual && expected && strcmp(actual,expected)==0);
  free(actual);free(expected);assert(term()==1);
  puts("C values42/43 + origin + runtime init/term passed");
  /* Deliberately retain handle until process exit: no unloading claim. */
  return 0;
}
