"""
Memory Hierarchy: Registers, Cache, RAM, SSD, and HDD
======================================================

A self-contained study and demonstration program that progresses from
absolute beginner concepts to advanced memory-hierarchy topics.

The program uses simulations rather than relying on a particular computer's
hardware. Real hardware characteristics vary by CPU, cache design, RAM type,
SSD controller, NAND generation, operating system, and workload.

Covered topics
--------------
- Why computer systems need a memory hierarchy
- Bits, bytes, addresses, storage capacity, and latency
- Registers
- CPU cache
- Cache lines
- Spatial and temporal locality
- L1, L2, and L3 cache
- SRAM versus DRAM
- RAM
- Virtual memory and paging
- SSDs and NAND flash
- HDDs and magnetic storage
- Volatile versus non-volatile storage
- Access-path comparisons
- Cache hits and misses
- Hit rate, miss rate, AMAT
- Multi-level cache modeling
- Write-through and write-back
- Write-allocate and no-write-allocate
- Cache mapping: direct, fully associative, set associative
- Replacement policies
- Dirty and valid bits
- TLBs
- Page faults
- Working sets
- Sequential versus random access
- Array traversal and cache locality
- False sharing
- Storage endurance and write amplification
- HDD seek and rotational latency
- SSD garbage collection and TRIM
- Performance simulations
- Benchmark interpretation
- Common misconceptions
- Validation and error handling
- Practical design principles

Run this file directly:
    python memory_hierarchy.py

No external packages are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple, Iterable, Any
import math
import random
import statistics
import time


# ============================================================================
# SECTION 1: BASIC UNITS AND CONCEPTS
# ============================================================================

def heading(title: str) -> None:
    """Print a consistent section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def subheading(title: str) -> None:
    """Print a smaller heading."""
    print("\n" + "-" * 78)
    print(title)
    print("-" * 78)


def format_bytes(number_of_bytes: int) -> str:
    """
    Convert a byte count into a readable binary-unit representation.

    Binary units:
        KiB = 1024 bytes
        MiB = 1024 KiB
        GiB = 1024 MiB
        TiB = 1024 GiB
    """
    if number_of_bytes < 0:
        raise ValueError("Byte count cannot be negative.")

    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    value = float(number_of_bytes)

    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024

    return f"{value:.2f} PiB"


def format_latency(nanoseconds: float) -> str:
    """Convert nanoseconds to an appropriate human-readable unit."""
    if nanoseconds < 1_000:
        return f"{nanoseconds:.2f} ns"
    if nanoseconds < 1_000_000:
        return f"{nanoseconds / 1_000:.2f} µs"
    if nanoseconds < 1_000_000_000:
        return f"{nanoseconds / 1_000_000:.2f} ms"
    return f"{nanoseconds / 1_000_000_000:.2f} s"


def explain_basic_units() -> None:
    heading("1. Fundamental Units: Bits, Bytes, Addresses, and Capacity")

    print("A bit stores one binary digit: 0 or 1.")
    print("A byte contains 8 bits.")
    print("Memory is normally addressed in units of bytes.")
    print()

    examples = [1, 8, 1024, 1024**2, 1024**3, 1024**4]
    for value in examples:
        print(f"{value:>15,} bytes = {format_bytes(value)}")

    print()
    print("Important distinction:")
    print("  bit  -> b")
    print("  byte -> B")
    print("  8 bits = 1 byte")
    print()
    print("A memory address identifies a location in an addressable memory space.")
    print("Capacity tells how much data can be stored.")
    print("Latency tells how long an access takes.")
    print("Bandwidth tells how much data can be transferred per unit time.")


# ============================================================================
# SECTION 2: THE MEMORY HIERARCHY
# ============================================================================

@dataclass(frozen=True)
class MemoryLevel:
    """Description of one conceptual memory-hierarchy level."""

    name: str
    capacity: str
    typical_latency_ns: float
    volatile: bool
    technology: str
    purpose: str


MEMORY_LEVELS = [
    MemoryLevel(
        "CPU Registers",
        "Very small",
        0.3,
        True,
        "Flip-flop/register storage",
        "Immediate operands, addresses, intermediate results",
    ),
    MemoryLevel(
        "L1 Cache",
        "Tens of KiB per core",
        1.0,
        True,
        "SRAM",
        "Very fast cache close to the execution core",
    ),
    MemoryLevel(
        "L2 Cache",
        "Hundreds of KiB to a few MiB",
        4.0,
        True,
        "SRAM",
        "Larger cache with slightly higher latency",
    ),
    MemoryLevel(
        "L3 Cache",
        "Several MiB to many tens of MiB",
        12.0,
        True,
        "SRAM",
        "Large shared or partially shared CPU cache",
    ),
    MemoryLevel(
        "RAM",
        "GiB scale",
        80.0,
        True,
        "DRAM",
        "Main working memory for active programs",
    ),
    MemoryLevel(
        "SSD",
        "Hundreds of GiB to many TiB",
        100_000.0,
        False,
        "NAND flash",
        "Persistent high-speed mass storage",
    ),
    MemoryLevel(
        "HDD",
        "TiB scale",
        10_000_000.0,
        False,
        "Magnetic disks",
        "Persistent high-capacity mass storage",
    ),
]


def print_memory_hierarchy() -> None:
    heading("2. The Memory Hierarchy")

    print(
        "A memory hierarchy combines technologies with different costs, "
        "capacities, speeds, and persistence properties."
    )
    print()
    print(
        f"{'Level':<20} {'Capacity':<25} {'Latency':<15} "
        f"{'Volatile':<10} {'Technology'}"
    )
    print("-" * 100)

    for level in MEMORY_LEVELS:
        print(
            f"{level.name:<20} "
            f"{level.capacity:<25} "
            f"{format_latency(level.typical_latency_ns):<15} "
            f"{str(level.volatile):<10} "
            f"{level.technology}"
        )

    print()
    print("The exact numbers above are educational approximations, not hardware specifications.")
    print()
    print("General pattern:")
    print("  Higher in hierarchy -> smaller, faster, more expensive per byte")
    print("  Lower in hierarchy  -> larger, slower, cheaper per byte, usually persistent")


# ============================================================================
# SECTION 3: REGISTERS
# ============================================================================

@dataclass
class CPURegisters:
    """
    A simplified register file.

    Real CPUs have architecture-specific registers and restrictions.
    This class models the fundamental idea rather than a particular ISA.
    """

    general_purpose: Dict[str, int] = field(default_factory=dict)
    program_counter: int = 0
    stack_pointer: int = 0
    flags: Dict[str, bool] = field(
        default_factory=lambda: {
            "zero": False,
            "negative": False,
            "carry": False,
            "overflow": False,
        }
    )

    def write(self, register: str, value: int) -> None:
        """Write an integer value into a general-purpose register."""
        if not isinstance(value, int):
            raise TypeError("This simplified register model stores integers only.")
        self.general_purpose[register] = value

    def read(self, register: str) -> int:
        """Read a register value."""
        if register not in self.general_purpose:
            raise KeyError(f"Register {register!r} has not been initialized.")
        return self.general_purpose[register]

    def add(self, destination: str, left: str, right: str) -> None:
        """Perform a simplified register-to-register addition."""
        result = self.read(left) + self.read(right)
        self.write(destination, result)

        self.flags["zero"] = result == 0
        self.flags["negative"] = result < 0

    def demo(self) -> None:
        self.write("R1", 25)
        self.write("R2", 17)
        self.add("R3", "R1", "R2")

        print(f"R1 = {self.read('R1')}")
        print(f"R2 = {self.read('R2')}")
        print(f"R3 = R1 + R2 = {self.read('R3')}")
        print(f"Zero flag = {self.flags['zero']}")
        print(f"Negative flag = {self.flags['negative']}")


def explain_registers() -> None:
    heading("3. CPU Registers")

    print(
        "Registers are tiny storage locations directly available to the CPU's "
        "instruction-execution machinery."
    )
    print()
    print("Common conceptual register categories:")
    print("  General-purpose registers -> integers, addresses, intermediate values")
    print("  Program counter            -> address of the next instruction")
    print("  Stack pointer              -> tracks the current stack position")
    print("  Status/flags               -> records arithmetic and control conditions")
    print()
    print("Example register operations:")
    registers = CPURegisters()
    registers.demo()
    print()
    print("Registers are not a replacement for RAM.")
    print("A CPU has only a limited number of registers because very fast storage")
    print("is expensive in chip area and must be close to the execution units.")


# ============================================================================
# SECTION 4: SRAM, DRAM, NAND FLASH, AND MAGNETIC STORAGE
# ============================================================================

def compare_memory_technologies() -> None:
    heading("4. Storage Technologies")

    technologies = [
        (
            "SRAM",
            "Static RAM",
            "Cache",
            "Fast, no refresh cycle, expensive and area-intensive",
        ),
        (
            "DRAM",
            "Dynamic RAM",
            "Main memory",
            "Dense and cheaper per bit, requires refresh",
        ),
        (
            "NAND flash",
            "Non-volatile semiconductor storage",
            "SSD",
            "Persistent, electrically programmed, erase-before-rewrite behavior",
        ),
        (
            "Magnetic media",
            "Magnetic recording",
            "HDD",
            "High capacity, mechanical movement, persistent",
        ),
    ]

    print(f"{'Technology':<15} {'Meaning':<20} {'Typical role':<18} Characteristics")
    print("-" * 100)

    for row in technologies:
        print(f"{row[0]:<15} {row[1]:<20} {row[2]:<18} {row[3]}")

    print()
    print("SRAM commonly forms CPU caches.")
    print("DRAM commonly forms system RAM.")
    print("NAND flash forms the persistent media inside SSDs.")
    print("HDDs use magnetic surfaces and moving mechanical components.")


# ============================================================================
# SECTION 5: CACHE FUNDAMENTALS
# ============================================================================

@dataclass
class CacheLine:
    """One cache line in a simplified cache."""

    tag: Optional[int] = None
    valid: bool = False
    dirty: bool = False
    data: Optional[int] = None


