#include <arpa/inet.h>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

/*
 * UDP INDUSTRY-STYLE CASE STUDY
 *
 * Scenario:
 *     A telemetry gateway receives sensor measurements from many remote
 *     devices using UDP.
 *
 * The system demonstrates:
 *     - connectionless communication
 *     - datagram boundaries
 *     - binary application protocols
 *     - sequence numbers
 *     - acknowledgements
 *     - duplicate detection
 *     - out-of-order buffering
 *     - retransmission modeling
 *     - validation
 *     - timeout behavior
 *     - idempotent processing
 *     - IPv4 socket programming
 *     - performance and reliability trade-offs
 *
 * Build:
 *     g++ -std=c++17 -O2 -Wall -Wextra -pedantic udp_gateway.cpp -o udp_gateway
 *
 * This example uses POSIX sockets and therefore targets Linux/macOS and
 * compatible Unix-like environments.
 */


// =============================================================================
// 1. BASIC DATA TYPES
// =============================================================================

struct TelemetryRecord {
    uint32_t deviceId;
    uint32_t sequenceNumber;
    double temperature;
    double pressure;
};

struct ReliablePacket {
    uint32_t sequenceNumber;
    std::string payload;
};


// =============================================================================
// 2. BYTE-ORDER HELPERS
// =============================================================================

void appendUint32(std::string& buffer, uint32_t value) {
    uint32_t networkValue = htonl(value);

    const char* bytes = reinterpret_cast<const char*>(&networkValue);
    buffer.append(bytes, sizeof(networkValue));
}

uint32_t readUint32(const std::string& buffer, std::size_t offset) {
    if (offset + sizeof(uint32_t) > buffer.size()) {
        throw std::runtime_error("Packet is too short for uint32.");
    }

    uint32_t networkValue = 0;
    std::memcpy(&networkValue, buffer.data() + offset, sizeof(networkValue));

    return ntohl(networkValue);
}


// =============================================================================
// 3. APPLICATION MESSAGE FORMAT
// =============================================================================

/*
 * Application protocol:
 *
 *   4 bytes  device ID
 *   4 bytes  sequence number
 *   8 bytes  temperature as IEEE-754 double
 *   8 bytes  pressure as IEEE-754 double
 *
 * Total = 24 bytes.
 *
 * For production protocols, floating-point wire representation and precision
 * should be specified formally. This example focuses on the architecture.
 */

std::string encodeTelemetry(const TelemetryRecord& record) {
    std::string packet;
    packet.reserve(24);

    appendUint32(packet, record.deviceId);
    appendUint32(packet, record.sequenceNumber);

    packet.append(
        reinterpret_cast<const char*>(&record.temperature),
        sizeof(record.temperature)
    );

    packet.append(
        reinterpret_cast<const char*>(&record.pressure),
        sizeof(record.pressure)
    );

    return packet;
}

TelemetryRecord decodeTelemetry(const std::string& packet) {
    constexpr std::size_t expectedSize = 24;

    if (packet.size() != expectedSize) {
        throw std::runtime_error("Invalid telemetry packet size.");
    }

    TelemetryRecord record{};

    record.deviceId = readUint32(packet, 0);
    record.sequenceNumber = readUint32(packet, 4);

    std::memcpy(
        &record.temperature,
        packet.data() + 8,
        sizeof(record.temperature)
    );

    std::memcpy(
        &record.pressure,
        packet.data() + 16,
        sizeof(record.pressure)
    );

    return record;
}


// =============================================================================
// 4. VALIDATION
// =============================================================================

