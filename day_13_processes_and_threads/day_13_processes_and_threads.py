"""
Processes and Threads
=====================

A comprehensive executable tutorial covering:

1. Programs, processes, and threads
2. Process address spaces and resources
3. Thread execution and shared memory
4. Process lifecycle
5. Thread lifecycle
6. Process creation
7. Thread creation
8. Concurrency and parallelism
9. Context switching
10. CPU-bound versus I/O-bound work
11. Race conditions
12. Locks and critical sections
13. RLock
14. Events
15. Conditions
16. Semaphores
17. Producer-consumer coordination
18. Thread pools
19. Process pools
20. Inter-process communication
21. Queues and pipes
22. Process isolation
23. Daemon threads
24. Deadlock
25. Starvation
26. Lock ordering
27. Shared state versus message passing
28. GIL implications in CPython
29. Performance measurement
30. Exception handling
31. Graceful shutdown
32. Practical patterns
33. Testing concurrent code
34. Common mistakes
35. Advanced implementation considerations

The examples intentionally use only the Python standard library.
"""

from __future__ import annotations

import concurrent.futures
import multiprocessing
import os
import queue
import random
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable


# ============================================================================
# 1. FUNDAMENTAL TERMINOLOGY
# ============================================================================

def section(title: str) -> None:
    """Print a clear separator for the educational examples."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def explain_fundamentals() -> None:
    section("1. Processes, threads, concurrency, and parallelism")

    print(
        """
A program is a passive collection of instructions stored on disk.

A process is a running instance of a program. A process normally has:
    - its own virtual address space
    - executable code
    - global/static data
    - heap memory
    - one or more threads
    - operating-system-managed resources
    - open files and other handles where applicable

A thread is an execution path inside a process.

Threads belonging to the same process normally share:
    - heap memory
    - global variables
    - open resources
    - process-level state

Each thread has its own:
    - program counter
    - CPU register state
    - stack
    - thread-local execution state

Concurrency means multiple tasks can make progress during overlapping periods.

Parallelism means multiple tasks are executing at the same instant, normally
on different CPU cores.

Concurrency is therefore a broader concept than parallelism.

A single-core CPU can provide concurrency by rapidly switching between tasks.
A multicore CPU can provide both concurrency and true parallel execution.
"""
    )


# ============================================================================
# 2. CURRENT PROCESS AND THREAD INFORMATION
# ============================================================================

def show_execution_identity() -> None:
    section("2. Identifying processes and threads")

    print(f"Main process ID: {os.getpid()}")
    print(f"Parent process ID: {os.getppid()}")
    print(f"Main thread ID: {threading.get_ident()}")
    print(f"Main thread name: {threading.current_thread().name}")

    print(
        """
The operating system identifies processes using process IDs.

Python identifies the currently executing thread through threading APIs.

A process can contain many threads, so a process ID and thread ID represent
different levels of execution identity.
"""
    )


# ============================================================================
# 3. THREAD CREATION
# ============================================================================

def thread_worker(worker_name: str, iterations: int = 3) -> None:
    """A simple function executed by a separate thread."""
    for iteration in range(1, iterations + 1):
        print(
            f"[thread={worker_name}] "
            f"iteration={iteration}, "
            f"thread_id={threading.get_ident()}"
        )
        time.sleep(0.05)


def demonstrate_threads() -> None:
    section("3. Creating and joining threads")

    threads: list[threading.Thread] = []

    for index in range(3):
        worker = threading.Thread(
            target=thread_worker,
            args=(f"worker-{index + 1}",),
            name=f"worker-{index + 1}",
        )
        threads.append(worker)
        worker.start()

    for worker in threads:
        worker.join()

    print("All worker threads have finished.")

    print(
        """
start() asks Python to begin execution of the target in another thread.

join() makes the calling thread wait until the target thread terminates.

A common mistake is to call the target function directly:

    thread_worker("wrong")

That executes the function immediately in the current thread instead of
creating concurrent execution.

The correct approach is:

    threading.Thread(target=thread_worker, args=("worker",)).start()
"""
    )


# ============================================================================
# 4. THREAD LIFECYCLE
# ============================================================================

def thread_lifecycle_worker() -> None:
    """Worker used to illustrate observable parts of a thread lifecycle."""
    print("Thread has started.")
    time.sleep(0.2)
    print("Thread is finishing.")


def demonstrate_thread_lifecycle() -> None:
    section("4. Thread lifecycle")

    worker = threading.Thread(
        target=thread_lifecycle_worker,
        name="lifecycle-worker",
    )

    print(f"Before start: alive={worker.is_alive()}")
    worker.start()
    print(f"After start: alive={worker.is_alive()}")
    worker.join()
    print(f"After join: alive={worker.is_alive()}")

    print(
        """
Conceptually, a thread moves through states such as:

    NEW
      |
      v
    READY/RUNNABLE <----+
      |                 |
      v                 |
    RUNNING             |
      |                 |
      +---- waiting ----+
      |
      v
    TERMINATED

The exact state model is operating-system dependent. Python does not expose
every scheduler state directly through threading.Thread.

A thread can wait because of:
    - sleep
    - I/O
    - lock acquisition
    - condition variables
    - events
    - operating-system scheduling

Termination occurs when the target function returns or an uncaught exception
terminates the thread's execution.
"""
    )


# ============================================================================
# 5. PROCESS CREATION
# ============================================================================

def process_worker(process_name: str) -> None:
    """Function executed by a separate operating-system process."""
    print(
        f"[process={process_name}] "
        f"pid={os.getpid()}, "
        f"parent_pid={os.getppid()}"
    )


def demonstrate_processes() -> None:
    section("5. Creating and joining processes")

    processes: list[multiprocessing.Process] = []

    for index in range(2):
        process = multiprocessing.Process(
            target=process_worker,
            args=(f"process-{index + 1}",),
            name=f"process-{index + 1}",
        )
        processes.append(process)
        process.start()

    for process in processes:
        process.join()

    print("All child processes have finished.")

    print(
        """
A process created through multiprocessing.Process executes independently
from the parent process.

Unlike ordinary threads, separate processes normally do not share the same
Python object memory directly.

That isolation is useful when:
    - CPU-bound work needs true parallel execution
    - failures should be isolated
    - security boundaries are important
    - independent worker processes are useful

Process creation has more overhead than thread creation because the operating
system must establish a separate process execution environment.
"""
    )


# ============================================================================
# 6. PROCESS LIFECYCLE
# ============================================================================

def demonstrate_process_lifecycle() -> None:
    section("6. Process lifecycle")

    process = multiprocessing.Process(
        target=process_worker,
        args=("lifecycle-process",),
    )

    print(f"Before start: alive={process.is_alive()}")
    process.start()
    print(f"After start: alive={process.is_alive()}")

    process.join()

    print(f"After join: alive={process.is_alive()}")
    print(f"Exit code: {process.exitcode}")

    print(
        """
A simplified process lifecycle is:

    NEW
      |
      v
    READY
      |
      v
    RUNNING
      |
      +---- WAITING/BLOCKED
      |          |
      |          +---- READY
      |
      v
    TERMINATED

The operating system scheduler determines when a runnable process receives
CPU time.