class SimpleDirectMappedCache:
    """
    A small direct-mapped cache.

    Each memory block maps to exactly one cache line.

    Mapping:
        line_index = block_number % number_of_lines
        tag = block_number // number_of_lines
    """

    def __init__(self, number_of_lines: int = 8, block_size: int = 4):
        if number_of_lines <= 0:
            raise ValueError("Cache must have at least one line.")
        if block_size <= 0:
            raise ValueError("Block size must be positive.")

        self.number_of_lines = number_of_lines
        self.block_size = block_size
        self.lines = [CacheLine() for _ in range(number_of_lines)]
        self.hits = 0
        self.misses = 0

    def _decode_address(self, address: int) -> Tuple[int, int, int]:
        if address < 0:
            raise ValueError("Memory addresses cannot be negative.")

        block_number = address // self.block_size
        offset = address % self.block_size
        line_index = block_number % self.number_of_lines
        tag = block_number // self.number_of_lines

        return block_number, line_index, tag

    def access(self, address: int, memory: List[int]) -> Tuple[bool, int]:
        """Read one memory address and report whether the cache hit."""
        if address >= len(memory):
            raise IndexError("Address lies outside the simulated memory.")

        block_number, line_index, tag = self._decode_address(address)
        line = self.lines[line_index]

        if line.valid and line.tag == tag:
            self.hits += 1
            assert line.data is not None
            return True, memory[address]

        self.misses += 1

        # A real cache would fetch an entire cache line, not just one scalar.
        base_address = block_number * self.block_size
        fetched_data = memory[base_address]

        self.lines[line_index] = CacheLine(
            tag=tag,
            valid=True,
            dirty=False,
            data=fetched_data,
        )

        return False, memory[address]

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    @property
    def miss_rate(self) -> float:
        return 1.0 - self.hit_rate

    def reset_statistics(self) -> None:
        self.hits = 0
        self.misses = 0

    def dump(self) -> None:
        print("Cache lines:")
        for index, line in enumerate(self.lines):
            print(
                f"  line {index}: "
                f"valid={line.valid}, tag={line.tag}, dirty={line.dirty}, data={line.data}"
            )


def explain_cache_basics() -> None:
    heading("5. Cache Fundamentals")

    print("A cache stores recently or frequently needed copies of data.")
    print()
    print("Important terms:")
    print("  Cache line  -> fixed-size unit transferred between cache and lower memory")
    print("  Hit         -> requested data is already available in the cache")
    print("  Miss        -> requested data is not available in that cache")
    print("  Tag         -> identifies which memory block occupies a cache location")
    print("  Index       -> selects a cache location or set")
    print("  Offset      -> identifies a byte within a cache line")
    print()
    print("The cache is effective because programs tend to exhibit locality.")
    print("Temporal locality: recently used data is likely to be used again.")
    print("Spatial locality: nearby addresses are likely to be used soon.")

    memory = list(range(32))
    cache = SimpleDirectMappedCache(number_of_lines=4, block_size=4)

    addresses = [0, 1, 2, 3, 0, 1, 2, 3, 16, 17, 0, 1]

    print()
    print("Address access simulation:")
    for address in addresses:
        hit, value = cache.access(address, memory)
        print(f"  address={address:>2}, value={value:>2}, {'HIT' if hit else 'MISS'}")

    print()
    print(f"Hits     = {cache.hits}")
    print(f"Misses   = {cache.misses}")
    print(f"Hit rate = {cache.hit_rate:.2%}")
    cache.dump()


# ============================================================================
# SECTION 6: CACHE ADDRESS DECOMPOSITION
# ============================================================================

def demonstrate_address_decomposition(
    address: int,
    block_size: int,
    number_of_lines: int,
) -> None:
    """
    Show block, offset, index, and tag for a direct-mapped cache.

    This is a conceptual byte-addressed model.
    """
    if address < 0:
        raise ValueError("Address cannot be negative.")
    if block_size <= 0 or number_of_lines <= 0:
        raise ValueError("Block size and number of lines must be positive.")

    block_number = address // block_size
    offset = address % block_size
    index = block_number % number_of_lines
    tag = block_number // number_of_lines

    print(f"Address       : {address}")
    print(f"Block size    : {block_size} bytes")
    print(f"Block number  : {block_number}")
    print(f"Offset        : {offset}")
    print(f"Cache index   : {index}")
    print(f"Tag           : {tag}")


def demonstrate_cache_address_fields() -> None:
    heading("6. Cache Address Decomposition")

    print(
        "For a direct-mapped cache, an address can conceptually be decomposed "
        "into tag, index, and offset."
    )
    print()

    demonstrate_address_decomposition(
        address=37,
        block_size=4,
        number_of_lines=8,
    )

    print()
    print("For power-of-two dimensions, hardware commonly implements these fields")
    print("using bit ranges rather than expensive integer division operations.")


# ============================================================================
# SECTION 7: ASSOCIATIVITY
# ============================================================================

class MappingType(Enum):
    DIRECT = "Direct mapped"
    SET_ASSOCIATIVE = "Set associative"
    FULLY_ASSOCIATIVE = "Fully associative"


@dataclass
class AssociativeCache:
    """
    Educational set-associative cache.

    The implementation uses an OrderedDict per set to model LRU replacement.
    """

    number_of_sets: int
    ways: int
    block_size: int

    def __post_init__(self) -> None:
        if self.number_of_sets <= 0:
            raise ValueError("Number of sets must be positive.")
        if self.ways <= 0:
            raise ValueError("Associativity must be positive.")
        if self.block_size <= 0:
            raise ValueError("Block size must be positive.")

        self.sets: List[OrderedDict[int, int]] = [
            OrderedDict() for _ in range(self.number_of_sets)
        ]
        self.hits = 0
        self.misses = 0

    def access(self, address: int, memory: List[int]) -> Tuple[bool, int]:
        if address < 0 or address >= len(memory):
            raise IndexError("Address outside memory.")

        block = address // self.block_size
        set_index = block % self.number_of_sets
        current_set = self.sets[set_index]

        if block in current_set:
            self.hits += 1
            value = current_set.pop(block)
            current_set[block] = value
            return True, memory[address]

        self.misses += 1

        if len(current_set) >= self.ways:
            current_set.popitem(last=False)

        current_set[block] = memory[block * self.block_size]
        return False, memory[address]

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


def compare_cache_mapping() -> None:
    heading("7. Cache Mapping and Associativity")

    print("Three fundamental mapping organizations:")
    print("  Direct mapped       -> each block has exactly one possible location")
    print("  Set associative     -> each block maps to one set and may occupy one of several ways")
    print("  Fully associative   -> a block can occupy any cache line")
    print()
    print("Trade-off:")
    print("  More associativity reduces some conflict misses.")
    print("  More associativity requires more comparison and hardware complexity.")
    print()
    print("A 4-way cache has four possible lines within each set.")
    print("A fully associative cache with N lines effectively has N ways in one set.")

    memory = list(range(128))
    access_pattern = [0, 8, 16, 24, 0, 8, 16, 24]

    direct = SimpleDirectMappedCache(number_of_lines=4, block_size=4)
    associative = AssociativeCache(number_of_sets=1, ways=4, block_size=4)

    for address in access_pattern:
        direct.access(address, memory)
        associative.access(address, memory)

    print()
    print("Conflict-heavy access pattern:")
    print(f"  Direct-mapped hit rate = {direct.hit_rate:.2%}")
    print(f"  Fully associative-like hit rate = {associative.hit_rate:.2%}")

    print()
    print("This demonstrates why associativity matters when multiple blocks compete")
    print("for the same cache location.")


# ============================================================================
# SECTION 8: CACHE MISS CLASSIFICATION
# ============================================================================

def classify_cache_misses() -> None:
    heading("8. Types of Cache Misses")

    print("A useful conceptual classification is:")
    print()
    print("Compulsory miss")
    print("  The first access to a block misses because the block has never been cached.")
    print()
    print("Capacity miss")
    print("  The working set exceeds the available cache capacity.")
    print()
    print("Conflict miss")
    print("  Blocks would fit in total cache capacity but mapping forces them")
    print("  to compete for the same location or set.")
    print()
    print("Coherence-related effects")
    print("  In multicore systems, another core can invalidate or modify a cached line.")
    print("  These effects are distinct from the traditional three C classification.")
    print()
    print("Miss classification is useful because the remedy differs:")
    print("  Compulsory -> prefetching or larger initial fetches may help.")
    print("  Capacity   -> improve locality or increase cache capacity.")
    print("  Conflict   -> change layout/access pattern or increase associativity.")


# ============================================================================
# SECTION 9: CACHE REPLACEMENT POLICIES
# ============================================================================

class ReplacementPolicy(Enum):
    LRU = "Least Recently Used"
    FIFO = "First In First Out"
    RANDOM = "Random"


class ReplacementCache:
    """Small fully associative cache with configurable replacement policy."""

    def __init__(self, capacity: int, policy: ReplacementPolicy):
        if capacity <= 0:
            raise ValueError("Capacity must be positive.")

        self.capacity = capacity
        self.policy = policy
        self.entries: List[int] = []
        self.access_order: OrderedDict[int, None] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def access(self, block: int) -> bool:
        if block in self.entries:
            self.hits += 1

            if self.policy == ReplacementPolicy.LRU:
                self.access_order.pop(block, None)
                self.access_order[block] = None

            return True

        self.misses += 1

        if len(self.entries) < self.capacity:
            self.entries.append(block)
        else:
            if self.policy == ReplacementPolicy.LRU:
                victim = next(iter(self.access_order))
                self.access_order.pop(victim, None)
            elif self.policy == ReplacementPolicy.FIFO:
                victim = self.entries[0]
            else:
                victim = random.choice(self.entries)

            self.entries.remove(victim)
            self.entries.append(block)

        if self.policy == ReplacementPolicy.LRU:
            self.access_order[block] = None

        return False

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


def compare_replacement_policies() -> None:
    heading("9. Cache Replacement Policies")

    sequence = [1, 2, 3, 1, 4, 1, 2, 5, 1, 2, 3, 4, 5]

    print(f"Access sequence: {sequence}")
    print()

    for policy in ReplacementPolicy:
        random.seed(7)
        cache = ReplacementCache(capacity=3, policy=policy)

        for block in sequence:
            cache.access(block)

        print(
            f"{policy.value:<25} "
            f"hits={cache.hits:<3} "
            f"misses={cache.misses:<3} "
            f"hit_rate={cache.hit_rate:.2%}"
        )

    print()
    print("Real processors use more sophisticated policies than a simple textbook LRU")
    print("implementation. Exact policies are implementation-specific and may be adaptive.")


# ============================================================================
# SECTION 10: WRITE POLICIES
# ============================================================================

class WritePolicy(Enum):
    WRITE_THROUGH = "Write-through"
    WRITE_BACK = "Write-back"


class WriteCache:
    """
    Demonstrates the conceptual difference between write-through and write-back.

    The backing memory is a Python list.
    """

    def __init__(self, size: int, policy: WritePolicy):
        if size <= 0:
            raise ValueError("Cache size must be positive.")

        self.cache: Dict[int, Tuple[int, bool]] = {}
        self.memory = [0] * size
        self.policy = policy
        self.memory_writes = 0

    def write(self, address: int, value: int) -> None:
        if address < 0 or address >= len(self.memory):
            raise IndexError("Address outside memory.")

        if self.policy == WritePolicy.WRITE_THROUGH:
            self.cache[address] = (value, False)
            self.memory[address] = value
            self.memory_writes += 1
        else:
            self.cache[address] = (value, True)

    def read(self, address: int) -> int:
        if address in self.cache:
            return self.cache[address][0]
        return self.memory[address]

    def flush(self) -> None:
        """Write dirty cache entries to backing memory."""
        for address, (value, dirty) in list(self.cache.items()):
            if dirty:
                self.memory[address] = value
                self.memory_writes += 1
                self.cache[address] = (value, False)


