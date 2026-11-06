# SPDX-License-Identifier: MIT
from cffi import FFI
from pathlib import Path
import json, sys

ffi = FFI()
ffi.cdef("""
int purifier_init(void); int purifier_term(void); int purifier_answer(void);
typedef struct { const char *dli_fname; void *dli_fbase; const char *dli_sname; void *dli_saddr; } Dl_info;
int dladdr(void *, Dl_info *);
""")
p = Path(sys.argv[1]).resolve()
lib = ffi.dlopen(str(p))
host = ffi.dlopen(None)
assert lib.purifier_init() == 1
assert [lib.purifier_answer(), lib.purifier_answer()] == [42, 43]
info = ffi.new("Dl_info *")
assert host.dladdr(ffi.cast("void *", lib.purifier_answer), info) != 0
origin = ffi.string(info.dli_fname).decode()
assert Path(origin).resolve() == p
assert lib.purifier_term() == 1
print(json.dumps({"values": [42, 43], "origin": origin, "runtimeInitTerm": True}))
