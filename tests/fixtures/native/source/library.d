// SPDX-License-Identifier: MIT
module library;
import core.runtime : rt_init, rt_term;
import core.memory : GC;
import core.thread : thread_attachThis, thread_detachThis;
__gshared int moduleValue;
int calls;
shared static this() { moduleValue = 40; }
extern(C) export int purifier_init() { return rt_init(); }
extern(C) export int purifier_term() { return rt_term(); }
extern(C) export int purifier_answer() {
  auto values = new int[1];
  values[0] = moduleValue + 1 + ++calls;
  auto result = values[0];
  GC.collect();
  return result;
}

extern(C) export void purifier_thread_enter() { thread_attachThis(); }
extern(C) export void purifier_thread_leave() { thread_detachThis(); }

extern(C) export int purifier_module_value() { return moduleValue; }