def demonstrate_write_policies() -> None:
    heading("10. Write-Through and Write-Back")

    for policy in WritePolicy:
        cache = WriteCache(size=16, policy=policy)

        for value in [10, 20, 30, 40]:
            cache.write(3, value)

        before_flush = cache.memory_writes
        cache.flush()
        after_flush = cache.memory_writes

        print(f"{policy.value}:")
        print(f"  Final cached value = {cache.read(3)}")
        print(f"  Memory writes before flush = {before_flush}")
        print(f"  Memory writes after flush  = {after_flush}")
        print()

    print("Write-through:")
    print("  Cache writes are propagated to lower memory immediately.")
    print()
    print("Write-back:")
    print("  Modified lines become dirty and are written to lower memory when evicted")
    print("  or explicitly flushed.")
    print()
    print("Write-back can reduce lower-level traffic but requires dirty-state management.")


# ============================================================================
# SECTION 11: AMAT
# ============================================================================

def average_memory_access_time(
    hit_time_ns: float,
    miss_rate: float,
    miss_penalty_ns: float,
) -> float:
    """
    Calculate Average Memory Access Time using:

        AMAT = hit time + miss rate * miss penalty
    """
    if hit_time_ns < 0:
        raise ValueError("Hit time cannot be negative.")
    if not 0 <= miss_rate <= 1:
        raise ValueError("Miss rate must be between 0 and 1.")
    if miss_penalty_ns < 0:
        raise ValueError("Miss penalty cannot be negative.")

    return hit_time_ns + miss_rate * miss_penalty_ns


def demonstrate_amat() -> None:
    heading("11. Average Memory Access Time")

    print("A simple one-level model is:")
    print("  AMAT = hit time + miss rate × miss penalty")
    print()

    scenarios = [
        ("Excellent locality", 1.0, 0.02, 80.0),
        ("Moderate locality", 1.0, 0.10, 80.0),
        ("Poor locality", 1.0, 0.30, 80.0),
    ]

    for name, hit_time, miss_rate, penalty in scenarios:
        amat = average_memory_access_time(hit_time, miss_rate, penalty)
        print(
            f"{name:<22} "
            f"miss rate={miss_rate:.0%}, "
            f"AMAT={amat:.2f} ns"
        )

    print()
    print("A small improvement in hit rate can matter greatly when the miss penalty")
    print("is large. This is one reason locality is central to performance engineering.")


# ============================================================================
# SECTION 12: MULTI-LEVEL CACHE AMAT
# ============================================================================

def multilevel_amat(
    l1_hit_time: float,
    l1_miss_rate: float,
    l2_hit_time: float,
    l2_local_miss_rate: float,
    memory_penalty: float,
) -> float:
    """
    Compute a simple two-cache-level AMAT model.

    Formula:
        AMAT =
            L1 hit time
            + L1 miss rate * (
                L2 hit time
                + L2 local miss rate * memory penalty
            )
    """
    if not 0 <= l1_miss_rate <= 1:
        raise ValueError("L1 miss rate must be in [0, 1].")
    if not 0 <= l2_local_miss_rate <= 1:
        raise ValueError("L2 local miss rate must be in [0, 1].")

    return (
        l1_hit_time
        + l1_miss_rate
        * (l2_hit_time + l2_local_miss_rate * memory_penalty)
    )


def demonstrate_multilevel_amat() -> None:
    heading("12. Multi-Level Cache Performance")

    amat = multilevel_amat(
        l1_hit_time=1.0,
        l1_miss_rate=0.08,
        l2_hit_time=4.0,
        l2_local_miss_rate=0.15,
        memory_penalty=80.0,
    )

    print(f"Estimated two-level AMAT = {amat:.2f} ns")
    print()
    print("A cache hierarchy prevents every L1 miss from immediately becoming")
    print("a main-memory access.")
    print()
    print("The distinction between local and global miss rates matters.")
    print("Local miss rate: misses / accesses reaching that cache.")
    print("Global miss rate: misses at that level relative to all original accesses.")


# ============================================================================
# SECTION 13: LOCALITY DEMONSTRATION
# ============================================================================

def sequential_access(data: List[int]) -> int:
    """Sequential traversal tends to have strong spatial locality."""
    total = 0
    for value in data:
        total += value
    return total


def strided_access(data: List[int], stride: int) -> int:
    """Stride access skips elements and can reduce spatial locality."""
    if stride <= 0:
        raise ValueError("Stride must be positive.")

    total = 0
    for index in range(0, len(data), stride):
        total += data[index]
    return total


def repeated_access(data: List[int], repetitions: int) -> int:
    """Repeatedly touching a small region demonstrates temporal locality."""
    if repetitions < 0:
        raise ValueError("Repetitions cannot be negative.")

    total = 0
    limit = min(64, len(data))

    for _ in range(repetitions):
        for index in range(limit):
            total += data[index]

    return total


def benchmark_function(function, *args, repeats: int = 5) -> Tuple[float, float]:
    """Return minimum and median runtime in seconds."""
    if repeats <= 0:
        raise ValueError("repeats must be positive.")

    timings = []

    for _ in range(repeats):
        start = time.perf_counter()
        function(*args)
        timings.append(time.perf_counter() - start)

    return min(timings), statistics.median(timings)


def demonstrate_locality() -> None:
    heading("13. Temporal and Spatial Locality")

    data = list(range(2_000_000))

    sequential_min, sequential_median = benchmark_function(
        sequential_access,
        data,
        repeats=3,
    )

    stride_min, stride_median = benchmark_function(
        strided_access,
        data,
        16,
        repeats=3,
    )

    repeated_min, repeated_median = benchmark_function(
        repeated_access,
        data,
        10_000,
        repeats=3,
    )

    print("These timings are illustrative and depend on Python interpreter and system.")
    print()
    print(
        f"Sequential access: min={sequential_min:.6f}s, "
        f"median={sequential_median:.6f}s"
    )
    print(
        f"Stride-16 access:  min={stride_min:.6f}s, "
        f"median={stride_median:.6f}s"
    )
    print(
        f"Repeated small region: min={repeated_min:.6f}s, "
        f"median={repeated_median:.6f}s"
    )

    print()
    print("The benchmark does not isolate CPU-cache effects.")
    print("Python interpreter overhead, object representation, branch behavior,")
    print("memory allocation, and the operating system all affect the results.")
    print()
    print("The conceptual lesson is stronger than the exact timing:")
    print("  Sequential access uses nearby memory locations.")
    print("  Repeated access reuses recently touched locations.")
    print("  Large or irregular strides can reduce locality.")


# ============================================================================
# SECTION 14: TWO-DIMENSIONAL DATA AND CACHE-FRIENDLY TRAVERSAL
# ============================================================================

def row_major_sum(matrix: List[List[int]]) -> int:
    """Traverse rows from left to right."""
    total = 0

    for row in matrix:
        for value in row:
            total += value

    return total


def column_major_sum(matrix: List[List[int]]) -> int:
    """Traverse columns first for a row-oriented Python list of lists."""
    if not matrix:
        return 0

    rows = len(matrix)
    columns = len(matrix[0])

    total = 0

    for column in range(columns):
        for row in range(rows):
            total += matrix[row][column]

    return total


def demonstrate_matrix_locality() -> None:
    heading("14. Access Order and Cache Locality")

    size = 600
    matrix = [list(range(size)) for _ in range(size)]

    row_min, row_median = benchmark_function(
        row_major_sum,
        matrix,
        repeats=3,
    )

    column_min, column_median = benchmark_function(
        column_major_sum,
        matrix,
        repeats=3,
    )

    print(
        f"Row-major traversal    : min={row_min:.6f}s, "
        f"median={row_median:.6f}s"
    )
    print(
        f"Column-major traversal : min={column_min:.6f}s, "
        f"median={column_median:.6f}s"
    )

    print()
    print("A row-oriented representation places elements of each row together.")
    print("Walking across a row therefore tends to access nearby objects.")
    print("Walking down a column jumps between separate row objects.")
    print()
    print("This principle appears in image processing, numerical computing,")
    print("database storage, tensor processing, and compiler optimization.")


# ============================================================================
# SECTION 15: CACHE SIMULATION WITH BLOCKS
# ============================================================================

@dataclass
class CacheStatistics:
    accesses: int = 0
    hits: int = 0
    misses: int = 0

    @property
    def hit_rate(self) -> float:
        return self.hits / self.accesses if self.accesses else 0.0

    @property
    def miss_rate(self) -> float:
        return self.misses / self.accesses if self.accesses else 0.0


class BlockCacheSimulator:
    """
    Generic cache simulator.

    It models cache lines at block granularity and uses LRU replacement.
    """

    def __init__(
        self,
        cache_size_bytes: int,
        line_size_bytes: int,
        associativity: int,
    ):
        if cache_size_bytes <= 0:
            raise ValueError("Cache size must be positive.")
        if line_size_bytes <= 0:
            raise ValueError("Line size must be positive.")
        if associativity <= 0:
            raise ValueError("Associativity must be positive.")
        if cache_size_bytes % line_size_bytes != 0:
            raise ValueError("Cache size must be divisible by line size.")

        number_of_lines = cache_size_bytes // line_size_bytes

        if number_of_lines % associativity != 0:
            raise ValueError(
                "Number of lines must be divisible by associativity."
            )

        self.cache_size_bytes = cache_size_bytes
        self.line_size_bytes = line_size_bytes
        self.associativity = associativity
        self.number_of_sets = number_of_lines // associativity

        self.sets = [
            OrderedDict() for _ in range(self.number_of_sets)
        ]

        self.statistics = CacheStatistics()

    def access(self, address: int) -> bool:
        if address < 0:
            raise ValueError("Address cannot be negative.")

        block = address // self.line_size_bytes
        set_index = block % self.number_of_sets
        current_set = self.sets[set_index]

        self.statistics.accesses += 1

        if block in current_set:
            self.statistics.hits += 1
            value = current_set.pop(block)
            current_set[block] = value
            return True

        self.statistics.misses += 1

        if len(current_set) >= self.associativity:
            current_set.popitem(last=False)

        current_set[block] = None
        return False

    def run(self, addresses: Iterable[int]) -> CacheStatistics:
        for address in addresses:
            self.access(address)
        return self.statistics


def demonstrate_cache_simulator() -> None:
    heading("15. Configurable Cache Simulation")

    addresses = [
        0, 4, 8, 12,
        0, 4, 8, 12,
        64, 68, 72, 76,
        0, 4, 8, 12,
    ]

    configurations = [
        (32, 4, 1),
        (32, 4, 2),
        (32, 4, 4),
    ]

    print(
        f"{'Cache':<18} {'Line':<10} {'Ways':<8} "
        f"{'Hits':<8} {'Misses':<8} {'Hit rate'}"
    )
    print("-" * 75)

    for cache_size, line_size, ways in configurations:
        simulator = BlockCacheSimulator(cache_size, line_size, ways)
        stats = simulator.run(addresses)

        print(
            f"{format_bytes(cache_size):<18} "
            f"{format_bytes(line_size):<10} "
            f"{ways:<8} "
            f"{stats.hits:<8} "
            f"{stats.misses:<8} "
            f"{stats.hit_rate:.2%}"
        )


