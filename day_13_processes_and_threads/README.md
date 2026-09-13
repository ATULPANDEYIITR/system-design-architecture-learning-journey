# Processes and threads

## Introduction

Processes and threads are fundamental operating-system concepts used to execute multiple tasks concurrently. They explain how modern operating systems run applications, distribute CPU time, coordinate independent activities, and manage shared resources.

A **process** is a running instance of a program. A process normally owns an independent virtual address space and operating-system resources. A process contains one or more **threads**, which are execution paths responsible for carrying out instructions.

A **thread** is a unit of execution within a process. Threads belonging to the same process normally share the process's heap, global data, and many operating-system resources. Each thread maintains its own execution state, including a stack and CPU register context.

The Python script associated with this README progresses from basic process and thread concepts to synchronization, context switching, inter-process communication, worker pools, concurrency hazards, performance considerations, security concerns, and production-oriented design.

## Programs, processes, and threads

A program is a passive collection of instructions and data stored on a storage device. It does not execute merely because it exists as a file.

A process is an active execution instance of a program. When an operating system launches an application, it creates a process and assigns resources to that execution environment.

A process commonly contains:

- executable instructions
- global and static data
- heap memory
- one or more thread stacks
- CPU execution state
- operating-system-managed resources
- open files or handles
- networking resources where applicable

A process may contain a single thread or multiple threads.

A thread represents an execution path inside a process. Multiple threads in one process can execute different functions or different portions of the same application.

## Process memory and thread memory

One of the most important distinctions is memory ownership.

Separate processes normally have separate virtual address spaces. A Python variable created in one process is not automatically the same variable in another process.

Threads within the same process normally share:

- heap objects
- global variables
- application state
- open resources

Each thread maintains execution-specific state such as:

- program counter
- CPU register context
- stack
- thread-local data

This difference explains both the convenience and danger of threads.

Shared memory makes communication easy because a thread can directly access an object created by another thread. The same property creates opportunities for race conditions and inconsistent state.

Processes provide stronger isolation, but communication requires explicit mechanisms such as queues, pipes, sockets, files, or shared-memory facilities.

## Process lifecycle

A simplified process lifecycle can be represented conceptually as:

NEW → READY → RUNNING → TERMINATED

A running process can also enter waiting or blocked states. It may wait for I/O, synchronization resources, another process, or an operating-system event.

A simplified model is:

NEW → READY → RUNNING → WAITING → READY → RUNNING → TERMINATED

The exact state names and transitions depend on the operating system and scheduler.

The Python multiprocessing example demonstrates creation of a process, starting it, waiting for it with `join()`, and inspecting its exit status.

A process may terminate normally or because of an error, explicit termination, or an external operating-system event.

## Thread lifecycle

Threads have a similar conceptual lifecycle.

A newly created thread has not started execution. Calling `start()` begins its execution. A running thread can become blocked while waiting for a lock, I/O operation, event, condition, or other resource.

The conceptual states are:

NEW → READY/RUNNABLE → RUNNING → TERMINATED

A thread may move between runnable and waiting states many times before termination.

Python does not expose every scheduler state directly through `threading.Thread`. Operating-system scheduling happens beneath the Python threading API.

## Creating threads

Python provides the `threading.Thread` class for explicit thread creation.

A thread is normally created with:

- a target function
- optional positional arguments
- optional keyword arguments
- a name
- daemon configuration

Calling `start()` begins concurrent execution.

Calling `join()` waits for the thread to terminate.

Calling the target function directly is not equivalent to starting a thread. Direct invocation executes the function in the current thread.

Joining is important when the program must wait for worker completion before continuing.

## Creating processes

Python's `multiprocessing` module provides process-based concurrency.

A `multiprocessing.Process` can execute a target function in a separate process.

The parent can start the process and later call `join()` to wait for its termination.

Process creation normally has greater overhead than thread creation because a separate process execution environment must be established and managed.

Processes are especially useful when:

- CPU-bound work needs parallel execution
- stronger isolation is desirable
- independent workers are appropriate
- failure boundaries between components are valuable

## Concurrency and parallelism

**Concurrency** means multiple tasks can make progress during overlapping periods.

**Parallelism** means multiple tasks execute at the same instant, generally on separate CPU cores.

These concepts are related but not identical.

A single CPU core can provide concurrency by rapidly switching between runnable tasks. A multicore processor can execute multiple tasks simultaneously.

A useful distinction is:

- concurrency concerns overlapping progress
- parallelism concerns simultaneous execution

A system can therefore be concurrent without being parallel.

## Context switching

A **context switch** occurs when the system changes execution from one runnable execution context to another.

The saved execution context can include information such as:

- CPU registers
- program counter
- stack pointer
- scheduling state
- memory-management information where applicable

The operating system saves the current execution context and restores the context of another runnable task.

Context switching makes time-sharing and multitasking possible.

It also introduces overhead. The processor performs work to save and restore execution state, and switching between working sets can affect CPU cache locality.

The Python script contains a simplified round-robin scheduler simulation. The simulation illustrates the conceptual idea of time slices and switching between tasks. It is not an implementation of a real operating-system scheduler.

## Scheduling

The operating-system scheduler decides which runnable execution context should receive CPU time.

Important scheduling concepts include:

### Preemption

Preemption occurs when the operating system interrupts a running task so another task can execute.

### Time slice

A time slice, or quantum, is a scheduling interval used by certain scheduling strategies.

### Priority

Priority represents a relative scheduling preference between competing tasks.

### Throughput

Throughput measures how much useful work a system completes during a period.

### Latency

Latency measures the delay between an event or request and the desired response.

### Response time

Response time is the time experienced by the user or calling system before receiving a response.

### Fairness

Fairness concerns whether competing tasks receive reasonable opportunities to execute or obtain resources.

Scheduling policies differ across operating systems and configurations. Application developers should not assume that threads will execute in a predictable order.

## I/O-bound and CPU-bound workloads

The type of workload strongly influences the appropriate concurrency model.

An **I/O-bound** task spends substantial time waiting for external operations such as:

- network responses
- disk access
- database operations
- user input
- remote services

Threads can be effective for I/O-bound work because one thread can make progress while another is waiting.

A **CPU-bound** task spends most of its time performing computation. Examples include:

- numerical calculations
- simulations
- compression
- image processing
- complex transformations

In standard CPython, the Global Interpreter Lock, commonly called the **GIL**, limits simultaneous execution of Python bytecode by multiple threads in the usual CPython configuration.

As a result, threads are generally not the primary mechanism for achieving CPU parallelism for ordinary Python bytecode.

Separate processes can execute independently on multiple CPU cores.

This is a practical rule rather than an absolute law. Native libraries can release the GIL, and Python implementations and execution environments can differ.

## Threads versus processes

The main distinctions are:

| Aspect | Processes | Threads |
|---|---|---|
| Memory | Separate address spaces | Shared process memory |
| Isolation | Stronger | Weaker |
| Communication | Explicit IPC normally required | Shared objects or thread-safe queues |
| Creation overhead | Usually higher | Usually lower |
| Failure isolation | Generally stronger | Generally weaker |
| Shared mutable state | Requires explicit mechanisms | Directly accessible |
| CPU parallelism in standard CPython | Suitable | Limited for Python bytecode by the GIL |
| Common use | CPU-bound parallel workloads | I/O-bound concurrent workloads |

Neither model is universally superior.

Threads are attractive when shared memory is useful and tasks frequently wait for I/O.

Processes are attractive when CPU parallelism, isolation, or independent worker execution is important.

## Shared memory

Threads can directly access shared objects within a process.

This makes communication convenient but creates the need for synchronization.

Suppose multiple threads execute:

1. read a shared value
2. calculate a new value
3. write the new value

A context switch between these operations can allow another thread to observe or modify intermediate state.

This creates the possibility of a **race condition**.

## Race conditions

A race condition occurs when the correctness of a program depends on the unpredictable timing or ordering of concurrent operations.

A common example is a bank account.

Suppose the account contains 100 units and two threads simultaneously attempt to withdraw 80 units.

Both threads could perform:

1. check whether balance is at least 80
2. observe balance as 100
3. wait
4. subtract 80

The logical operation should have been indivisible.

The problem is not merely that two statements execute simultaneously. The problem is that the application invariant was not protected across the complete logical transaction.

## Critical sections

A **critical section** is a region of code that accesses shared state under a synchronization rule.

For example, a bank account's withdrawal operation may need to guarantee:

`balance >= amount`

before performing:

`balance = balance - amount`

The check and update belong to the same critical section.

Locks can enforce this requirement.

## Locks

A lock, or mutex, provides mutual exclusion.

When one thread owns the lock, another thread attempting to acquire the same lock must wait until the owner releases it.

Python commonly uses:

`threading.Lock`

The preferred style is to use a context manager so the lock is reliably released:

`with lock:`

Locks should protect logical invariants rather than arbitrary individual statements.

Holding a lock for too long reduces concurrency.

Holding a lock while performing slow I/O is often undesirable because unrelated workers may remain blocked while the operation completes.

## Reentrant locks

Python provides `threading.RLock`, a reentrant lock.

A thread that already owns an RLock can acquire it again.

This is useful when synchronized methods call other synchronized methods on the same object.

A normal Lock can deadlock if the same thread attempts to acquire it again without releasing it first.

RLock tracks ownership and acquisition depth so that nested acquisition by the owning thread is supported.

RLock should not be used automatically. A normal Lock is simpler when reentrancy is not required.

## Events

An Event is a signaling primitive.

One thread can wait for an event:

`event.wait()`

Another thread can signal it:

`event.set()`

Events are useful for:

- startup coordination
- global state changes
- shutdown requests
- one-way notifications

An Event is not a replacement for a lock. It signals a condition but does not automatically protect shared mutable data.

## Condition variables

A Condition combines a lock with a mechanism for waiting until a state becomes appropriate.

A producer-consumer system can use a Condition to wait when:

- a buffer is full
- a buffer is empty

The standard conceptual pattern is:

`with condition:`

followed by:

`while not predicate:`

and:

`condition.wait()`

The `while` loop is important because being awakened does not necessarily mean the desired condition remains true.

Conditions are appropriate for state-dependent coordination.

## Semaphores

A semaphore represents a limited number of permits.

If a semaphore starts with two permits, at most two workers can hold the resource simultaneously.

Semaphores are useful for controlling access to finite resources such as:

- database connections
- external service capacity
- network request limits
- worker slots

A lock usually represents mutual exclusion.

A semaphore represents a capacity limit.

This distinction is important when designing resource management.

## Queues and producer-consumer systems

A thread-safe queue provides a useful communication mechanism between producers and consumers.

The basic architecture is:

Producer → Queue → Consumer

The producer creates work and places it into the queue.

The consumer retrieves work and processes it.

A queue can provide buffering and help decouple producer and consumer speeds.

A bounded queue provides **backpressure**.

If the queue has limited capacity and producers are faster than consumers, producers eventually wait instead of creating unlimited work.

Backpressure is important for preventing uncontrolled memory growth and resource exhaustion.

## Queue task accounting

Python's `queue.Queue` provides `task_done()` and `join()` for task accounting.

A worker calls `task_done()` after processing a queue item.

The main thread can call `join()` to wait until all queued items have been marked complete.

This is different from thread joining.

`thread.join()` waits for a specific thread to terminate.

`queue.join()` waits for all queued work to be acknowledged as completed.

## Thread pools

`ThreadPoolExecutor` provides reusable worker threads.

A thread pool avoids repeatedly creating and destroying threads for independent tasks.

Advantages include:

- simpler worker management
- reusable threads
- controlled concurrency
- Future-based result handling
- straightforward exception propagation

Thread pools are commonly useful for I/O-bound tasks.

The correct pool size depends on the workload, external resource limits, and the desired level of concurrency.

More threads do not automatically mean better performance.

## Process pools

`ProcessPoolExecutor` provides a pool of worker processes.

It is useful for independent CPU-bound tasks.

Process pools can achieve real parallel execution across CPU cores because workers are separate processes.

There are costs:

- process management
- task serialization
- data transfer
- result transfer
- process startup

For very small tasks, these costs can exceed the computational benefit.

Task granularity is therefore an important performance consideration.

## Futures

A Future represents a result that becomes available later.

Submitting a task to an executor produces a Future.

Calling `future.result()` waits for completion and returns the result.

If the worker raised an exception, `future.result()` propagates that exception to the caller.

This makes Futures useful for explicit error handling.

Ignoring Future results can cause worker failures to remain unnoticed.

## Timeouts

A timeout controls how long a caller waits.

It does not necessarily terminate the underlying task.

This distinction is essential:

**waiting timeout is not the same as task cancellation**

A caller can stop waiting while a worker continues executing.

Production systems must separately define:

- timeout behavior
- cancellation behavior
- cleanup
- retry behavior
- partial result handling

## Cooperative cancellation

Running threads cannot generally be safely terminated by abruptly killing their execution.

A safer approach is cooperative cancellation.

A worker periodically checks a signal such as an Event.

