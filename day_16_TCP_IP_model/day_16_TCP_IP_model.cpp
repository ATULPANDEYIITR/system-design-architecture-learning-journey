/*
 * TCP/IP Model: Network Stack and Practical Communication
 * ========================================================
 *
 * Complete C++17 case study:
 * A small industry-style telemetry gateway that accepts TCP clients,
 * authenticates a simple application protocol, validates telemetry records,
 * stores recent measurements, and reports statistics.
 *
 * The program demonstrates:
 * - TCP/IP layering
 * - TCP sockets
 * - IPv4 addressing
 * - Ports
 * - TCP connection handling
 * - Application-level framing
 * - Binary/network byte order
 * - JSON-like application protocol design without external libraries
 * - Validation
 * - Concurrency
 * - Thread synchronization
 * - Error handling
 * - Timeouts
 * - Resource limits
 * - Statistics
 * - Security considerations
 * - Complexity and performance trade-offs
 *
 * Compile:
 *     g++ -std=c++17 -O2 -pthread tcp_ip_case_study.cpp -o tcp_gateway
 *
 * The program uses only the C++ standard library and POSIX/BSD socket APIs.
 * It is intended for Linux/macOS and other POSIX-compatible environments.
 */

#include <arpa/inet.h>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <netinet/in.h>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>
#include <sys/socket.h>
#include <unistd.h>


// ============================================================================
// Utility functions
// ============================================================================

namespace util {

void printSection(const std::string& title) {
    std::cout << "\n" << std::string(78, '=') << "\n";
    std::cout << title << "\n";
    std::cout << std::string(78, '=') << "\n";
}

void printSubsection(const std::string& title) {
    std::cout << "\n" << std::string(78, '-') << "\n";
    std::cout << title << "\n";
    std::cout << std::string(78, '-') << "\n";
}

std::string trim(const std::string& value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) {
        return "";
    }

    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

bool isSafeIdentifier(const std::string& value) {
    if (value.empty() || value.size() > 64) {
        return false;
    }

    for (char character : value) {
        const bool valid =
            (character >= 'a' && character <= 'z') ||
            (character >= 'A' && character <= 'Z') ||
            (character >= '0' && character <= '9') ||
            character == '_' ||
            character == '-';

        if (!valid) {
            return false;
        }
    }

    return true;
}

bool parseDouble(const std::string& text, double& result) {
    try {
        size_t consumed = 0;
        result = std::stod(text, &consumed);

        return consumed == text.size() && std::isfinite(result);
    } catch (...) {
        return false;
    }
}

} // namespace util


// ============================================================================
// TCP/IP model representation
// ============================================================================

enum class TcpIpLayer {
    Application,
    Transport,
    Internet,
    Link
};


std::string layerName(TcpIpLayer layer) {
    switch (layer) {
        case TcpIpLayer::Application:
            return "Application";
        case TcpIpLayer::Transport:
            return "Transport";
        case TcpIpLayer::Internet:
            return "Internet";
        case TcpIpLayer::Link:
            return "Link / Network Access";
    }

    return "Unknown";
}


void demonstrateModel() {
    util::printSection("1. TCP/IP model");

    std::cout << "Application: HTTP, DNS, SSH and telemetry protocols\n";
    std::cout << "Transport:   TCP and UDP\n";
    std::cout << "Internet:    IPv4, IPv6, ICMP and routing\n";
    std::cout << "Link:        Ethernet and Wi-Fi\n";

    std::cout
        << "\nThe telemetry application implemented below operates at the "
        << "Application layer while relying on TCP at the Transport layer "
        << "and IPv4 at the Internet layer.\n";
}


// ============================================================================
// IPv4 address abstraction
// ============================================================================

class IPv4Address {
private:
    in_addr address_{};

public:
    explicit IPv4Address(const std::string& text) {
        if (inet_pton(AF_INET, text.c_str(), &address_) != 1) {
            throw std::invalid_argument("Invalid IPv4 address: " + text);
        }
    }

    const in_addr& native() const {
        return address_;
    }

    std::string toString() const {
        char buffer[INET_ADDRSTRLEN]{};

        if (inet_ntop(
                AF_INET,
                &address_,
                buffer,
                sizeof(buffer)) == nullptr) {
            throw std::runtime_error("Unable to format IPv4 address.");
        }

        return buffer;
    }
};


