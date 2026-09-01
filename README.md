# 120-Day System Design & Architecture Learning Journey

| Day | Level | Module | Topic | Key Concepts / Learning Objectives |
|---:|---|---|---|---|
| 1 | Beginner | System Design Foundations | What is System Design? | System design, software architecture, components, interfaces, constraints |
| 2 | Beginner | System Design Foundations | Software Design vs System Design | LLD vs HLD, component design, architecture decisions |
| 3 | Beginner | System Design Foundations | Functional Requirements | Features, user actions, system behavior, use cases |
| 4 | Beginner | System Design Foundations | Non-Functional Requirements | Scalability, availability, reliability, latency, security |
| 5 | Beginner | System Design Foundations | Scalability Fundamentals | Vertical scaling, horizontal scaling, scaling bottlenecks |
| 6 | Beginner | System Design Foundations | Availability | Uptime, downtime, SLA, SLO, SLI |
| 7 | Beginner | System Design Foundations | Reliability | Faults, failures, recovery, fault tolerance |
| 8 | Beginner | System Design Foundations | Latency and Throughput | Response time, requests/sec, processing capacity |
| 9 | Beginner | System Design Foundations | Back-of-the-Envelope Estimation | QPS, storage, bandwidth, traffic estimation |
| 10 | Beginner | System Design Foundations | Capacity Planning | User growth, traffic projections, infrastructure sizing |
| 11 | Beginner | Computer Fundamentals | How Computers Work | CPU, RAM, storage, processes, threads |
| 12 | Beginner | Computer Fundamentals | Memory Hierarchy | Registers, cache, RAM, SSD, HDD |
| 13 | Beginner | Computer Fundamentals | Processes and Threads | Concurrency, context switching, process lifecycle |
| 14 | Beginner | Networking | Computer Networks | LAN, WAN, routers, switches, packets |
| 15 | Beginner | Networking | OSI Model | Seven layers and their responsibilities |
| 16 | Beginner | Networking | TCP/IP Model | Network stack and practical communication |
| 17 | Beginner | Networking | IP Addressing | IPv4, IPv6, public/private IP |
| 18 | Beginner | Networking | DNS | Domain resolution, recursive DNS, caching |
| 19 | Beginner | Networking | TCP | Connections, handshake, reliability, retransmission |
| 20 | Beginner | Networking | UDP | Connectionless communication, speed vs reliability |
| 21 | Beginner | Networking | HTTP | Requests, responses, methods, status codes |
| 22 | Beginner | Networking | HTTPS & TLS | Encryption, certificates, secure communication |
| 23 | Beginner | Web Architecture | Client-Server Architecture | Browser, server, request-response lifecycle |
| 24 | Beginner | Web Architecture | REST APIs | Resources, endpoints, methods, statelessness |
| 25 | Beginner | Web Architecture | API Design | Versioning, pagination, filtering, error handling |
| 26 | Beginner | Web Architecture | GraphQL | Queries, mutations, schemas, advantages and trade-offs |
| 27 | Beginner | Web Architecture | gRPC | RPC, Protocol Buffers, service-to-service communication |
| 28 | Beginner | Web Architecture | Synchronous vs Asynchronous Communication | Blocking, non-blocking, async workflows |
| 29 | Beginner | Databases | Database Fundamentals | Tables, records, schemas, queries |
| 30 | Beginner | Databases | Relational Databases | SQL, relationships, constraints |
| 31 | Beginner | Databases | Database Normalization | 1NF, 2NF, 3NF, denormalization |
| 32 | Beginner | Databases | SQL Indexes | B-Tree indexes, query performance |
| 33 | Beginner | Databases | Transactions | ACID properties and transactional guarantees |
| 34 | Beginner | Databases | Isolation Levels | Read uncommitted, read committed, repeatable read, serializable |
| 35 | Intermediate | Databases | NoSQL Databases | Key-value, document, column-family, graph databases |
| 36 | Intermediate | Databases | SQL vs NoSQL | Data models, scalability, consistency, use cases |
| 37 | Intermediate | Databases | Database Replication | Primary-replica, synchronous and asynchronous replication |
| 38 | Intermediate | Databases | Database Partitioning | Horizontal and vertical partitioning |
| 39 | Intermediate | Databases | Database Sharding | Shard keys, routing, distributed storage |
| 40 | Intermediate | Databases | Consistent Hashing | Hash rings, virtual nodes, distributed partitioning |
| 41 | Intermediate | Distributed Systems | Distributed Systems Fundamentals | Multiple machines, network failures, coordination |
| 42 | Intermediate | Distributed Systems | CAP Theorem | Consistency, availability, partition tolerance |
| 43 | Intermediate | Distributed Systems | Consistency Models | Strong, eventual, causal consistency |
| 44 | Intermediate | Distributed Systems | Distributed Transactions | Two-phase commit and distributed coordination |
| 45 | Intermediate | Distributed Systems | Idempotency | Safe retries, duplicate requests, idempotent APIs |
| 46 | Intermediate | Distributed Systems | Time in Distributed Systems | Logical clocks, clock skew, timestamps |
| 47 | Intermediate | Caching | Why Caching? | Latency reduction, database load reduction |
| 48 | Intermediate | Caching | Cache Strategies | Cache-aside, read-through, write-through |
| 49 | Intermediate | Caching | Cache Eviction | LRU, LFU, FIFO, TTL |
| 50 | Intermediate | Caching | Cache Invalidation | Stale data, invalidation strategies |
| 51 | Intermediate | Caching | Distributed Caching | Redis, Memcached, cache clusters |
| 52 | Intermediate | Caching | Cache Failure Patterns | Cache stampede, penetration, avalanche |
| 53 | Intermediate | Load Balancing | Load Balancers | Traffic distribution and health checks |
| 54 | Intermediate | Load Balancing | Load Balancing Algorithms | Round robin, weighted, least connections |
| 55 | Intermediate | Load Balancing | Reverse Proxy | Nginx, proxying, TLS termination |
| 56 | Intermediate | Load Balancing | L4 vs L7 Load Balancing | Transport vs application-level balancing |
| 57 | Intermediate | CDN | Content Delivery Networks | Edge servers, caching, geographic distribution |
| 58 | Intermediate | CDN | CDN Architecture | Origin server, edge locations, cache policies |
| 59 | Intermediate | Messaging | Message Queues | Producers, consumers, brokers |
| 60 | Intermediate | Messaging | Queue Patterns | Point-to-point, competing consumers |
| 61 | Intermediate | Messaging | Pub/Sub | Topics, subscribers, event broadcasting |
| 62 | Intermediate | Messaging | Kafka Fundamentals | Topics, partitions, offsets, brokers |
| 63 | Intermediate | Messaging | Kafka Architecture | Replication, consumer groups, fault tolerance |
| 64 | Intermediate | Messaging | Event-Driven Architecture | Events, producers, consumers, decoupling |
| 65 | Intermediate | Microservices | Monolith Architecture | Advantages, limitations, scaling |
| 66 | Intermediate | Microservices | Modular Monolith | Boundaries, modules, migration strategy |
| 67 | Intermediate | Microservices | Microservices Architecture | Service boundaries and independent deployment |
| 68 | Intermediate | Microservices | Service Communication | REST, gRPC, messaging |
| 69 | Intermediate | Microservices | API Gateway | Routing, authentication, rate limiting |
| 70 | Intermediate | Microservices | Service Discovery | Registration, discovery, health checks |
| 71 | Advanced | Microservices | Circuit Breaker | Failure isolation and graceful degradation |
| 72 | Advanced | Microservices | Retry & Timeout Patterns | Backoff, jitter, retry storms |
| 73 | Advanced | Microservices | Saga Pattern | Distributed transaction management |
| 74 | Advanced | Microservices | Event Sourcing | Events as source of truth |
| 75 | Advanced | Microservices | CQRS | Separate read and write models |
| 76 | Advanced | Architecture | Layered Architecture | Presentation, application, domain, infrastructure |
| 77 | Advanced | Architecture | Clean Architecture | Dependency inversion and boundaries |
| 78 | Advanced | Architecture | Hexagonal Architecture | Ports and adapters |
| 79 | Advanced | Architecture | Domain-Driven Design | Bounded contexts, aggregates, entities |
| 80 | Advanced | Architecture | Architecture Trade-offs | Cost, complexity, performance, reliability |
| 81 | Advanced | Reliability | Fault Tolerance | Failure detection and recovery |
| 82 | Advanced | Reliability | Redundancy | Active-active, active-passive architectures |
| 83 | Advanced | Reliability | Disaster Recovery | Backup, restore, RPO, RTO |
| 84 | Advanced | Reliability | Multi-Region Architecture | Regional failover and geographic redundancy |
| 85 | Advanced | Reliability | High Availability Architecture | Eliminating single points of failure |
| 86 | Advanced | Reliability | Graceful Degradation | Partial functionality during failures |
| 87 | Advanced | Reliability | Bulkheads | Resource isolation and failure containment |
| 88 | Advanced | Observability | Logging | Structured logs, centralized logging |
| 89 | Advanced | Observability | Metrics | Counters, gauges, histograms, SLIs |
| 90 | Advanced | Observability | Distributed Tracing | Trace IDs, spans, request tracing |
| 91 | Advanced | Observability | Monitoring & Alerting | Dashboards, thresholds, incident detection |
| 92 | Advanced | Security Architecture | Authentication | Sessions, tokens, OAuth, JWT |
| 93 | Advanced | Security Architecture | Authorization | RBAC, ABAC, permissions |
| 94 | Advanced | Security Architecture | API Security | API keys, rate limits, validation |
| 95 | Advanced | Security Architecture | Data Security | Encryption at rest and in transit |
| 96 | Advanced | Security Architecture | Zero Trust Architecture | Identity-centric security and least privilege |
| 97 | Advanced | Cloud Architecture | Cloud Computing Fundamentals | IaaS, PaaS, SaaS |
| 98 | Advanced | Cloud Architecture | Cloud Networking | VPC, subnets, routing, gateways |
| 99 | Advanced | Cloud Architecture | Containers | Docker, images, containers |
| 100 | Advanced | Cloud Architecture | Kubernetes | Pods, services, deployments, scaling |
| 101 | Advanced | Cloud Architecture | Infrastructure as Code | Terraform, declarative infrastructure |
| 102 | Advanced | Cloud Architecture | CI/CD Architecture | Build, test, deployment pipelines |
| 103 | Advanced | Scalability | Auto Scaling | Horizontal scaling and elasticity |
| 104 | Advanced | Scalability | Rate Limiting | Token bucket, leaky bucket, sliding window |
| 105 | Advanced | Scalability | Backpressure | Controlling overloaded systems |
| 106 | Advanced | Scalability | Search Architecture | Inverted indexes, Elasticsearch, distributed search |
| 107 | Advanced | Scalability | Real-Time Systems | WebSockets, Server-Sent Events, streaming |
| 108 | Advanced | Scalability | Geo-Distributed Systems | Global traffic routing and regional data |
| 109 | Expert | Distributed Systems | Consensus | Leader election, quorum, consensus |
| 110 | Expert | Distributed Systems | Raft & Paxos Concepts | Replicated state machines and consensus |
| 111 | Expert | Distributed Systems | Exactly-Once vs At-Least-Once | Delivery semantics and duplicate processing |
| 112 | Expert | Distributed Systems | Stream Processing | Kafka Streams, windowing, event processing |
| 113 | Expert | Distributed Systems | Data Pipelines | Batch vs streaming architectures |
| 114 | Expert | Modern Architecture | AI System Architecture | Model serving, inference, pipelines |
| 115 | Expert | Modern Architecture | RAG Architecture | Embeddings, vector databases, retrieval |
| 116 | Expert | Modern Architecture | LLM Application Architecture | Prompting, inference, caching, orchestration |
| 117 | Expert | System Design Practice | Design a URL Shortener | Requirements, APIs, database, caching, scaling |
| 118 | Expert | System Design Practice | Design a Chat System | WebSockets, messaging, presence, delivery |
| 119 | Expert | System Design Practice | Design a Video Streaming Platform | CDN, storage, transcoding, streaming |
| 120 | Expert | System Design Mastery | Design a Global-Scale Platform | Requirements → estimation → architecture → scaling → reliability → security → trade-offs |
