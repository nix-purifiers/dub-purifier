from pathlib import Path
import sys

path = Path(sys.argv[1]) / "source/workspaced/com/dcd.d"
source = path.read_text()
if "import workspaced.process_lifecycle" not in source:
    source = source.replace(
        "import workspaced.api;",
        "import workspaced.api;\nimport workspaced.process_lifecycle : pollChild, waitChild, killChild;",
    )
    needle = "\t\tserverThreads.create({"
    assert source.count(needle) == 1
    source = source.replace(needle, "\t\tauto serverPid = serverPipes.pid;\n" + needle)
    assert source.count("serverPipes.pid.wait()") == 1
    source = source.replace("serverPipes.pid.wait()", "waitChild(serverPid)")
    # The reader owns the PID it started with, even if a restart installs a
    # new ProcessPipes before the old reader finishes logging its exit.
    needle = "serverPipes.pid.kill();"
    assert source.count(needle) == 2
    source = source.replace(needle, "killChild(serverPid);", 1)
    source = source.replace(needle, "killChild(serverPipes.pid);")
    assert source.count("serverPipes.pid.tryWait()") == 3
    source = source.replace("serverPipes.pid.tryWait()", "pollChild(serverPipes.pid)")
    path.write_text(source)