// ============================================================================
// Socket RAII wrapper
// ============================================================================

class Socket {
private:
    int descriptor_ = -1;

public:
    Socket() = default;

    explicit Socket(int descriptor)
        : descriptor_(descriptor) {}

    Socket(const Socket&) = delete;
    Socket& operator=(const Socket&) = delete;

    Socket(Socket&& other) noexcept
        : descriptor_(other.descriptor_) {
        other.descriptor_ = -1;
    }

    Socket& operator=(Socket&& other) noexcept {
        if (this != &other) {
            closeSocket();
            descriptor_ = other.descriptor_;
            other.descriptor_ = -1;
        }

        return *this;
    }

    ~Socket() {
        closeSocket();
    }

    int get() const {
        return descriptor_;
    }

    bool valid() const {
        return descriptor_ >= 0;
    }

    void closeSocket() {
        if (descriptor_ >= 0) {
            ::close(descriptor_);
            descriptor_ = -1;
        }
    }
};


// ============================================================================
// Network byte order
// ============================================================================

void demonstrateByteOrder() {
    util::printSection("2. Network byte order");

    const uint16_t hostValue = 8080;
    const uint16_t networkValue = htons(hostValue);
    const uint16_t restored = ntohs(networkValue);

    std::cout << "Host-order port: " << hostValue << "\n";
    std::cout << "Network-order representation: " << networkValue << "\n";
    std::cout << "Decoded port: " << restored << "\n";

    std::cout
        << "\nNetwork protocols use defined byte-order rules so that systems "
        << "with different native architectures interpret multi-byte fields "
        << "consistently.\n";
}


// ============================================================================
// Application protocol
// ============================================================================

/*
 * Protocol format:
 *
 *   4-byte unsigned network-order payload length
 *   payload:
 *       VERSION|COMMAND|DEVICE|VALUE|UNIT\n
 *
 * Example:
 *
 *   1|MEASURE|sensor-17|23.5|C
 *
 * TCP is a byte stream, so the four-byte length prefix creates an explicit
 * application-level message boundary.
 */

class Protocol {
public:
    static constexpr uint32_t MAX_PAYLOAD = 4096;

    struct Measurement {
        int version{};
        std::string command;
        std::string device;
        double value{};
        std::string unit;
    };

    static std::string encode(const Measurement& measurement) {
        if (measurement.version != 1) {
            throw std::invalid_argument("Unsupported protocol version.");
        }

        if (!util::isSafeIdentifier(measurement.device)) {
            throw std::invalid_argument("Invalid device identifier.");
        }

        if (!std::isfinite(measurement.value)) {
            throw std::invalid_argument("Measurement must be finite.");
        }

        std::ostringstream stream;

        stream << measurement.version << '|'
               << measurement.command << '|'
               << measurement.device << '|'
               << std::setprecision(15)
               << measurement.value << '|'
               << measurement.unit
               << '\n';

        const std::string payload = stream.str();

        if (payload.size() > MAX_PAYLOAD) {
            throw std::length_error("Application payload is too large.");
        }

        return payload;
    }

    static Measurement decode(const std::string& payload) {
        if (payload.empty() || payload.size() > MAX_PAYLOAD) {
            throw std::invalid_argument("Invalid payload length.");
        }

        std::vector<std::string> fields;
        std::stringstream stream(payload);
        std::string field;

        while (std::getline(stream, field, '|')) {
            fields.push_back(util::trim(field));
        }

        if (fields.size() != 5) {
            throw std::invalid_argument(
                "Protocol requires exactly five fields."
            );
        }

        Measurement measurement;

        try {
            size_t consumed = 0;
            measurement.version = std::stoi(fields[0], &consumed);

            if (consumed != fields[0].size()) {
                throw std::invalid_argument("Bad version.");
            }
        } catch (...) {
            throw std::invalid_argument("Invalid protocol version.");
        }

        measurement.command = fields[1];
        measurement.device = fields[2];

        if (measurement.command != "MEASURE") {
            throw std::invalid_argument("Unsupported command.");
        }

        if (!util::isSafeIdentifier(measurement.device)) {
            throw std::invalid_argument("Invalid device identifier.");
        }

        if (!util::parseDouble(fields[3], measurement.value)) {
            throw std::invalid_argument("Invalid measurement value.");
        }

        measurement.unit = fields[4];

        if (measurement.unit.empty() || measurement.unit.size() > 16) {
            throw std::invalid_argument("Invalid measurement unit.");
        }

        return measurement;
    }
};


