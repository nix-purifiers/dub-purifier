# SPDX-License-Identifier: MIT
import ctypes, json, pathlib, sys
import purifier_native

p = pathlib.Path(sys.argv[1]).resolve()
assert pathlib.Path(purifier_native.LIBRARIES["purifier-native-proof"]).resolve() == p
d = purifier_native.load("purifier-native-proof")
assert d.purifier_module_value() == 0
assert d.purifier_init() == 1
assert d.purifier_module_value() == 40
assert [d.purifier_answer(), d.purifier_answer()] == [42, 43]


class DlInfo(ctypes.Structure):
    _fields_ = [
        ("fname", ctypes.c_char_p),
        ("base", ctypes.c_void_p),
        ("sname", ctypes.c_char_p),
        ("saddr", ctypes.c_void_p),
    ]


info = DlInfo()
host = ctypes.CDLL(None)
assert (
    host.dladdr(ctypes.cast(d.purifier_answer, ctypes.c_void_p), ctypes.byref(info))
    != 0
)
assert pathlib.Path(info.fname.decode()).resolve() == p
catalog = json.loads(
    (pathlib.Path(purifier_native.__file__).parent / "catalog.json").read_text()
)
compiler = pathlib.Path(
    catalog["targets"]["purifier-native-proof"]["compiler"]["path"]
).resolve()
assert host.dladdr(ctypes.cast(d.rt_init, ctypes.c_void_p), ctypes.byref(info)) != 0
assert pathlib.Path(info.fname.decode()).resolve().is_relative_to(compiler / "lib")

import threading

worker_values = []


def worker():
    d.purifier_thread_enter()
    worker_values.extend([d.purifier_answer(), d.purifier_answer()])
    d.purifier_thread_leave()


t = threading.Thread(target=worker)
t.start()
t.join(timeout=5)
assert not t.is_alive() and worker_values == [42, 43], worker_values
assert d.purifier_answer() == 44
assert d.purifier_term() == 1
print(
    json.dumps(
        {
            "values": [42, 43],
            "origin": str(p),
            "runtimeOrigin": info.fname.decode(),
            "explicitRuntimeInitTerm": True,
            "gcAndTls": True,
        }
    )
)