# ============================================================================
# SECTION 16: RAM AND DRAM
# ============================================================================

@dataclass
class DRAMCell:
    """Conceptual DRAM cell containing one bit."""

    value: int = 0


class SimpleDRAM:
    """
    A conceptual DRAM array.

    Real DRAM uses capacitors, access transistors, sense amplifiers,
    rows, columns, banks, refresh operations, and timing constraints.
    """

    def __init__(self, number_of_bits: int):
        if number_of_bits <= 0:
            raise ValueError("DRAM must contain at least one bit.")

        self.cells = [DRAMCell() for _ in range(number_of_bits)]

    def write_bit(self, address: int, value: int) -> None:
        if address < 0 or address >= len(self.cells):
            raise IndexError("DRAM address outside range.")
        if value not in (0, 1):
            raise ValueError("A bit must be 0 or 1.")

        self.cells[address].value = value

    def read_bit(self, address: int) -> int:
        if address < 0 or address >= len(self.cells):
            raise IndexError("DRAM address outside range.")

        return self.cells[address].value

    def refresh(self) -> None:
        """
        Conceptually refresh the stored values.

        Real DRAM refresh is electrical and hardware-controlled.
        This method only represents the idea.
        """
        for cell in self.cells:
            cell.value = 1 if cell.value else 0


def demonstrate_dram() -> None:
    heading("16. RAM and DRAM")

    dram = SimpleDRAM(16)

    dram.write_bit(0, 1)
    dram.write_bit(1, 0)
    dram.write_bit(2, 1)

    print("Conceptual DRAM contents:")
    print([dram.read_bit(index) for index in range(8)])

    dram.refresh()

    print("After conceptual refresh:")
    print([dram.read_bit(index) for index in range(8)])

    print()
    print("DRAM is called dynamic because stored charge must be periodically refreshed.")
    print("The actual DRAM organization is much more complex than this simulation.")


# ============================================================================
# SECTION 17: VIRTUAL MEMORY
# ============================================================================

@dataclass
class PageTableEntry:
    frame_number: Optional[int]
    present: bool
    writable: bool = True


class PageTable:
    """Simplified virtual-to-physical page mapping."""

    def __init__(self, page_size: int):
        if page_size <= 0:
            raise ValueError("Page size must be positive.")

        self.page_size = page_size
        self.entries: Dict[int, PageTableEntry] = {}

    def map_page(
        self,
        virtual_page: int,
        physical_frame: int,
        writable: bool = True,
    ) -> None:
        if virtual_page < 0 or physical_frame < 0:
            raise ValueError("Page and frame numbers cannot be negative.")

        self.entries[virtual_page] = PageTableEntry(
            frame_number=physical_frame,
            present=True,
            writable=writable,
        )

    def unmap_page(self, virtual_page: int) -> None:
        if virtual_page in self.entries:
            self.entries[virtual_page].present = False
            self.entries[virtual_page].frame_number = None

    def translate(self, virtual_address: int) -> int:
        if virtual_address < 0:
            raise ValueError("Virtual address cannot be negative.")

        virtual_page = virtual_address // self.page_size
        offset = virtual_address % self.page_size

        entry = self.entries.get(virtual_page)

        if entry is None or not entry.present or entry.frame_number is None:
            raise MemoryError(f"Page fault: virtual page {virtual_page} is not present.")

        return entry.frame_number * self.page_size + offset


def demonstrate_virtual_memory() -> None:
    heading("17. Virtual Memory and Paging")

    print("Virtual memory gives each process an abstraction of its address space.")
    print("A virtual address is divided conceptually into:")
    print("  Virtual page number + page offset")
    print()
    print("The page table maps virtual pages to physical frames.")

    page_table = PageTable(page_size=4096)

    page_table.map_page(0, 12)
    page_table.map_page(1, 25)

    virtual_addresses = [0, 100, 4096, 5000]

    for address in virtual_addresses:
        try:
            physical = page_table.translate(address)
            print(f"Virtual {address:>5} -> Physical {physical:>6}")
        except MemoryError as error:
            print(f"Virtual {address:>5} -> {error}")

    print()
    print("Unmapped pages can trigger page faults.")
    print("The operating system may load required data from storage and update the page table.")
    print("This is dramatically slower than a normal cache hit.")


# ============================================================================
# SECTION 18: TLB
# ============================================================================

class TLB:
    """
    Translation Lookaside Buffer.

    A TLB caches recent virtual-page to physical-frame translations.
    """

    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("TLB capacity must be positive.")

        self.capacity = capacity
        self.entries: OrderedDict[int, int] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def lookup(self, virtual_page: int) -> Optional[int]:
        if virtual_page in self.entries:
            self.hits += 1
            frame = self.entries.pop(virtual_page)
            self.entries[virtual_page] = frame
            return frame

        self.misses += 1
        return None

    def insert(self, virtual_page: int, physical_frame: int) -> None:
        if virtual_page in self.entries:
            self.entries.pop(virtual_page)

        elif len(self.entries) >= self.capacity:
            self.entries.popitem(last=False)

        self.entries[virtual_page] = physical_frame


def demonstrate_tlb() -> None:
    heading("18. Translation Lookaside Buffer")

    print("A TLB caches page-table translations.")
    print("Without a useful TLB entry, address translation may require page-table access.")
    print()

    tlb = TLB(capacity=2)

    mappings = {
        0: 100,
        1: 200,
        2: 300,
    }

    sequence = [0, 1, 0, 2, 0, 1, 2]

    for virtual_page in sequence:
        frame = tlb.lookup(virtual_page)

        if frame is None:
            frame = mappings[virtual_page]
            tlb.insert(virtual_page, frame)
            result = "TLB MISS"
        else:
            result = "TLB HIT"

        print(
            f"virtual page {virtual_page} -> frame {frame} ({result})"
        )

    print()
    print(f"TLB hits   = {tlb.hits}")
    print(f"TLB misses = {tlb.misses}")
    print(f"TLB hit rate = {tlb.hits / (tlb.hits + tlb.misses):.2%}")


# ============================================================================
# SECTION 19: WORKING SET
# ============================================================================

def working_set(sequence: List[int], window_size: int) -> List[int]:
    """Return the number of unique blocks in each sliding window."""
    if window_size <= 0:
        raise ValueError("Window size must be positive.")
    if window_size > len(sequence):
        raise ValueError("Window size cannot exceed sequence length.")

    result = []

    for start in range(len(sequence) - window_size + 1):
        window = sequence[start:start + window_size]
        result.append(len(set(window)))

    return result


def demonstrate_working_set() -> None:
    heading("19. Working Sets and Locality")

    sequence = [
        1, 2, 3, 1, 2, 3,
        1, 2, 3, 1, 2, 3,
        20, 21, 22, 23, 24, 25,
        20, 21, 22, 23, 24, 25,
    ]

    sizes = working_set(sequence, window_size=6)

    print(f"Access sequence: {sequence}")
    print(f"Six-access working-set sizes: {sizes}")
    print()
    print("A working set approximates the data a program actively needs during a period.")
    print("If the active working set fits in a cache or memory level, locality can be strong.")
    print("If it repeatedly exceeds the level's capacity, misses increase.")


# ============================================================================
# SECTION 20: PREFETCHING
# ============================================================================

class PrefetchCache:
    """
    Educational cache with optional next-block prefetching.

    Real hardware prefetchers use multiple heuristics and do not simply
    fetch every next block.
    """

    def __init__(self, capacity: int, prefetch: bool):
        if capacity <= 0:
            raise ValueError("Capacity must be positive.")

        self.capacity = capacity
        self.prefetch = prefetch
        self.cache: OrderedDict[int, None] = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.prefetches = 0

    def _insert(self, block: int) -> None:
        if block in self.cache:
            self.cache.move_to_end(block)
            return

        if len(self.cache) >= self.capacity:
            self.cache.popitem(last=False)

        self.cache[block] = None

    def access(self, block: int) -> bool:
        if block in self.cache:
            self.hits += 1
            self.cache.move_to_end(block)
            return True

        self.misses += 1
        self._insert(block)

        if self.prefetch:
            self._insert(block + 1)
            self.prefetches += 1

        return False


def demonstrate_prefetching() -> None:
    heading("20. Prefetching")

    sequential_blocks = list(range(30))

    for enabled in (False, True):
        cache = PrefetchCache(capacity=8, prefetch=enabled)

        for block in sequential_blocks:
            cache.access(block)

        total = cache.hits + cache.misses

        print(
            f"Prefetch={'ON ' if enabled else 'OFF'} "
            f"hits={cache.hits}, "
            f"misses={cache.misses}, "
            f"hit_rate={cache.hits / total:.2%}, "
            f"prefetches={cache.prefetches}"
        )

    print()
    print("Prefetching can hide latency when future accesses are predictable.")
    print("It can hurt when predictions are wrong because it consumes bandwidth")
    print("and may evict useful data.")


# ============================================================================
# SECTION 21: FALSE SHARING
# ============================================================================

@dataclass
class CacheLineOwnership:
    owner: Optional[str] = None
    invalidations: int = 0


def simulate_false_sharing(
    iterations: int,
    same_cache_line: bool,
) -> CacheLineOwnership:
    """
    Simplified false-sharing simulation.

    Two threads update different variables. If they occupy the same cache line,
    coherence traffic can occur even though the logical variables differ.
    """
    if iterations < 0:
        raise ValueError("Iterations cannot be negative.")

    state = CacheLineOwnership()

    for iteration in range(iterations):
        thread = "T0" if iteration % 2 == 0 else "T1"

        if state.owner is not None and state.owner != thread and same_cache_line:
            state.invalidations += 1

        state.owner = thread

    return state


def demonstrate_false_sharing() -> None:
    heading("21. Multicore Cache Coherence and False Sharing")

    same_line = simulate_false_sharing(100, same_cache_line=True)
    separate_lines = simulate_false_sharing(100, same_cache_line=False)

    print("Two logical counters are updated by different threads.")
    print()
    print(f"Same cache line    -> invalidations={same_line.invalidations}")
    print(f"Separate cache lines -> invalidations={separate_lines.invalidations}")
    print()
    print("False sharing occurs when independent variables share a cache line.")
    print("The coherence system tracks cache lines, not individual high-level variables.")
    print("Padding or layout changes can sometimes reduce this effect.")


# ============================================================================
# SECTION 22: CACHE COHERENCE
# ============================================================================

def explain_cache_coherence() -> None:
    heading("22. Cache Coherence")

    print("In multicore systems, multiple cores may cache the same memory block.")
    print()
    print("A coherence protocol maintains rules about which cached copies are valid")
    print("and which core may modify a cache line.")
    print()
    print("Common conceptual protocol states include the MESI states:")
    print("  M = Modified")
    print("  E = Exclusive")
    print("  S = Shared")
    print("  I = Invalid")
    print()
    print("MESI is an example, not a universal implementation.")
    print("Coherence is different from consistency:")
    print("  Coherence concerns a particular memory location and its cached copies.")
    print("  Consistency concerns the ordering rules visible across memory operations.")