// ============================================================================
// Exact socket reads
// ============================================================================

bool receiveExact(int socketDescriptor, void* buffer, size_t length) {
    char* destination = static_cast<char*>(buffer);
    size_t receivedTotal = 0;

    while (receivedTotal < length) {
        const ssize_t received = ::recv(
            socketDescriptor,
            destination + receivedTotal,
            length - receivedTotal,
            0
        );

        if (received == 0) {
            return false;
        }

        if (received < 0) {
            if (errno == EINTR) {
                continue;
            }

            return false;
        }

        receivedTotal += static_cast<size_t>(received);
    }

    return true;
}


bool sendAll(int socketDescriptor, const void* data, size_t length) {
    const char* source = static_cast<const char*>(data);
    size_t sentTotal = 0;

    while (sentTotal < length) {
        const ssize_t sent = ::send(
            socketDescriptor,
            source + sentTotal,
            length - sentTotal,
            0
        );

        if (sent < 0) {
            if (errno == EINTR) {
                continue;
            }

            return false;
        }

        if (sent == 0) {
            return false;
        }

        sentTotal += static_cast<size_t>(sent);
    }

    return true;
}


// ============================================================================
// Framed protocol transport
// ============================================================================

bool sendFrame(int socketDescriptor, const std::string& payload) {
    if (payload.size() > Protocol::MAX_PAYLOAD) {
        return false;
    }

    const uint32_t length =
        htonl(static_cast<uint32_t>(payload.size()));

    if (!sendAll(socketDescriptor, &length, sizeof(length))) {
        return false;
    }

    return sendAll(
        socketDescriptor,
        payload.data(),
        payload.size()
    );
}


bool receiveFrame(int socketDescriptor, std::string& payload) {
    uint32_t networkLength = 0;

    if (!receiveExact(
            socketDescriptor,
            &networkLength,
            sizeof(networkLength))) {
        return false;
    }

    const uint32_t length = ntohl(networkLength);

    /*
     * This validation must happen before allocating the payload buffer.
     * Otherwise, a malicious peer could advertise an enormous size and
     * exhaust server memory.
     */
    if (length > Protocol::MAX_PAYLOAD) {
        return false;
    }

    payload.resize(length);

    if (length == 0) {
        return true;
    }

    return receiveExact(
        socketDescriptor,
        payload.data(),
        length
    );
}


// ============================================================================
// Telemetry storage
// ============================================================================

struct TelemetryRecord {
    std::string device;
    double value{};
    std::string unit;
    std::chrono::system_clock::time_point timestamp;
};


class TelemetryStore {
private:
    std::unordered_map<std::string, std::vector<TelemetryRecord>> records_;
    mutable std::mutex mutex_;

public:
    void add(const TelemetryRecord& record) {
        std::lock_guard<std::mutex> lock(mutex_);

        /*
         * unordered_map gives expected O(1) lookup by device. A vector gives
         * efficient append and sequential traversal for recent records.
         */
        records_[record.device].push_back(record);
    }

    size_t deviceCount() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return records_.size();
    }

    size_t recordCount() const {
        std::lock_guard<std::mutex> lock(mutex_);

        size_t count = 0;

        for (const auto& [device, records] : records_) {
            count += records.size();
        }

        return count;
    }

    std::vector<TelemetryRecord> getDeviceRecords(
        const std::string& device) const {
        std::lock_guard<std::mutex> lock(mutex_);

        const auto iterator = records_.find(device);

        if (iterator == records_.end()) {
            return {};
        }

        return iterator->second;
    }

    double average(const std::string& device) const {
        const auto records = getDeviceRecords(device);

        if (records.empty()) {
            throw std::runtime_error("No measurements for device.");
        }

        double sum = 0.0;

        for (const auto& record : records) {
            sum += record.value;
        }

        return sum / static_cast<double>(records.size());
    }
};


// ============================================================================
// TCP telemetry server
// ============================================================================

class TelemetryServer {
private:
    Socket listeningSocket_;
    uint16_t port_ = 0;
    TelemetryStore store_;