A process may terminate normally, return an exit status, be terminated by
another process, or be killed because of an operating-system-level event.
"""
    )


# ============================================================================
# 7. SHARED MEMORY DIFFERENCE
# ============================================================================

shared_thread_counter = 0


def increment_thread_counter_without_lock(iterations: int) -> None:
    global shared_thread_counter

    for _ in range(iterations):
        # The expression involves reading, computing, and writing shared state.
        # A context switch between those operations can create a race condition.
        shared_thread_counter += 1


def demonstrate_thread_shared_memory() -> None:
    section("7. Threads share process memory")

    global shared_thread_counter
    shared_thread_counter = 0

    threads = [
        threading.Thread(
            target=increment_thread_counter_without_lock,
            args=(10_000,),
        )
        for _ in range(4)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    print(f"Counter after four threads: {shared_thread_counter}")
    print(
        """
Threads can access ordinary Python objects belonging to the same process.

This is convenient, but it creates a synchronization problem.

Whenever multiple threads can modify the same mutable state, developers must
reason about:
    - atomicity
    - ordering
    - visibility
    - synchronization
    - invariants

Even when an implementation appears to produce the expected result, relying
on accidental interpreter behavior instead of explicit synchronization is
poor concurrent-programming practice.
"""
    )


# ============================================================================
# 8. LOCKS AND CRITICAL SECTIONS
# ============================================================================

class SafeCounter:
    """Counter protected by a mutex."""

    def __init__(self) -> None:
        self.value = 0
        self._lock = threading.Lock()

    def increment(self) -> None:
        # Only one thread at a time can enter this critical section.
        with self._lock:
            self.value += 1


def demonstrate_lock() -> None:
    section("8. Locks and critical sections")

    counter = SafeCounter()

    def worker() -> None:
        for _ in range(10_000):
            counter.increment()

    threads = [threading.Thread(target=worker) for _ in range(4)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    print(f"Protected counter: {counter.value}")

    print(
        """
A critical section is code that accesses shared state and must obey a
synchronization rule.

A Lock, also called a mutex, provides mutual exclusion.

The pattern:

    with lock:
        modify_shared_state()

is preferred because the lock is released automatically even if an exception
occurs.

Locks protect invariants, not merely individual lines of code.

An important design question is:

    What state must always remain consistent?

The answer determines the correct critical section.
"""
    )


# ============================================================================
# 9. RLOCK
# ============================================================================

class RecursiveLockExample:
    """Demonstrates a reentrant lock."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.value = 0

    def outer_operation(self) -> None:
        with self._lock:
            self.value += 1
            self.inner_operation()

    def inner_operation(self) -> None:
        # A normal Lock could deadlock here because the same thread would
        # attempt to acquire the lock twice. RLock permits re-entry.
        with self._lock:
            self.value += 1


def demonstrate_rlock() -> None:
    section("9. Reentrant locks")

    example = RecursiveLockExample()
    example.outer_operation()

    print(f"Value after nested locking: {example.value}")

    print(
        """
RLock is a reentrant lock.

The thread that owns an RLock may acquire it multiple times, provided it also
releases it the corresponding number of times.

RLock is useful when synchronized methods call other synchronized methods on
the same object.

It should not be selected automatically. A normal Lock is often simpler when
reentrancy is unnecessary.
"""
    )


# ============================================================================
# 10. EVENTS
# ============================================================================

def event_worker(start_event: threading.Event) -> None:
    print("Worker is waiting for the start event.")
    start_event.wait()
    print("Worker received the start event.")


def demonstrate_event() -> None:
    section("10. Event synchronization")

    start_event = threading.Event()

    worker = threading.Thread(
        target=event_worker,
        args=(start_event,),
    )

    worker.start()
    time.sleep(0.1)

    print("Main thread signals the worker.")
    start_event.set()

    worker.join()

    print(
        """
An Event is a simple signaling mechanism.

A thread can wait:

    event.wait()

Another thread can signal:

    event.set()

Events are useful for:
    - startup coordination
    - shutdown signals
    - notifying workers that a condition has become globally relevant

An Event is not a replacement for a mutex when protecting shared data.
"""
    )


# ============================================================================
# 11. CONDITIONS
# ============================================================================

class BoundedBuffer:
    """Thread-safe fixed-capacity producer-consumer buffer."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.items: list[int] = []
        self.condition = threading.Condition()

    def put(self, item: int) -> None:
        with self.condition:
            # Always use a loop because the condition may become false again
            # before this thread reacquires the lock.
            while len(self.items) >= self.capacity:
                self.condition.wait()

            self.items.append(item)
            self.condition.notify_all()

    def get(self) -> int:
        with self.condition:
            while not self.items:
                self.condition.wait()

            item = self.items.pop(0)
            self.condition.notify_all()
            return item


def demonstrate_condition() -> None:
    section("11. Condition variables")

    buffer = BoundedBuffer(capacity=2)
    consumed: list[int] = []

    def producer() -> None:
        for value in range(5):
            buffer.put(value)
            print(f"Produced {value}")
            time.sleep(0.02)

    def consumer() -> None:
        for _ in range(5):
            value = buffer.get()
            consumed.append(value)
            print(f"Consumed {value}")
            time.sleep(0.04)

    producer_thread = threading.Thread(target=producer)
    consumer_thread = threading.Thread(target=consumer)

    producer_thread.start()
    consumer_thread.start()

    producer_thread.join()
    consumer_thread.join()

    print(f"Consumed values: {consumed}")

    print(
        """
A Condition combines:
    - a lock
    - a waiting mechanism
    - notification

Conditions are useful when a thread needs to wait for a state transition.

The standard pattern is:

    with condition:
        while not predicate():
            condition.wait()
        perform_action()

The while loop is important. A wake-up does not itself guarantee that the
desired condition remains true.
"""
    )


# ============================================================================
# 12. SEMAPHORES
# ============================================================================

def demonstrate_semaphore() -> None:
    section("12. Semaphores")

    semaphore = threading.Semaphore(2)
    active_workers = 0
    active_lock = threading.Lock()
    maximum_observed = 0

    def worker(worker_id: int) -> None:
        nonlocal active_workers, maximum_observed

        with semaphore:
            with active_lock:
                active_workers += 1
                maximum_observed = max(maximum_observed, active_workers)

            print(f"Worker {worker_id} entered limited resource.")
            time.sleep(0.05)

            with active_lock:
                active_workers -= 1

    threads = [
        threading.Thread(target=worker, args=(worker_id,))
        for worker_id in range(5)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    print(f"Maximum simultaneous workers: {maximum_observed}")

    print(
        """
A semaphore maintains a count of available permits.

If the semaphore starts at 2, at most two workers can hold permits at once.

Typical uses include:
    - limiting database connections
    - limiting network requests
    - controlling access to a finite resource

A semaphore represents capacity. A lock represents mutual exclusion.
"""
    )


# ============================================================================
# 13. QUEUES AND PRODUCER-CONSUMER
# ============================================================================

def demonstrate_queue() -> None:
    section("13. Thread-safe queues")

    work_queue: queue.Queue[int | None] = queue.Queue()
    results: list[int] = []
    results_lock = threading.Lock()

    def producer() -> None:
        for value in range(10):
            work_queue.put(value)

        # Sentinel tells the consumer that no more work will be produced.
        work_queue.put(None)

    def consumer() -> None:
        while True:
            item = work_queue.get()
            try:
                if item is None:
                    return

                result = item * item

                with results_lock:
                    results.append(result)
            finally:
                work_queue.task_done()

    producer_thread = threading.Thread(target=producer)
    consumer_thread = threading.Thread(target=consumer)

    producer_thread.start()
    consumer_thread.start()

    producer_thread.join()
    work_queue.join()
    consumer_thread.join()

    print(f"Squared values: {sorted(results)}")

    print(
        """