When cancellation is requested, the worker exits at a safe point.

This allows the worker to release resources and maintain data consistency.

Cancellation is especially important for tasks involving:

- locks
- files
- sockets
- transactions
- external services

## Daemon threads

A daemon thread is a background thread that does not normally prevent the Python process from exiting after all non-daemon threads have completed.

Daemon status should not be treated as a complete shutdown strategy.

A production background worker should have an explicit shutdown protocol.

Useful mechanisms include:

- Events
- queue sentinels
- cancellation flags
- controlled lifecycle methods

Explicit shutdown makes resource cleanup predictable.

## Deadlock

A deadlock occurs when concurrent tasks become permanently blocked because each is waiting for resources held by another task.

A classic situation involves two locks:

Thread A acquires Lock 1 and waits for Lock 2.

Thread B acquires Lock 2 and waits for Lock 1.

Neither can proceed.

The four classic Coffman conditions are:

1. Mutual exclusion
2. Hold and wait
3. No preemption
4. Circular wait

Deadlock prevention can include:

- consistent lock ordering
- minimizing lock scope
- avoiding unnecessary nested locks
- timed lock acquisition
- reducing shared mutable state
- using message passing

The tutorial intentionally explains deadlock without creating an actual permanent deadlock.

## Lock ordering

A practical deadlock-prevention technique is consistent lock ordering.

If every operation that needs multiple locks acquires them in the same deterministic order, circular wait can be prevented.

For example, two resources can be ordered by a stable identifier. Every operation then acquires the lower-ordered resource first.

This rule must be applied consistently across all relevant code paths.

## Starvation

Starvation differs from deadlock.

In deadlock, tasks are mutually blocked.

In starvation, a task may remain capable of executing but repeatedly fails to receive sufficient CPU time or access to a resource.

Potential causes include:

- unfair scheduling
- excessive lock contention
- priority differences
- repeated resource acquisition by competing workers

Fairness is important in schedulers and resource-management systems.

## Barrier synchronization

A Barrier allows a fixed number of participants to wait until all participants reach the same point.

This is useful for phased algorithms:

Phase 1 → Barrier → Phase 2

For example, several workers may independently prepare data and then wait until all workers have completed preparation before beginning the next phase.

A barrier must be designed carefully because one missing participant can prevent other participants from progressing.

## Thread-local storage

Thread-local storage provides data that is specific to the current thread.

Python's `threading.local()` can be used when a worker needs private contextual state.

Thread-local storage can be useful for:

- request context
- per-thread temporary state
- worker-specific metadata

It should not be used merely to hide poorly designed shared state.

Excessive thread-local state can make program behavior harder to understand.

## Process isolation

Separate processes normally have separate memory.

If a child process changes an ordinary global variable, the parent's copy does not automatically change.

This isolation provides a useful boundary.

It can help with:

- CPU parallelism
- fault containment
- resource separation
- independent worker architecture

When processes need shared data, explicit IPC or shared-memory facilities are necessary.

## Inter-process communication

**Inter-process communication**, or IPC, provides mechanisms for exchanging information between processes.

Common mechanisms include:

- queues
- pipes
- sockets
- files
- shared memory
- operating-system-specific IPC facilities

The tutorial demonstrates multiprocessing queues and pipes.

A queue is useful when many work items must be distributed.

A pipe is useful for relatively direct communication between endpoints.

IPC introduces communication overhead, so data transfer should be designed deliberately.

## Shared process state

Python's multiprocessing module provides mechanisms such as `multiprocessing.Value` for simple shared state.

Shared process memory must still be synchronized.

If multiple processes perform a read-modify-write operation without synchronization, race conditions can occur.

The script protects a shared counter using the lock associated with the shared value.

Shared memory can be efficient, but it increases synchronization complexity.

## Process start methods

Python multiprocessing supports different process start methods depending on the platform.

Important methods include:

### spawn

A fresh Python interpreter is started and required program state is initialized.

### fork

The child process is created using operating-system process duplication. It has important interactions with inherited state and multithreading.

### forkserver

A dedicated server process creates child processes on systems that support this mechanism.

Available methods and defaults depend on the operating system and Python version.

For portable multiprocessing code, process creation should normally be protected by:

`if __name__ == "__main__":`

This is particularly important with the `spawn` method.

## Threads, processes, and asynchronous programming

Threads and processes are not the only concurrency models.

Asynchronous programming uses cooperative tasks managed by an event loop.