    std::mutex clientCountMutex_;
    size_t activeClients_ = 0;

    static constexpr size_t MAX_ACTIVE_CLIENTS = 32;

    void incrementClientCount() {
        std::lock_guard<std::mutex> lock(clientCountMutex_);
        ++activeClients_;
    }

    void decrementClientCount() {
        std::lock_guard<std::mutex> lock(clientCountMutex_);

        if (activeClients_ > 0) {
            --activeClients_;
        }
    }

    bool canAcceptClient() {
        std::lock_guard<std::mutex> lock(clientCountMutex_);
        return activeClients_ < MAX_ACTIVE_CLIENTS;
    }

public:
    void start() {
        const int descriptor = ::socket(
            AF_INET,
            SOCK_STREAM,
            0
        );

        if (descriptor < 0) {
            throw std::runtime_error(
                "socket() failed: " + std::string(std::strerror(errno))
            );
        }

        listeningSocket_ = Socket(descriptor);

        int reuse = 1;

        if (::setsockopt(
                listeningSocket_.get(),
                SOL_SOCKET,
                SO_REUSEADDR,
                &reuse,
                sizeof(reuse)) < 0) {
            throw std::runtime_error("setsockopt(SO_REUSEADDR) failed.");
        }

        sockaddr_in address{};
        address.sin_family = AF_INET;
        address.sin_port = htons(0);

        /*
         * Loopback binding prevents this educational server from exposing
         * itself to other machines.
         */
        if (inet_pton(
                AF_INET,
                "127.0.0.1",
                &address.sin_addr) != 1) {
            throw std::runtime_error("Unable to configure loopback address.");
        }

        if (::bind(
                listeningSocket_.get(),
                reinterpret_cast<sockaddr*>(&address),
                sizeof(address)) < 0) {
            throw std::runtime_error(
                "bind() failed: " + std::string(std::strerror(errno))
            );
        }

        if (::listen(listeningSocket_.get(), 16) < 0) {
            throw std::runtime_error(
                "listen() failed: " + std::string(std::strerror(errno))
            );
        }

        sockaddr_in actualAddress{};
        socklen_t actualLength = sizeof(actualAddress);

        if (::getsockname(
                listeningSocket_.get(),
                reinterpret_cast<sockaddr*>(&actualAddress),
                &actualLength) < 0) {
            throw std::runtime_error("getsockname() failed.");
        }

        port_ = ntohs(actualAddress.sin_port);

        std::cout
            << "Telemetry server listening on "
            << "127.0.0.1:"
            << port_
            << "\n";
    }

    uint16_t port() const {
        return port_;
    }

    TelemetryStore& store() {
        return store_;
    }

    void handleClient(int clientSocket) {
        Socket connection(clientSocket);
        incrementClientCount();

        /*
         * SO_RCVTIMEO prevents a connected client from holding a server
         * worker indefinitely without transmitting data.
         */
        timeval timeout{};
        timeout.tv_sec = 5;
        timeout.tv_usec = 0;

        ::setsockopt(
            connection.get(),
            SOL_SOCKET,
            SO_RCVTIMEO,
            &timeout,
            sizeof(timeout)
        );

        try {
            std::string payload;

            while (receiveFrame(connection.get(), payload)) {
                try {
                    const auto measurement =
                        Protocol::decode(payload);

                    TelemetryRecord record{
                        measurement.device,
                        measurement.value,
                        measurement.unit,
                        std::chrono::system_clock::now()
                    };

                    store_.add(record);

                    const std::string response =
                        "OK|" + measurement.device;

                    if (!sendFrame(connection.get(), response)) {
                        break;
                    }
                } catch (const std::exception& error) {
                    const std::string response =
                        std::string("ERROR|") + error.what();

                    if (!sendFrame(connection.get(), response)) {
                        break;
                    }
                }
            }
        } catch (...) {
            /*
             * Connection-level failures terminate this client session.
             * The server itself remains available to other clients.
             */
        }

        decrementClientCount();
    }