queue.Queue is designed for safe communication between threads.

It can reduce the need for manually sharing mutable collections.

Producer-consumer architecture separates:
    producer -> creates work
    queue    -> buffers work
    consumer -> processes work

This pattern is common in servers, pipelines, background jobs, and task
processing systems.
"""
    )


# ============================================================================
# 14. THREAD POOLS
# ============================================================================

def square_number(number: int) -> int:
    """Small independent task suitable for a worker pool."""
    time.sleep(0.01)
    return number * number


def demonstrate_thread_pool() -> None:
    section("14. ThreadPoolExecutor")

    numbers = list(range(10))

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(square_number, number) for number in numbers]

        results = [future.result() for future in futures]

    print(f"Results: {results}")

    print(
        """
ThreadPoolExecutor manages a reusable group of worker threads.

Advantages:
    - avoids creating a new thread for every task
    - limits concurrency
    - simplifies result collection
    - propagates task exceptions through Future.result()

Thread pools are particularly useful for I/O-bound tasks.

For a very large number of short tasks, pool size should be chosen based on
the workload rather than arbitrarily maximizing the number of threads.
"""
    )


# ============================================================================
# 15. PROCESS POOLS
# ============================================================================

def cpu_heavy_calculation(number: int) -> int:
    """A deterministic CPU workload executed in another process."""
    total = 0

    for value in range(1, number + 1):
        total += value * value

    return total


def demonstrate_process_pool() -> None:
    section("15. ProcessPoolExecutor")

    numbers = [20_000, 22_000, 24_000, 26_000]

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=min(4, len(numbers))
    ) as executor:
        futures = [
            executor.submit(cpu_heavy_calculation, number)
            for number in numbers
        ]

        results = [future.result() for future in futures]

    print(f"CPU-task results: {results}")

    print(
        """
ProcessPoolExecutor distributes independent tasks across worker processes.

This is useful for CPU-bound workloads because separate processes can execute
Python bytecode on multiple CPU cores.

Functions submitted to a process pool should be designed to be serializable.
Large arguments and results can introduce inter-process communication overhead.

A process pool is not automatically faster. The workload must be large enough
to justify:
    - process scheduling
    - serialization
    - communication
    - process management
"""
    )


# ============================================================================
# 16. INTER-PROCESS COMMUNICATION WITH QUEUES
# ============================================================================

def process_queue_worker(
    work_queue: multiprocessing.Queue,
    result_queue: multiprocessing.Queue,
) -> None:
    """Process worker communicating through multiprocessing queues."""
    while True:
        item = work_queue.get()

        if item is None:
            break

        result_queue.put((item, item * item))


def demonstrate_process_queue() -> None:
    section("16. Inter-process communication")

    work_queue: multiprocessing.Queue = multiprocessing.Queue()
    result_queue: multiprocessing.Queue = multiprocessing.Queue()

    process = multiprocessing.Process(
        target=process_queue_worker,
        args=(work_queue, result_queue),
    )

    process.start()

    for number in range(5):
        work_queue.put(number)

    work_queue.put(None)

    results = [result_queue.get() for _ in range(5)]

    process.join()

    print(f"IPC results: {sorted(results)}")

    print(
        """
Processes do not normally share ordinary Python variables.

Inter-process communication, often abbreviated IPC, provides explicit ways
for processes to exchange data.

Common IPC mechanisms include:
    - pipes
    - queues
    - shared memory
    - sockets
    - files
    - operating-system-specific mechanisms

Message passing through a queue makes ownership and communication explicit.
"""
    )


# ============================================================================
# 17. PIPES
# ============================================================================

def pipe_worker(connection: multiprocessing.connection.Connection) -> None:
    """Child process endpoint for a multiprocessing pipe."""
    message = connection.recv()
    connection.send(message.upper())
    connection.close()


def demonstrate_pipe() -> None:
    section("17. Process pipes")

    parent_connection, child_connection = multiprocessing.Pipe()

    process = multiprocessing.Process(
        target=pipe_worker,
        args=(child_connection,),
    )

    process.start()

    parent_connection.send("hello from parent")
    response = parent_connection.recv()

    process.join()

    print(f"Pipe response: {response}")

    parent_connection.close()

    print(
        """
A Pipe creates communication endpoints.

One process can send a message and another process can receive it.

Pipes are useful when communication is relatively direct and the application
does not require a larger queueing architecture.
"""
    )


# ============================================================================
# 18. CONTEXT SWITCHING
# ============================================================================

@dataclass
class SimulatedTask:
    """A simple task used to model scheduler context switching."""

    name: str
    remaining_steps: int
    current_step: int = 0

    def run_one_time_slice(self) -> bool:
        if self.remaining_steps <= 0:
            return False

        self.current_step += 1
        self.remaining_steps -= 1

        print(
            f"Running {self.name}: "
            f"step={self.current_step}, "
            f"remaining={self.remaining_steps}"
        )

        return self.remaining_steps > 0


def simulate_round_robin_scheduler() -> None:
    section("18. Simulating context switching")

    tasks = [
        SimulatedTask("Task-A", 3),
        SimulatedTask("Task-B", 4),
        SimulatedTask("Task-C", 2),
    ]

    print(
        """
A context switch occurs when execution changes from one runnable execution
context to another.

The operating system may need to preserve and restore information such as:
    - CPU registers
    - program counter
    - stack pointer
    - scheduling state
    - memory-management state where relevant

The following example is a simplified simulation, not an implementation of
an operating-system scheduler.
"""
    )

    while any(task.remaining_steps > 0 for task in tasks):
        for task in tasks:
            if task.remaining_steps > 0:
                still_running = task.run_one_time_slice()

                if still_running:
                    print(f"Context switch away from {task.name}")
                else:
                    print(f"{task.name} has terminated.")

    print(
        """
Context switching enables concurrency but has overhead.

Too little scheduling can make interactive workloads unresponsive.

Too much switching can waste CPU time because switching itself requires work.

The operating system uses scheduling policies and hardware mechanisms to
balance responsiveness, fairness, throughput, and latency.
"""
    )


# ============================================================================
# 19. I/O-BOUND VERSUS CPU-BOUND CONCURRENCY
# ============================================================================

def io_bound_task(task_id: int) -> str:
    """Simulate waiting for external I/O."""
    time.sleep(0.1)
    return f"I/O task {task_id} complete"


def cpu_bound_task(limit: int) -> int:
    """Perform deterministic CPU work."""
    result = 0

    for number in range(limit):
        result += number * number

    return result


def demonstrate_workload_types() -> None:
    section("19. I/O-bound and CPU-bound workloads")

    print(
        """
I/O-bound work spends substantial time waiting for external operations:
    - network responses
    - disk operations
    - database operations
    - user input

Threads can be effective for I/O-bound workloads because while one task waits,
another task can make progress.

CPU-bound work spends substantial time performing computation:
    - numerical algorithms
    - image processing
    - compression
    - simulations

