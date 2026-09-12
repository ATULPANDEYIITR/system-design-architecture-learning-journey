# Memory hierarchy: registers, cache, RAM, SSD, and HDD

## Introduction

Computer systems do not use one universal type of memory for all data. A processor requires extremely fast access to instructions and operands, while users and applications require storage capacities that are many orders of magnitude larger. A single technology cannot provide maximum speed, maximum capacity, low cost, and persistence simultaneously.

The memory hierarchy solves this problem by combining several levels of storage:

- CPU registers
- L1 cache
- L2 cache
- L3 cache
- RAM
- SSD
- HDD

The upper levels are generally smaller and faster. The lower levels are generally larger, slower, cheaper per byte, and, in the case of SSDs and HDDs, non-volatile.

The Python study file models these levels and demonstrates the mechanisms that make a hierarchy effective. The simulations are intentionally simplified. They explain architectural principles without pretending to reproduce a particular processor, SSD controller, operating system, or hard-disk firmware.

## The central idea

A processor repeatedly needs data and instructions. If every request had to travel to persistent storage, program execution would be extremely slow. Instead, frequently used information is kept as close to the processor as practical.

The conceptual path is:

CPU execution  
↓  
Registers  
↓  
L1 cache  
↓  
L2 cache  
↓  
L3 cache  
↓  
RAM  
↓  
SSD / HDD

This is a conceptual hierarchy rather than a universal physical layout. Modern processors vary considerably. Some processors have multiple cache levels, different sharing arrangements, separate instruction and data caches, integrated memory controllers, different NUMA domains, or cache organizations that do not correspond exactly to a simple textbook diagram.

The important principle is that faster storage exists in smaller quantities closer to the computation, while larger and persistent storage exists farther away.

## Bits, bytes, addresses, latency, and bandwidth

A bit is a binary digit with a value of zero or one.

A byte contains eight bits.

Memory is commonly addressed at byte granularity. An address identifies a location within an address space, while capacity describes how much information can be stored.

The Python script distinguishes capacity from performance because they represent different properties.

### Capacity

Capacity describes the amount of information a storage level can contain.

Common binary units are:

- 1 KiB = 1,024 bytes
- 1 MiB = 1,024 KiB
- 1 GiB = 1,024 MiB
- 1 TiB = 1,024 GiB

Decimal storage specifications often use:

- 1 kB = 1,000 bytes
- 1 MB = 1,000,000 bytes
- 1 GB = 1,000,000,000 bytes
- 1 TB = 1,000,000,000,000 bytes

This difference explains why a storage device marketed using decimal units can appear smaller when reported by software using binary units.

### Latency

Latency is the time required before an operation produces useful progress or data.

CPU cache latency is measured in very small fractions of a microsecond. Storage-device latency is normally much larger.

A small random access is often dominated by latency rather than maximum transfer bandwidth.

### Bandwidth

Bandwidth describes the rate at which data can be transferred.

For example, a storage device might have high sequential bandwidth while still having substantially higher latency than RAM for a tiny random request.

This distinction is important when evaluating storage performance.

## Registers

Registers are the storage locations most directly connected to CPU instruction execution.

They are extremely small compared with RAM and storage devices, but they provide very fast access to values needed by the execution units.

The script implements a simplified register file containing:

- General-purpose registers
- Program counter
- Stack pointer
- Arithmetic flags

The register demonstration performs an addition by reading two registers and placing the result in another register.

The conceptual operation is:

R1 = 25  
R2 = 17  
R3 = R1 + R2

The actual behavior of registers depends on the instruction-set architecture. A particular architecture can provide different register counts, widths, special-purpose registers, vector registers, floating-point registers, control registers, and other architectural resources.

Registers should not be confused with cache.

Registers contain values directly used by instructions. Caches contain copies of memory blocks and are managed largely by hardware.

## SRAM and CPU cache

CPU caches are commonly implemented using SRAM.

SRAM is faster and does not require the same refresh mechanism as DRAM, but it consumes considerably more silicon area per bit. This makes very large SRAM structures expensive in terms of chip area and power.

CPU caches therefore occupy a compromise position:

- Faster than RAM
- Smaller than RAM
- More expensive per stored bit
- Located close to CPU execution units

Caches exploit predictable behavior in programs rather than storing the entire program state.

## Cache lines

A cache does not normally transfer arbitrary individual bytes as independent hardware objects. It operates on fixed-size blocks commonly called cache lines.

A cache line might contain multiple neighboring bytes.

If a program reads one element from an array, the cache may fetch the entire surrounding cache line. If the program then reads adjacent elements, those elements may already be present.

This behavior is the basis of spatial locality.

The Python cache simulations represent memory blocks using configurable line sizes.

## Temporal locality

Temporal locality means that recently accessed data is likely to be accessed again.

For example, a loop repeatedly updating the same small set of variables exhibits strong temporal locality.