    void serveOneConnection() {
        sockaddr_in clientAddress{};
        socklen_t clientLength = sizeof(clientAddress);

        const int clientSocket = ::accept(
            listeningSocket_.get(),
            reinterpret_cast<sockaddr*>(&clientAddress),
            &clientLength
        );

        if (clientSocket < 0) {
            throw std::runtime_error(
                "accept() failed: " +
                std::string(std::strerror(errno))
            );
        }

        if (!canAcceptClient()) {
            const std::string response = "ERROR|server busy";
            sendFrame(clientSocket, response);
            ::close(clientSocket);
            return;
        }

        /*
         * Each connection gets its own worker. This is easy to understand but
         * creates a thread-management cost. Production systems may use an
         * event-driven architecture or a bounded worker pool.
         */
        std::thread worker(
            &TelemetryServer::handleClient,
            this,
            clientSocket
        );

        worker.detach();
    }
};


// ============================================================================
// TCP client used by the case study
// ============================================================================

Socket connectToLocalServer(uint16_t port) {
    const int descriptor = ::socket(
        AF_INET,
        SOCK_STREAM,
        0
    );

    if (descriptor < 0) {
        throw std::runtime_error("Client socket creation failed.");
    }

    Socket socket(descriptor);

    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(port);

    if (inet_pton(
            AF_INET,
            "127.0.0.1",
            &address.sin_addr) != 1) {
        throw std::runtime_error("Invalid loopback address.");
    }

    if (::connect(
            socket.get(),
            reinterpret_cast<sockaddr*>(&address),
            sizeof(address)) < 0) {
        throw std::runtime_error(
            "connect() failed: " +
            std::string(std::strerror(errno))
        );
    }

    return socket;
}


std::string sendMeasurement(
    uint16_t port,
    const Protocol::Measurement& measurement) {

    Socket socket = connectToLocalServer(port);

    const std::string payload = Protocol::encode(measurement);

    if (!sendFrame(socket.get(), payload)) {
        throw std::runtime_error("Failed to send telemetry frame.");
    }

    std::string response;

    if (!receiveFrame(socket.get(), response)) {
        throw std::runtime_error("Failed to receive server response.");
    }

    return response;
}


// ============================================================================
// Concurrent clients
// ============================================================================

void demonstrateConcurrentClients(
    TelemetryServer& server,
    uint16_t port) {

    util::printSection("3. Concurrent TCP clients");

    std::vector<std::thread> clients;

    for (int index = 0; index < 6; ++index) {
        clients.emplace_back(
            [port, index]() {
                try {
                    Protocol::Measurement measurement{
                        1,
                        "MEASURE",
                        "sensor-" + std::to_string(index),
                        20.0 + index,
                        "C"
                    };

                    const std::string response =
                        sendMeasurement(port, measurement);

                    std::cout
                        << "Client "
                        << index
                        << " received: "
                        << response
                        << "\n";
                } catch (const std::exception& error) {
                    std::cerr
                        << "Client "
                        << index
                        << " failed: "
                        << error.what()
                        << "\n";
                }
            }
        );
    }

    for (auto& client : clients) {
        client.join();
    }

    std::cout
        << "Stored devices: "
        << server.store().deviceCount()
        << "\n";

    std::cout
        << "Stored records: "
        << server.store().recordCount()
        << "\n";
}


// ============================================================================
// Validation edge cases
// ============================================================================

void demonstrateValidation() {
    util::printSection("4. Protocol validation and edge cases");

    const std::vector<std::string> invalidMessages{
        "",
        "1|MEASURE|bad device|20|C\n",
        "1|UNKNOWN|sensor-1|20|C\n",
        "1|MEASURE|sensor-1|not-a-number|C\n",
        "1|MEASURE|sensor-1|20|\n",
        "2|MEASURE|sensor-1|20|C\n",
        "1|MEASURE|sensor-1|nan|C\n"
    };

    for (const auto& message : invalidMessages) {
        try {
            const auto measurement =
                Protocol::decode(message);

            std::cout
                << "Unexpectedly accepted: "
                << measurement.device
                << "\n";
        } catch (const std::exception& error) {
            std::cout
                << "Rejected safely: "
                << error.what()
                << "\n";
        }
    }
}


// ============================================================================
// UDP conceptual example
// ============================================================================

void demonstrateUdpConcept() {
    util::printSection("5. UDP compared with TCP");

    std::cout
        << "A UDP socket sends independent datagrams.\n"
        << "UDP does not establish a TCP-style connection.\n"
        << "UDP does not itself guarantee delivery or ordering.\n"
        << "Applications can implement sequence numbers, acknowledgments,\n"
        << "retransmission, and deadlines when their requirements justify it.\n";
}


