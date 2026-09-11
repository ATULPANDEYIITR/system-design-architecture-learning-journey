"""
Computer Fundamentals: How Computers Work
CPU, RAM, Storage, Processes, and Threads

A self-contained study and demonstration script covering:
- Binary data and information representation
- CPU architecture and instruction execution
- Registers, ALU, control unit, clock cycles, caches
- RAM and virtual memory concepts
- Storage hierarchy and persistent storage
- Operating-system processes
- Threads and concurrency
- Context switching and scheduling
- CPU-bound vs I/O-bound work
- Process/thread memory behavior
- Race conditions, locks, deadlocks, and synchronization
- Performance measurement and bottlenecks
- Reliability, security, and production considerations

The demonstrations use only Python's standard library.
"""

from __future__ import annotations

import math
import os
import platform
import random
import statistics
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from multiprocessing import Process, Queue, Value
from queue import Queue as ThreadQueue
from typing import Callable, Iterable, Optional


# =============================================================================
# 1. FUNDAMENTAL DATA REPRESENTATION
# =============================================================================

def section(title: str) -> None:
    """Print a readable section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def subsection(title: str) -> None:
    print("\n" + "-" * 78)
    print(title)
    print("-" * 78)


def decimal_to_binary(number: int) -> str:
    """Return an integer's binary representation without using bin()."""
    if number == 0:
        return "0"

    negative = number < 0
    number = abs(number)
    bits = []

    while number:
        bits.append(str(number % 2))
        number //= 2

    result = "".join(reversed(bits))
    return "-" + result if negative else result


def binary_to_decimal(binary: str) -> int:
    """Convert a binary string to decimal manually."""
    binary = binary.strip()

    if not binary:
        raise ValueError("Binary input cannot be empty.")

    negative = binary.startswith("-")
    if negative:
        binary = binary[1:]

    if any(bit not in "01" for bit in binary):
        raise ValueError("Binary input may contain only 0 and 1.")

    value = 0
    for bit in binary:
        value = value * 2 + int(bit)

    return -value if negative else value


def demonstrate_binary() -> None:
    subsection("Binary representation")

    values = [0, 1, 2, 5, 8, 42, 255, 1024]

    for value in values:
        binary = decimal_to_binary(value)
        recovered = binary_to_decimal(binary)
        print(f"{value:>4} -> {binary:<12} -> {recovered}")

    # One byte contains eight bits and can represent 256 distinct patterns.
    print("\nAn unsigned byte has:")
    print("  bits:", 8)
    print("  possible values:", 2 ** 8)
    print("  range:", f"0 to {2 ** 8 - 1}")

    # Text is also represented as numerical data.
    text = "CPU"
    encoded = text.encode("utf-8")
    print(f"\nText: {text!r}")
    print("UTF-8 bytes:", list(encoded))
    print("Hexadecimal:", encoded.hex())


# =============================================================================
# 2. COMPUTER MEMORY HIERARCHY
# =============================================================================

@dataclass
class MemoryLevel:
    name: str
    capacity: str
    persistence: str
    relative_speed: str
    purpose: str


def demonstrate_memory_hierarchy() -> None:
    subsection("Memory hierarchy")

    hierarchy = [
        MemoryLevel(
            "CPU registers",
            "Very small",
            "Volatile",
            "Fastest",
            "Hold immediate operands and CPU state",
        ),
        MemoryLevel(
            "CPU cache",
            "Small",
            "Volatile",
            "Very fast",
            "Keeps frequently accessed data/instructions close to CPU",
        ),
        MemoryLevel(
            "RAM",
            "GBs",
            "Volatile",
            "Fast",
            "Holds active programs and data",
        ),
        MemoryLevel(
            "SSD",
            "GBs to TBs",
            "Persistent",
            "Slower than RAM",
            "Stores files and programs persistently",
        ),
        MemoryLevel(
            "HDD",
            "TBs",
            "Persistent",
            "Slower than SSD",
            "Magnetic persistent storage",
        ),
    ]

    print(
        f"{'Level':<20} {'Capacity':<15} {'Persistence':<12} "
        f"{'Speed':<20} Purpose"
    )

    for level in hierarchy:
        print(
            f"{level.name:<20} {level.capacity:<15} "
            f"{level.persistence:<12} {level.relative_speed:<20} "
            f"{level.purpose}"
        )

    print(
        "\nGeneral principle: smaller, closer-to-CPU storage is usually faster "
        "and more expensive per byte."
    )


# =============================================================================
# 3. CPU FUNDAMENTALS
# =============================================================================

@dataclass
class CPURegisters:
    """A simplified educational CPU register set."""

    program_counter: int = 0
    instruction_register: Optional[str] = None
    accumulator: int = 0
    status_zero: bool = False
    status_negative: bool = False


class SimpleCPU:
    """
    A tiny educational CPU simulator.

    It demonstrates the basic fetch-decode-execute cycle without attempting
    to reproduce any real processor architecture.
    """

    def __init__(self, program: list[tuple]) -> None:
        self.program = program
        self.registers = CPURegisters()
        self.memory = {}
        self.halted = False
        self.execution_log: list[str] = []

    def fetch(self) -> tuple:
        """Fetch the instruction pointed to by the program counter."""
        if self.registers.program_counter >= len(self.program):
            self.halted = True
            return ("HALT",)

        instruction = self.program[self.registers.program_counter]
        self.registers.instruction_register = str(instruction)
        self.registers.program_counter += 1
        return instruction

    def update_flags(self) -> None:
        self.registers.status_zero = self.registers.accumulator == 0
        self.registers.status_negative = self.registers.accumulator < 0

    def execute(self, instruction: tuple) -> None:
        """Decode and execute one simplified instruction."""
        opcode = instruction[0]

        if opcode == "LOAD":
            self.registers.accumulator = instruction[1]

        elif opcode == "ADD":
            self.registers.accumulator += instruction[1]

        elif opcode == "SUB":
            self.registers.accumulator -= instruction[1]

        elif opcode == "STORE":
            address = instruction[1]
            self.memory[address] = self.registers.accumulator

        elif opcode == "JUMP":
            self.registers.program_counter = instruction[1]

        elif opcode == "JUMP_IF_ZERO":
            if self.registers.status_zero:
                self.registers.program_counter = instruction[1]

        elif opcode == "HALT":
            self.halted = True

        else:
            raise ValueError(f"Unknown opcode: {opcode}")

        self.update_flags()

    def run(self, max_cycles: int = 1_000) -> None:
        """Run until HALT or until a safety cycle limit is reached."""
        cycles = 0

        while not self.halted:
            if cycles >= max_cycles:
                raise RuntimeError("Program exceeded maximum CPU cycles.")

            instruction = self.fetch()
            self.execution_log.append(
                f"cycle={cycles + 1:03d}, instruction={instruction}, "
                f"ACC={self.registers.accumulator}"
            )
            self.execute(instruction)
            cycles += 1


def demonstrate_cpu() -> None:
    subsection("CPU instruction cycle")

    # The program computes 10 + 5 - 3 and stores the result at memory address 100.
    program = [
        ("LOAD", 10),
        ("ADD", 5),
        ("SUB", 3),
        ("STORE", 100),
        ("HALT",),
    ]

    cpu = SimpleCPU(program)
    cpu.run()

    print("Program:")
    for index, instruction in enumerate(program):
        print(f"  {index}: {instruction}")

    print("\nExecution log:")
    for line in cpu.execution_log:
        print(" ", line)

    print("\nFinal accumulator:", cpu.registers.accumulator)
    print("Memory[100]:", cpu.memory[100])

    print(
        "\nConceptual cycle: fetch instruction -> decode instruction -> "
        "execute operation -> update CPU state."
    )