# ============================================================================
# SECTION 23: HDD MODEL
# ============================================================================

@dataclass
class HDDGeometry:
    tracks: int
    sectors_per_track: int
    rotation_rpm: int


class HDDSimulator:
    """
    Simplified HDD timing model.

    It models:
        seek time
        rotational latency
        transfer time

    Actual HDDs have zones, caches, command scheduling, firmware effects,
    head movement characteristics, and variable transfer rates.
    """

    def __init__(self, geometry: HDDGeometry, average_seek_ms: float):
        if geometry.tracks <= 0:
            raise ValueError("Tracks must be positive.")
        if geometry.sectors_per_track <= 0:
            raise ValueError("Sectors per track must be positive.")
        if geometry.rotation_rpm <= 0:
            raise ValueError("RPM must be positive.")
        if average_seek_ms < 0:
            raise ValueError("Seek time cannot be negative.")

        self.geometry = geometry
        self.average_seek_ms = average_seek_ms

    @property
    def rotation_period_ms(self) -> float:
        return 60_000 / self.geometry.rotation_rpm

    @property
    def average_rotational_latency_ms(self) -> float:
        return self.rotation_period_ms / 2

    def access_time_ms(
        self,
        sectors: int,
        transfer_rate_mb_per_s: float = 180.0,
    ) -> float:
        if sectors <= 0:
            raise ValueError("Sector count must be positive.")
        if transfer_rate_mb_per_s <= 0:
            raise ValueError("Transfer rate must be positive.")

        transfer_time_ms = (
            sectors / self.geometry.sectors_per_track
            * self.rotation_period_ms
        )

        transfer_time_ms = min(
            transfer_time_ms,
            (sectors * 512) / (transfer_rate_mb_per_s * 1_000_000) * 1000,
        )

        return (
            self.average_seek_ms
            + self.average_rotational_latency_ms
            + transfer_time_ms
        )


def demonstrate_hdd() -> None:
    heading("23. HDD Access Mechanics")

    hdd = HDDSimulator(
        HDDGeometry(
            tracks=1_000_000,
            sectors_per_track=1_000,
            rotation_rpm=7_200,
        ),
        average_seek_ms=8.0,
    )

    print(f"Rotation period = {hdd.rotation_period_ms:.3f} ms")
    print(
        f"Average rotational latency = "
        f"{hdd.average_rotational_latency_ms:.3f} ms"
    )
    print(
        f"Estimated access = "
        f"{hdd.access_time_ms(sectors=8):.3f} ms"
    )

    print()
    print("HDD latency contains mechanical components:")
    print("  Seek latency       -> moving the actuator/head")
    print("  Rotational latency -> waiting for the required sector to rotate into position")
    print("  Transfer time      -> reading or writing the data")
    print()
    print("Sequential I/O can be much more efficient because it reduces mechanical movement.")


# ============================================================================
# SECTION 24: SSD MODEL
# ============================================================================

class SSDModel:
    """
    Conceptual NAND SSD model.

    The model demonstrates:
        pages
        erase blocks
        logical-to-physical mapping
        invalid pages
        garbage collection
        write amplification

    It intentionally does not model a real SSD controller.
    """

    def __init__(self, pages_per_block: int, number_of_blocks: int):
        if pages_per_block <= 0 or number_of_blocks <= 0:
            raise ValueError("SSD dimensions must be positive.")

        self.pages_per_block = pages_per_block
        self.number_of_blocks = number_of_blocks
        self.total_pages = pages_per_block * number_of_blocks

        self.logical_to_physical: Dict[int, int] = {}
        self.valid_physical_pages: set[int] = set()
        self.next_free_page = 0

        self.host_writes = 0
        self.physical_page_programs = 0
        self.block_erases = 0

    def _allocate_page(self) -> int:
        if self.next_free_page >= self.total_pages:
            self.garbage_collect()

        if self.next_free_page >= self.total_pages:
            raise RuntimeError("SSD has no available page after garbage collection.")

        page = self.next_free_page
        self.next_free_page += 1
        return page

    def write(self, logical_page: int) -> None:
        if logical_page < 0:
            raise ValueError("Logical page cannot be negative.")
        if logical_page >= self.total_pages:
            raise IndexError("Logical page outside simulated SSD.")

        physical_page = self._allocate_page()

        old_page = self.logical_to_physical.get(logical_page)

        if old_page is not None:
            self.valid_physical_pages.discard(old_page)

        self.logical_to_physical[logical_page] = physical_page
        self.valid_physical_pages.add(physical_page)

        self.host_writes += 1
        self.physical_page_programs += 1

    def garbage_collect(self) -> None:
        """
        Simplified garbage collection.

        A real SSD chooses victim blocks using controller-specific policies,
        copies valid pages, erases blocks, and manages spare area.
        """
        if not self.valid_physical_pages:
            self.next_free_page = 0
            self.block_erases += 1
            return

        occupied_blocks = {
            page // self.pages_per_block
            for page in self.valid_physical_pages
        }

        victim_block = min(occupied_blocks)

        victim_start = victim_block * self.pages_per_block
        victim_end = victim_start + self.pages_per_block

        valid_pages = [
            page
            for page in self.valid_physical_pages
            if victim_start <= page < victim_end
        ]

        remaining_pages = [
            page
            for page in self.valid_physical_pages
            if not (victim_start <= page < victim_end)
        ]

        relocation_map: Dict[int, int] = {}

        for old_physical in valid_pages:
            new_physical = self.next_free_page
            self.next_free_page += 1

            if self.next_free_page >= self.total_pages:
                self.next_free_page = 0

            relocation_map[old_physical] = new_physical
            self.physical_page_programs += 1

        for logical_page, physical_page in list(self.logical_to_physical.items()):
            if physical_page in relocation_map:
                new_physical = relocation_map[physical_page]
                self.logical_to_physical[logical_page] = new_physical

        self.valid_physical_pages = set(remaining_pages)
        self.valid_physical_pages.update(relocation_map.values())

        self.block_erases += 1

        if self.next_free_page >= self.total_pages:
            self.next_free_page = 0

    @property
    def write_amplification(self) -> float:
        if self.host_writes == 0:
            return 0.0
        return self.physical_page_programs / self.host_writes


def demonstrate_ssd() -> None:
    heading("24. SSDs, NAND Flash, and Write Amplification")

    ssd = SSDModel(pages_per_block=8, number_of_blocks=8)

    for logical_page in range(24):
        ssd.write(logical_page)

    for logical_page in range(12):
        ssd.write(logical_page)

    print(f"Host writes             = {ssd.host_writes}")
    print(f"Physical page programs  = {ssd.physical_page_programs}")
    print(f"Block erases            = {ssd.block_erases}")
    print(f"Write amplification     = {ssd.write_amplification:.2f}x")

    print()
    print("NAND flash generally cannot overwrite arbitrary existing data in place.")
    print("Data is programmed in pages and erased in larger erase blocks.")
    print()
    print("An SSD controller therefore performs logical-to-physical mapping and")
    print("background operations such as garbage collection and wear management.")
    print()
    print("Write amplification means:")
    print("  physical NAND writes / host-requested writes")
    print()
    print("Higher write amplification can increase latency, consume bandwidth,")
    print("and contribute to flash wear.")


# ============================================================================
# SECTION 25: SSD CONCEPTS
# ============================================================================

def explain_ssd_concepts() -> None:
    heading("25. Important SSD Concepts")

    concepts = {
        "NAND page": "A typical unit for programming or reading flash data.",
        "Erase block": "A larger unit that must generally be erased before reuse.",
        "FTL": "Flash Translation Layer mapping logical addresses to physical flash locations.",
        "Garbage collection": "Reclaims blocks by moving valid data and erasing obsolete data.",
        "Wear leveling": "Distributes writes to avoid concentrating wear on a small set of cells.",
        "Over-provisioning": "Reserved capacity used to improve internal management and performance.",
        "TRIM": "A host hint telling an SSD which logical blocks are no longer needed.",
        "Write amplification": "Physical flash writes divided by host-requested writes.",
    }

    for term, definition in concepts.items():
        print(f"{term:<22} -> {definition}")


# ============================================================================
# SECTION 26: VOLATILITY
# ============================================================================

def demonstrate_volatility() -> None:
    heading("26. Volatile and Non-Volatile Storage")

    print("Volatile storage loses its contents when power is removed.")
    print("Non-volatile storage retains information without continuous power.")
    print()

    rows = [
        ("Registers", True),
        ("CPU cache", True),
        ("RAM", True),
        ("SSD", False),
        ("HDD", False),
    ]

    for name, volatile in rows:
        print(f"{name:<15} volatile={volatile}")

    print()
    print("The hierarchy is not simply a speed ranking.")
    print("It also reflects persistence, cost, capacity, physical technology,")
    print("and how directly the CPU can access the data.")


# ============================================================================
# SECTION 27: BANDWIDTH VERSUS LATENCY
# ============================================================================

def demonstrate_latency_bandwidth() -> None:
    heading("27. Latency Versus Bandwidth")

    print("Latency:")
    print("  Time before useful data begins arriving.")
    print()
    print("Bandwidth:")
    print("  Rate at which data can be transferred after transfer begins.")
    print()

    transfer_size_mb = 100
    examples = [
        ("SSD-like", 0.10, 5_000),
        ("HDD-like", 10.0, 180),
    ]

    for name, latency_ms, bandwidth_mb_s in examples:
        transfer_ms = transfer_size_mb / bandwidth_mb_s * 1000
        total_ms = latency_ms + transfer_ms

        print(
            f"{name:<12} latency={latency_ms:>7.2f} ms, "
            f"transfer={transfer_ms:>8.2f} ms, "
            f"total={total_ms:>8.2f} ms"
        )

    print()
    print("For large sequential transfers, bandwidth becomes important.")
    print("For tiny random accesses, latency can dominate.")


# ============================================================================
# SECTION 28: RANDOM VERSUS SEQUENTIAL ACCESS
# ============================================================================

def generate_sequential_addresses(
    count: int,
    element_size: int,
) -> List[int]:
    if count < 0 or element_size <= 0:
        raise ValueError("Invalid count or element size.")

    return [index * element_size for index in range(count)]


def generate_random_addresses(
    count: int,
    address_space: int,
    seed: int = 42,
) -> List[int]:
    if count < 0 or address_space <= 0:
        raise ValueError("Invalid count or address space.")

    generator = random.Random(seed)
    return [generator.randrange(address_space) for _ in range(count)]