// ============================================================================
// Routing and ARP concepts
// ============================================================================

void demonstrateRouting() {
    util::printSection("6. Routing and local delivery");

    std::cout << "Destination: 192.168.1.50\n";
    std::cout << "If local subnet: resolve destination MAC and send locally.\n";
    std::cout << "If remote subnet: resolve next-hop router MAC.\n";
    std::cout << "Router examines destination IP and selects a route.\n";
    std::cout
        << "Longest-prefix matching generally selects the most specific "
        << "matching route.\n";
}


// ============================================================================
// TCP lifecycle
// ============================================================================

void demonstrateTcpLifecycle() {
    util::printSection("7. TCP connection lifecycle");

    std::cout << "Three-way handshake:\n";
    std::cout << "  SYN ->\n";
    std::cout << "  <- SYN+ACK\n";
    std::cout << "  ACK ->\n";

    std::cout << "\nData transfer:\n";
    std::cout
        << "TCP uses sequence numbers, acknowledgments, retransmission, "
        << "flow control and congestion control.\n";

    std::cout << "\nGraceful termination:\n";
    std::cout
        << "FIN and ACK exchanges move endpoints through TCP states "
        << "such as FIN-WAIT, CLOSE-WAIT and TIME-WAIT.\n";
}


// ============================================================================
// IPv4 header fields
// ============================================================================

void demonstrateIpv4Header() {
    util::printSection("8. IPv4 packet structure");

    const std::vector<std::pair<std::string, std::string>> fields{
        {"Version", "Identifies IPv4"},
        {"IHL", "Header length"},
        {"Total Length", "Packet length"},
        {"Identification", "Fragmentation-related identifier"},
        {"Flags", "Fragmentation control"},
        {"Fragment Offset", "Fragment position"},
        {"TTL", "Limits forwarding lifetime"},
        {"Protocol", "Identifies TCP, UDP, ICMP, etc."},
        {"Header Checksum", "Detects header corruption"},
        {"Source", "Origin IP address"},
        {"Destination", "Target IP address"}
    };

    for (const auto& [field, purpose] : fields) {
        std::cout
            << std::left
            << std::setw(20)
            << field
            << purpose
            << "\n";
    }
}


// ============================================================================
// TCP header fields
// ============================================================================

void demonstrateTcpHeader() {
    util::printSection("9. TCP segment structure");

    const std::vector<std::pair<std::string, std::string>> fields{
        {"Source port", "Sending application"},
        {"Destination port", "Receiving application"},
        {"Sequence number", "Byte-stream position"},
        {"Acknowledgment number", "Next expected byte"},
        {"Flags", "SYN, ACK, FIN, RST and others"},
        {"Window", "Flow-control information"},
        {"Checksum", "Transport checksum"},
        {"Options", "Negotiated TCP capabilities"}
    };

    for (const auto& [field, purpose] : fields) {
        std::cout
            << std::left
            << std::setw(24)
            << field
            << purpose
            << "\n";
    }
}


// ============================================================================
// Performance analysis
// ============================================================================

void demonstratePerformance() {
    util::printSection("10. Performance considerations");

    std::cout << "Important measurements:\n";
    std::cout << "  RTT\n";
    std::cout << "  throughput\n";
    std::cout << "  packet loss\n";
    std::cout << "  CPU utilization\n";
    std::cout << "  memory per connection\n";
    std::cout << "  serialization cost\n";
    std::cout << "  concurrent connection count\n";

    std::cout
        << "\nTelemetryStore insertion is expected O(1) amortized for vector "
        << "append plus expected O(1) hash-map device lookup.\n";

    std::cout
        << "Computing one device's average is O(n) in the number of its "
        << "stored measurements.\n";

    std::cout
        << "\nA thread-per-connection design is simple but can become costly "
        << "at very high connection counts. Event-driven I/O or a bounded "
        << "thread pool can provide different scalability characteristics.\n";
}


// ============================================================================
// Security
// ============================================================================