The main distinctions are:

### Threads

Multiple execution threads share a process's memory.

They are convenient for blocking I/O and workloads that benefit from shared memory.

### Processes

Multiple isolated operating-system processes execute independently.

They are useful for CPU-bound parallel work and stronger isolation.

### Asynchronous tasks

Many lightweight tasks cooperate within an event-loop model and explicitly yield control.

Async programming can be efficient for large numbers of I/O operations when compatible asynchronous APIs are available.

These models can be combined. For example, an asynchronous application can delegate CPU-heavy computation to a process pool.

## Thread safety

A component is **thread-safe** when its behavior remains correct under the concurrent usage patterns described by its contract.

Important concepts include:

### Atomicity

An operation is atomic when it is treated as indivisible under the relevant concurrency model.

### Race condition

The result depends on uncontrolled timing or ordering.

### Data race

Conflicting concurrent memory accesses occur without the synchronization required by the programming model.

### Critical section

A region that requires controlled access to shared state.

### Invariant

A condition that must remain true for an object or system.

Thread safety is not equivalent to overall application correctness.

An internally synchronized class can still be used incorrectly if several calls must be treated as one larger transaction.

## Message passing

Message passing reduces the need for shared mutable state.

Instead of multiple workers directly modifying a complex shared object, components can exchange messages.

A message can represent:

- a request
- a work item
- a result
- a status update
- a shutdown instruction

Immutable messages make reasoning easier because their contents cannot be changed after creation.

The script demonstrates this approach using a frozen dataclass and a queue.

## Worker systems

A worker system commonly contains:

Producer → Bounded Queue → Worker Pool → Results

The example worker system in the script demonstrates:

- multiple reusable threads
- bounded queue capacity
- producer submission
- worker processing
- synchronized result storage
- queue task accounting
- sentinel-based shutdown

This structure resembles common background-job and task-processing architectures.

Production systems require additional concerns such as persistent queues, retry policies, monitoring, timeouts, failure recovery, idempotency, and resource limits.

## Backpressure

Backpressure occurs when a producer is required to slow down because downstream processing cannot keep up.

A bounded queue is one way to implement backpressure.

Without backpressure, a fast producer can continually create tasks while consumers remain overloaded.

This can cause:

- memory growth
- increased latency
- resource exhaustion
- cascading failures

Backpressure is therefore an important production design concept.

## Exception handling in concurrent programs

Concurrent programs require explicit error-handling policies.

Questions include:

- What happens if one worker fails?
- Should other workers continue?
- Should failed work be retried?
- Is the operation idempotent?
- Should partial results be retained?
- Should the entire job be cancelled?
- How is the failure reported?

Executors make worker exceptions accessible through Futures.

Production applications should not silently discard concurrent task failures.

## Graceful shutdown

A concurrent system should define how workers stop.

A typical shutdown sequence is:

1. signal shutdown
2. prevent new work where appropriate
3. allow current safe work to complete
4. release resources
5. wait for workers
6. terminate the component cleanly

Queue sentinels and Events are useful for implementing shutdown protocols.

Graceful shutdown is especially important for long-running services.

## Performance considerations

Concurrency has overhead.

Important performance factors include:

### Task granularity

A task must be large enough for the concurrency mechanism to justify its management cost.

### Lock contention

If many workers compete for one lock, the protected section can become a serialization point.

### Lock duration

Long critical sections reduce the amount of useful parallel progress.

### Queue overhead

Very large numbers of tiny messages can make communication expensive.

### Serialization

Process-based communication can require objects to be serialized and transferred.

### Memory

Additional processes and threads consume resources.

### Context switching

Frequent switching creates scheduling overhead and can affect cache locality.

### Oversubscription

Creating more runnable workers than the hardware and workload require can increase scheduling overhead.

### Amdahl's law

A parallel program's maximum speedup is limited by the portion of work that remains sequential.

For example, if a workload contains a large sequential component, increasing the number of workers eventually produces diminishing returns.

Benchmarking should use representative workloads rather than assuming concurrency will improve performance.

## Security considerations

Concurrency can create security issues as well as ordinary correctness problems.

### Time-of-check to time-of-use

A resource may be checked and then used later, allowing another actor to change it between those operations.

### Shared-state integrity

Incorrect synchronization can corrupt authorization, accounting, inventory, or transaction state.

### Resource exhaustion

Unbounded thread creation, process creation, queue growth, or task submission can exhaust system resources.