If the required data remains in a higher cache level between accesses, subsequent accesses can be much faster than the first access.

The script demonstrates repeated access to a small region to illustrate this principle.

## Spatial locality

Spatial locality means that addresses near recently accessed addresses are likely to be accessed soon.

Sequential array traversal is a common example:

array[0]  
array[1]  
array[2]  
array[3]  
...

The elements are stored near one another, so fetching one cache line can make several upcoming accesses cheaper.

Spatial locality is one of the most important reasons caches are effective.

## L1, L2, and L3 caches

Modern CPUs commonly use multiple cache levels.

### L1 cache

L1 is the smallest and generally fastest cache level.

Many processors divide L1 into:

- Instruction cache
- Data cache

This separation allows instruction fetching and data access to proceed through specialized paths.

### L2 cache

L2 is generally larger than L1 and somewhat slower.

It can provide data that was not found in L1 without requiring a main-memory access.

### L3 cache

L3 is commonly much larger than L1 and L2.

It may be shared among multiple CPU cores or organized into slices or other implementation-specific structures.

The exact architecture differs between processors.

## Cache hits and misses

A cache hit occurs when the requested cache block is already present at that cache level.

A cache miss occurs when it is not present.

For example:

CPU requests address A  
↓  
L1 hit  
↓  
use data

If the L1 lookup misses:

CPU  
↓  
L1 miss  
↓  
L2 hit  
↓  
use data

If L2 also misses, the request can continue toward L3 and eventually RAM.

A miss at one level does not necessarily mean that the request reaches RAM.

## Cache tags, indices, and offsets

A cache address can conceptually be divided into:

- Tag
- Index
- Offset

The offset identifies a location inside a cache line.

The index identifies a cache line or set.

The tag identifies which memory block currently occupies that location.

For a direct-mapped cache:

block number = address / line size  
offset = address % line size  
index = block number % number of cache lines  
tag = block number / number of cache lines

Real hardware commonly uses bit fields when cache and address dimensions are powers of two.

The script demonstrates this decomposition numerically.

## Cache mapping

There are three fundamental cache organizations.

### Direct-mapped cache

Each memory block has exactly one possible cache location.

The organization is simple and fast, but multiple active blocks can compete for the same location.

This can produce conflict misses.

### Fully associative cache

A memory block can be stored in any cache line.

This minimizes mapping restrictions but requires more extensive tag comparison hardware.

### Set-associative cache

The cache is divided into sets.

A memory block maps to one set but can occupy one of several ways within that set.

For example, a four-way set-associative cache allows four different lines within a set.

Set associativity is a practical compromise between direct mapping and full associativity.

The script compares different organizations using simulated access patterns.

## Cache misses

A common educational classification divides cache misses into three categories.

### Compulsory misses

A compulsory miss occurs the first time a block is accessed.

The cache cannot already contain the block because it has not been requested previously.

### Capacity misses

A capacity miss occurs because the working set is larger than the cache capacity.

Even with good mapping, the cache cannot hold everything currently needed.

### Conflict misses

A conflict miss occurs because the cache mapping forces several blocks to compete for the same location or set.

A direct-mapped cache is especially susceptible to this problem.

Multicore systems also introduce coherence-related invalidations, which are a separate concern from the traditional three-C classification.

## Replacement policies

When a cache set is full and another block must be inserted, the system needs a replacement policy.

The study script demonstrates:

- LRU
- FIFO
- Random

### LRU

Least Recently Used replacement removes the item that has gone unused for the longest time.

LRU is intuitive because recently used data often has strong temporal locality.

Exact true LRU becomes increasingly expensive to implement as associativity grows, so real processors can use approximations or adaptive policies.

### FIFO

First In First Out removes the oldest inserted entry.

It is simple but does not directly represent recent access behavior.

### Random

Random replacement chooses a candidate without using recency information.

It can be surprisingly useful in some hardware contexts because it avoids maintaining complex state.

Real processor replacement policies are implementation-specific.

## Cache-line size

Larger cache lines can improve spatial locality.

Suppose a program reads:

A[0]  
A[1]  
A[2]  
A[3]

If these elements occupy the same cache line, one miss can bring several future values into the cache.

There is a trade-off.

If the program accesses:

A[0]  
A[100000]  
A[200000]

fetching large neighboring regions may provide little benefit.

Large cache lines can:

- Improve sequential access
- Exploit spatial locality
- Increase transfer size
- Consume bandwidth
- Reduce the number of distinct lines that fit in a fixed cache

The appropriate line size is therefore an architectural design decision.

## Write-through and write-back caches

Caches must decide how modified data is propagated toward lower levels.

### Write-through

A write to the cache is also propagated to lower memory.

Advantages include simpler lower-level visibility and easier reasoning about some states.

The disadvantage is increased lower-level write traffic.

### Write-back