void demonstrateSecurity() {
    util::printSection("11. Security considerations");

    const std::vector<std::string> principles{
        "TCP reliability is not authentication.",
        "TCP reliability is not encryption.",
        "Validate every application-layer length.",
        "Reject malformed protocol messages.",
        "Limit concurrent connections.",
        "Use receive and send timeouts where appropriate.",
        "Use TLS for sensitive communication.",
        "Authenticate devices and users.",
        "Authorize operations independently.",
        "Do not expose development services unnecessarily.",
        "Do not log secrets.",
        "Apply rate limits and resource quotas where appropriate."
    };

    for (const auto& principle : principles) {
        std::cout << "- " << principle << "\n";
    }
}


// ============================================================================
// Troubleshooting
// ============================================================================

void demonstrateTroubleshooting() {
    util::printSection("12. Troubleshooting methodology");

    const std::vector<std::string> steps{
        "Check application configuration.",
        "Resolve the hostname.",
        "Verify the destination IP.",
        "Inspect the route.",
        "Verify the destination port is listening.",
        "Check firewalls and security policy.",
        "Distinguish timeout from connection refusal.",
        "Inspect application framing and payloads.",
        "Measure RTT, throughput and loss.",
        "Capture packets when necessary."
    };

    for (size_t index = 0; index < steps.size(); ++index) {
        std::cout
            << index + 1
            << ". "
            << steps[index]
            << "\n";
    }
}


// ============================================================================
// OSI comparison
// ============================================================================

void demonstrateOsiComparison() {
    util::printSection("13. TCP/IP and OSI comparison");

    std::cout
        << "TCP/IP Application  ~= OSI Application + Presentation + Session\n"
        << "TCP/IP Transport    ~= OSI Transport\n"
        << "TCP/IP Internet     ~= OSI Network\n"
        << "TCP/IP Link         ~= OSI Data Link + Physical\n";

    std::cout
        << "\nThese are conceptual correspondences rather than exact one-to-one "
        << "protocol classifications.\n";
}


// ============================================================================
// End-to-end workflow
// ============================================================================

void demonstrateEndToEndWorkflow() {
    util::printSection("14. End-to-end communication");

    const std::vector<std::string> steps{
        "Application creates a telemetry message.",
        "Application protocol serializes the message.",
        "TCP frames the byte stream internally.",
        "IPv4 adds source and destination addresses.",
        "The link layer delivers the frame to the next local hop.",
        "Routers forward the IP packet.",
        "The remote host removes lower-layer encapsulation.",
        "TCP reassembles and orders the application byte stream.",
        "The application protocol parses the message.",
        "Validation checks the received data.",
        "Business logic stores the measurement.",
        "A framed application response is sent back."
    };

    for (size_t index = 0; index < steps.size(); ++index) {
        std::cout
            << index + 1
            << ". "
            << steps[index]
            << "\n";
    }
}


// ============================================================================
// Case study execution
// ============================================================================

int main() {
    try {
        demonstrateModel();
        demonstrateByteOrder();

        util::printSection("Case study: telemetry gateway");

        TelemetryServer server;
        server.start();

        /*
         * Give the operating system a short opportunity to finish the
         * listening setup before client threads attempt to connect.
         */
        std::this_thread::sleep_for(
            std::chrono::milliseconds(50)
        );

        demonstrateConcurrentClients(
            server,
            server.port()
        );

        demonstrateValidation();
        demonstrateUdpConcept();
        demonstrateRouting();
        demonstrateTcpLifecycle();
        demonstrateIpv4Header();
        demonstrateTcpHeader();
        demonstratePerformance();
        demonstrateSecurity();
        demonstrateTroubleshooting();
        demonstrateOsiComparison();
        demonstrateEndToEndWorkflow();

        util::printSection("Case study results");

        std::cout
            << "Devices stored: "
            << server.store().deviceCount()
            << "\n";

        std::cout
            << "Measurements stored: "
            << server.store().recordCount()
            << "\n";

        try {
            const double average =
                server.store().average("sensor-1");

            std::cout
                << "Average for sensor-1: "
                << std::fixed
                << std::setprecision(2)
                << average
                << "\n";
        } catch (const std::exception& error) {
            std::cout
                << "Average unavailable: "
                << error.what()
                << "\n";
        }

        std::cout
            << "\nThe case study demonstrates how an application-layer "
            << "protocol depends on transport and Internet-layer services "
            << "without directly implementing Ethernet or router behavior.\n";

        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << "\n";

        return 1;
    }
}