void validateTelemetry(const TelemetryRecord& record) {
    /*
     * UDP servers must assume that every received datagram can be malformed
     * or intentionally crafted by an untrusted sender.
     */

    if (record.deviceId == 0) {
        throw std::runtime_error("Device ID cannot be zero.");
    }

    if (record.sequenceNumber == 0) {
        throw std::runtime_error("Sequence number cannot be zero.");
    }

    if (!std::isfinite(record.temperature)) {
        throw std::runtime_error("Temperature must be finite.");
    }

    if (!std::isfinite(record.pressure)) {
        throw std::runtime_error("Pressure must be finite.");
    }

    if (record.temperature < -100.0 || record.temperature > 200.0) {
        throw std::runtime_error("Temperature is outside accepted range.");
    }

    if (record.pressure < 0.0 || record.pressure > 2000.0) {
        throw std::runtime_error("Pressure is outside accepted range.");
    }
}


// =============================================================================
// 5. DUPLICATE DETECTION
// =============================================================================

class DuplicateDetector {
private:
    std::unordered_map<uint32_t, uint32_t> highestSequenceByDevice_;

public:
    bool isNew(uint32_t deviceId, uint32_t sequenceNumber) {
        auto iterator = highestSequenceByDevice_.find(deviceId);

        if (iterator == highestSequenceByDevice_.end()) {
            highestSequenceByDevice_[deviceId] = sequenceNumber;
            return true;
        }

        if (sequenceNumber <= iterator->second) {
            return false;
        }

        iterator->second = sequenceNumber;
        return true;
    }
};


// =============================================================================
// 6. OUT-OF-ORDER BUFFER
// =============================================================================

class OrderedTelemetryBuffer {
private:
    uint32_t nextExpected_;
    std::map<uint32_t, TelemetryRecord> pending_;

public:
    explicit OrderedTelemetryBuffer(uint32_t firstExpected = 1)
        : nextExpected_(firstExpected) {}

    std::vector<TelemetryRecord> receive(const TelemetryRecord& record) {
        std::vector<TelemetryRecord> ready;

        if (record.sequenceNumber < nextExpected_) {
            // Old packet or duplicate.
            return ready;
        }

        pending_.emplace(record.sequenceNumber, record);

        while (true) {
            auto iterator = pending_.find(nextExpected_);

            if (iterator == pending_.end()) {
                break;
            }

            ready.push_back(iterator->second);
            pending_.erase(iterator);
            ++nextExpected_;
        }

        return ready;
    }

    std::size_t bufferedCount() const {
        return pending_.size();
    }

    uint32_t nextExpected() const {
        return nextExpected_;
    }
};


// =============================================================================
// 7. ACKNOWLEDGEMENT AND RETRANSMISSION MODEL
// =============================================================================

struct PendingTransmission {
    ReliablePacket packet;
    std::chrono::steady_clock::time_point sentAt;
    unsigned retries;
};

class ReliableSenderModel {
private:
    uint32_t nextSequence_;
    std::chrono::milliseconds timeout_;
    unsigned maximumRetries_;

    std::map<uint32_t, PendingTransmission> pending_;

public:
    ReliableSenderModel(
        std::chrono::milliseconds timeout,
        unsigned maximumRetries
    )
        : nextSequence_(1),
          timeout_(timeout),
          maximumRetries_(maximumRetries) {}

    ReliablePacket createPacket(const std::string& payload) {
        return ReliablePacket{nextSequence_++, payload};
    }

    void markSent(const ReliablePacket& packet) {
        pending_[packet.sequenceNumber] = PendingTransmission{
            packet,
            std::chrono::steady_clock::now(),
            0
        };
    }

    bool acknowledge(uint32_t sequenceNumber) {
        return pending_.erase(sequenceNumber) > 0;
    }

    std::vector<ReliablePacket> collectRetransmissions() {
        const auto now = std::chrono::steady_clock::now();
        std::vector<ReliablePacket> retransmissions;

        for (auto iterator = pending_.begin(); iterator != pending_.end();) {
            auto& transmission = iterator->second;

            if (now - transmission.sentAt < timeout_) {
                ++iterator;
                continue;
            }

            if (transmission.retries >= maximumRetries_) {
                iterator = pending_.erase(iterator);
                continue;
            }

            ++transmission.retries;
            transmission.sentAt = now;
            retransmissions.push_back(transmission.packet);
            ++iterator;
        }

        return retransmissions;
    }