def compare_sequential_random_cache_behavior() -> None:
    heading("28. Sequential Versus Random Access")

    cache_size = 32 * 1024
    line_size = 64
    ways = 8

    sequential = generate_sequential_addresses(
        count=100_000,
        element_size=8,
    )

    random_addresses = generate_random_addresses(
        count=100_000,
        address_space=8 * 1024 * 1024,
    )

    sequential_cache = BlockCacheSimulator(cache_size, line_size, ways)
    random_cache = BlockCacheSimulator(cache_size, line_size, ways)

    sequential_stats = sequential_cache.run(sequential)
    random_stats = random_cache.run(random_addresses)

    print(f"Sequential hit rate = {sequential_stats.hit_rate:.2%}")
    print(f"Random hit rate     = {random_stats.hit_rate:.2%}")

    print()
    print("The exact values depend on cache size, line size, working set, and pattern.")
    print("Sequential access benefits strongly from cache-line fetching.")
    print("Random access tends to expose latency and cache-capacity limitations.")


# ============================================================================
# SECTION 29: MEMORY ACCESS COST MODEL
# ============================================================================

@dataclass
class AccessCostModel:
    """Simplified hierarchy latency model."""

    register_ns: float = 0.3
    l1_ns: float = 1.0
    l2_ns: float = 4.0
    l3_ns: float = 12.0
    ram_ns: float = 80.0
    ssd_ns: float = 100_000.0
    hdd_ns: float = 10_000_000.0

    def display(self) -> None:
        levels = [
            ("Register", self.register_ns),
            ("L1", self.l1_ns),
            ("L2", self.l2_ns),
            ("L3", self.l3_ns),
            ("RAM", self.ram_ns),
            ("SSD", self.ssd_ns),
            ("HDD", self.hdd_ns),
        ]

        for name, latency in levels:
            print(f"{name:<12} {format_latency(latency)}")


def demonstrate_cost_model() -> None:
    heading("29. Relative Access Cost")

    model = AccessCostModel()
    model.display()

    print()
    print("The hierarchy exists because making every byte of storage as fast as a")
    print("register would be economically and physically impractical.")
    print()
    print("The system therefore attempts to keep the currently useful data near the CPU.")


# ============================================================================
# SECTION 30: CACHE LINE SIZE
# ============================================================================

def evaluate_line_sizes(
    addresses: List[int],
    cache_size: int,
    line_sizes: List[int],
    ways: int,
) -> None:
    print(
        f"{'Line size':<15} {'Hits':<10} {'Misses':<10} {'Hit rate':<12}"
    )
    print("-" * 55)

    for line_size in line_sizes:
        cache = BlockCacheSimulator(
            cache_size_bytes=cache_size,
            line_size_bytes=line_size,
            associativity=ways,
        )

        stats = cache.run(addresses)

        print(
            f"{format_bytes(line_size):<15} "
            f"{stats.hits:<10} "
            f"{stats.misses:<10} "
            f"{stats.hit_rate:.2%}"
        )


def demonstrate_line_size_tradeoff() -> None:
    heading("30. Cache-Line Size Trade-offs")

    addresses = generate_sequential_addresses(
        count=10_000,
        element_size=8,
    )

    evaluate_line_sizes(
        addresses=addresses,
        cache_size=32 * 1024,
        line_sizes=[16, 32, 64, 128],
        ways=4,
    )

    print()
    print("Larger lines can improve spatial locality because one miss fetches more data.")
    print("They can also waste bandwidth when nearby data is never used.")
    print("Larger lines reduce the number of lines available for a fixed cache capacity.")
    print("Real systems choose a hardware-specific cache-line size.")


# ============================================================================
# SECTION 31: MEMORY ALIGNMENT
# ============================================================================

def alignment_offset(address: int, alignment: int) -> int:
    if address < 0:
        raise ValueError("Address cannot be negative.")
    if alignment <= 0:
        raise ValueError("Alignment must be positive.")

    return address % alignment


def demonstrate_alignment() -> None:
    heading("31. Memory Alignment")

    addresses = [0, 1, 7, 8, 15, 16, 31, 32]
    alignments = [4, 8, 16]

    for address in addresses:
        offsets = [
            alignment_offset(address, alignment)
            for alignment in alignments
        ]
        print(f"address={address:>2}: offsets for 4/8/16-byte alignment = {offsets}")

    print()
    print("Alignment means placing data at addresses satisfying a required boundary.")
    print("Aligned access can simplify hardware and may improve performance.")
    print("Modern CPUs can often handle unaligned accesses, but the cost depends")
    print("on architecture, data type, alignment, and whether an access crosses boundaries.")


# ============================================================================
# SECTION 32: CACHE-AWARE ALGORITHM EXAMPLE
# ============================================================================

def blocked_matrix_multiply(
    a: List[List[float]],
    b: List[List[float]],
    block_size: int,
) -> List[List[float]]:
    """
    Cache-blocked matrix multiplication.

    The mathematical result is the same as ordinary matrix multiplication,
    but computation is organized into smaller blocks to improve locality.

    This is an educational implementation rather than a high-performance BLAS.
    """
    if not a or not b:
        return []

    n = len(a)
    common = len(a[0])
    m = len(b[0])

    if any(len(row) != common for row in a):
        raise ValueError("Matrix A is not rectangular.")
    if any(len(row) != m for row in b):
        raise ValueError("Matrix B is not rectangular.")
    if len(b) != common:
        raise ValueError("Matrix dimensions are incompatible.")
    if block_size <= 0:
        raise ValueError("Block size must be positive.")

    result = [[0.0 for _ in range(m)] for _ in range(n)]

    for row_start in range(0, n, block_size):
        for common_start in range(0, common, block_size):
            for column_start in range(0, m, block_size):

                row_end = min(row_start + block_size, n)
                common_end = min(common_start + block_size, common)
                column_end = min(column_start + block_size, m)

                for i in range(row_start, row_end):
                    for k in range(common_start, common_end):
                        a_value = a[i][k]

                        for j in range(column_start, column_end):
                            result[i][j] += a_value * b[k][j]

    return result


def naive_matrix_multiply(
    a: List[List[float]],
    b: List[List[float]],
) -> List[List[float]]:
    """Simple matrix multiplication used as a correctness reference."""
    if not a or not b:
        return []

    n = len(a)
    common = len(a[0])
    m = len(b[0])

    if len(b) != common:
        raise ValueError("Matrix dimensions are incompatible.")

    return [
        [
            sum(a[i][k] * b[k][j] for k in range(common))
            for j in range(m)
        ]
        for i in range(n)
    ]


def demonstrate_cache_aware_algorithm() -> None:
    heading("32. Cache-Aware Algorithms and Blocking")

    size = 48

    a = [[float((i + j) % 7) for j in range(size)] for i in range(size)]
    b = [[float((i * j) % 5) for j in range(size)] for i in range(size)]

    reference = naive_matrix_multiply(a, b)
    blocked = blocked_matrix_multiply(a, b, block_size=8)

    identical = all(
        math.isclose(reference[i][j], blocked[i][j], rel_tol=1e-12, abs_tol=1e-12)
        for i in range(size)
        for j in range(size)
    )

    print(f"Blocked multiplication matches reference = {identical}")

    naive_min, naive_median = benchmark_function(
        naive_matrix_multiply,
        a,
        b,
        repeats=2,
    )

    blocked_min, blocked_median = benchmark_function(
        blocked_matrix_multiply,
        a,
        b,
        8,
        repeats=2,
    )

    print(f"Naive   min={naive_min:.6f}s, median={naive_median:.6f}s")
    print(f"Blocked min={blocked_min:.6f}s, median={blocked_median:.6f}s")

    print()
    print("Blocking attempts to keep frequently reused portions of the matrices")
    print("in higher cache levels for longer.")
    print("Python-level benchmarks do not isolate hardware cache effects, but")
    print("the algorithmic locality principle is widely applicable.")


# ============================================================================
# SECTION 33: MEMORY ORDERING AND CONSISTENCY
# ============================================================================

def explain_memory_ordering() -> None:
    heading("33. Memory Ordering and Consistency")

    print("Multicore processors may execute memory operations out of the exact")
    print("source-code order when the architecture permits it.")
    print()
    print("Compiler optimization and CPU reordering can both affect observed ordering.")
    print()
    print("Memory-ordering models define which observations are permitted.")
    print("Synchronization primitives such as locks and atomic operations provide")
    print("the guarantees needed by concurrent programs.")
    print()
    print("Important distinction:")
    print("  Cache coherence != memory consistency.")
    print("  Cache coherence tracks agreement about individual memory locations.")
    print("  Memory consistency specifies ordering relationships among operations.")
    print()
    print("Correct concurrent software should rely on the synchronization guarantees")
    print("of its language and target architecture rather than assuming sequential execution.")


# ============================================================================
# SECTION 34: PAGE FAULT COST
# ============================================================================

def page_fault_cost_model(
    tlb_hit_ns: float,
    page_table_walk_ns: float,
    page_fault_ms: float,
) -> Dict[str, float]:
    if min(tlb_hit_ns, page_table_walk_ns, page_fault_ms) < 0:
        raise ValueError("Costs cannot be negative.")

    return {
        "TLB hit": tlb_hit_ns,
        "Page-table walk": page_table_walk_ns,
        "Page fault": page_fault_ms * 1_000_000,
    }


def demonstrate_page_fault_cost() -> None:
    heading("34. Why Page Faults Are Expensive")

    costs = page_fault_cost_model(
        tlb_hit_ns=1,
        page_table_walk_ns=100,
        page_fault_ms=5,
    )

    for event, cost_ns in costs.items():
        print(f"{event:<20} {format_latency(cost_ns)}")

    print()
    print("A page fault can require operating-system work and storage I/O.")
    print("Its cost can be many orders of magnitude greater than a CPU-cache hit.")
    print()
    print("This is why excessive paging or thrashing can make a system feel extremely slow.")


# ============================================================================
# SECTION 35: THRASHING
# ============================================================================

def simulate_page_working_set(
    page_sequence: List[int],
    physical_frames: int,
) -> Tuple[int, int]:
    """
    Simple FIFO paging simulation.

    Returns:
        (page_faults, page_hits)
    """
    if physical_frames <= 0:
        raise ValueError("Physical frame count must be positive.")

    frames: List[int] = []
    hits = 0
    faults = 0

    for page in page_sequence:
        if page in frames:
            hits += 1
            continue

        faults += 1

        if len(frames) >= physical_frames:
            frames.pop(0)

        frames.append(page)

    return faults, hits


def demonstrate_thrashing() -> None:
    heading("35. Paging Pressure and Thrashing")

    sequence = [0, 1, 2, 3] * 100

    for frames in [2, 3, 4]:
        faults, hits = simulate_page_working_set(
            sequence,
            physical_frames=frames,
        )

        total = faults + hits

        print(
            f"Frames={frames}: "
            f"faults={faults}, hits={hits}, "
            f"fault rate={faults / total:.2%}"
        )

    print()
    print("When the active page set does not fit in available frames,")
    print("the system can spend excessive time moving pages rather than executing work.")
    print("This condition is commonly called thrashing.")


# ============================================================================
# SECTION 36: STORAGE DURABILITY
# ============================================================================