# =============================================================================
# 4. ALU, CONTROL UNIT, REGISTERS, CLOCK
# =============================================================================

class ArithmeticLogicUnit:
    """Simplified representation of common ALU operations."""

    @staticmethod
    def add(a: int, b: int) -> int:
        return a + b

    @staticmethod
    def subtract(a: int, b: int) -> int:
        return a - b

    @staticmethod
    def bitwise_and(a: int, b: int) -> int:
        return a & b

    @staticmethod
    def bitwise_or(a: int, b: int) -> int:
        return a | b

    @staticmethod
    def bitwise_xor(a: int, b: int) -> int:
        return a ^ b


def demonstrate_cpu_components() -> None:
    subsection("CPU components")

    a = 12
    b = 10

    print("ALU operations:")
    print("  ADD:", ArithmeticLogicUnit.add(a, b))
    print("  SUB:", ArithmeticLogicUnit.subtract(a, b))
    print("  AND:", ArithmeticLogicUnit.bitwise_and(a, b))
    print("  OR :", ArithmeticLogicUnit.bitwise_or(a, b))
    print("  XOR:", ArithmeticLogicUnit.bitwise_xor(a, b))

    registers = CPURegisters(
        program_counter=42,
        instruction_register="ADD 10",
        accumulator=52,
    )

    print("\nExample CPU state:")
    print("  Program counter:", registers.program_counter)
    print("  Instruction register:", registers.instruction_register)
    print("  Accumulator:", registers.accumulator)

    print(
        "\nThe control unit coordinates instruction execution. "
        "The ALU performs arithmetic and logical operations. "
        "Registers provide extremely fast CPU-local storage."
    )


# =============================================================================
# 5. CACHE AND LOCALITY
# =============================================================================

def sequential_access_demo(size: int = 500_000) -> float:
    """Measure sequential access over a Python list."""
    values = list(range(size))

    start = time.perf_counter()
    total = 0

    for value in values:
        total += value

    return time.perf_counter() - start


def strided_access_demo(size: int = 500_000, stride: int = 16) -> float:
    """Measure a strided access pattern."""
    values = list(range(size))

    start = time.perf_counter()
    total = 0

    for index in range(0, size, stride):
        total += values[index]

    return time.perf_counter() - start


def demonstrate_locality() -> None:
    subsection("Cache locality")

    sequential_time = sequential_access_demo()
    strided_time = strided_access_demo()

    print(f"Sequential traversal time: {sequential_time:.6f} seconds")
    print(f"Strided traversal time:    {strided_time:.6f} seconds")

    print(
        "\nSequential access often benefits from spatial locality because "
        "nearby memory locations are likely to be loaded together."
    )

    print(
        "Timing results are hardware-, interpreter-, operating-system-, "
        "and workload-dependent, so this is an educational experiment rather "
        "than a CPU benchmark."
    )


# =============================================================================
# 6. RAM AND ADDRESSING
# =============================================================================

class SimulatedRAM:
    """A tiny byte-addressable RAM model."""

    def __init__(self, size: int) -> None:
        if size <= 0:
            raise ValueError("RAM size must be positive.")

        self._memory = bytearray(size)

    @property
    def size(self) -> int:
        return len(self._memory)

    def read_byte(self, address: int) -> int:
        self._validate_address(address)
        return self._memory[address]

    def write_byte(self, address: int, value: int) -> None:
        self._validate_address(address)

        if not 0 <= value <= 255:
            raise ValueError("A byte must contain a value from 0 to 255.")

        self._memory[address] = value

    def read_bytes(self, address: int, length: int) -> bytes:
        if length < 0:
            raise ValueError("Length cannot be negative.")

        if address < 0 or address + length > self.size:
            raise IndexError("Memory range is outside RAM.")

        return bytes(self._memory[address:address + length])

    def _validate_address(self, address: int) -> None:
        if not 0 <= address < self.size:
            raise IndexError(f"Invalid memory address: {address}")


def demonstrate_ram() -> None:
    subsection("RAM and memory addresses")

    ram = SimulatedRAM(16)

    ram.write_byte(0, 65)
    ram.write_byte(1, 66)
    ram.write_byte(2, 67)

    print("RAM size:", ram.size, "bytes")
    print("Address 0:", ram.read_byte(0))
    print("Address 1:", ram.read_byte(1))
    print("Address 2:", ram.read_byte(2))
    print("Addresses 0-2 as bytes:", ram.read_bytes(0, 3))
    print("Addresses 0-2 as text:", ram.read_bytes(0, 3).decode("ascii"))

    try:
        ram.read_byte(16)
    except IndexError as error:
        print("Handled invalid address:", error)

    try:
        ram.write_byte(3, 300)
    except ValueError as error:
        print("Handled invalid byte:", error)


# =============================================================================
# 7. STORAGE AND FILE I/O
# =============================================================================

def demonstrate_storage() -> None:
    subsection("Persistent storage")

    temporary_filename = "computer_fundamentals_demo.tmp"
    payload = b"Persistent data survives after a program stops."

    try:
        # Writing a file represents persistent storage conceptually.
        with open(temporary_filename, "wb") as file:
            file.write(payload)

        with open(temporary_filename, "rb") as file:
            recovered = file.read()

        print("Bytes written:", len(payload))
        print("Bytes recovered:", len(recovered))
        print("Data identical:", payload == recovered)

    finally:
        # The example cleans up after itself.
        try:
            os.remove(temporary_filename)
        except FileNotFoundError:
            pass

    print(
        "\nRAM is normally volatile: power loss removes its contents. "
        "Storage is designed to retain data when the machine is powered off."
    )


# =============================================================================
# 8. VIRTUAL MEMORY CONCEPTS
# =============================================================================

@dataclass
class Page:
    virtual_page: int
    physical_frame: Optional[int] = None
    present: bool = False


class SimplePageTable:
    """
    Educational virtual-memory mapping.

    A real operating system uses hardware-supported page tables and memory
    management mechanisms that are much more sophisticated.
    """

    def __init__(self, page_size: int, physical_frames: int) -> None:
        if page_size <= 0 or physical_frames <= 0:
            raise ValueError("Page size and frame count must be positive.")

        self.page_size = page_size
        self.frames = list(range(physical_frames))
        self.pages: dict[int, Page] = {}

    def map_page(self, virtual_page: int) -> int:
        if virtual_page in self.pages and self.pages[virtual_page].present:
            return self.pages[virtual_page].physical_frame  # type: ignore

        if not self.frames:
            raise MemoryError("No free physical frames available.")

        frame = self.frames.pop(0)
        self.pages[virtual_page] = Page(
            virtual_page=virtual_page,
            physical_frame=frame,
            present=True,
        )
        return frame

    def translate(self, virtual_address: int) -> tuple[int, bool]:
        if virtual_address < 0:
            raise ValueError("Virtual address cannot be negative.")

        virtual_page, offset = divmod(virtual_address, self.page_size)

        if virtual_page not in self.pages:
            frame = self.map_page(virtual_page)
            page_fault = True
        else:
            page = self.pages[virtual_page]
            if not page.present:
                frame = self.map_page(virtual_page)
                page_fault = True
            else:
                frame = page.physical_frame
                page_fault = False

        assert frame is not None
        physical_address = frame * self.page_size + offset
        return physical_address, page_fault


def demonstrate_virtual_memory() -> None:
    subsection("Virtual memory and paging")

    table = SimplePageTable(page_size=256, physical_frames=2)

    virtual_addresses = [0, 100, 256, 300, 512]

    for address in virtual_addresses:
        try:
            physical, page_fault = table.translate(address)
            print(
                f"Virtual address {address:>3} -> "
                f"physical address {physical:>3}, "
                f"page fault={page_fault}"
            )
        except MemoryError as error:
            print("Memory limitation:", error)

    print(
        "\nVirtual memory gives processes an abstraction of memory addresses. "
        "Paging divides virtual and physical memory into fixed-size pages/frames."
    )