### IPC boundaries

Data received from another process should still be validated.

Communication between trusted components does not automatically eliminate the need for validation.

### Process isolation

Processes provide stronger isolation than threads in many respects, but process boundaries should not automatically be treated as complete security sandboxes.

### Privilege separation

Sensitive operations can sometimes be isolated into components with fewer privileges.

Concurrent systems should enforce bounded resources, explicit permissions, input validation, and well-defined failure behavior.

## Debugging concurrent programs

Concurrent bugs are often difficult to reproduce because timing affects execution order.

Adding logging can itself change timing.

Useful diagnostic information includes:

- process ID
- thread ID
- thread name
- timestamps
- task IDs
- queue state
- lifecycle events
- resource acquisition and release information

Structured logging is generally preferable to scattered print statements in production systems.

Testing should focus on invariants rather than assuming a particular thread execution order.

## Testing concurrent code

A concurrency test should verify properties that must always remain true.

Examples include:

- expected final counters
- bounded resource usage
- absence of lost updates
- correct queue accounting
- correct shutdown
- exception propagation
- timeout behavior
- cancellation behavior

Stress testing can execute operations repeatedly under varied timing.

A single successful execution does not prove a concurrent system is race-free.

## Common mistakes

Common concurrency errors include:

### Forgetting to join required workers

The main thread may continue before worker operations are complete.

### Sharing mutable state without synchronization

This can cause race conditions.

### Holding locks during slow I/O

This can unnecessarily serialize unrelated operations.

### Acquiring locks inconsistently

This can create deadlocks.

### Creating a thread for every tiny operation

Thread management overhead can exceed the actual useful work.

### Treating a timeout as cancellation

The underlying operation may continue after the caller stops waiting.

### Ignoring worker exceptions

A failed task may silently leave the system incomplete.

### Using daemon threads as the only shutdown mechanism

Resource cleanup may become unpredictable.

### Passing unnecessarily large data to processes

Serialization and IPC can become a major performance cost.

### Assuming threads automatically provide CPU parallelism in standard CPython

The GIL limits simultaneous execution of Python bytecode in the usual CPython configuration.

### Using locks everywhere

Excessive locking reduces concurrency and can make deadlocks more likely.

### Coordinating workers with arbitrary sleeps

Sleeping is not a reliable synchronization mechanism. Events, Conditions, Queues, and Barriers provide explicit coordination semantics.

## Production design considerations

A production concurrent architecture should explicitly define:

### Ownership

Which component owns each resource?

### Lifecycle

How are workers started, monitored, restarted, and stopped?

### Capacity

How many tasks may execute simultaneously?

### Backpressure

What happens when producers generate work faster than consumers process it?

### Failure handling

What happens when a worker crashes?

### Timeout policy

How long can an operation wait?

### Cancellation

How can work be stopped safely?

### Observability

How are errors, latency, throughput, queue depth, and worker health measured?

### Consistency

Which operations must be atomic?

### Recovery

Can unfinished work be recovered after a process or machine failure?

### Idempotency

Can an operation safely be executed more than once?

Explicit lifecycle and ownership contracts make concurrent systems substantially easier to reason about.

## Practical applications

Processes and threads are used in many real systems.

### Web servers

A server may use multiple workers or threads to handle concurrent requests.

### Database systems

Connection pools and worker pools control concurrent database operations.

### Background job systems

Producers submit work to queues while worker processes or threads consume jobs.

### Data processing

Large datasets can be partitioned into independent tasks and processed concurrently.

### Scientific computing

CPU-intensive numerical workloads can use process-based parallelism or native numerical libraries.

### Networking

Concurrent execution allows a program to manage multiple connections and external services.

### Desktop applications

Background workers can prevent long-running operations from blocking user interfaces.

### Operating systems

The operating system itself uses scheduling and execution contexts to provide multitasking.

## Implementation principles

A sound concurrency design generally follows these principles:

- minimize shared mutable state
- define ownership explicitly
- protect complete logical invariants
- keep critical sections small
- use deterministic lock ordering
- prefer message passing where practical
- bound queues and resources
- reuse workers through pools when appropriate
- propagate exceptions
- design explicit cancellation
- design graceful shutdown
- avoid timing-based synchronization
- benchmark representative workloads
- test concurrent invariants
- monitor production behavior

The most important architectural decision is not simply whether to use threads or processes. It is determining how work, state, ownership, synchronization, communication, failure, and lifecycle should interact.
