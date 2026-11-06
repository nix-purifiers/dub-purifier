// SPDX-License-Identifier: MIT
import java.lang.foreign.*;
import java.lang.invoke.*;
import java.nio.file.*;
public class NativeConsumer {
  public static void main(String[] args) throws Throwable {
    Path expected = Path.of(args[0]).toRealPath();
    Linker linker = Linker.nativeLinker();
    Arena libraryArena = args.length>1 && args[1].equals("confined") ? Arena.ofConfined() : Arena.global();
    SymbolLookup lib = SymbolLookup.libraryLookup(expected, libraryArena);
    FunctionDescriptor descriptor = FunctionDescriptor.of(ValueLayout.JAVA_INT);
    MethodHandle init = linker.downcallHandle(lib.find("purifier_init").orElseThrow(), descriptor);
    MethodHandle call = linker.downcallHandle(lib.find("purifier_answer").orElseThrow(), descriptor);
    MethodHandle term = linker.downcallHandle(lib.find("purifier_term").orElseThrow(), descriptor);
    if ((int)init.invokeExact()!=1) throw new AssertionError("init");
    if ((int)call.invokeExact()!=42 || (int)call.invokeExact()!=43) throw new AssertionError("values");
    try (Arena a = Arena.ofConfined()) {
      MemorySegment info = a.allocate(4 * ValueLayout.ADDRESS.byteSize(), ValueLayout.ADDRESS.byteAlignment());
      MethodHandle dladdr = linker.downcallHandle(linker.defaultLookup().find("dladdr").orElseThrow(),
        FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.ADDRESS, ValueLayout.ADDRESS));
      if ((int)dladdr.invokeExact(lib.find("purifier_answer").orElseThrow(), info)==0) throw new AssertionError("dladdr");
      String origin = info.get(ValueLayout.ADDRESS,0).reinterpret(4096).getString(0);
      if (!Path.of(origin).toRealPath().equals(expected)) throw new AssertionError(origin);
    }
    if ((args.length<2 || !args[1].equals("retain")) && (int)term.invokeExact()!=1) throw new AssertionError("term");
    if (args.length>1 && args[1].equals("confined")) libraryArena.close();
    System.out.println("Java FFM values42/43 + origin passed; mode="+(args.length>1?args[1]:"term"));
  }
}