    std::size_t outstanding() const {
        return pending_.size();
    }
};


// =============================================================================
// 8. TELEMETRY DATABASE MODEL
// =============================================================================

class TelemetryStore {
private:
    std::vector<TelemetryRecord> records_;

public:
    void insert(const TelemetryRecord& record) {
        records_.push_back(record);
    }

    const std::vector<TelemetryRecord>& records() const {
        return records_;
    }

    std::optional<double> averageTemperature() const {
        if (records_.empty()) {
            return std::nullopt;
        }

        double total = 0.0;

        for (const auto& record : records_) {
            total += record.temperature;
        }

        return total / static_cast<double>(records_.size());
    }
};


// =============================================================================
// 9. TELEMETRY PROCESSOR
// =============================================================================

class TelemetryProcessor {
private:
    DuplicateDetector duplicateDetector_;
    std::map<uint32_t, OrderedTelemetryBuffer> deviceBuffers_;
    TelemetryStore store_;

public:
    void process(const TelemetryRecord& record) {
        validateTelemetry(record);

        if (!duplicateDetector_.isNew(
                record.deviceId,
                record.sequenceNumber)) {
            std::cout
                << "Duplicate/stale packet ignored: device="
                << record.deviceId
                << ", sequence="
                << record.sequenceNumber
                << '\n';

            return;
        }

        auto iterator = deviceBuffers_.find(record.deviceId);

        if (iterator == deviceBuffers_.end()) {
            iterator = deviceBuffers_.emplace(
                record.deviceId,
                OrderedTelemetryBuffer(record.sequenceNumber)
            ).first;
        }

        std::vector<TelemetryRecord> ready =
            iterator->second.receive(record);

        for (const auto& readyRecord : ready) {
            store_.insert(readyRecord);

            std::cout
                << std::fixed
                << std::setprecision(2)
                << "Processed device="
                << readyRecord.deviceId
                << " sequence="
                << readyRecord.sequenceNumber
                << " temperature="
                << readyRecord.temperature
                << " pressure="
                << readyRecord.pressure
                << '\n';
        }
    }

    const TelemetryStore& store() const {
        return store_;
    }
};


// =============================================================================
// 10. UDP SERVER
// =============================================================================

class UdpTelemetryServer {
private:
    int socketFd_;
    sockaddr_in address_;

public:
    UdpTelemetryServer()
        : socketFd_(-1) {

        socketFd_ = ::socket(AF_INET, SOCK_DGRAM, 0);

        if (socketFd_ < 0) {
            throw std::runtime_error(
                std::string("socket() failed: ") + std::strerror(errno)
            );
        }

        int reuseAddress = 1;

        if (setsockopt(
                socketFd_,
                SOL_SOCKET,
                SO_REUSEADDR,
                &reuseAddress,
                sizeof(reuseAddress)) < 0) {

            close(socketFd_);

            throw std::runtime_error(
                std::string("setsockopt() failed: ") + std::strerror(errno)
            );
        }

        std::memset(&address_, 0, sizeof(address_));

        address_.sin_family = AF_INET;

        // Binding to loopback makes this educational case study local.
        address_.sin_addr.s_addr = htonl(INADDR_LOOPBACK);

        // Port zero lets the operating system choose an available port.
        address_.sin_port = htons(0);

        if (bind(
                socketFd_,
                reinterpret_cast<sockaddr*>(&address_),
                sizeof(address_)) < 0) {

            close(socketFd_);

            throw std::runtime_error(
                std::string("bind() failed: ") + std::strerror(errno)
            );
        }

        socklen_t length = sizeof(address_);

        if (getsockname(
                socketFd_,
                reinterpret_cast<sockaddr*>(&address_),
                &length) < 0) {

            close(socketFd_);

            throw std::runtime_error(
                std::string("getsockname() failed: ") + std::strerror(errno)
            );
        }
    }