In standard CPython, the Global Interpreter Lock (GIL) limits simultaneous
execution of Python bytecode by multiple threads in the usual CPython build.
Therefore, threads are generally not the primary mechanism for CPU-bound
parallelism in CPython.

Separate processes can execute Python workloads on separate CPU cores.

This distinction is a design heuristic, not an absolute rule. Native libraries
may release the GIL, and Python runtime implementations can differ.
"""
    )

    start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        io_results = list(executor.map(io_bound_task, range(5)))

    io_elapsed = time.perf_counter() - start

    print(f"I/O results: {io_results}")
    print(f"Threaded I/O elapsed time: {io_elapsed:.3f} seconds")

    start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        cpu_results = list(executor.map(cpu_bound_task, [100_000] * 4))

    cpu_thread_elapsed = time.perf_counter() - start

    print(f"CPU results generated by threads: {cpu_results}")
    print(
        f"CPU workload with threads elapsed time: "
        f"{cpu_thread_elapsed:.3f} seconds"
    )


# ============================================================================
# 20. PROCESS VERSUS THREAD COMPARISON
# ============================================================================

def print_process_thread_comparison() -> None:
    section("20. Process versus thread comparison")

    comparison = [
        ("Memory", "Separate address spaces", "Shared process memory"),
        ("Isolation", "Strong", "Weaker"),
        ("Communication", "IPC required", "Shared objects / queues"),
        ("Creation overhead", "Usually higher", "Usually lower"),
        ("Failure isolation", "Generally stronger", "Generally weaker"),
        ("Shared mutable state", "Requires IPC/shared memory", "Directly accessible"),
        ("CPU parallelism in CPython", "Suitable", "Limited by GIL for Python bytecode"),
        ("Typical strength", "CPU-bound parallel work", "I/O-bound concurrency"),
    ]

    print(f"{'Aspect':<30} {'Process':<32} Thread")
    print("-" * 78)

    for aspect, process_value, thread_value in comparison:
        print(f"{aspect:<30} {process_value:<32} {thread_value}")

    print(
        """
The correct choice depends on the workload and its constraints.

Use processes when isolation or CPU parallelism is important.

Use threads when shared-memory concurrency or I/O overlap is convenient.

Use asynchronous programming when the workload consists of many cooperative
I/O operations and the programming model benefits from an event loop.

Concurrency is an architectural decision, not simply a performance switch.
"""
    )


# ============================================================================
# 21. RACE CONDITIONS
# ============================================================================

class BankAccount:
    """Intentionally simple account used to demonstrate synchronization."""

    def __init__(self, balance: int) -> None:
        self.balance = balance

    def withdraw_unsafe(self, amount: int) -> bool:
        if self.balance >= amount:
            # The sleep makes the timing window easier to observe.
            time.sleep(0.01)
            self.balance -= amount
            return True

        return False


def demonstrate_race_condition() -> None:
    section("21. Race conditions")

    account = BankAccount(100)

    results: list[bool] = []

    def withdraw() -> None:
        results.append(account.withdraw_unsafe(80))

    first = threading.Thread(target=withdraw)
    second = threading.Thread(target=withdraw)

    first.start()
    second.start()

    first.join()
    second.join()

    print(f"Withdrawal results: {results}")
    print(f"Final balance: {account.balance}")

    print(
        """
A race condition occurs when the result depends on the unpredictable timing
or ordering of concurrent operations.

The unsafe operation follows:

    check balance
    wait
    subtract amount

Two threads can both observe the same old balance before either performs the
subtraction.

The underlying problem is that the check and update are logically one
transaction but were not protected as one critical section.
"""
    )


# ============================================================================
# 22. FIXING THE RACE CONDITION
# ============================================================================

class ThreadSafeBankAccount:
    """Bank account with a lock protecting the balance invariant."""

    def __init__(self, balance: int) -> None:
        self.balance = balance
        self._lock = threading.Lock()

    def withdraw(self, amount: int) -> bool:
        with self._lock:
            if self.balance < amount:
                return False

            time.sleep(0.01)
            self.balance -= amount
            return True


def demonstrate_race_condition_fix() -> None:
    section("22. Protecting a shared invariant")

    account = ThreadSafeBankAccount(100)
    results: list[bool] = []
    results_lock = threading.Lock()

    def withdraw() -> None:
        result = account.withdraw(80)

        with results_lock:
            results.append(result)

    threads = [
        threading.Thread(target=withdraw)
        for _ in range(2)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    print(f"Safe withdrawal results: {results}")
    print(f"Final safe balance: {account.balance}")

    print(
        """
The lock protects the complete invariant:

    balance >= amount
    followed by
    balance = balance - amount

This is more important than protecting individual statements.

Synchronization must cover the complete logical operation whose correctness
depends on shared state.
"""
    )


# ============================================================================
# 23. DEADLOCK
# ============================================================================

def demonstrate_deadlock_concept() -> None:
    section("23. Deadlock")

    print(
        """
A deadlock occurs when concurrent execution reaches a state where tasks
cannot proceed because each is waiting for resources held by another.

A classic two-lock example is:

    Thread A:
        acquire Lock 1
        acquire Lock 2

    Thread B:
        acquire Lock 2
        acquire Lock 1

Possible sequence:

    A owns Lock 1
    B owns Lock 2
    A waits for Lock 2
    B waits for Lock 1

Neither can continue.

The four classic Coffman conditions are:

    1. Mutual exclusion
    2. Hold and wait
    3. No preemption
    4. Circular wait

Deadlock prevention strategies include:
    - consistent lock ordering
    - minimizing lock scope
    - avoiding unnecessary nested locks
    - using timed lock acquisition where appropriate
    - reducing shared mutable state
    - preferring message passing

The example is described rather than intentionally executed so the tutorial
does not permanently block itself.
"""
    )


# ============================================================================
# 24. LOCK ORDERING
# ============================================================================

def demonstrate_lock_ordering() -> None:
    section("24. Preventing deadlock through lock ordering")

    account_a_lock = threading.Lock()
    account_b_lock = threading.Lock()

    def transfer_using_consistent_order() -> None:
        # Every transfer acquires locks in the same deterministic order.
        first, second = sorted(
            (account_a_lock, account_b_lock),
            key=id,
        )

        with first:
            with second:
                print("Transfer performed with consistent lock ordering.")

    threads = [
        threading.Thread(target=transfer_using_consistent_order)
        for _ in range(2)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    print(
        """
Consistent global lock ordering prevents circular wait when all participating
operations follow the same ordering rule.

A practical rule is:

    If multiple locks are required, acquire them in one deterministic order.
"""
    )


# ============================================================================
# 25. STARVATION AND FAIRNESS
# ============================================================================

def explain_starvation() -> None:
    section("25. Starvation and fairness")

    print(
        """
Starvation occurs when a runnable task repeatedly fails to obtain the CPU or
a required resource because other tasks continuously receive preference.

Possible causes include:
    - unfair scheduling
    - excessive lock contention
    - priority differences
    - one task repeatedly reacquiring a resource

Starvation differs from deadlock.

Deadlock means the affected tasks are mutually blocked.

Starvation means a task may remain capable of proceeding but does not receive
a reasonable opportunity.