The cache can modify a cached line without immediately writing it to lower memory.

The line is marked dirty.

When the line is evicted, the dirty contents must be written to the next level.

Write-back reduces repeated lower-level writes but requires:

- Dirty bits
- Eviction handling
- More complex coherence and consistency management

The Python implementation tracks dirty state conceptually.

## Write allocation

Write policy also involves what happens after a write miss.

With write-allocate, a missing block is brought into the cache before modification.

With no-write-allocate, the write may bypass the cache or use another lower-level mechanism.

These choices interact with write-through and write-back policies.

The best policy depends on workload and architecture.

## Average Memory Access Time

Average Memory Access Time, or AMAT, provides a simplified way to reason about hierarchical memory performance.

For one cache level:

AMAT = hit time + miss rate × miss penalty

For example, if:

- Hit time = 1 ns
- Miss rate = 10%
- Miss penalty = 80 ns

then:

AMAT = 1 + 0.10 × 80  
= 9 ns

The miss penalty can be large enough that a modest change in miss rate has a substantial effect on average access cost.

## Multi-level AMAT

With multiple cache levels, the access path becomes hierarchical.

A simplified model is:

AMAT = L1 hit time + L1 miss rate × (L2 hit time + L2 local miss rate × memory penalty)

This illustrates why L2 and L3 caches are valuable.

An L1 miss can still be inexpensive if L2 or L3 supplies the requested block.

The distinction between local and global miss rates is important.

A local L2 miss rate means:

L2 misses / accesses reaching L2

A global L2 miss rate refers to L2 misses relative to all original CPU accesses.

These quantities should not be mixed when calculating performance.

## RAM and DRAM

RAM generally refers to the main memory used by active programs.

Modern main memory is commonly implemented using DRAM.

DRAM cells use a storage mechanism that requires periodic refresh.

The script provides a conceptual DRAM model containing individual bit cells.

The model is deliberately simple. Real DRAM includes:

- Rows
- Columns
- Banks
- Sense amplifiers
- Row buffers
- Refresh operations
- Timing parameters
- Memory channels
- Controllers
- Command scheduling

Important DRAM performance concepts include row locality, bank parallelism, memory-channel bandwidth, and timing parameters.

## Virtual memory

Virtual memory provides processes with virtual address spaces rather than requiring applications to directly manage physical RAM addresses.

A virtual address can be divided into:

Virtual page number + page offset

The page table maps virtual pages to physical frames.

For example:

Virtual page 0 → Physical frame 12  
Virtual page 1 → Physical frame 25

A virtual address within page 1 can therefore be translated to an address within physical frame 25.

The page offset remains unchanged during normal page translation.

## Page faults

A page fault occurs when a process references a virtual page that is not currently available in the required physical-memory state.

The operating system may need to:

- Locate the page
- Obtain it from storage
- Allocate or reclaim a physical frame
- Update page tables
- Resume execution

A page fault is enormously more expensive than a normal CPU cache hit.

This difference explains why excessive paging can severely degrade system performance.

## Translation Lookaside Buffer

A TLB is a cache of recent virtual-to-physical address translations.

Without a TLB, address translation can require page-table access.

With a TLB hit, the processor can often obtain the translation much faster.

The TLB is therefore another example of the same general architectural idea:

> Keep frequently needed information in a small, fast structure.

The TLB is conceptually different from a data cache because it caches address translations rather than ordinary application data.

## Working sets

A working set represents the collection of data or pages actively needed by a program during a period.

A small working set can fit comfortably in a cache or memory level.

A large working set creates more pressure.

For example:

Working set < cache capacity

can allow substantial cache reuse.

Whereas:

Working set > cache capacity

can cause frequent evictions and misses.

The working set can change over time as the program moves between phases.

## Thrashing

Thrashing occurs when a system spends excessive effort moving pages between memory and storage instead of performing useful computation.

A common cause is that the actively needed pages do not fit in available physical memory.

The Python paging simulation demonstrates how changing the number of available frames changes page-fault behavior.

Thrashing is much more severe than an ordinary cache miss because storage-backed paging can have vastly higher latency.

## Prefetching

Prefetching attempts to fetch data before the processor explicitly requests it.

A sequential pattern is highly predictable:

Block 10  
Block 11  
Block 12  
Block 13

A hardware prefetcher may infer that block 11 will soon be needed while block 10 is being accessed.

Benefits include reduced effective miss latency.

Costs include:

- Additional bandwidth
- Cache pollution
- Power consumption
- Incorrect predictions

Aggressive prefetching is therefore not universally beneficial.

## Cache-aware programming

Algorithm design can intentionally exploit locality.

One important technique is blocking, also called tiling.

Matrix multiplication provides a classic example.

A naive implementation may repeatedly move across large regions of matrices. A blocked implementation processes smaller submatrices so frequently reused data is more likely to remain in higher cache levels.