    ~UdpTelemetryServer() {
        if (socketFd_ >= 0) {
            close(socketFd_);
        }
    }

    int port() const {
        return ntohs(address_.sin_port);
    }

    void receiveOne(TelemetryProcessor& processor) {
        /*
         * A fixed upper bound prevents the application from attempting to
         * process arbitrarily large UDP datagrams.
         */
        constexpr std::size_t maxDatagramSize = 2048;

        char buffer[maxDatagramSize];

        sockaddr_in senderAddress{};
        socklen_t senderLength = sizeof(senderAddress);

        const ssize_t received = recvfrom(
            socketFd_,
            buffer,
            sizeof(buffer),
            0,
            reinterpret_cast<sockaddr*>(&senderAddress),
            &senderLength
        );

        if (received < 0) {
            throw std::runtime_error(
                std::string("recvfrom() failed: ") + std::strerror(errno)
            );
        }

        std::string packet(buffer, static_cast<std::size_t>(received));

        try {
            TelemetryRecord record = decodeTelemetry(packet);
            processor.process(record);
        }
        catch (const std::exception& error) {
            /*
             * A malformed datagram should normally be rejected without
             * terminating the entire UDP service.
             */
            std::cerr
                << "Rejected UDP datagram: "
                << error.what()
                << '\n';
        }
    }

    void sendAcknowledgement(
        uint32_t deviceId,
        uint32_t sequenceNumber,
        const sockaddr_in& destination
    ) {
        std::string acknowledgement;

        appendUint32(acknowledgement, deviceId);
        appendUint32(acknowledgement, sequenceNumber);

        const ssize_t sent = sendto(
            socketFd_,
            acknowledgement.data(),
            acknowledgement.size(),
            0,
            reinterpret_cast<const sockaddr*>(&destination),
            sizeof(destination)
        );

        if (sent < 0) {
            throw std::runtime_error(
                std::string("sendto() failed: ") + std::strerror(errno)
            );
        }
    }
};


// =============================================================================
// 11. LOCAL CLIENT
// =============================================================================

class UdpTelemetryClient {
private:
    int socketFd_;
    sockaddr_in destination_;

public:
    explicit UdpTelemetryClient(int serverPort)
        : socketFd_(-1) {

        socketFd_ = ::socket(AF_INET, SOCK_DGRAM, 0);

        if (socketFd_ < 0) {
            throw std::runtime_error(
                std::string("Client socket() failed: ") + std::strerror(errno)
            );
        }

        std::memset(&destination_, 0, sizeof(destination_));

        destination_.sin_family = AF_INET;
        destination_.sin_port = htons(static_cast<uint16_t>(serverPort));

        if (inet_pton(
                AF_INET,
                "127.0.0.1",
                &destination_.sin_addr) != 1) {

            close(socketFd_);

            throw std::runtime_error("Failed to create IPv4 destination.");
        }
    }

    ~UdpTelemetryClient() {
        if (socketFd_ >= 0) {
            close(socketFd_);
        }
    }

    void send(const TelemetryRecord& record) {
        const std::string packet = encodeTelemetry(record);

        const ssize_t sent = sendto(
            socketFd_,
            packet.data(),
            packet.size(),
            0,
            reinterpret_cast<const sockaddr*>(&destination_),
            sizeof(destination_)
        );

        if (sent < 0) {
            throw std::runtime_error(
                std::string("Client sendto() failed: ") + std::strerror(errno)
            );
        }

        if (static_cast<std::size_t>(sent) != packet.size()) {
            throw std::runtime_error("Unexpected partial UDP send.");
        }
    }
};


// =============================================================================
// 12. CHECKSUM DEMONSTRATION
// =============================================================================