Fairness is an important concern in schedulers, thread pools, databases,
resource managers, and distributed systems.
"""
    )


# ============================================================================
# 26. DAEMON THREADS
# ============================================================================

def demonstrate_daemon_thread() -> None:
    section("26. Daemon threads")

    stop_event = threading.Event()

    def background_worker() -> None:
        while not stop_event.is_set():
            print("Daemon-style background worker is active.")
            stop_event.wait(0.03)

    worker = threading.Thread(
        target=background_worker,
        daemon=True,
        name="background-worker",
    )

    worker.start()
    time.sleep(0.08)
    stop_event.set()
    worker.join(timeout=1)

    print(f"Worker stopped: {not worker.is_alive()}")

    print(
        """
A daemon thread is intended for background work that should not prevent the
Python process from exiting when all non-daemon threads have finished.

Daemon status should not be used as a substitute for graceful shutdown.

Background services should preferably have an explicit shutdown mechanism,
such as an Event, queue sentinel, or another lifecycle protocol.
"""
    )


# ============================================================================
# 27. GRACEFUL SHUTDOWN
# ============================================================================

def demonstrate_graceful_shutdown() -> None:
    section("27. Graceful thread shutdown")

    stop_event = threading.Event()

    def worker() -> None:
        while not stop_event.is_set():
            print("Worker performing periodic work.")
            stop_event.wait(0.03)

        print("Worker received shutdown request.")

    thread = threading.Thread(target=worker)
    thread.start()

    time.sleep(0.1)
    stop_event.set()
    thread.join()

    print("Worker terminated cleanly.")

    print(
        """
Graceful shutdown means allowing a concurrent component to:
    - receive a stop request
    - finish or cancel appropriate work
    - release resources
    - exit predictably

A shared boolean can work in simple situations, but Event provides a clearer
synchronization primitive for one-way signaling.
"""
    )


# ============================================================================
# 28. FUTURES AND EXCEPTION HANDLING
# ============================================================================

def task_that_can_fail(value: int) -> int:
    if value == 0:
        raise ValueError("Zero is not a valid task input.")

    return 100 // value


def demonstrate_future_exceptions() -> None:
    section("28. Exceptions in concurrent tasks")

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(task_that_can_fail, value)
            for value in [5, 0, 10]
        ]

        for future in futures:
            try:
                print(f"Task result: {future.result()}")
            except ValueError as error:
                print(f"Task failed safely: {error}")

    print(
        """
A Future represents a result that may become available later.

future.result():
    - returns the task's result when complete
    - raises the task's exception in the calling thread

This is preferable to silently ignoring worker failures.

A production system should define what happens when:
    - one worker fails
    - several workers fail
    - a task times out
    - cancellation is requested
    - partial results are available
"""
    )


# ============================================================================
# 29. TIMEOUTS
# ============================================================================

def slow_task() -> str:
    time.sleep(0.2)
    return "finished"


def demonstrate_timeout() -> None:
    section("29. Waiting with timeouts")

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(slow_task)

        try:
            result = future.result(timeout=0.05)
            print(result)
        except concurrent.futures.TimeoutError:
            print("Task did not finish within the requested timeout.")

        # The executor context still waits for the worker to finish before
        # leaving the with block.
        print(f"Eventually completed: {future.result()}")

    print(
        """
A timeout limits how long the caller waits.

A timeout does not necessarily terminate the underlying task.

This distinction is important:

    waiting timeout != task cancellation

Production systems must explicitly design cancellation and cleanup behavior.
"""
    )


# ============================================================================
# 30. CANCELLATION
# ============================================================================

def cancellable_worker(stop_event: threading.Event) -> int:
    completed_units = 0

    for _ in range(20):
        if stop_event.is_set():
            break

        time.sleep(0.01)
        completed_units += 1

    return completed_units


def demonstrate_cooperative_cancellation() -> None:
    section("30. Cooperative cancellation")

    stop_event = threading.Event()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(cancellable_worker, stop_event)

        time.sleep(0.05)
        stop_event.set()

        completed = future.result()

    print(f"Units completed before cancellation: {completed}")

    print(
        """
Cancellation is often cooperative.

The worker periodically checks a cancellation signal and exits at a safe
point.

Calling Future.cancel() does not forcibly stop a task that is already running.

Forceful termination is dangerous because arbitrary code may be holding:
    - locks
    - files
    - sockets
    - database transactions
    - partially updated data

Safe cancellation therefore depends on task design.
"""
    )


# ============================================================================
# 31. CONTEXT SWITCHING AND SCHEDULER CONCEPTS
# ============================================================================

def explain_scheduler_concepts() -> None:
    section("31. Scheduler concepts")

    print(
        """
The operating-system scheduler chooses which runnable execution context
should receive CPU time.

Important concepts include:

Preemption
    The operating system can interrupt a running task and schedule another.

Time slice / quantum
    A scheduling interval used by some scheduling policies.

Priority
    A relative scheduling preference.

Throughput
    Amount of useful work completed per unit of time.

Latency
    Time between an event/request and the desired response.

Response time
    Time experienced by a user or caller before receiving a response.

Fairness
    Reasonable allocation of CPU or resources among competing tasks.

Context-switch overhead
    Work required to save and restore execution state.

CPU cache effects
    Switching between workloads can affect cache locality and therefore
    performance.

The exact scheduler implementation depends on the operating system and its
configuration.
"""
    )


# ============================================================================
# 32. CONTEXT SWITCHING COST
# ============================================================================

def demonstrate_thread_overhead() -> None:
    section("32. Concurrency overhead")

    def tiny_task() -> int:
        return 1

    start = time.perf_counter()

    for _ in range(1_000):
        tiny_task()

    sequential_elapsed = time.perf_counter() - start

    start = time.perf_counter()

    threads = [
        threading.Thread(target=tiny_task)
        for _ in range(100)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    threaded_elapsed = time.perf_counter() - start

    print(f"Sequential tiny calls: {sequential_elapsed:.6f} seconds")
    print(f"Creating 100 threads: {threaded_elapsed:.6f} seconds")

    print(
        """
Very small tasks often do not benefit from creating one thread per task.

Thread creation, scheduling, synchronization, and context switching have
costs.

For short tasks, a pool can amortize worker-management overhead.

For extremely small operations, ordinary sequential execution may be faster.

Benchmarking should be performed on representative workloads rather than
assuming concurrency automatically improves performance.
"""
    )


# ============================================================================
# 33. THREAD-SAFE COLLECTION DESIGN
# ============================================================================

class ThreadSafeList:
    """Simple list abstraction protected by a lock."""

    def __init__(self) -> None:
        self._items: list[int] = []
        self._lock = threading.Lock()

    def append(self, item: int) -> None:
        with self._lock:
            self._items.append(item)

    def snapshot(self) -> list[int]:
        with self._lock:
            return list(self._items)


def demonstrate_thread_safe_collection() -> None:
    section("33. Encapsulating synchronization")

    collection = ThreadSafeList()

    def worker(start: int) -> None:
        for value in range(start, start + 100):
            collection.append(value)

    threads = [
        threading.Thread(target=worker, args=(start,))
        for start in [0, 100, 200, 300]
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    snapshot = collection.snapshot()

    print(f"Collection length: {len(snapshot)}")
    print(f"First values: {sorted(snapshot)[:10]}")
    print(f"Last values: {sorted(snapshot)[-10:]}")

    print(
        """
Encapsulating synchronization inside an abstraction is safer than exposing
shared mutable data and asking every caller to remember locking rules.