# =============================================================================
# 9. PROCESSES
# =============================================================================

@dataclass
class ProcessInfo:
    pid: int
    name: str
    state: str
    priority: int
    memory_mb: int


def demonstrate_process_model() -> None:
    subsection("Processes")

    process_states = [
        ProcessInfo(101, "browser", "Running", 5, 850),
        ProcessInfo(102, "editor", "Ready", 7, 240),
        ProcessInfo(103, "backup", "Waiting", 10, 120),
        ProcessInfo(104, "terminal", "Ready", 6, 80),
    ]

    print(
        f"{'PID':<8} {'Process':<12} {'State':<10} "
        f"{'Priority':<10} {'Memory':<10}"
    )

    for process in process_states:
        print(
            f"{process.pid:<8} {process.name:<12} {process.state:<10} "
            f"{process.priority:<10} {process.memory_mb} MB"
        )

    print(
        "\nA process is a running program together with its execution state, "
        "virtual address space, resources, and operating-system-managed metadata."
    )


def process_worker(number: int, result_queue: Queue) -> None:
    """Worker function executed in a separate operating-system process."""
    result = number * number
    result_queue.put((os.getpid(), number, result))


def demonstrate_real_process() -> None:
    subsection("Creating an operating-system process")

    result_queue: Queue = Queue()
    process = Process(target=process_worker, args=(12, result_queue))

    process.start()
    process.join()

    if process.exitcode != 0:
        raise RuntimeError(f"Child process failed with code {process.exitcode}")

    child_pid, number, result = result_queue.get()

    print("Parent process PID:", os.getpid())
    print("Child process PID :", child_pid)
    print("Child calculation :", f"{number}² = {result}")

    print(
        "\nSeparate processes normally have separate virtual address spaces. "
        "Inter-process communication mechanisms are required to exchange data."
    )


# =============================================================================
# 10. THREADS
# =============================================================================

def thread_worker(
    worker_name: str,
    output: list[str],
    lock: threading.Lock,
) -> None:
    for step in range(3):
        time.sleep(0.01)
        with lock:
            output.append(f"{worker_name}: step {step + 1}")