def explain_durability() -> None:
    heading("36. Persistence and Durability")

    print("Storage being non-volatile does not automatically mean every write is durable")
    print("at the exact instant a program requests it.")
    print()
    print("Data may temporarily exist in:")
    print("  CPU caches")
    print("  operating-system page cache")
    print("  SSD controller buffers")
    print("  HDD caches")
    print()
    print("Durability depends on the complete I/O path and the guarantees exposed by")
    print("the operating system, filesystem, storage device, and application.")
    print()
    print("A database that requires durable commits must use appropriate synchronization")
    print("and storage semantics rather than assuming that a successful write call alone")
    print("always means the data is physically persistent.")


# ============================================================================
# SECTION 37: SECURITY CONSIDERATIONS
# ============================================================================

def explain_security() -> None:
    heading("37. Security Considerations")

    print("Memory hierarchy behavior has security implications.")
    print()
    print("Examples:")
    print("  Cache side channels can reveal information through timing differences.")
    print("  Speculative execution vulnerabilities can expose data through microarchitectural state.")
    print("  DMA-capable devices can create memory-isolation concerns.")
    print("  Remanence concerns arise when sensitive information remains in memory or storage.")
    print()
    print("Security is not determined only by software permissions.")
    print("The underlying microarchitecture and operating-system isolation mechanisms matter.")
    print()
    print("Mitigations are architecture- and vulnerability-specific.")
    print("Examples include isolation, constant-time techniques where appropriate,")
    print("microcode or firmware updates, operating-system changes, and careful privilege boundaries.")


# ============================================================================
# SECTION 38: PERFORMANCE TRADE-OFFS
# ============================================================================

def explain_tradeoffs() -> None:
    heading("38. Major Design Trade-offs")

    tradeoffs = [
        (
            "Cache size",
            "Larger cache can reduce capacity misses",
            "Consumes chip area and can increase access time and power",
        ),
        (
            "Associativity",
            "Reduces conflict misses",
            "Adds comparison and hardware complexity",
        ),
        (
            "Cache-line size",
            "Improves spatial locality",
            "Can waste bandwidth and cache capacity",
        ),
        (
            "Prefetching",
            "Can hide future miss latency",
            "Wrong predictions consume bandwidth and space",
        ),
        (
            "Write-back",
            "Reduces repeated lower-level writes",
            "Requires dirty tracking and eviction handling",
        ),
        (
            "More RAM",
            "Reduces pressure for paging",
            "Costs more and does not automatically fix poor locality",
        ),
        (
            "SSD",
            "Very low storage latency and high random I/O performance",
            "Higher cost per byte than many HDDs and finite flash endurance",
        ),
        (
            "HDD",
            "High capacity at low cost per byte",
            "Mechanical latency and lower random-access performance",
        ),
    ]

    print(f"{'Design choice':<22} {'Benefit':<48} Cost / drawback")
    print("-" * 120)

    for choice, benefit, drawback in tradeoffs:
        print(f"{choice:<22} {benefit:<48} {drawback}")


# ============================================================================
# SECTION 39: COMMON MISCONCEPTIONS
# ============================================================================

def explain_common_misconceptions() -> None:
    heading("39. Common Misconceptions")

    misconceptions = [
        (
            "RAM is permanent storage.",
            "RAM is normally volatile working memory. SSDs and HDDs provide persistent storage.",
        ),
        (
            "SSD means RAM-like speed.",
            "An SSD is much faster than an HDD for many workloads, but it is still far slower than CPU caches and RAM.",
        ),
        (
            "CPU cache stores everything the program needs.",
            "Caches store selected copies of data. The hierarchy continually replaces lines.",
        ),
        (
            "More cache always means faster execution.",
            "A larger cache can help, but latency, power, associativity, workload locality, and implementation all matter.",
        ),
        (
            "A cache miss always means RAM.",
            "A miss at one level may be satisfied by another cache level before RAM is accessed.",
        ),
        (
            "Sequential access is always fastest.",
            "It often has excellent locality, but the best access pattern depends on the workload and representation.",
        ),
        (
            "Non-volatile means writes are instantly durable.",
            "Durability depends on buffering, caches, device semantics, and synchronization.",
        ),
        (
            "Cache coherence makes all threads automatically safe.",
            "Coherence does not replace synchronization or guarantee application-level correctness.",
        ),
    ]

    for statement, correction in misconceptions:
        print(f"Misconception: {statement}")
        print(f"Correction:    {correction}")
        print()


# ============================================================================
# SECTION 40: PRACTICAL DIAGNOSTICS
# ============================================================================

def diagnose_workload(
    working_set_bytes: int,
    cache_bytes: int,
    ram_bytes: int,
    access_pattern: str,
    storage_pattern: str,
) -> None:
    """
    Give a conceptual diagnosis from workload characteristics.

    This is educational rather than a hardware profiler.
    """
    if working_set_bytes < 0 or cache_bytes <= 0 or ram_bytes <= 0:
        raise ValueError("Memory capacities must be valid positive values.")

    print(f"Working set : {format_bytes(working_set_bytes)}")
    print(f"Cache       : {format_bytes(cache_bytes)}")
    print(f"RAM         : {format_bytes(ram_bytes)}")
    print(f"CPU access  : {access_pattern}")
    print(f"Storage I/O : {storage_pattern}")
    print()

    if working_set_bytes <= cache_bytes:
        print("Diagnosis: working set can potentially fit in the specified cache.")
    elif working_set_bytes <= ram_bytes:
        print("Diagnosis: working set exceeds this cache but fits within RAM.")
    else:
        print("Diagnosis: working set exceeds RAM and may create paging/storage pressure.")

    if access_pattern.lower() == "sequential":
        print("Locality note: sequential access usually provides strong spatial locality.")
    elif access_pattern.lower() == "random":
        print("Locality note: random access can produce more cache and TLB misses.")
    else:
        print("Locality note: irregular patterns require workload-specific measurement.")

    if storage_pattern.lower() == "random":
        print("Storage note: random I/O can expose SSD/HDD latency.")
    elif storage_pattern.lower() == "sequential":
        print("Storage note: sequential I/O generally makes better use of device bandwidth.")


def demonstrate_diagnostics() -> None:
    heading("40. Conceptual Performance Diagnosis")

    diagnose_workload(
        working_set_bytes=16 * 1024 * 1024,
        cache_bytes=8 * 1024 * 1024,
        ram_bytes=16 * 1024**3,
        access_pattern="sequential",
        storage_pattern="sequential",
    )

    print()
    diagnose_workload(
        working_set_bytes=64 * 1024**3,
        cache_bytes=32 * 1024**2,
        ram_bytes=16 * 1024**3,
        access_pattern="random",
        storage_pattern="random",
    )


# ============================================================================
# SECTION 41: END-TO-END ACCESS PATH
# ============================================================================

def simulate_memory_access_path(
    address: int,
    l1: BlockCacheSimulator,
    l2: BlockCacheSimulator,
    l3: BlockCacheSimulator,
) -> str:
    """
    Simulate a conceptual CPU-to-memory access path.

    This does not model actual hardware timing.
    """
    if address < 0:
        raise ValueError("Address cannot be negative.")

    if l1.access(address):
        return "L1 cache hit"

    if l2.access(address):
        return "L1 miss -> L2 hit"

    if l3.access(address):
        return "L1 miss -> L2 miss -> L3 hit"

    return "L1 miss -> L2 miss -> L3 miss -> RAM"


def demonstrate_end_to_end_access() -> None:
    heading("41. End-to-End CPU Memory Access Path")

    l1 = BlockCacheSimulator(
        cache_size_bytes=4 * 1024,
        line_size_bytes=64,
        associativity=2,
    )

    l2 = BlockCacheSimulator(
        cache_size_bytes=32 * 1024,
        line_size_bytes=64,
        associativity=4,
    )

    l3 = BlockCacheSimulator(
        cache_size_bytes=256 * 1024,
        line_size_bytes=64,
        associativity=8,
    )

    addresses = [0, 64, 128, 0, 64, 4096, 8192, 0]

    for address in addresses:
        result = simulate_memory_access_path(address, l1, l2, l3)
        print(f"address={address:>5}: {result}")

    print()
    print("Real processors also include instruction caches, data caches,")
    print("TLBs, hardware prefetchers, coherence machinery, and many other mechanisms.")


# ============================================================================
# SECTION 42: INSTRUCTION CACHE VERSUS DATA CACHE
# ============================================================================

def explain_instruction_data_caches() -> None:
    heading("42. Instruction Cache and Data Cache")

    print("Many CPUs separate instruction and data caches at lower cache levels.")
    print()
    print("Instruction cache:")
    print("  Stores recently fetched machine instructions.")
    print()
    print("Data cache:")
    print("  Stores program data such as arrays, objects, and variables.")
    print()
    print("A unified higher-level cache may hold both instructions and data.")
    print()
    print("Separating instruction and data paths can improve throughput because")
    print("instruction fetches and data accesses can proceed independently.")


# ============================================================================
# SECTION 43: CACHE INCLUSION
# ============================================================================

def explain_cache_inclusion() -> None:
    heading("43. Inclusive, Exclusive, and Non-Inclusive Cache Designs")

    print("Inclusive design:")
    print("  A higher-level cache may contain copies of lines present in lower-level caches.")
    print()
    print("Exclusive design:")
    print("  Cache levels attempt to hold different lines, reducing duplication.")
    print()
    print("Non-inclusive design:")
    print("  Does not require strict inclusion or exclusion.")
    print()
    print("Each design has trade-offs in capacity utilization, coherence management,")
    print("eviction behavior, and implementation complexity.")
    print("Modern processors vary significantly, so there is no universal hierarchy policy.")


# ============================================================================
# SECTION 44: NUMA
# ============================================================================

def explain_numa() -> None:
    heading("44. NUMA and Memory Locality")

    print("NUMA means Non-Uniform Memory Access.")
    print()
    print("In a NUMA system, a processor may access some physical memory regions")
    print("with lower latency than others.")
    print()
    print("A typical large server may contain multiple CPU sockets or memory domains.")
    print()
    print("NUMA-aware software tries to keep threads and their frequently used data")
    print("close to the same memory domain.")
    print()
    print("This extends the locality principle beyond CPU caches into system architecture.")


# ============================================================================
# SECTION 45: STORAGE FILESYSTEM LAYERS
# ============================================================================

def explain_storage_stack() -> None:
    heading("45. The Storage Access Stack")

    layers = [
        "Application",
        "Library or runtime",
        "Operating-system system call",
        "Filesystem",
        "Block layer",
        "Device driver",
        "Storage controller",
        "SSD controller or HDD firmware",
        "Physical media",
    ]

    for index, layer in enumerate(layers, start=1):
        print(f"{index:>2}. {layer}")

    print()
    print("A file read therefore does not necessarily mean a direct physical-device access.")
    print("The operating system can satisfy reads from memory caches.")
    print("The storage device can also maintain its own cache and mapping layers.")


# ============================================================================
# SECTION 46: PERFORMANCE COUNTERS CONCEPT
# ============================================================================