A useful design principle is:

    Make ownership and synchronization rules explicit at the API boundary.
"""
    )


# ============================================================================
# 34. IMMUTABILITY AND MESSAGE PASSING
# ============================================================================

@dataclass(frozen=True)
class WorkMessage:
    """Immutable message passed between concurrent components."""

    task_id: int
    payload: int


def demonstrate_message_passing() -> None:
    section("34. Reducing shared state through message passing")

    work_queue: queue.Queue[WorkMessage | None] = queue.Queue()
    output_queue: queue.Queue[tuple[int, int]] = queue.Queue()

    def producer() -> None:
        for task_id in range(5):
            work_queue.put(
                WorkMessage(task_id=task_id, payload=task_id + 10)
            )

        work_queue.put(None)

    def consumer() -> None:
        while True:
            message = work_queue.get()

            try:
                if message is None:
                    return

                output_queue.put(
                    (message.task_id, message.payload * 2)
                )
            finally:
                work_queue.task_done()

    producer_thread = threading.Thread(target=producer)
    consumer_thread = threading.Thread(target=consumer)

    producer_thread.start()
    consumer_thread.start()

    producer_thread.join()
    work_queue.join()
    consumer_thread.join()

    results = []

    while not output_queue.empty():
        results.append(output_queue.get())

    print(f"Message-passing results: {sorted(results)}")

    print(
        """
Message passing can reduce the amount of shared mutable state.

Instead of allowing multiple workers to directly modify one complex object,
workers can receive messages and produce new messages.

Immutable messages are especially useful because their contents cannot be
changed accidentally after creation.
"""
    )


# ============================================================================
# 35. BARRIER
# ============================================================================

def demonstrate_barrier() -> None:
    section("35. Barrier synchronization")

    barrier = threading.Barrier(3)

    def worker(worker_id: int) -> None:
        print(f"Worker {worker_id} completed phase 1.")
        barrier.wait()
        print(f"Worker {worker_id} started phase 2.")

    threads = [
        threading.Thread(target=worker, args=(worker_id,))
        for worker_id in range(3)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    print(
        """
A Barrier allows a fixed number of participating threads to wait until all
participants reach the same synchronization point.

This is useful for phased algorithms:

    Phase 1
       |
    barrier
       |
    Phase 2

A barrier must be designed carefully because failure or unexpected departure
of a participant can prevent the remaining participants from progressing.
"""
    )


# ============================================================================
# 36. THREAD-LOCAL STATE
# ============================================================================

def demonstrate_thread_local_storage() -> None:
    section("36. Thread-local storage")

    local_data = threading.local()

    def worker(worker_id: int) -> None:
        local_data.worker_id = worker_id
        time.sleep(0.01)

        print(
            f"Thread {threading.get_ident()} "
            f"sees local worker_id={local_data.worker_id}"
        )

    threads = [
        threading.Thread(target=worker, args=(worker_id,))
        for worker_id in range(3)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    print(
        """
threading.local() provides attributes that are local to the current thread.

This can be useful for context that should not be shared across workers.

Thread-local storage should not be used merely to hide shared-state design
problems. Excessive thread-local state can make program behavior harder to
reason about.
"""
    )


# ============================================================================
# 37. PROCESS ISOLATION
# ============================================================================

process_global_value = 10


def process_isolation_worker() -> None:
    global process_global_value
    process_global_value = 99

    print(
        f"Child process changed its own value to {process_global_value}"
    )


def demonstrate_process_isolation() -> None:
    section("37. Process memory isolation")

    global process_global_value
    process_global_value = 10

    process = multiprocessing.Process(
        target=process_isolation_worker,
    )

    process.start()
    process.join()

    print(f"Parent process value remains: {process_global_value}")

    print(
        """
The child process changes its own process memory.

The parent's ordinary Python variable does not become 99.

This isolation is one of the major differences between processes and threads.

When processes need shared data, explicit IPC or shared-memory mechanisms are
required.
"""
    )


# ============================================================================
# 38. MULTIPROCESSING SHARED VALUE WITH LOCK
# ============================================================================

def shared_value_worker(
    shared_value: multiprocessing.Value,
    iterations: int,
) -> None:
    for _ in range(iterations):
        with shared_value.get_lock():
            shared_value.value += 1


def demonstrate_process_shared_memory() -> None:
    section("38. Explicit shared process state")

    shared_value = multiprocessing.Value("i", 0)

    processes = [
        multiprocessing.Process(
            target=shared_value_worker,
            args=(shared_value, 1_000),
        )
        for _ in range(3)
    ]

    for process in processes:
        process.start()

    for process in processes:
        process.join()

    print(f"Shared process value: {shared_value.value}")

    print(
        """
multiprocessing.Value provides a simple shared value between processes.

The value is still shared mutable state and therefore needs synchronization
when multiple processes modify it.

The get_lock() mechanism protects the read-modify-write operation.

Shared memory improves communication speed in some workloads but increases
the complexity of synchronization and correctness.
"""
    )


# ============================================================================
# 39. PROCESS START METHODS
# ============================================================================

def explain_process_start_methods() -> None:
    section("39. Process start methods")

    available = multiprocessing.get_all_start_methods()
    current = multiprocessing.get_start_method(allow_none=True)

    print(f"Available start methods: {available}")
    print(f"Current configured method: {current}")

    print(
        """
Python multiprocessing can use platform-dependent process-start strategies.

Common methods include:

spawn
    Starts a fresh Python interpreter and imports the necessary program state.

fork
    Creates a child by duplicating the parent's process state at the operating
    system level. This method has important platform and multithreading
    considerations.

forkserver
    Uses a dedicated server process to create workers on systems supporting it.

The available methods and defaults depend on the platform and Python version.

Code that creates processes should normally protect the program entry point:

    if __name__ == "__main__":
        main()

This is particularly important when using spawn.
"""
    )


# ============================================================================
# 40. ASYNCHRONOUS CONCURRENCY COMPARISON
# ============================================================================

def explain_async_comparison() -> None:
    section("40. Threads, processes, and asynchronous execution")

    print(
        """
Threads
    Multiple execution threads share a process's memory.

Processes
    Multiple isolated operating-system processes execute independently.

Async tasks
    Cooperative tasks run within an event-loop model and explicitly yield
    control at await points.

Threads are often convenient for blocking I/O APIs.

Processes are often appropriate for CPU-bound Python workloads requiring
parallelism.

Async programming can efficiently manage large numbers of concurrent I/O
operations when the involved libraries support asynchronous APIs.

These models can also be combined. For example, an asynchronous server may
delegate CPU-heavy work to a process pool.
"""
    )


# ============================================================================
# 41. THREAD SAFETY
# ============================================================================

def explain_thread_safety() -> None:
    section("41. Thread safety")

    print(
        """
Thread-safe code remains correct when called concurrently according to its
documented contract.

Important concepts include:

Atomic operation
    An operation that appears indivisible to other observers under the relevant
    concurrency model.

Race condition
    Correctness depends on timing or ordering that is not controlled.

Data race
    Concurrent conflicting memory accesses where at least one is a write and
    synchronization requirements are violated.

Critical section
    A region requiring controlled access.

Invariant
    A condition that must remain true for an object or system.

Linearizability
    A concurrency correctness property in which operations appear to occur
    atomically at some point between invocation and completion.