uint16_t internetChecksum(const std::string& data) {
    uint32_t sum = 0;

    for (std::size_t index = 0; index < data.size(); index += 2) {
        uint16_t word =
            static_cast<unsigned char>(data[index]) << 8;

        if (index + 1 < data.size()) {
            word |= static_cast<unsigned char>(data[index + 1]);
        }

        sum += word;

        while (sum >> 16U) {
            sum = (sum & 0xFFFFU) + (sum >> 16U);
        }
    }

    return static_cast<uint16_t>(~sum);
}


// =============================================================================
// 13. COMPLEXITY DEMONSTRATION
// =============================================================================

void explainComplexity() {
    std::cout << "\n"
              << std::string(78, '=')
              << "\nALGORITHMIC COMPLEXITY\n"
              << std::string(78, '=')
              << '\n';

    std::cout
        << "Duplicate lookup with unordered_map: average O(1)\n"
        << "Out-of-order packet insertion with map: O(log n)\n"
        << "Delivering k contiguous buffered packets: O(k log n) in this design\n"
        << "Appending telemetry to vector: amortized O(1)\n"
        << "Encoding a packet of n bytes: O(n)\n"
        << "Decoding a packet of n bytes: O(n)\n";
}


// =============================================================================
// 14. TESTS
// =============================================================================

void require(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error("Test failed: " + message);
    }
}

void testTelemetryEncoding() {
    TelemetryRecord original{
        7,
        42,
        25.75,
        1013.20
    };

    const std::string encoded = encodeTelemetry(original);
    const TelemetryRecord decoded = decodeTelemetry(encoded);

    require(decoded.deviceId == original.deviceId, "device ID mismatch");
    require(
        decoded.sequenceNumber == original.sequenceNumber,
        "sequence mismatch"
    );

    require(
        std::abs(decoded.temperature - original.temperature) < 1e-9,
        "temperature mismatch"
    );

    require(
        std::abs(decoded.pressure - original.pressure) < 1e-9,
        "pressure mismatch"
    );
}

void testValidation() {
    TelemetryRecord invalid{
        0,
        1,
        20.0,
        1000.0
    };

    bool rejected = false;

    try {
        validateTelemetry(invalid);
    }
    catch (const std::exception&) {
        rejected = true;
    }

    require(rejected, "invalid device ID was accepted");
}

void testOrdering() {
    OrderedTelemetryBuffer buffer(1);

    TelemetryRecord first{1, 1, 20.0, 1000.0};
    TelemetryRecord third{1, 3, 22.0, 1002.0};
    TelemetryRecord second{1, 2, 21.0, 1001.0};

    auto result1 = buffer.receive(first);
    require(result1.size() == 1, "first packet was not delivered");

    auto result2 = buffer.receive(third);
    require(result2.empty(), "out-of-order packet should be buffered");

    auto result3 = buffer.receive(second);

    require(
        result3.size() == 2,
        "buffered packets were not released in order"
    );

    require(
        result3[0].sequenceNumber == 2 &&
        result3[1].sequenceNumber == 3,
        "incorrect delivery order"
    );
}

void testReliableSender() {
    ReliableSenderModel sender(
        std::chrono::milliseconds(10),
        2
    );

    ReliablePacket packet = sender.createPacket("critical");

    sender.markSent(packet);

    std::this_thread::sleep_for(std::chrono::milliseconds(15));

    auto retransmissions = sender.collectRetransmissions();

    require(
        retransmissions.size() == 1,
        "expected one retransmission"
    );

    require(
        sender.acknowledge(packet.sequenceNumber),
        "ACK should remove pending packet"
    );

    require(
        sender.outstanding() == 0,
        "packet should no longer be outstanding"
    );
}

void runTests() {
    std::cout << "\n"
              << std::string(78, '=')
              << "\nSELF-TESTS\n"
              << std::string(78, '=')
              << '\n';

    testTelemetryEncoding();
    testValidation();
    testOrdering();
    testReliableSender();

    std::cout << "All tests passed.\n";
}


// =============================================================================
// 15. CASE STUDY
// =============================================================================

