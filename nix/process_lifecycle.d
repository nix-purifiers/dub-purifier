module workspaced.process_lifecycle;

import core.thread : Thread;
import core.time : msecs;
import std.process : Pid, kill, tryWait;

// Phobos caches a child's exit status in Pid without synchronization. All
// users of a shared child must serialize waitpid and access to that cache.
auto pollChild(Pid child)
{
    synchronized (child)
    {
        return tryWait(child);
    }
}

int waitChild(Pid child)
{
    while (true)
    {
        auto result = pollChild(child);
        if (result.terminated)
            return result.status;
        // Do not hold the monitor while waiting: shutdown must remain able
        // to poll or terminate a child whose stderr closed before it exits.
        Thread.sleep(1.msecs);
    }
}

void killChild(Pid child)
{
    synchronized (child)
    {
        if (!tryWait(child).terminated)
            kill(child);
    }
}

unittest
{
    import core.sync.barrier : Barrier;
    import std.process : environment, spawnProcess;

    foreach (iteration; 0 .. 32)
    {
        auto child = spawnProcess([environment["PURIFIER_TEST_SHELL"], "-c", "exit 17"]);
        auto gate = new Barrier(5);
        Thread[] workers;
        foreach (reader; 0 .. 4)
        {
            auto worker = new Thread({
                gate.wait();
                assert(waitChild(child) == 17);
            });
            workers ~= worker;
            worker.start();
        }
        gate.wait();
        assert(waitChild(child) == 17);
        foreach (worker; workers)
            worker.join();
        assert(pollChild(child).terminated && pollChild(child).status == 17);
    }

    auto child = spawnProcess([environment["PURIFIER_TEST_SHELL"], "-c", "exec sleep 10"]);
    auto worker = new Thread({ waitChild(child); });
    worker.start();
    killChild(child);
    worker.join();
    assert(pollChild(child).terminated);
    // An already reaped child's PID must never be signalled again.
    killChild(child);
}