def demonstrate_threads() -> None:
    subsection("Threads")

    output: list[str] = []
    lock = threading.Lock()

    threads = [
        threading.Thread(
            target=thread_worker,
            args=(f"Thread-{index}", output, lock),
        )
        for index in range(1, 4)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    for line in output:
        print(line)

    print(
        "\nThreads within a process share process memory and resources, "
        "while each thread has its own execution state and stack."
    )


# =============================================================================
# 11. PROCESS VS THREAD COMPARISON
# =============================================================================

def compare_processes_and_threads() -> None:
    subsection("Process versus thread")

    comparison = [
        ("Address space", "Normally separate", "Shared within process"),
        ("Creation overhead", "Usually higher", "Usually lower"),
        ("Communication", "IPC mechanisms", "Shared memory / synchronization"),
        ("Failure isolation", "Generally stronger", "Generally weaker"),
        ("Shared state", "Explicitly communicated", "Naturally shared"),
        ("Synchronization need", "Often IPC-specific", "Locks/events/etc."),
    ]

    print(f"{'Aspect':<22} {'Process':<28} Thread")
    for aspect, process_value, thread_value in comparison:
        print(f"{aspect:<22} {process_value:<28} {thread_value}")


# =============================================================================
# 12. THREAD-SAFE COUNTER
# =============================================================================

class ThreadSafeCounter:
    """Counter protected by a lock."""

    def __init__(self) -> None:
        self._value = 0
        self._lock = threading.Lock()

    def increment(self) -> None:
        with self._lock:
            self._value += 1

    @property
    def value(self) -> int:
        with self._lock:
            return self._value


def demonstrate_synchronization() -> None:
    subsection("Synchronization and race-condition prevention")

    counter = ThreadSafeCounter()

    def worker(iterations: int) -> None:
        for _ in range(iterations):
            counter.increment()

    thread_count = 8
    iterations = 10_000

    threads = [
        threading.Thread(target=worker, args=(iterations,))
        for _ in range(thread_count)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    expected = thread_count * iterations

    print("Expected value:", expected)
    print("Actual value:  ", counter.value)
    print("Correct:       ", counter.value == expected)

    print(
        "\nA lock provides mutual exclusion around the shared state. "
        "Synchronization prevents unsafe concurrent updates."
    )


# =============================================================================
# 13. RACE CONDITION EXPLANATION
# =============================================================================

def demonstrate_race_condition_model() -> None:
    subsection("How a race condition can happen")

    shared_value = 0

    # The operation:
    #     shared_value += 1
    # is conceptually a read-modify-write sequence.
    #
    # Two workers can interleave:
    #     Worker A reads 10
    #     Worker B reads 10
    #     Worker A writes 11
    #     Worker B writes 11
    #
    # One increment is lost.

    starting_value = 10
    print("Starting value:", starting_value)
    print("\nPossible unsafe interleaving:")
    print("  Worker A reads 10")
    print("  Worker B reads 10")
    print("  Worker A calculates 11")
    print("  Worker B calculates 11")
    print("  Worker A writes 11")
    print("  Worker B writes 11")
    print("  Final value becomes 11 instead of 12")

    shared_value = starting_value
    shared_value += 1
    print("\nSingle-threaded equivalent after one increment:", shared_value)

    print(
        "\nPython implementation details can affect exactly how a race appears. "
        "The important principle is that compound shared-state operations should "
        "not be assumed to be atomic merely because they look like one line."
    )


# =============================================================================
# 14. DEADLOCK
# =============================================================================

def demonstrate_deadlock_prevention() -> None:
    subsection("Deadlock and lock ordering")

    lock_a = threading.Lock()
    lock_b = threading.Lock()

    def safe_worker(first: threading.Lock, second: threading.Lock) -> None:
        # A consistent global lock order prevents circular wait.
        with first:
            with second:
                time.sleep(0.001)

    thread_one = threading.Thread(
        target=safe_worker,
        args=(lock_a, lock_b),
    )
    thread_two = threading.Thread(
        target=safe_worker,
        args=(lock_a, lock_b),
    )

    thread_one.start()
    thread_two.start()

    thread_one.join(timeout=1)
    thread_two.join(timeout=1)

    if thread_one.is_alive() or thread_two.is_alive():
        raise RuntimeError("Unexpected deadlock detected.")

    print("Both workers completed.")
    print(
        "A common deadlock-prevention technique is acquiring multiple locks "
        "in a consistent order."
    )


# =============================================================================
# 15. PRODUCER-CONSUMER
# =============================================================================

def demonstrate_producer_consumer() -> None:
    subsection("Producer-consumer concurrency pattern")

    work_queue: ThreadQueue[int] = ThreadQueue()
    results: list[int] = []

    def producer() -> None:
        for number in range(1, 11):
            work_queue.put(number)

        # Sentinel tells the consumer that production is complete.
        work_queue.put(None)  # type: ignore[arg-type]

    def consumer() -> None:
        while True:
            number = work_queue.get()
            try:
                if number is None:
                    return
                results.append(number * number)
            finally:
                work_queue.task_done()

    producer_thread = threading.Thread(target=producer)
    consumer_thread = threading.Thread(target=consumer)

    producer_thread.start()
    consumer_thread.start()

    producer_thread.join()
    work_queue.join()

    # The consumer receives the sentinel after all preceding items.
    consumer_thread.join()

    print("Produced values:", list(range(1, 11)))
    print("Consumed results:", results)


# =============================================================================
# 16. CPU-BOUND VS I/O-BOUND WORK
# =============================================================================

def cpu_bound_work(iterations: int) -> int:
    """Perform deliberately CPU-heavy arithmetic."""
    result = 0

    for number in range(iterations):
        result += (number * number) % 97

    return result


def io_bound_work(delay: float = 0.05) -> str:
    """Simulate waiting for external I/O."""
    time.sleep(delay)
    return "I/O completed"


def demonstrate_workload_types() -> None:
    subsection("CPU-bound versus I/O-bound workloads")

    start = time.perf_counter()
    cpu_result = cpu_bound_work(200_000)
    cpu_time = time.perf_counter() - start

    start = time.perf_counter()
    io_result = io_bound_work()
    io_time = time.perf_counter() - start

    print("CPU-bound result:", cpu_result)
    print("CPU-bound time:  ", f"{cpu_time:.6f} seconds")
    print("I/O-bound result:", io_result)
    print("I/O-bound time:  ", f"{io_time:.6f} seconds")

    print(
        "\nCPU-bound work spends most of its time computing. "
        "I/O-bound work spends significant time waiting for external resources."
    )


# =============================================================================
# 17. CONCURRENT I/O WORK
# =============================================================================

def demonstrate_concurrent_io() -> None:
    subsection("Threads for concurrent I/O-style work")

    delays = [0.04, 0.03, 0.05, 0.02]

    def task(delay: float) -> float:
        start = time.perf_counter()
        time.sleep(delay)
        return time.perf_counter() - start

    sequential_start = time.perf_counter()

    sequential_results = [task(delay) for delay in delays]
    sequential_total = time.perf_counter() - sequential_start

    concurrent_results: list[float] = []
    result_lock = threading.Lock()

    def concurrent_task(delay: float) -> None:
        duration = task(delay)
        with result_lock:
            concurrent_results.append(duration)

    concurrent_start = time.perf_counter()

    threads = [
        threading.Thread(target=concurrent_task, args=(delay,))
        for delay in delays
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    concurrent_total = time.perf_counter() - concurrent_start

    print("Sequential task durations:", [round(x, 4) for x in sequential_results])
    print("Sequential total:", round(sequential_total, 4), "seconds")
    print("Concurrent task durations:", [round(x, 4) for x in concurrent_results])
    print("Concurrent total:", round(concurrent_total, 4), "seconds")

    print(
        "\nConcurrency can overlap waiting periods. It does not automatically "
        "make CPU-bound Python code faster."
    )


# =============================================================================
# 18. SIMPLE CPU SCHEDULER SIMULATION
# =============================================================================

@dataclass
class ScheduledTask:
    name: str
    burst_time: int
    remaining_time: int = field(init=False)

    def __post_init__(self) -> None:
        if self.burst_time <= 0:
            raise ValueError("Burst time must be positive.")
        self.remaining_time = self.burst_time


def round_robin_schedule(
    tasks: Iterable[ScheduledTask],
    quantum: int,
) -> list[tuple[str, int]]:
    """
    Simulate round-robin scheduling.

    Returns:
        A list containing (task_name, execution_time) slices.
    """
    if quantum <= 0:
        raise ValueError("Quantum must be positive.")

    queue = deque(tasks)
    timeline: list[tuple[str, int]] = []

    while queue:
        task = queue.popleft()
        run_time = min(quantum, task.remaining_time)
        task.remaining_time -= run_time
        timeline.append((task.name, run_time))

        if task.remaining_time > 0:
            queue.append(task)

    return timeline


def demonstrate_scheduling() -> None:
    subsection("CPU scheduling")

    tasks = [
        ScheduledTask("Browser", 7),
        ScheduledTask("Editor", 4),
        ScheduledTask("Compiler", 9),
    ]

    timeline = round_robin_schedule(tasks, quantum=3)

    print("Round-robin timeline:")
    for name, duration in timeline:
        print(f"  {name:<10} ran for {duration} time units")

    print(
        "\nScheduling algorithms determine which ready task receives CPU time. "
        "Real operating systems use sophisticated policies involving priorities, "
        "fairness, responsiveness, workload type, and hardware characteristics."
    )


# =============================================================================
# 19. CONTEXT SWITCHING
# =============================================================================

@dataclass
class CPUContext:
    process_id: int
    program_counter: int
    register_values: dict[str, int]


def demonstrate_context_switch() -> None:
    subsection("Context switching")

    process_a = CPUContext(
        process_id=101,
        program_counter=1200,
        register_values={"R1": 10, "R2": 20},
    )

    process_b = CPUContext(
        process_id=202,
        program_counter=5400,
        register_values={"R1": 99, "R2": 7},
    )

    current_context = process_a

    print("Running process:", current_context.process_id)
    print("Program counter:", current_context.program_counter)

    saved_context = current_context
    current_context = process_b

    print("\nContext saved for process:", saved_context.process_id)
    print("CPU switched to process:", current_context.process_id)
    print("Restored program counter:", current_context.program_counter)

    print(
        "\nA context switch preserves enough execution state for the operating "
        "system to pause one execution context and later resume it."
    )


# =============================================================================
# 20. THREAD STATES
# =============================================================================

def demonstrate_thread_states() -> None:
    subsection("Typical execution states")

    states = [
        ("New", "Thread has been created but has not started execution."),
        ("Ready", "Eligible to run and waiting for CPU scheduling."),
        ("Running", "Currently executing on a CPU core."),
        ("Blocked/Waiting", "Waiting for I/O, a lock, an event, or another condition."),
        ("Terminated", "Execution has completed."),
    ]

    for name, description in states:
        print(f"{name:<18} {description}")


# =============================================================================
# 21. MULTI-CORE PROCESSING
# =============================================================================

def cpu_worker(number: int, iterations: int, output_queue: Queue) -> None:
    result = cpu_bound_work(iterations)
    output_queue.put((number, result, os.getpid()))


def demonstrate_multiple_processes() -> None:
    subsection("Multiple processes and CPU parallelism")

    output_queue: Queue = Queue()
    processes: list[Process] = []

    for worker_number in range(2):
        process = Process(
            target=cpu_worker,
            args=(worker_number, 100_000, output_queue),
        )
        processes.append(process)
        process.start()

    for process in processes:
        process.join()

    results = []
    for _ in processes:
        results.append(output_queue.get())

    results.sort()

    for worker_number, result, pid in results:
        print(
            f"Worker {worker_number}: result={result}, "
            f"process PID={pid}"
        )

    print(
        "\nSeparate processes can execute independently and may run in parallel "
        "on multiple CPU cores, subject to operating-system scheduling and hardware."
    )


# =============================================================================
# 22. PERFORMANCE: Amdahl'S LAW
# =============================================================================

def amdahls_speedup(parallel_fraction: float, processors: int) -> float:
    """
    Calculate idealized Amdahl's Law speedup.

    Speedup = 1 / ((1 - P) + P/N)

    P = fraction of work that can be parallelized.
    N = number of processors.
    """
    if not 0 <= parallel_fraction <= 1:
        raise ValueError("Parallel fraction must be between 0 and 1.")

    if processors <= 0:
        raise ValueError("Processor count must be positive.")

    serial_fraction = 1 - parallel_fraction
    return 1 / (serial_fraction + parallel_fraction / processors)


def demonstrate_amdahl() -> None:
    subsection("Parallel performance and Amdahl's Law")

    parallel_fraction = 0.90

    for processors in [1, 2, 4, 8, 16, 64]:
        speedup = amdahls_speedup(parallel_fraction, processors)
        print(f"{processors:>2} processors -> ideal speedup {speedup:.3f}x")

    print(
        "\nIf part of a workload cannot be parallelized, that serial portion "
        "limits the maximum achievable speedup."
    )


# =============================================================================
# 23. THROUGHPUT, LATENCY, AND UTILIZATION
# =============================================================================

def demonstrate_performance_metrics() -> None:
    subsection("Performance terminology")

    jobs_completed = 120
    elapsed_seconds = 30
    average_latency = 0.4
    cpu_busy_seconds = 24

    throughput = jobs_completed / elapsed_seconds
    utilization = cpu_busy_seconds / elapsed_seconds

    print("Throughput:", f"{throughput:.2f} jobs/second")
    print("Average latency:", f"{average_latency:.2f} seconds/job")
    print("CPU utilization:", f"{utilization * 100:.1f}%")

    print(
        "\nThroughput measures completed work per unit time. "
        "Latency measures the time taken by an individual operation. "
        "Utilization measures how busy a resource is."
    )


# =============================================================================
# 24. GARBAGE COLLECTION AND MEMORY LIFETIME
# =============================================================================

class Resource:
    """Object used to demonstrate explicit resource lifetime."""

    active_resources = 0

    def __init__(self, name: str) -> None:
        self.name = name
        Resource.active_resources += 1

    def close(self) -> None:
        if self.name is not None:
            Resource.active_resources -= 1
            self.name = None

    def __enter__(self) -> "Resource":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def demonstrate_memory_lifetime() -> None:
    subsection("Memory lifetime and resource management")

    print("Resources before:", Resource.active_resources)

    with Resource("database connection") as resource:
        print("Inside context:", resource.name)
        print("Resources inside:", Resource.active_resources)

    print("Resources after:", Resource.active_resources)

    print(
        "\nMemory management and resource management are related but distinct. "
        "A memory object can become unreachable while an external resource "
        "such as a file descriptor or database connection requires explicit cleanup."
    )


# =============================================================================
# 25. ERROR HANDLING AND FAULTS
# =============================================================================

def demonstrate_errors() -> None:
    subsection("Faults and error handling")

    examples: list[Callable[[], object]] = [
        lambda: 10 / 0,
        lambda: [1, 2, 3][10],
        lambda: int("not-a-number"),
    ]

    for operation in examples:
        try:
            operation()
        except (ZeroDivisionError, IndexError, ValueError) as error:
            print(type(error).__name__, "->", error)

    print(
        "\nOperating systems also manage hardware and software faults. "
        "Examples include invalid memory accesses, failed system calls, "
        "device errors, and process termination."
    )


# =============================================================================
# 26. SECURITY CONSIDERATIONS
# =============================================================================

def demonstrate_security_principles() -> None:
    subsection("Computer architecture and security")

    security_principles = {
        "Process isolation": "Limits direct access between independent processes.",
        "Virtual memory protection": "Helps restrict which addresses a process can access.",
        "User/kernel separation": "Privileged operations are restricted to protected execution contexts.",
        "Least privilege": "Software should receive only the permissions it needs.",
        "Memory safety": "Invalid memory access should be prevented or detected.",
        "Secure storage": "Persistent data may require access control and encryption.",
        "Input validation": "Untrusted input should be checked before processing.",
    }

    for principle, explanation in security_principles.items():
        print(f"{principle:<25} {explanation}")

    print(
        "\nSecurity is not provided by one component. CPU privilege mechanisms, "
        "memory protection, operating-system controls, application design, "
        "authentication, authorization, and secure storage work together."
    )


# =============================================================================
# 27. SYSTEM INFORMATION
# =============================================================================

def demonstrate_system_information() -> None:
    subsection("Inspecting the current computer")

    print("Operating system:", platform.system())
    print("OS release:", platform.release())
    print("Machine architecture:", platform.machine())
    print("Python version:", platform.python_version())
    print("Logical CPU count:", os.cpu_count())

    print(
        "\nLogical CPU count is not necessarily the number of physical CPU cores. "
        "Modern processors can expose multiple logical execution units per core."
    )


# =============================================================================
# 28. STORAGE CAPACITY UNITS
# =============================================================================

def demonstrate_storage_units() -> None:
    subsection("Storage and memory units")

    units = [
        ("bit", 1),
        ("byte", 8),
        ("KiB", 8 * 1024),
        ("MiB", 8 * 1024**2),
        ("GiB", 8 * 1024**3),
        ("TiB", 8 * 1024**4),
    ]

    for name, bits in units:
        print(f"{name:<6} = {bits:,} bits")

    print(
        "\nBinary prefixes such as KiB, MiB, and GiB use powers of 1024. "
        "Decimal prefixes such as kB, MB, and GB commonly use powers of 1000."
    )


# =============================================================================
# 29. CACHE SIMULATION
# =============================================================================

class DirectMappedCache:
    """
    Very small educational direct-mapped cache.

    This demonstrates the basic idea of cache hits and misses rather than
    modeling a modern CPU cache in full detail.
    """

    def __init__(self, number_of_lines: int) -> None:
        if number_of_lines <= 0:
            raise ValueError("Cache must have at least one line.")

        self.number_of_lines = number_of_lines
        self.tags: list[Optional[int]] = [None] * number_of_lines
        self.hits = 0
        self.misses = 0

    def access(self, memory_block: int) -> bool:
        index = memory_block % self.number_of_lines
        tag = memory_block // self.number_of_lines

        if self.tags[index] == tag:
            self.hits += 1
            return True

        self.tags[index] = tag
        self.misses += 1
        return False


def demonstrate_cache() -> None:
    subsection("Cache hit and miss simulation")

    cache = DirectMappedCache(number_of_lines=4)
    accesses = [0, 1, 2, 3, 0, 1, 2, 3, 4, 0, 4, 0]

    for address in accesses:
        result = cache.access(address)
        print(f"Memory block {address:>2}: {'HIT' if result else 'MISS'}")

    print("\nHits:", cache.hits)
    print("Misses:", cache.misses)
    print("Hit rate:", f"{cache.hits / len(accesses) * 100:.1f}%")

    print(
        "\nA cache hit means required data is already in the relevant cache level. "
        "A cache miss requires obtaining the data from a lower level."
    )


# =============================================================================
# 30. STACK AND HEAP CONCEPTS
# =============================================================================

def stack_example(depth: int) -> int:
    """
    Recursive calls create nested execution frames conceptually associated
    with the call stack.
    """
    if depth == 0:
        return 1

    return depth * stack_example(depth - 1)


def demonstrate_stack_and_heap() -> None:
    subsection("Stack and heap concepts")

    print("5! calculated through recursive calls:", stack_example(5))

    sample_list = [10, 20, 30]

    print("A Python list object:", sample_list)
    print("The variable refers to an object managed by the Python runtime.")

    print(
        "\nThe call stack tracks active function calls and local execution state. "
        "Dynamically allocated objects are managed by the language runtime and "
        "underlying memory allocator. Exact implementation details depend on "
        "the programming language and runtime."
    )


# =============================================================================
# 31. SYSTEM CALL CONCEPT
# =============================================================================

def demonstrate_system_call_concept() -> None:
    subsection("System calls")

    print("Application request:")
    print("  Python program asks the operating system to open a file.")
    print("\nConceptual flow:")
    print("  application")
    print("      ↓")
    print("  language runtime")
    print("      ↓")
    print("  system call interface")
    print("      ↓")
    print("  operating system kernel")
    print("      ↓")
    print("  file system / storage device")

    print(
        "\nA system call is a controlled interface through which a user-space "
        "program requests services from the operating-system kernel."
    )


# =============================================================================
# 32. USER MODE AND KERNEL MODE
# =============================================================================

def demonstrate_privilege_levels() -> None:
    subsection("User mode and kernel mode")

    operations = [
        ("Normal application arithmetic", "User mode"),
        ("Reading protected kernel memory", "Not directly permitted"),
        ("Opening a file", "User request -> kernel service"),
        ("Changing hardware configuration", "Privileged operation"),
    ]

    for operation, privilege in operations:
        print(f"{operation:<42} {privilege}")

    print(
        "\nPrivilege separation reduces the impact of bugs and malicious behavior "
        "by restricting sensitive operations."
    )


# =============================================================================
# 33. INTERRUPTS
# =============================================================================

def demonstrate_interrupts() -> None:
    subsection("Interrupts")

    print("Example sequence:")
    print("  1. CPU executes normal instructions.")
    print("  2. Hardware device needs CPU attention.")
    print("  3. Interrupt is raised.")
    print("  4. CPU saves relevant execution state.")
    print("  5. Interrupt handler executes.")
    print("  6. CPU resumes the interrupted work.")

    print(
        "\nInterrupts allow hardware and software events to request CPU attention "
        "without requiring the CPU to continuously poll every device."
    )


# =============================================================================
# 34. FILE SYSTEM CONCEPTS
# =============================================================================

@dataclass
class FileMetadata:
    name: str
    size_bytes: int
    permissions: str
    file_type: str


def demonstrate_file_system() -> None:
    subsection("File-system concepts")

    files = [
        FileMetadata("report.txt", 12_000, "rw-r--r--", "regular file"),
        FileMetadata("photo.jpg", 2_400_000, "rw-r--r--", "regular file"),
        FileMetadata("script.py", 4_500, "rwxr-xr-x", "regular file"),
        FileMetadata("documents", 0, "rwxr-xr-x", "directory"),
    ]

    print(f"{'Name':<18} {'Size':<12} {'Permissions':<15} Type")
    for file in files:
        print(
            f"{file.name:<18} {file.size_bytes:<12,} "
            f"{file.permissions:<15} {file.file_type}"
        )

    print(
        "\nA file system organizes persistent data and metadata. "
        "Actual file-system structures differ across operating systems."
    )


# =============================================================================
# 35. THREAD POOL
# =============================================================================

def demonstrate_thread_pool() -> None:
    subsection("Thread-pool pattern")

    tasks = list(range(1, 11))
    results: list[int] = []
    result_lock = threading.Lock()

    def worker(number: int) -> None:
        result = number ** 2
        with result_lock:
            results.append(result)

    threads: list[threading.Thread] = []

    for number in tasks:
        thread = threading.Thread(target=worker, args=(number,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    results.sort()

    print("Input:", tasks)
    print("Output:", results)

    print(
        "\nA production thread pool normally reuses a bounded number of worker "
        "threads rather than creating one thread per task. This limits resource use."
    )


# =============================================================================
# 36. BACKPRESSURE
# =============================================================================

def demonstrate_backpressure() -> None:
    subsection("Backpressure")

    queue_capacity = 3
    queue = deque(maxlen=queue_capacity)

    producer_items = list(range(1, 7))

    print("Queue capacity:", queue_capacity)

    for item in producer_items:
        if len(queue) == queue_capacity:
            removed = queue.popleft()
            print(f"Queue full: consumed/discarded older item {removed}")

        queue.append(item)
        print(f"Produced {item}; queue={list(queue)}")

    print(
        "\nBackpressure occurs when producers can create work faster than consumers "
        "can process it. Systems must choose strategies such as blocking producers, "
        "buffering, dropping work, scaling consumers, or applying rate limits."
    )


# =============================================================================
# 37. MEASURING A FUNCTION
# =============================================================================

def benchmark_function(
    function: Callable[[], object],
    repetitions: int = 5,
) -> tuple[float, float]:
    """Return mean and standard deviation of elapsed execution time."""
    if repetitions <= 0:
        raise ValueError("Repetitions must be positive.")

    timings = []

    for _ in range(repetitions):
        start = time.perf_counter()
        function()
        timings.append(time.perf_counter() - start)

    mean_time = statistics.mean(timings)

    if len(timings) > 1:
        standard_deviation = statistics.stdev(timings)
    else:
        standard_deviation = 0.0

    return mean_time, standard_deviation


def demonstrate_benchmarking() -> None:
    subsection("Basic benchmarking")

    mean_time, standard_deviation = benchmark_function(
        lambda: cpu_bound_work(50_000),
        repetitions=5,
    )

    print("Mean execution time:", f"{mean_time:.6f} seconds")
    print("Standard deviation:", f"{standard_deviation:.6f} seconds")

    print(
        "\nReliable benchmarking requires controlled workloads, repeated runs, "
        "appropriate warm-up, stable system conditions, and meaningful metrics."
    )


# =============================================================================
# 38. BIG-O AND CPU WORK
# =============================================================================

def linear_sum(values: list[int]) -> int:
    total = 0

    for value in values:
        total += value

    return total


def quadratic_pair_count(values: list[int]) -> int:
    count = 0

    for index in range(len(values)):
        for other_index in range(index + 1, len(values)):
            if values[index] < values[other_index]:
                count += 1

    return count


def demonstrate_algorithmic_cost() -> None:
    subsection("Algorithmic complexity and CPU time")

    values = list(range(1_000))

    start = time.perf_counter()
    linear_result = linear_sum(values)
    linear_time = time.perf_counter() - start

    start = time.perf_counter()
    pair_result = quadratic_pair_count(values)
    quadratic_time = time.perf_counter() - start

    print("Linear operation result:", linear_result)
    print("Linear operation time:", f"{linear_time:.6f} seconds")

    print("Quadratic operation result:", pair_result)
    print("Quadratic operation time:", f"{quadratic_time:.6f} seconds")

    print(
        "\nCPU performance is influenced not only by processor speed but also by "
        "algorithmic complexity, memory behavior, branching, I/O, synchronization, "
        "and workload characteristics."
    )


# =============================================================================
# 39. NUMERICAL REPRESENTATION AND INTEGER OVERFLOW CONCEPT
# =============================================================================

def fixed_width_unsigned(value: int, bits: int) -> int:
    """Simulate truncation to a fixed-width unsigned integer."""
    if bits <= 0:
        raise ValueError("Bit width must be positive.")

    maximum = 2 ** bits
    return value % maximum


def demonstrate_fixed_width_integers() -> None:
    subsection("Fixed-width integer behavior")

    bits = 8
    values = [0, 1, 255, 256, 257, 511, 512]

    for value in values:
        stored = fixed_width_unsigned(value, bits)
        print(f"{value:>4} stored in {bits}-bit unsigned value -> {stored:>3}")

    print(
        "\nMany low-level systems use fixed-width integers. If an operation "
        "exceeds the representable range, behavior depends on the language, "
        "data type, compiler, and architecture. Python integers grow dynamically."
    )


# =============================================================================
# 40. THREAD LOCAL STATE
# =============================================================================

def demonstrate_thread_local_storage() -> None:
    subsection("Thread-local state")

    local_data = threading.local()
    observations: list[tuple[str, int]] = []
    lock = threading.Lock()

    def worker(value: int) -> None:
        local_data.value = value

        # Each thread sees its own local_data.value.
        time.sleep(0.005)

        with lock:
            observations.append(
                (threading.current_thread().name, local_data.value)
            )

    threads = [
        threading.Thread(
            target=worker,
            args=(index,),
            name=f"Worker-{index}",
        )
        for index in range(3)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    for observation in sorted(observations):
        print(observation)

    print(
        "\nThread-local storage allows each thread to maintain independent "
        "state without sharing that particular variable."
    )


# =============================================================================
# 41. EVENTS AND CONDITION SYNCHRONIZATION
# =============================================================================

def demonstrate_event_synchronization() -> None:
    subsection("Event-based synchronization")

    ready_event = threading.Event()
    result: list[str] = []

    def worker() -> None:
        ready_event.wait()
        result.append("Worker received the start signal.")

    worker_thread = threading.Thread(target=worker)
    worker_thread.start()

    time.sleep(0.01)
    print("Main thread signals worker.")
    ready_event.set()

    worker_thread.join()

    print(result[0])

    print(
        "\nSynchronization primitives can coordinate execution without repeatedly "
        "polling shared state."
    )


# =============================================================================
# 42. PROCESS COMMUNICATION
# =============================================================================

def process_message_worker(output: Queue) -> None:
    output.put(
        {
            "pid": os.getpid(),
            "message": "Data sent from child process",
        }
    )


def demonstrate_process_communication() -> None:
    subsection("Inter-process communication")

    output: Queue = Queue()

    process = Process(target=process_message_worker, args=(output,))
    process.start()
    process.join()

    message = output.get()

    print("Received:", message["message"])
    print("Sender PID:", message["pid"])

    print(
        "\nProcesses generally cannot safely exchange ordinary Python variables "
        "by simply referencing the same object. IPC mechanisms provide controlled "
        "communication."
    )


# =============================================================================
# 43. CPU PIPELINE CONCEPT
# =============================================================================

def demonstrate_pipeline() -> None:
    subsection("CPU instruction pipelining")

    stages = ["Fetch", "Decode", "Execute", "Memory", "Write-back"]
    instructions = ["I1", "I2", "I3", "I4"]

    print("Conceptual pipeline schedule:")

    for cycle in range(len(instructions) + len(stages) - 1):
        active = []

        for instruction_index, instruction in enumerate(instructions):
            stage_index = cycle - instruction_index

            if 0 <= stage_index < len(stages):
                active.append(f"{instruction}:{stages[stage_index]}")

        print(f"  Cycle {cycle + 1}: " + ", ".join(active))

    print(
        "\nPipelining overlaps different stages of multiple instructions. "
        "Modern CPUs use much more sophisticated pipelines and execution mechanisms."
    )


# =============================================================================
# 44. BRANCH PREDICTION CONCEPT
# =============================================================================

def demonstrate_branch_prediction() -> None:
    subsection("Branch prediction concept")

    branch_history = [True, True, True, True, False, True, True, False]

    predictor = True
    correct = 0

    for actual in branch_history:
        if predictor == actual:
            correct += 1

        # A simple predictor assumes the next result resembles the current result.
        predictor = actual

    accuracy = correct / len(branch_history)

    print("Branch outcomes:", branch_history)
    print("Simple predictor accuracy:", f"{accuracy * 100:.1f}%")

    print(
        "\nModern processors predict branches to keep pipelines busy. "
        "A wrong prediction can require speculative work to be discarded."
    )


# =============================================================================
# 45. FALSE SHARING CONCEPT
# =============================================================================

def demonstrate_false_sharing_concept() -> None:
    subsection("False sharing")

    print("Conceptual scenario:")
    print("  Core 1 frequently updates variable A.")
    print("  Core 2 frequently updates variable B.")
    print("  A and B happen to occupy the same cache line.")
    print("  Cache-coherence traffic can occur even though A and B are logically independent.")

    print(
        "\nFalse sharing is a performance problem in some multithreaded workloads. "
        "Data layout and cache-line behavior can matter in high-performance systems."
    )


# =============================================================================
# 46. CACHE COHERENCE CONCEPT
# =============================================================================

def demonstrate_cache_coherence() -> None:
    subsection("Cache coherence")

    print("Two CPU cores:")
    print("  Core 1 cache: X = 10")
    print("  Core 2 cache: X = 10")
    print("\nCore 1 updates X to 20.")
    print("A coherence protocol helps ensure other cores do not indefinitely use stale data.")

    print(
        "\nCache coherence is a hardware-level mechanism for maintaining a "
        "consistent view of shared cacheable memory across processor cores."
    )


# =============================================================================
# 47. DMA CONCEPT
# =============================================================================

def demonstrate_dma() -> None:
    subsection("Direct memory access")

    print("Traditional conceptual path:")
    print("  device -> CPU handles every data movement step -> RAM")

    print("\nDMA-enabled conceptual path:")
    print("  device -> DMA controller -> RAM")
    print("  CPU configures transfer and can perform other work while transfer proceeds.")

    print(
        "\nDirect memory access reduces CPU involvement in some bulk data transfers. "
        "Exact mechanisms depend on hardware and operating-system drivers."
    )


# =============================================================================
# 48. STORAGE PERFORMANCE CONCEPTS
# =============================================================================

def demonstrate_storage_performance() -> None:
    subsection("Storage performance")

    metrics = {
        "Latency": "Time required for an individual operation.",
        "Throughput": "Amount of data transferred per unit time.",
        "IOPS": "Input/output operations completed per second.",
        "Sequential access": "Reading or writing nearby data in order.",
        "Random access": "Accessing data at less predictable locations.",
    }

    for name, meaning in metrics.items():
        print(f"{name:<20} {meaning}")

    print(
        "\nA storage device can have strong sequential throughput while having "
        "very different random-access latency and IOPS characteristics."
    )


# =============================================================================
# 49. RELIABILITY AND REDUNDANCY
# =============================================================================

def demonstrate_reliability() -> None:
    subsection("Reliability considerations")

    principles = [
        "Use backups for important persistent data.",
        "Validate data before trusting it.",
        "Handle process and thread failures explicitly.",
        "Avoid unbounded queues and memory consumption.",
        "Monitor latency, throughput, errors, and resource utilization.",
        "Use timeouts for operations that can block indefinitely.",
        "Design recovery procedures for hardware and software failures.",
    ]

    for principle in principles:
        print("•", principle)


# =============================================================================
# 50. TIMEOUTS AND FAILURE BOUNDARIES
# =============================================================================

def demonstrate_timeout() -> None:
    subsection("Timeouts")

    completed = threading.Event()

    def slow_operation() -> None:
        time.sleep(0.1)
        completed.set()

    worker = threading.Thread(target=slow_operation)
    worker.start()

    finished = completed.wait(timeout=0.03)

    print("Completed before timeout:", finished)

    if not finished:
        print("Timeout occurred; caller can apply its failure policy.")

    worker.join()

    print(
        "\nTimeouts prevent callers from waiting indefinitely. "
        "A timeout should be paired with a clear policy such as retry, cancellation, "
        "fallback, or error reporting."
    )


# =============================================================================
# 51. PRODUCTION DESIGN: BOUNDED CONCURRENCY
# =============================================================================

def demonstrate_bounded_concurrency() -> None:
    subsection("Bounded concurrency")

    maximum_workers = 4
    tasks = 12

    print("Tasks:", tasks)
    print("Maximum concurrent workers:", maximum_workers)

    batches = math.ceil(tasks / maximum_workers)

    print("Minimum conceptual batches:", batches)

    print(
        "\nUnbounded concurrency can exhaust CPU, memory, sockets, file descriptors, "
        "or downstream service capacity. Production systems commonly bound concurrency."
    )


# =============================================================================
# 52. OBSERVABILITY
# =============================================================================

def demonstrate_observability() -> None:
    subsection("Observability")

    measurements = {
        "CPU utilization": "Shows how much CPU capacity is being consumed.",
        "Memory usage": "Shows active memory consumption and pressure.",
        "Disk utilization": "Shows storage activity and saturation.",
        "Thread count": "Shows the number of active threads.",
        "Process count": "Shows active operating-system processes.",
        "Latency": "Shows how long operations take.",
        "Error rate": "Shows how frequently operations fail.",
    }

    for metric, meaning in measurements.items():
        print(f"{metric:<20} {meaning}")


# =============================================================================
# 53. INTEGRATED COMPUTER EXECUTION MODEL
# =============================================================================

def integrated_execution_example() -> None:
    subsection("Integrated example: what happens when a program runs")

    print("1. Persistent storage contains the executable.")
    print("2. The operating system creates a process.")
    print("3. Program instructions and required data are mapped into virtual memory.")
    print("4. Required pages are brought into physical RAM.")
    print("5. CPU fetches instructions.")
    print("6. CPU decodes instructions.")
    print("7. Execution uses registers, ALU, caches, and memory.")
    print("8. The process may request operating-system services through system calls.")
    print("9. I/O operations may cause the process to wait.")
    print("10. The scheduler may switch the CPU to another runnable process/thread.")
    print("11. Threads may execute concurrently and synchronize shared state.")
    print("12. Results may eventually be written back to persistent storage.")


# =============================================================================
# 54. COMMON MISTAKES
# =============================================================================

def demonstrate_common_mistakes() -> None:
    subsection("Common conceptual mistakes")

    mistakes = {
        "RAM equals storage": "RAM is active working memory; storage is persistent.",
        "More GHz always means faster": "Performance also depends on IPC, architecture, cache, memory, workload, and software.",
        "A process equals a thread": "A process is an execution/resource container; threads are execution units within it.",
        "Threads always improve speed": "They help with some workloads, especially overlapping I/O, but add overhead and synchronization costs.",
        "CPU utilization near 100% is always bad": "High utilization can be healthy if latency and throughput targets are satisfied.",
        "More threads always means more performance": "Too many threads can cause scheduling, memory, contention, and context-switch overhead.",
        "Virtual memory is just extra RAM": "It is an address-space abstraction backed by physical memory and potentially storage.",
        "SSD and RAM are interchangeable": "Their persistence, latency, bandwidth, and access characteristics differ substantially.",
    }

    for mistake, correction in mistakes.items():
        print(f"\nMistake: {mistake}")
        print(f"Correction: {correction}")


# =============================================================================
# 55. EDGE CASES
# =============================================================================

def demonstrate_edge_cases() -> None:
    subsection("Important edge cases")

    edge_cases = [
        "A program can be CPU-idle while waiting on disk or network I/O.",
        "A machine can have free RAM but still experience poor performance due to CPU, storage, or software bottlenecks.",
        "A process can contain many threads that contend for the same lock.",
        "A cache can be ineffective when an access pattern has poor locality.",
        "Adding CPU cores cannot eliminate work that is fundamentally serial.",
        "A memory leak can occur when objects remain reachable even though they are no longer useful.",
        "A deadlock can leave resources permanently unavailable until a participant is terminated or the condition is otherwise broken.",
        "A race condition may appear rarely, making it difficult to reproduce.",
        "An I/O bottleneck can remain even after increasing CPU capacity.",
        "High throughput does not necessarily imply low latency.",
    ]

    for index, case in enumerate(edge_cases, start=1):
        print(f"{index:>2}. {case}")


# =============================================================================
# 56. END-TO-END SYSTEM MODEL
# =============================================================================

def demonstrate_end_to_end_model() -> None:
    subsection("End-to-end computer model")

    layers = [
        ("Applications", "User-facing programs and services"),
        ("Libraries/runtime", "Reusable APIs and language execution environment"),
        ("Operating system", "Processes, threads, memory, files, devices, security"),
        ("CPU", "Instruction execution and computation"),
        ("RAM/cache", "Fast working data and instructions"),
        ("Storage", "Persistent data"),
        ("Devices", "Network, display, keyboard, disks, sensors, and more"),
        ("Hardware interconnects", "Paths connecting system components"),
    ]

    for layer, role in layers:
        print(f"{layer:<24} {role}")

    print(
        "\nA computer is a coordinated system rather than a single component. "
        "Program performance and behavior emerge from interactions between software, "
        "the operating system, CPU, memory hierarchy, storage, and devices."
    )


# =============================================================================
# 57. MINI QUIZ
# =============================================================================

def run_self_check() -> None:
    subsection("Self-check questions")

    questions = [
        (
            "Which component performs arithmetic and logical operations?",
            "ALU",
        ),
        (
            "Which memory type normally loses its contents when power is removed?",
            "RAM",
        ),
        (
            "What is the basic CPU instruction sequence?",
            "Fetch, decode, execute",
        ),
        (
            "What is a process?",
            "A running program together with its execution state and resources",
        ),
        (
            "What is a thread?",
            "An execution path within a process",
        ),
        (
            "What is a race condition?",
            "A correctness problem caused by unsafe timing/interleaving of concurrent operations",
        ),
        (
            "What is a context switch?",
            "Saving one execution context and restoring another",
        ),
        (
            "What is virtual memory?",
            "An abstraction that gives processes virtual address spaces mapped to physical memory",
        ),
    ]

    for index, (question, answer) in enumerate(questions, start=1):
        print(f"\n{index}. {question}")
        print("   Answer:", answer)


# =============================================================================
# 58. MAIN PROGRAM
# =============================================================================

def main() -> None:
    """Run the complete computer-fundamentals tutorial."""

    print("=" * 78)
    print("COMPUTER FUNDAMENTALS: HOW COMPUTERS WORK")
    print("CPU, RAM, STORAGE, PROCESSES, AND THREADS")
    print("=" * 78)

    demonstrate_binary()
    demonstrate_memory_hierarchy()
    demonstrate_cpu()
    demonstrate_cpu_components()
    demonstrate_locality()
    demonstrate_ram()
    demonstrate_storage()
    demonstrate_virtual_memory()
    demonstrate_process_model()
    demonstrate_real_process()
    demonstrate_threads()
    compare_processes_and_threads()
    demonstrate_synchronization()
    demonstrate_race_condition_model()
    demonstrate_deadlock_prevention()
    demonstrate_producer_consumer()
    demonstrate_workload_types()
    demonstrate_concurrent_io()
    demonstrate_scheduling()
    demonstrate_context_switch()
    demonstrate_thread_states()
    demonstrate_multiple_processes()
    demonstrate_amdahl()
    demonstrate_performance_metrics()
    demonstrate_memory_lifetime()
    demonstrate_errors()
    demonstrate_security_principles()
    demonstrate_system_information()
    demonstrate_storage_units()
    demonstrate_cache()
    demonstrate_stack_and_heap()
    demonstrate_system_call_concept()
    demonstrate_privilege_levels()
    demonstrate_interrupts()
    demonstrate_file_system()
    demonstrate_thread_pool()
    demonstrate_backpressure()
    demonstrate_benchmarking()
    demonstrate_algorithmic_cost()
    demonstrate_fixed_width_integers()
    demonstrate_thread_local_storage()
    demonstrate_event_synchronization()
    demonstrate_process_communication()
    demonstrate_pipeline()
    demonstrate_branch_prediction()
    demonstrate_false_sharing_concept()
    demonstrate_cache_coherence()
    demonstrate_dma()
    demonstrate_storage_performance()
    demonstrate_reliability()
    demonstrate_timeout()
    demonstrate_bounded_concurrency()
    demonstrate_observability()
    integrated_execution_example()
    demonstrate_common_mistakes()
    demonstrate_edge_cases()
    demonstrate_end_to_end_model()
    run_self_check()

    section("Tutorial execution completed")
    print(
        "The demonstrations above model the major relationships between "
        "CPU execution, memory, persistent storage, operating-system processes, "
        "threads, concurrency, and system performance."
    )


if __name__ == "__main__":
    main()