Thread-safe does not mean:
    - automatically fast
    - free of deadlocks
    - free of starvation
    - logically correct under every usage pattern

An API can be internally synchronized and still be incorrectly used as part
of a larger unsynchronized transaction.
"""
    )


# ============================================================================
# 42. DEBUGGING CONCURRENT PROGRAMS
# ============================================================================

def demonstrate_debugging_information() -> None:
    section("42. Debugging concurrent execution")

    def worker(worker_id: int) -> None:
        print(
            f"worker={worker_id}, "
            f"thread={threading.current_thread().name}, "
            f"thread_id={threading.get_ident()}, "
            f"pid={os.getpid()}"
        )

    threads = [
        threading.Thread(
            target=worker,
            args=(worker_id,),
            name=f"debug-worker-{worker_id}",
        )
        for worker_id in range(3)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    print(
        """
Concurrent bugs can be difficult because timing changes when diagnostics are
added.

Useful debugging information includes:
    - process ID
    - thread name
    - thread ID
    - timestamps
    - task IDs
    - lock ownership information
    - queue sizes where meaningful
    - lifecycle events

Logging is generally preferable to scattered print statements in production.

Deterministic tests, stress tests, timeouts, assertions, and explicit
synchronization protocols are valuable tools for finding concurrency bugs.
"""
    )


# ============================================================================
# 43. CONCURRENT TESTING
# ============================================================================

def test_thread_safe_counter() -> None:
    """Executable correctness test for SafeCounter."""
    counter = SafeCounter()

    threads = [
        threading.Thread(
            target=lambda: [
                counter.increment()
                for _ in range(1_000)
            ]
        )
        for _ in range(4)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    expected = 4_000

    assert counter.value == expected, (
        f"Expected {expected}, got {counter.value}"
    )


def demonstrate_concurrent_testing() -> None:
    section("43. Testing concurrent code")

    test_thread_safe_counter()

    print("Thread-safe counter test passed.")

    print(
        """
Concurrent tests should validate invariants rather than rely only on exact
execution ordering.

Good tests may check:
    - final state
    - resource limits
    - absence of lost updates
    - shutdown completion
    - exception propagation
    - timeout behavior
    - queue accounting

Stress testing can repeat operations many times and use varied timing.

A test that passes once does not prove a concurrent program is race-free.
"""
    )


# ============================================================================
# 44. COMMON MISTAKES
# ============================================================================

def explain_common_mistakes() -> None:
    section("44. Common mistakes")

    print(
        """
1. Starting threads without joining when completion is required
   Result: the main workflow may proceed before work is finished.

2. Sharing mutable state without a synchronization strategy
   Result: race conditions and inconsistent state.

3. Holding locks while performing slow I/O
   Result: unnecessary contention and poor throughput.

4. Acquiring locks in inconsistent order
   Result: possible deadlock.

5. Creating one thread for every tiny task
   Result: excessive overhead and resource consumption.

6. Assuming timeout means cancellation
   Result: the task can continue running after the caller stops waiting.

7. Ignoring worker exceptions
   Result: silent task failure.

8. Using daemon threads as the only shutdown mechanism
   Result: resources may not be cleaned up predictably.

9. Passing huge objects to process workers
   Result: serialization and IPC overhead.

10. Assuming threads automatically provide CPU parallelism in CPython
    Result: poor expectations for CPU-bound Python code.

11. Using a lock around everything
    Result: reduced concurrency and potentially complicated deadlocks.

12. Using no lock because one individual operation appears atomic
    Result: larger multi-step invariants can still fail.

13. Assuming a scheduler gives a predictable order
    Result: flaky tests and timing-dependent bugs.

14. Sleeping to coordinate threads
    Result: fragile timing assumptions. Prefer Events, Conditions, Queues,
    Barriers, or other synchronization primitives.
"""
    )


# ============================================================================
# 45. PERFORMANCE DESIGN
# ============================================================================

def explain_performance() -> None:
    section("45. Performance considerations")

    print(
        """
Concurrency performance depends on more than CPU count.

Important factors include:

Task granularity
    Tasks should be large enough to justify scheduling and communication cost.

Contention
    Many workers competing for one lock can serialize the program.

Lock duration
    Long critical sections reduce concurrency.

Queue overhead
    Passing many tiny messages can become expensive.

Serialization
    Process-based communication may require converting objects into a
    transferable representation.

Memory usage
    More processes and threads require additional resources.

Cache locality
    Frequent switching between working sets can reduce locality.

Oversubscription
    Too many runnable workers can increase scheduling overhead.

Amdahl's law
    The maximum speedup of a parallel program is limited by the fraction of
    work that remains sequential.

Benchmarking
    Measure realistic workloads instead of assuming a concurrency mechanism
    will improve performance.
"""
    )


# ============================================================================
# 46. SECURITY CONSIDERATIONS
# ============================================================================

def explain_security() -> None:
    section("46. Security considerations")

    print(
        """
Concurrency introduces security concerns in addition to ordinary application
security.

TOCTOU
    Time-of-check to time-of-use vulnerabilities occur when a resource is
    checked and then used later while another actor can change it between the
    operations.

Shared state
    Incorrect synchronization can violate authorization, accounting, or
    transactional invariants.

Resource exhaustion
    Unbounded threads, processes, queues, or tasks can consume CPU and memory.

IPC boundaries
    Inter-process communication should be treated as a communication boundary.
    Do not assume incoming data is trustworthy merely because it came from
    another process.

Process isolation
    Separate processes can provide stronger fault boundaries, but process
    isolation is not automatically a complete security sandbox.

Privilege separation
    Sensitive work can sometimes be isolated into a component with fewer
    privileges.

Production systems should use bounded resources, validate data, control
permissions, and define failure behavior explicitly.
"""
    )


# ============================================================================
# 47. PRODUCTION ARCHITECTURE
# ============================================================================

def explain_production_design() -> None:
    section("47. Production design considerations")

    print(
        """
A production concurrent system should define:

Ownership
    Which component owns each resource?

Lifecycle
    How are workers started, monitored, restarted, and stopped?

Backpressure
    What happens when producers are faster than consumers?

Capacity
    How many concurrent tasks are allowed?

Failure handling
    What happens when one worker crashes?

Timeout policy
    How long may an operation wait?

Cancellation
    How is work stopped safely?

Observability
    How are latency, errors, queue depth, worker health, and throughput
    measured?

Consistency
    Which state changes must be atomic?

Recovery
    Can unfinished work be retried safely?

Idempotency
    Can an operation safely be repeated?