The script implements both a straightforward matrix multiplication and a blocked version.

The mathematical result is unchanged. The difference is the order in which data is accessed.

This concept is important in:

- Numerical computing
- Image processing
- Machine-learning workloads
- Scientific simulation
- Databases
- Graphics
- Signal processing

## Row-major and column-major access

The order in which multidimensional data is traversed affects locality.

For a row-oriented representation:

row 0: A A A A  
row 1: B B B B  
row 2: C C C C

Walking across one row generally accesses neighboring elements.

Walking down a column jumps between separate rows.

The Python matrix example demonstrates both traversal patterns.

The exact performance difference depends on the data representation, language runtime, compiler, CPU architecture, and dimensions.

## Sequential versus random access

Sequential access generally provides strong spatial locality.

Random access tends to reduce spatial locality and can increase:

- Cache misses
- TLB misses
- Memory latency exposure
- Storage-device latency

This is particularly important for storage.

HDDs are especially sensitive to random access because mechanical positioning is involved.

SSDs remove mechanical seek and rotational latency, making random I/O much faster than on HDDs, although random I/O still has higher latency than accessing RAM or CPU caches.

## HDD architecture

Hard disk drives use magnetic storage surfaces and mechanical movement.

A simplified HDD access consists of:

1. Seek
2. Rotational positioning
3. Data transfer

### Seek latency

The actuator moves the read/write head to the required track.

### Rotational latency

The disk platter rotates until the required sector reaches the head.

For a disk rotating at a constant rate, average rotational latency is approximately half of one rotation.

For a 7,200 RPM disk:

rotation period = 60 seconds / 7,200

which is approximately 8.33 milliseconds.

Average rotational latency is therefore approximately 4.17 milliseconds before considering other effects.

### Transfer time

Once the head is positioned, the requested data is transferred.

HDDs therefore benefit strongly from sequential access because it can reduce mechanical movement.

## SSD architecture

SSDs use NAND flash rather than magnetic platters.

An SSD has no spinning disk or mechanical read/write head.

This eliminates mechanical seek and rotational latency.

A simplified NAND hierarchy contains:

- Cells
- Pages
- Erase blocks

A key property of NAND flash is that programming and erasing are not symmetric operations. Data is generally programmed in pages while erasure occurs in larger blocks.

An existing logical page cannot simply be treated like a RAM byte and overwritten indefinitely in place.

## Flash Translation Layer

The Flash Translation Layer, or FTL, maps logical addresses exposed to the operating system to physical NAND locations.

This abstraction allows the SSD controller to manage:

- Logical-to-physical mapping
- Garbage collection
- Wear leveling
- Bad-block management
- Spare area
- Performance optimization

The operating system therefore sees a logical block device rather than the physical NAND organization.

## Garbage collection

Over time, an SSD contains a mixture of valid and obsolete physical pages.

Garbage collection selects blocks containing reclaimable space.

Valid pages may be moved elsewhere, after which the block can be erased and reused.

This internal movement contributes to physical writes that were not directly requested by the host.

The Python SSD simulation illustrates this idea conceptually.

Real SSD garbage collection is considerably more sophisticated.

## Write amplification

Write amplification is commonly expressed as:

Write amplification = physical storage writes / host-requested writes

A value of 1.0 means physical writes equal host writes in the simplified measurement.

A value above 1.0 means the device performs additional internal writes.

Write amplification can increase because of:

- Garbage collection
- Data relocation
- Small random writes
- Limited free space
- Flash-management policies

High write amplification can affect performance and flash endurance.

## Wear leveling

NAND flash cells have finite program/erase endurance.

Wear leveling attempts to distribute writes across physical flash cells rather than repeatedly using the same small region.

This is another reason logical addresses cannot simply be assumed to correspond permanently to fixed physical NAND locations.

## TRIM

TRIM is a mechanism through which the host can inform an SSD that certain logical blocks are no longer needed.

This information can help the controller avoid preserving obsolete data during future internal operations.

TRIM is particularly relevant to filesystem deletion and SSD garbage collection.

The exact behavior depends on operating-system and storage-device support.

## SSD versus HDD

| Characteristic | SSD | HDD |
|---|---|---|
| Storage technology | NAND flash | Magnetic media |
| Mechanical movement | None | Yes |
| Random-access latency | Low | High |
| Sequential throughput | High | Moderate to high |
| Capacity per cost | Usually higher cost per byte | Usually lower cost per byte |
| Noise | Silent | Mechanical noise |
| Shock sensitivity | Generally lower | Generally higher |
| Write behavior | Flash-management overhead | Mechanical positioning |
| Typical role | Fast primary storage | Large-capacity storage and archival workloads |

These are broad comparisons. Specific devices vary substantially.

## Volatile versus non-volatile storage

Registers, CPU caches, and RAM are normally volatile.

They require power to retain active contents.