@dataclass
class PerformanceCounters:
    instructions: int = 0
    cycles: int = 0
    cache_references: int = 0
    cache_misses: int = 0
    branch_misses: int = 0

    @property
    def cpi(self) -> float:
        return self.cycles / self.instructions if self.instructions else 0.0

    @property
    def cache_miss_rate(self) -> float:
        return (
            self.cache_misses / self.cache_references
            if self.cache_references
            else 0.0
        )


def demonstrate_performance_counters() -> None:
    heading("46. Performance Counters")

    counters = PerformanceCounters(
        instructions=1_000_000,
        cycles=1_800_000,
        cache_references=400_000,
        cache_misses=20_000,
        branch_misses=5_000,
    )

    print(f"Instructions    = {counters.instructions:,}")
    print(f"Cycles          = {counters.cycles:,}")
    print(f"CPI             = {counters.cpi:.2f}")
    print(f"Cache references= {counters.cache_references:,}")
    print(f"Cache misses    = {counters.cache_misses:,}")
    print(f"Cache miss rate = {counters.cache_miss_rate:.2%}")
    print(f"Branch misses   = {counters.branch_misses:,}")

    print()
    print("Modern CPUs expose hardware performance-monitoring facilities.")
    print("Counters can help determine whether cache behavior is contributing")
    print("to a workload's performance.")


# ============================================================================
# SECTION 47: EXPERIMENTAL DESIGN
# ============================================================================

def explain_benchmarking() -> None:
    heading("47. Benchmarking Memory-Hierarchy Behavior")

    print("A useful benchmark should control or measure:")
    print("  Data-set size")
    print("  Access pattern")
    print("  Working-set size")
    print("  Alignment")
    print("  Number of repetitions")
    print("  Warm-up effects")
    print("  Compiler optimization")
    print("  Runtime overhead")
    print("  CPU frequency behavior")
    print("  Other processes")
    print("  Operating-system caching")
    print()
    print("A single wall-clock measurement is not enough to prove a cache hypothesis.")
    print("Performance counters and carefully controlled experiments provide stronger evidence.")
    print()
    print("For storage benchmarks, distinguish:")
    print("  Sequential versus random")
    print("  Read versus write")
    print("  Queue depth")
    print("  Block size")
    print("  Synchronous versus asynchronous I/O")
    print("  Cached versus direct I/O semantics")


# ============================================================================
# SECTION 48: EDGE CASES
# ============================================================================

def demonstrate_edge_cases() -> None:
    heading("48. Important Edge Cases")

    print("The examples below intentionally exercise invalid configurations.")

    invalid_operations = [
        (
            "Negative byte formatting",
            lambda: format_bytes(-1),
        ),
        (
            "Zero-size cache",
            lambda: SimpleDirectMappedCache(0, 4),
        ),
        (
            "Negative memory address",
            lambda: SimpleDirectMappedCache(4, 4)._decode_address(-1),
        ),
        (
            "Invalid miss rate",
            lambda: average_memory_access_time(1, 1.5, 80),
        ),
        (
            "Invalid page size",
            lambda: PageTable(0),
        ),
        (
            "Invalid SSD dimensions",
            lambda: SSDModel(0, 8),
        ),
    ]

    for description, operation in invalid_operations:
        try:
            operation()
        except (ValueError, IndexError, KeyError, MemoryError, RuntimeError) as error:
            print(f"{description:<30} -> correctly rejected: {error}")
        except Exception as error:
            print(
                f"{description:<30} -> unexpected exception type: "
                f"{type(error).__name__}: {error}"
            )
        else:
            print(f"{description:<30} -> ERROR: invalid operation was accepted")


# ============================================================================
# SECTION 49: RELATIONSHIPS BETWEEN LEVELS
# ============================================================================

def explain_hierarchy_relationships() -> None:
    heading("49. How the Levels Work Together")

    print("Registers")
    print("  The execution units directly manipulate register values.")
    print()
    print("L1/L2/L3 cache")
    print("  Hold copies of recently useful memory blocks close to CPU cores.")
    print()
    print("RAM")
    print("  Holds active process memory and operating-system working data.")
    print()
    print("SSD/HDD")
    print("  Provide persistent backing storage for files and, when needed, virtual memory.")
    print()
    print("The operating system coordinates virtual address spaces and physical memory.")
    print("The CPU's cache hierarchy automatically manages many cache transfers in hardware.")
    print()
    print("No single layer replaces the others. Each solves a different part of the")
    print("capacity, latency, cost, and persistence problem.")


# ============================================================================
# SECTION 50: FINAL INTEGRATED SIMULATION
# ============================================================================

@dataclass
class IntegratedResult:
    total_accesses: int
    l1_hits: int
    l1_misses: int
    l2_hits: int
    l2_misses: int
    l3_hits: int
    l3_misses: int
    ram_accesses: int

    @property
    def l1_hit_rate(self) -> float:
        return self.l1_hits / self.total_accesses if self.total_accesses else 0.0


def run_integrated_hierarchy_simulation(
    addresses: List[int],
) -> IntegratedResult:
    """
    Run addresses through L1 -> L2 -> L3 -> RAM.

    Each cache is simulated independently at block level.
    """
    l1 = BlockCacheSimulator(
        cache_size_bytes=8 * 1024,
        line_size_bytes=64,
        associativity=2,
    )

    l2 = BlockCacheSimulator(
        cache_size_bytes=64 * 1024,
        line_size_bytes=64,
        associativity=4,
    )

    l3 = BlockCacheSimulator(
        cache_size_bytes=512 * 1024,
        line_size_bytes=64,
        associativity=8,
    )

    l1_hits = l1_misses = 0
    l2_hits = l2_misses = 0
    l3_hits = l3_misses = 0
    ram_accesses = 0

    for address in addresses:
        if l1.access(address):
            l1_hits += 1
            continue

        l1_misses += 1

        if l2.access(address):
            l2_hits += 1
            continue

        l2_misses += 1

        if l3.access(address):
            l3_hits += 1
            continue

        l3_misses += 1
        ram_accesses += 1

    return IntegratedResult(
        total_accesses=len(addresses),
        l1_hits=l1_hits,
        l1_misses=l1_misses,
        l2_hits=l2_hits,
        l2_misses=l2_misses,
        l3_hits=l3_hits,
        l3_misses=l3_misses,
        ram_accesses=ram_accesses,
    )


def demonstrate_integrated_simulation() -> None:
    heading("50. Integrated Memory-Hierarchy Simulation")

    generator = random.Random(123)

    addresses = []

    # First phase: repeated access to a small hot region.
    for _ in range(2_000):
        addresses.append(generator.randrange(0, 8 * 1024))

    # Second phase: a larger working set.
    for _ in range(2_000):
        addresses.append(generator.randrange(0, 2 * 1024 * 1024))

    result = run_integrated_hierarchy_simulation(addresses)

    print(f"Total accesses = {result.total_accesses:,}")
    print()
    print(f"L1 hits        = {result.l1_hits:,}")
    print(f"L1 misses      = {result.l1_misses:,}")
    print(f"L1 hit rate    = {result.l1_hit_rate:.2%}")
    print()
    print(f"L2 hits        = {result.l2_hits:,}")
    print(f"L2 misses      = {result.l2_misses:,}")
    print()
    print(f"L3 hits        = {result.l3_hits:,}")
    print(f"L3 misses      = {result.l3_misses:,}")
    print()
    print(f"RAM accesses   = {result.ram_accesses:,}")

    print()
    print("The first phase has a small working set and tends to benefit from locality.")
    print("The second phase expands the working set and creates more cache pressure.")


# ============================================================================
# SECTION 51: KNOWLEDGE CHECK
# ============================================================================

def knowledge_check() -> None:
    heading("51. Knowledge Check")

    questions = [
        (
            "Which level is normally closest to CPU execution units?",
            "Registers and the nearest CPU caches.",
        ),
        (
            "Why is RAM not as fast as a register?",
            "RAM uses a denser technology and is physically farther from the execution units.",
        ),
        (
            "What is temporal locality?",
            "Recently used data is likely to be used again.",
        ),
        (
            "What is spatial locality?",
            "Nearby addresses are likely to be accessed soon.",
        ),
        (
            "What is a cache hit?",
            "The requested block is already present at that cache level.",
        ),
        (
            "What is a page fault?",
            "An attempted virtual-memory access requires a page that is not currently present.",
        ),
        (
            "Why can HDD random access be slow?",
            "Mechanical seek and rotational delays contribute substantial latency.",
        ),
        (
            "Why does an SSD perform garbage collection?",
            "NAND flash uses larger erase units and cannot simply overwrite arbitrary pages in place.",
        ),
        (
            "What does write amplification measure?",
            "Physical storage writes relative to host-requested writes.",
        ),
        (
            "Why can larger cache lines help?",
            "They exploit spatial locality by fetching neighboring data together.",
        ),
    ]

    for question, answer in questions:
        print(f"Question: {question}")
        print(f"Answer:   {answer}")
        print()


# ============================================================================
# SECTION 52: MAIN PROGRAM
# ============================================================================

def main() -> None:
    """
    Execute the complete educational walkthrough.

    Each section is deliberately independent so the file can also be used
    as a reference when studying individual concepts.
    """
    explain_basic_units()
    print_memory_hierarchy()
    explain_registers()
    compare_memory_technologies()
    explain_cache_basics()
    demonstrate_cache_address_fields()
    compare_cache_mapping()
    classify_cache_misses()
    compare_replacement_policies()
    demonstrate_write_policies()
    demonstrate_amat()
    demonstrate_multilevel_amat()
    demonstrate_locality()
    demonstrate_matrix_locality()
    demonstrate_cache_simulator()
    demonstrate_dram()
    demonstrate_virtual_memory()
    demonstrate_tlb()
    demonstrate_working_set()
    demonstrate_prefetching()
    demonstrate_false_sharing()
    explain_cache_coherence()
    demonstrate_hdd()
    demonstrate_ssd()
    explain_ssd_concepts()
    demonstrate_volatility()
    demonstrate_latency_bandwidth()
    compare_sequential_random_cache_behavior()
    demonstrate_cost_model()
    demonstrate_line_size_tradeoff()
    demonstrate_alignment()
    demonstrate_cache_aware_algorithm()
    explain_memory_ordering()
    demonstrate_page_fault_cost()
    demonstrate_thrashing()
    explain_durability()
    explain_security()
    explain_tradeoffs()
    explain_common_misconceptions()
    demonstrate_diagnostics()
    demonstrate_end_to_end_access()
    explain_instruction_data_caches()
    explain_cache_inclusion()
    explain_numa()
    explain_storage_stack()
    demonstrate_performance_counters()
    explain_benchmarking()
    demonstrate_edge_cases()
    explain_hierarchy_relationships()
    demonstrate_integrated_simulation()
    knowledge_check()

    heading("Study File Complete")
    print("The simulations model the core ideas of the memory hierarchy.")
    print("Hardware implementations are more complex and architecture-specific.")


if __name__ == "__main__":
    main()