void runCaseStudy() {
    std::cout << "\n"
              << std::string(78, '=')
              << "\nINDUSTRY-STYLE UDP TELEMETRY CASE STUDY\n"
              << std::string(78, '=')
              << '\n';

    /*
     * The server binds to an ephemeral local port. The client sends several
     * independent UDP datagrams to it.
     */
    UdpTelemetryServer server;

    std::cout
        << "Server listening on 127.0.0.1:"
        << server.port()
        << '\n';

    UdpTelemetryClient client(server.port());

    TelemetryProcessor processor;

    /*
     * Run the receive operation in a worker thread. This demonstrates that
     * the UDP socket can be integrated into a larger event-driven or threaded
     * architecture.
     */
    std::thread receiver([&server, &processor]() {
        for (int i = 0; i < 4; ++i) {
            try {
                server.receiveOne(processor);
            }
            catch (const std::exception& error) {
                std::cerr
                    << "Receive error: "
                    << error.what()
                    << '\n';
            }
        }
    });

    /*
     * Four datagrams represent sensor observations.
     *
     * Sequence numbers are deliberately sent out of order to demonstrate why
     * an application that needs ordered processing must implement ordering.
     */
    client.send(TelemetryRecord{100, 1, 23.1, 1008.4});
    client.send(TelemetryRecord{100, 3, 23.5, 1008.8});
    client.send(TelemetryRecord{100, 2, 23.3, 1008.6});

    // This is a duplicate of sequence 2.
    client.send(TelemetryRecord{100, 2, 23.3, 1008.6});

    receiver.join();

    const auto average = processor.store().averageTemperature();

    if (average.has_value()) {
        std::cout
            << "Average processed temperature: "
            << std::fixed
            << std::setprecision(2)
            << average.value()
            << '\n';
    }

    std::cout
        << "Processed records: "
        << processor.store().records().size()
        << '\n';
}


// =============================================================================
// 16. TRADE-OFF DISCUSSION
// =============================================================================

void explainTradeoffs() {
    std::cout << "\n"
              << std::string(78, '=')
              << "\nUDP DESIGN TRADE-OFFS\n"
              << std::string(78, '=')
              << '\n';

    std::cout
        << "Advantages:\n"
        << "  - No transport-level connection establishment.\n"
        << "  - Preserves datagram boundaries.\n"
        << "  - Small transport header.\n"
        << "  - Application can choose its own reliability strategy.\n"
        << "  - Suitable for multicast and broadcast scenarios.\n"
        << "  - Useful for latency-sensitive traffic when occasional loss is acceptable.\n"
        << '\n'
        << "Costs:\n"
        << "  - No built-in reliable delivery.\n"
        << "  - No built-in ordering.\n"
        << "  - No built-in duplicate suppression.\n"
        << "  - No built-in flow control.\n"
        << "  - No built-in congestion control.\n"
        << "  - Applications must defend against malformed or hostile traffic.\n"
        << "  - Building reliability above UDP can become complex.\n";
}


// =============================================================================
// 17. MAIN
// =============================================================================

int main() {
    try {
        std::cout
            << "UDP STUDY AND TELEMETRY GATEWAY\n"
            << "===============================\n";

        explainTradeoffs();

        runTests();

        std::cout << "\n"
                  << std::string(78, '=')
                  << "\nCHECKSUM EXAMPLE\n"
                  << std::string(78, '=')
                  << '\n';

        const std::string message = "UDP telemetry";

        std::cout
            << "Checksum for \""
            << message
            << "\": 0x"
            << std::hex
            << std::setw(4)
            << std::setfill('0')
            << internetChecksum(message)
            << std::dec
            << std::setfill(' ')
            << '\n';

        explainComplexity();

        runCaseStudy();

        std::cout << "\n"
                  << std::string(78, '=')
                  << "\nCASE STUDY COMPLETED\n"
                  << std::string(78, '=')
                  << '\n';

        return 0;
    }
    catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }
}