SSDs and HDDs are non-volatile.

They retain stored information without continuous electrical power.

The distinction is important because a computer must move persistent information into volatile working memory before the CPU can operate on it efficiently.

## Latency hierarchy

A conceptual latency progression is:

Registers  
↓  
L1 cache  
↓  
L2 cache  
↓  
L3 cache  
↓  
RAM  
↓  
SSD  
↓  
HDD

The precise values vary enormously between systems.

The important property is the scale difference.

A CPU-cache access may be measured in nanoseconds or fractions of a nanosecond at the appropriate architectural level.

RAM access is generally measured in tens to hundreds of nanoseconds depending on what is being measured.

SSD access is commonly measured in microseconds for device-level operations.

HDD access is commonly measured in milliseconds for random operations.

The hierarchy therefore represents several orders of magnitude of latency.

## Latency versus bandwidth

Latency answers:

> How long before the operation begins producing useful data?

Bandwidth answers:

> How quickly can data be transferred once the transfer is underway?

For a large sequential transfer, bandwidth can dominate total time.

For a tiny random access, latency can dominate.

This explains why a storage device can advertise a very high sequential throughput while still feeling slow for many tiny random operations.

## Cache coherence

Multicore processors can have multiple cores caching the same memory block.

If one core modifies the block, other cached copies may need to be invalidated or updated according to the architecture's coherence protocol.

MESI is a well-known coherence protocol model with states:

- Modified
- Exclusive
- Shared
- Invalid

Modern systems can use other protocols or extensions.

Cache coherence concerns the relationship between cached copies of memory.

It is not the same as memory consistency.

## False sharing

False sharing occurs when independent variables used by different threads occupy the same cache line.

The threads may logically access different variables, but the coherence mechanism operates on cache lines.

A simplified example is:

Cache line: [counter A][counter B]

If thread 1 updates counter A and thread 2 updates counter B repeatedly, the threads may cause unnecessary cache-coherence traffic because the hardware tracks ownership at the cache-line level.

Padding or changing data layout can sometimes prevent the variables from sharing a cache line.

## Cache coherence versus memory consistency

These concepts are often confused.

### Cache coherence

Concerns how different cached copies of a particular memory location remain consistent.

### Memory consistency

Defines the allowed ordering and visibility of memory operations across processors and threads.

A coherent system is not automatically a system in which all memory operations appear in strict source-code order.

Correct concurrent programs should use the synchronization and atomicity mechanisms provided by their programming language and target architecture.

## NUMA

NUMA means Non-Uniform Memory Access.

In large multiprocessor systems, not all physical memory may have identical latency from every CPU.

A processor may have a nearby memory domain and a more distant memory domain.

NUMA-aware software attempts to maintain locality between:

- Threads
- Frequently accessed data
- CPU cores
- Memory domains

This extends the memory-hierarchy concept beyond caches.

## Instruction and data caches

Many processors use separate instruction and data caches at lower cache levels.

An instruction cache contains recently fetched instructions.

A data cache contains application data.

Separating them can allow instruction fetching and data access to proceed independently.

Higher cache levels may be unified.

The exact arrangement depends on the CPU architecture.

## Inclusive, exclusive, and non-inclusive caches

Cache levels can be organized using different relationships.

### Inclusive

A higher-level cache contains copies of data also present in lower-level caches.

This can simplify certain coherence and tracking operations but consumes capacity through duplication.

### Exclusive

Different cache levels attempt to hold different blocks.

This can increase effective aggregate capacity but can complicate movement between levels.

### Non-inclusive

No strict inclusion or exclusion rule is required.

Modern processors use varied implementations, so these terms should be treated as architectural design concepts rather than universal properties.

## Memory alignment

Alignment means placing data at addresses satisfying a particular boundary.

Examples include:

- 4-byte alignment
- 8-byte alignment
- 16-byte alignment
- 64-byte alignment

Aligned data can simplify hardware access and may improve performance.

Modern processors often support unaligned accesses, but the cost depends on architecture and access pattern.

An access that crosses cache-line or page boundaries may require additional work.

## Virtual-memory locality

Locality matters at multiple levels.

A program can have:

- Cache locality
- TLB locality
- Page locality
- NUMA locality
- Storage locality

A workload that accesses nearby virtual addresses may benefit from both cache-line reuse and TLB reuse.

A workload with a very large random working set may defeat several of these mechanisms simultaneously.

## Storage access stack

An application does not normally communicate directly with magnetic platters or raw NAND cells.

A conceptual stack is:

Application  
↓  
Runtime or library  
↓  
Operating system  
↓  
Filesystem  
↓  
Block layer  
↓  
Device driver  
↓  
Storage controller  
↓  
SSD controller or HDD firmware  
↓  
Physical media

Caching can occur at multiple points.

A file read may be satisfied from system memory without requiring a physical storage operation.