A good concurrent design is usually based on explicit contracts rather than
implicit timing assumptions.
"""
    )


# ============================================================================
# 48. PRACTICAL WORKER SYSTEM
# ============================================================================

@dataclass
class Job:
    job_id: int
    value: int


class WorkerSystem:
    """
    Small production-style thread worker system.

    Features:
        - bounded queue
        - multiple workers
        - graceful shutdown
        - explicit ownership
        - result collection
        - synchronization
    """

    def __init__(self, worker_count: int = 3, queue_size: int = 5) -> None:
        if worker_count <= 0:
            raise ValueError("worker_count must be positive")

        if queue_size <= 0:
            raise ValueError("queue_size must be positive")

        self._queue: queue.Queue[Job | None] = queue.Queue(
            maxsize=queue_size
        )
        self._results: dict[int, int] = {}
        self._results_lock = threading.Lock()
        self._workers: list[threading.Thread] = []

        for worker_id in range(worker_count):
            thread = threading.Thread(
                target=self._worker,
                args=(worker_id,),
                name=f"job-worker-{worker_id}",
            )
            self._workers.append(thread)

    def start(self) -> None:
        for worker in self._workers:
            worker.start()

    def submit(self, job: Job) -> None:
        self._queue.put(job)

    def _worker(self, worker_id: int) -> None:
        while True:
            job = self._queue.get()

            try:
                if job is None:
                    return

                result = job.value * job.value

                with self._results_lock:
                    self._results[job.job_id] = result

                print(
                    f"Worker {worker_id} completed job {job.job_id}"
                )
            finally:
                self._queue.task_done()

    def wait_for_jobs(self) -> None:
        self._queue.join()

    def shutdown(self) -> None:
        # One sentinel per worker ensures every worker eventually exits.
        for _ in self._workers:
            self._queue.put(None)

        for worker in self._workers:
            worker.join()

    def results(self) -> dict[int, int]:
        with self._results_lock:
            return dict(self._results)


def demonstrate_worker_system() -> None:
    section("48. Complete worker-system example")

    system = WorkerSystem(worker_count=3, queue_size=4)

    system.start()

    for job_id in range(8):
        system.submit(
            Job(
                job_id=job_id,
                value=job_id + 1,
            )
        )

    system.wait_for_jobs()
    system.shutdown()

    print(f"Final job results: {system.results()}")

    print(
        """
This example combines several concepts:

    producer
        |
        v
    bounded queue
        |
        +---- worker 1
        +---- worker 2
        +---- worker 3
        |
        v
    synchronized results

The bounded queue provides backpressure.

Workers reuse threads rather than creating a thread per job.

A sentinel provides an explicit shutdown protocol.

The result dictionary is protected by a lock.

This architecture resembles many real systems, although production
applications require stronger monitoring, retry policies, persistence,
timeouts, and failure handling.
"""
    )


# ============================================================================
# 49. DESIGN TRADE-OFFS
# ============================================================================

def explain_tradeoffs() -> None:
    section("49. Design trade-offs")

    print(
        """
Shared memory
    Advantages:
        - fast direct access
        - convenient object sharing
    Costs:
        - synchronization complexity
        - race conditions
        - difficult ownership reasoning

Message passing
    Advantages:
        - clearer ownership
        - reduced shared mutable state
        - easier component boundaries
    Costs:
        - copying/serialization
        - queue management
        - communication overhead

Threads
    Advantages:
        - relatively lightweight
        - shared memory
        - convenient for blocking I/O
    Costs:
        - shared-state bugs
        - GIL considerations in CPython
        - synchronization complexity

Processes
    Advantages:
        - stronger isolation
        - CPU parallelism
    Costs:
        - higher overhead
        - IPC complexity
        - serialization costs

Locks
    Advantages:
        - direct mutual exclusion
        - simple for small critical sections
    Costs:
        - contention
        - deadlocks
        - reduced concurrency

Async execution
    Advantages:
        - efficient large-scale I/O concurrency
        - explicit cooperative scheduling
    Costs:
        - requires compatible async APIs
        - blocking calls can stall the event loop
        - different programming model
"""
    )


# ============================================================================
# 50. MINI DECISION GUIDE
# ============================================================================

def concurrency_decision_guide() -> None:
    section("50. Choosing a concurrency model")

    print(
        """
Question 1:
Is the workload mostly waiting on I/O?

    Yes -> threads or asynchronous programming may be appropriate.

Question 2:
Is the workload CPU-bound Python computation?

    Yes -> consider processes for true parallelism in standard CPython.

Question 3:
Do workers need extensive shared mutable state?

    Yes -> threads may be convenient, but carefully design synchronization.

Question 4:
Can work be represented as independent messages?

    Yes -> a worker pool and queue can simplify the design.

Question 5:
Is strong fault isolation important?

    Yes -> separate processes may be preferable.

Question 6:
Are there thousands of mostly idle network operations?

    Async I/O may be more resource-efficient than thousands of threads.

There is no universal best concurrency model.
"""
    )


# ============================================================================
# 51. INTEGRATED DEMONSTRATION
# ============================================================================

def integrated_concurrency_demo() -> None:
    section("51. Integrated concurrency demonstration")

    results: queue.Queue[str] = queue.Queue()

    def worker(worker_id: int) -> None:
        for item in range(3):
            # Simulated I/O wait.
            time.sleep(random.uniform(0.01, 0.03))

            results.put(
                f"worker-{worker_id} processed item-{item}"
            )

    threads = [
        threading.Thread(
            target=worker,
            args=(worker_id,),
            name=f"integrated-worker-{worker_id}",
        )
        for worker_id in range(3)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    messages = []

    while not results.empty():
        messages.append(results.get())

    for message in sorted(messages):
        print(message)

    print(
        """
The exact order in which messages are produced is not guaranteed.

This is a fundamental property of concurrent execution.

If an application requires a specific order, the order must be represented
explicitly through:
    - sequence numbers
    - synchronization
    - ordered result collection
    - dependency management

Do not rely on timing accidents.
"""
    )


# ============================================================================
# 52. MAIN EXECUTION
# ============================================================================

def main() -> None:
    """
    Execute the complete tutorial.

    The entry-point guard is essential for multiprocessing portability,
    especially on platforms using the spawn start method.
    """
    explain_fundamentals()
    show_execution_identity()
    demonstrate_threads()
    demonstrate_thread_lifecycle()
    demonstrate_processes()
    demonstrate_process_lifecycle()
    demonstrate_thread_shared_memory()
    demonstrate_lock()
    demonstrate_rlock()
    demonstrate_event()
    demonstrate_condition()
    demonstrate_semaphore()
    demonstrate_queue()
    demonstrate_thread_pool()
    demonstrate_process_pool()
    demonstrate_process_queue()
    demonstrate_pipe()
    simulate_round_robin_scheduler()
    demonstrate_workload_types()
    print_process_thread_comparison()
    demonstrate_race_condition()
    demonstrate_race_condition_fix()
    demonstrate_deadlock_concept()
    demonstrate_lock_ordering()
    explain_starvation()
    demonstrate_daemon_thread()
    demonstrate_graceful_shutdown()
    demonstrate_future_exceptions()
    demonstrate_timeout()
    demonstrate_cooperative_cancellation()
    explain_scheduler_concepts()
    demonstrate_thread_overhead()
    demonstrate_thread_safe_collection()
    demonstrate_message_passing()
    demonstrate_barrier()
    demonstrate_thread_local_storage()
    demonstrate_process_isolation()
    demonstrate_process_shared_memory()
    explain_process_start_methods()
    explain_async_comparison()
    explain_thread_safety()
    demonstrate_debugging_information()
    demonstrate_concurrent_testing()
    explain_common_mistakes()
    explain_performance()
    explain_security()
    explain_production_design()
    demonstrate_worker_system()
    explain_tradeoffs()
    concurrency_decision_guide()
    integrated_concurrency_demo()

    section("53. Tutorial completed")
    print(
        "All process, thread, concurrency, lifecycle, synchronization, "
        "context-switching, performance, debugging, and production examples "
        "have completed."
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