Similarly, storage devices can have their own internal caches.

## Persistence and durability

Non-volatile storage does not mean that every write request is instantly durable at the physical media.

Data can exist temporarily in:

- CPU caches
- Operating-system caches
- Filesystem buffers
- Storage-controller buffers
- Device caches

Applications that require strong durability, such as databases, must use appropriate synchronization and storage semantics.

Durability is therefore an end-to-end property rather than a simple synonym for "SSD" or "HDD."

## Cache-aware algorithm design

Memory hierarchy behavior should influence algorithm design when performance matters.

Useful principles include:

- Keep frequently used data together.
- Prefer predictable access patterns when appropriate.
- Reuse data before it is evicted.
- Avoid unnecessarily large working sets.
- Reduce pointer chasing when data-oriented layouts are practical.
- Consider blocking or tiling for large numerical workloads.
- Measure before optimizing.

A theoretically efficient algorithm can still perform poorly if its memory-access behavior creates excessive cache and TLB misses.

## Array-of-structures versus structure-of-arrays

Data layout can strongly affect locality.

Consider a conceptual record:

Person:
    age
    salary
    department
    identifier

An array of such records stores the fields together.

If an algorithm only needs salary values, it may load unrelated fields into cache.

A structure-of-arrays representation stores:

ages[]
salaries[]
departments[]
identifiers[]

If the algorithm only processes salaries, the relevant data is concentrated.

Neither layout is universally superior.

The appropriate choice depends on:

- Access pattern
- Data size
- SIMD/vectorization requirements
- Mutation patterns
- Memory footprint
- Code complexity

## Performance counters

Hardware performance-monitoring facilities can expose useful measurements.

Examples include:

- Instructions retired
- CPU cycles
- Cache references
- Cache misses
- Branch misses
- TLB events
- Memory bandwidth

A simplified metric is CPI:

CPI = CPU cycles / instructions

Cache miss rate can be represented as:

cache miss rate = cache misses / cache references

These counters can help distinguish a cache-bound workload from a computation-bound workload.

## Benchmarking considerations

Memory-hierarchy benchmarks are difficult to interpret if the experiment is poorly controlled.

Important variables include:

- Dataset size
- Cache size
- Working-set size
- Access pattern
- Stride
- Alignment
- Number of repetitions
- Warm-up behavior
- Compiler optimization
- Runtime overhead
- CPU frequency
- Other system activity
- Operating-system caching

For storage benchmarks, also consider:

- Sequential versus random access
- Read versus write
- Block size
- Queue depth
- Synchronous versus asynchronous I/O
- Cached versus direct I/O
- Filesystem behavior

A single timing result does not prove that cache behavior caused a performance difference.

## Python benchmark limitations

The study file contains timing demonstrations, but they should not be interpreted as direct measurements of hardware cache latency.

Python introduces substantial interpreter and object-management overhead.

Other influences include:

- Python object representation
- Garbage collection
- Dynamic dispatch
- Memory allocation
- Operating-system scheduling
- CPU frequency changes
- Background processes

For accurate microarchitectural analysis, native compiled workloads and hardware performance counters are generally more appropriate.

The Python examples are intended to demonstrate relationships and experimental reasoning.

## Security considerations

Memory hierarchy behavior can affect security.

Microarchitectural state can sometimes reveal information indirectly through timing.

Relevant concepts include:

- Cache side channels
- Speculative execution
- Memory isolation
- Privilege boundaries
- DMA
- Memory remanence

Cache timing can expose differences between cached and uncached accesses.

Speculative execution vulnerabilities have demonstrated that architectural permission checks alone do not necessarily describe every observable microarchitectural effect.

Security mitigations depend on the specific architecture and vulnerability and may involve hardware, firmware, operating-system, compiler, or application-level changes.

## Major design trade-offs

Memory hierarchy design is a continuous balancing problem.

### Larger caches

Advantages:

- Lower capacity-miss probability
- Larger working sets can remain close to the CPU

Costs:

- More silicon area
- More power
- Potentially greater access latency
- More complex management

### Higher associativity

Advantages:

- Fewer conflict misses

Costs:

- More tag comparisons
- Greater hardware complexity
- Potentially increased power

### Larger cache lines

Advantages:

- Better spatial locality

Costs:

- More bandwidth per miss
- Possible cache pollution
- Fewer distinct lines in a fixed-size cache

### Prefetching

Advantages:

- Can reduce effective miss latency

Costs:

- Consumes bandwidth
- Can evict useful data
- Incorrect predictions waste resources

### More RAM

Advantages:

- Larger active working set
- Lower paging pressure

Costs:

- Higher hardware cost
- Does not automatically improve poor CPU-cache locality

### SSD instead of HDD

Advantages:

- Much lower storage latency
- Strong random-I/O performance
- No mechanical seek

Costs:

- Often higher cost per byte
- NAND endurance considerations
- Internal garbage collection and write amplification

### HDD instead of SSD

Advantages:

- High capacity at low cost per byte

Costs:

- Mechanical latency
- Lower random-access performance
- Mechanical noise and vibration

## Common mistakes

### Thinking RAM and storage are the same thing

RAM is working memory. SSDs and HDDs provide persistent storage.

### Assuming an SSD is as fast as RAM

An SSD is dramatically faster than an HDD for many workloads, but it remains far slower than CPU caches and RAM.

### Assuming every cache miss reaches RAM

A miss in L1 may be satisfied by L2 or L3.

### Assuming a larger cache always improves performance

A larger cache can reduce some misses, but cache latency, power, associativity, and workload characteristics matter.

### Ignoring locality

Two algorithms with similar computational complexity can have very different performance because one accesses memory much more efficiently.

### Treating cache coherence as thread synchronization

Coherence does not replace locks, atomics, memory-ordering rules, or other synchronization mechanisms.

### Treating non-volatile storage as instantly durable

Storage controllers and operating systems can buffer writes.

### Assuming HDD performance is determined only by bandwidth

Random HDD performance is heavily affected by seek and rotational latency.

### Assuming SSDs behave like writable RAM

NAND flash uses pages, erase blocks, mapping, garbage collection, and wear management.

## Real-world applications

Memory hierarchy concepts are relevant to nearly every performance-sensitive computing system.

### Operating systems

Operating systems manage:

- Virtual memory
- Page tables
- Physical frames
- Paging
- Filesystem caches
- Storage I/O

### Databases

Databases rely heavily on locality.

They may maintain:

- Buffer pools
- Index structures
- Page caches
- Sequential scans
- Carefully organized data layouts

Database performance can change substantially depending on whether the active working set fits in memory.

### Compilers

Compilers can transform code to improve locality through techniques such as:

- Loop transformations
- Blocking
- Data-layout optimization
- Prefetching
- Vectorization

### Scientific computing

Large numerical workloads often depend on maximizing reuse of data in CPU caches and memory bandwidth.

Matrix multiplication is a classic example.

### Graphics

Graphics workloads process large amounts of structured data and rely on hierarchical memory systems and locality.

### Web servers

Web applications can benefit from:

- CPU caches
- RAM-based caching
- Filesystem caches
- SSD storage
- Database buffer pools

### Cloud and enterprise servers

Large servers introduce additional locality concerns such as NUMA and memory bandwidth contention.

### Embedded systems

Embedded devices often have much tighter limits on:

- Memory capacity
- Power
- Cache size
- Storage
- Thermal budget

Memory hierarchy decisions therefore directly affect system design.

## Integrated access path

The study script models a simplified access path:

CPU request  
↓  
L1  
├── hit → use data  
└── miss  
    ↓  
L2  
├── hit → use data  
└── miss  
    ↓  
L3  
├── hit → use data  
└── miss  
    ↓  
RAM

Persistent storage normally participates at a different layer.

For example, a page that is not resident in physical memory can require operating-system work involving SSD or HDD storage.

This distinction is important:

CPU cache miss

does not mean:

SSD access

A typical access may stop many levels earlier.

## Relationship between capacity and speed

The hierarchy can be understood as a series of compromises.

| Level | Relative capacity | Relative speed | Volatile | Typical technology |
|---|---|---|---|---|
| Registers | Extremely small | Extremely high | Yes | Register storage |
| L1 | Very small | Very high | Yes | SRAM |
| L2 | Small | Very high | Yes | SRAM |
| L3 | Larger | High | Yes | SRAM |
| RAM | Large | Moderate | Yes | DRAM |
| SSD | Very large | Lower | No | NAND flash |
| HDD | Very large | Lowest for random access | No | Magnetic media |

The boundaries are not absolute.

For example, some modern systems include additional cache-like structures, persistent-memory technologies, high-bandwidth memory, specialized accelerators, or multiple NUMA memory domains.

## Edge cases

The study script deliberately tests invalid conditions such as:

- Negative byte counts
- Zero-sized caches
- Negative memory addresses
- Invalid miss rates
- Invalid page sizes
- Invalid SSD dimensions

Robust systems should validate assumptions rather than silently accepting impossible configurations.

Memory-hierarchy software can also encounter edge cases involving:

- Address-space limits
- Alignment boundaries
- Cache-line boundaries
- Page boundaries
- NUMA boundaries
- Storage-device exhaustion
- SSD over-provisioning
- Full filesystems
- Memory pressure

## Implementation notes for the Python study file

The program is intentionally self-contained and uses only Python's standard library.

The simulations are conceptual rather than hardware emulators.

Important implementations include:

- `CPURegisters` for register behavior
- `SimpleDirectMappedCache` for direct-mapped cache behavior
- `AssociativeCache` for set-associative organization
- `ReplacementCache` for replacement-policy comparison
- `WriteCache` for write policy behavior
- `BlockCacheSimulator` for configurable cache experiments
- `SimpleDRAM` for conceptual DRAM storage
- `PageTable` for virtual-to-physical translation
- `TLB` for translation caching
- `PrefetchCache` for prefetching behavior
- `HDDSimulator` for simplified mechanical storage timing
- `SSDModel` for conceptual NAND management
- `blocked_matrix_multiply` for cache-aware algorithm design

Each implementation is deliberately small enough to inspect while still representing an important architectural idea.

## Important limitations of the simulations

The simulations do not reproduce any particular CPU or storage device.

They do not model all of the following hardware details:

- Exact transistor-level behavior
- Real cache timing
- Pipeline stalls
- Out-of-order execution
- Speculative execution
- Store buffers
- Load queues
- Hardware prefetcher internals
- Real MESI-family protocol traffic
- DRAM row-buffer timing
- Memory-controller scheduling
- Real TLB page-walk behavior
- Real SSD FTL algorithms
- NAND cell-level programming
- Real SSD garbage-collection policies
- HDD zone bit recording
- Real disk firmware scheduling
- Filesystem implementation details

These omissions are intentional.

The purpose is to demonstrate the underlying relationships between capacity, latency, locality, caching, virtual memory, and persistent storage.

## Key distinctions

| Concept A | Concept B | Main distinction |
|---|---|---|
| Register | Cache | Register holds CPU-operational values; cache holds copies of memory blocks |
| Cache | RAM | Cache is smaller and faster; RAM is larger working memory |
| RAM | SSD | RAM is volatile working memory; SSD is persistent flash storage |
| SSD | HDD | Both are persistent, but SSD uses flash while HDD uses magnetic media |
| Latency | Bandwidth | Latency measures delay; bandwidth measures transfer rate |
| Cache hit | Cache miss | Hit finds data at that level; miss requires another level |
| Coherence | Consistency | Coherence concerns cached copies; consistency concerns operation ordering |
| Page | Cache line | A page is a virtual-memory unit; a cache line is a CPU-cache transfer unit |
| TLB | Data cache | TLB caches address translations; data cache caches memory contents |
| Volatile | Non-volatile | Volatile storage needs power to retain active contents; non-volatile storage persists |
| Seek | Transfer | HDD seek positions the head; transfer moves the requested data |
| Garbage collection | Wear leveling | Garbage collection reclaims flash blocks; wear leveling distributes wear |

Understanding these distinctions prevents many common errors when reasoning about computer performance.

## Practical reasoning framework

When investigating a memory-related performance problem, the following questions provide a useful conceptual framework:

1. What is the working-set size?
2. What is the access pattern?
3. Is access sequential, strided, or random?
4. Does the active data fit in the relevant cache?
5. Are there excessive cache misses?
6. Are TLB misses significant?
7. Is the workload limited by memory bandwidth?
8. Is it limited by memory latency?
9. Is the system under RAM pressure?
10. Is paging occurring?
11. Is storage access sequential or random?
12. If storage is involved, is the device an SSD or HDD?
13. Are synchronization or coherence effects limiting multicore performance?
14. Are data structures causing poor locality?
15. Can the hypothesis be validated with measurements?

This approach is more reliable than assuming that "the computer is slow because RAM is slow."

Memory performance is a system-level interaction involving the processor, caches, memory controller, RAM, operating system, data layout, workload, and storage subsystem.

## Execution structure

The Python file presents the concepts in progression:

Fundamental units  
↓  
Memory hierarchy  
↓  
Registers  
↓  
SRAM and DRAM  
↓  
Cache lines and locality  
↓  
Cache mapping  
↓  
Replacement policies  
↓  
Write policies  
↓  
AMAT  
↓  
Multi-level caches  
↓  
Virtual memory  
↓  
TLB  
↓  
Working sets  
↓  
Prefetching  
↓  
Multicore coherence  
↓  
HDD  
↓  
SSD  
↓  
Cache-aware algorithms  
↓  
Performance analysis  
↓  
Security and production considerations

The resulting model is not simply a list of hardware components. It demonstrates why the components exist and how their properties interact.

## Real-world relevance

The memory hierarchy is one of the fundamental structures underlying modern computing.

A program's performance is determined not only by how many arithmetic operations it performs, but also by where its data resides, how often that data is reused, how it is laid out, and how efficiently it moves through the hierarchy.

The most important practical relationship is:

Good locality  
↓  
More cache reuse  
↓  
Fewer expensive lower-level accesses  
↓  
Lower effective memory-access cost  
↓  
Higher potential performance

The reverse can also occur:

Poor locality  
↓  
More cache and TLB misses  
↓  
More RAM traffic  
↓  
Possible paging pressure  
↓  
Potential storage I/O  
↓  
Much higher effective access cost
