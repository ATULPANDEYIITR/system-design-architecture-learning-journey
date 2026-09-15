/*
 * OSI Model Case Study
 * ====================
 *
 * Industry-style case study:
 * A simplified enterprise web service network.
 *
 * Scenario:
 *   A client in a corporate LAN accesses an HTTPS application hosted in a
 *   different network. The simulation demonstrates how the request moves
 *   through the OSI layers, how a switch performs MAC learning, how a router
 *   performs longest-prefix routing, how TCP establishes a connection, and
 *   how the server receives the application request.
 *
 * Requirements:
 *   C++17 or later
 *
 * This program intentionally models networking concepts without requiring
 * external networking libraries or administrator privileges.
 */

#include <algorithm>
#include <array>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using namespace std;


// =============================================================================
// 1. BASIC ADDRESS TYPES
// =============================================================================

class MACAddress {
private:
    string value;

public:
    explicit MACAddress(string address) : value(std::move(address)) {
        if (value.size() != 17) {
            throw invalid_argument("MAC address must contain 17 characters.");
        }

        for (size_t i = 0; i < value.size(); ++i) {
            if ((i + 1) % 3 == 0) {
                if (value[i] != ':') {
                    throw invalid_argument("Invalid MAC separator.");
                }
            }
        }
    }

    const string& str() const {
        return value;
    }

    bool operator<(const MACAddress& other) const {
        return value < other.value;
    }

    bool operator==(const MACAddress& other) const {
        return value == other.value;
    }
};


class IPv4Address {
private:
    array<int, 4> octets{};

public:
    explicit IPv4Address(const string& address) {
        stringstream stream(address);
        string part;
        int index = 0;

        while (getline(stream, part, '.')) {
            if (index >= 4 || part.empty()) {
                throw invalid_argument("Invalid IPv4 address.");
            }

            int value = stoi(part);

            if (value < 0 || value > 255) {
                throw invalid_argument("IPv4 octet outside 0-255.");
            }

            octets[index++] = value;
        }

        if (index != 4) {
            throw invalid_argument("IPv4 address must contain four octets.");
        }
    }

    uint32_t toInteger() const {
        return
            (static_cast<uint32_t>(octets[0]) << 24) |
            (static_cast<uint32_t>(octets[1]) << 16) |
            (static_cast<uint32_t>(octets[2]) << 8) |
            static_cast<uint32_t>(octets[3]);
    }

    string str() const {
        return to_string(octets[0]) + "." +
               to_string(octets[1]) + "." +
               to_string(octets[2]) + "." +
               to_string(octets[3]);
    }
};


// =============================================================================
// 2. LAYER 7: APPLICATION
// =============================================================================

class HttpRequest {
private:
    string method;
    string path;
    map<string, string> headers;
    string body;

public:
    HttpRequest(
        string requestMethod,
        string requestPath,
        map<string, string> requestHeaders,
        string requestBody = ""
    )
        : method(std::move(requestMethod)),
          path(std::move(requestPath)),
          headers(std::move(requestHeaders)),
          body(std::move(requestBody)) {}

    string serialize() const {
        ostringstream output;

        output << method << " " << path << " HTTP/1.1\r\n";

        for (const auto& [key, value] : headers) {
            output << key << ": " << value << "\r\n";
        }

        output << "\r\n";
        output << body;

        return output.str();
    }
};


// =============================================================================
// 3. LAYER 6: PRESENTATION
// =============================================================================

class PresentationCodec {
public:
    static string encodeUTF8LikeRepresentation(const string& input) {
        /*
         * The C++ string stores bytes. This case study keeps the operation
         * intentionally simple and treats the input as already UTF-8 bytes.
         */
        return input;
    }

    static string addTLSMarker(const string& input) {
        /*
         * This is not actual TLS cryptography. It demonstrates the conceptual
         * position of a representation/security transformation between the
         * application and transport layers.
         */
        return "[TLS-PROTECTED]" + input;
    }
};


// =============================================================================
// 4. LAYER 5: SESSION
// =============================================================================

enum class SessionState {
    New,
    Established,
    Closed
};


class Session {
private:
    int id;
    SessionState state = SessionState::New;

public:
    explicit Session(int sessionId) : id(sessionId) {}

    void establish() {
        if (state != SessionState::New) {
            throw logic_error("Session cannot be established.");
        }

        state = SessionState::Established;
    }

    void close() {
        state = SessionState::Closed;
    }

    int getId() const {
        return id;
    }

    SessionState getState() const {
        return state;
    }
};


// =============================================================================
// 5. LAYER 4: TRANSPORT
// =============================================================================

enum class TCPFlag {
    SYN,
    SYN_ACK,
    ACK,
    FIN
};


string tcpFlagName(TCPFlag flag) {
    switch (flag) {
        case TCPFlag::SYN:
            return "SYN";
        case TCPFlag::SYN_ACK:
            return "SYN-ACK";
        case TCPFlag::ACK:
            return "ACK";
        case TCPFlag::FIN:
            return "FIN";
    }

    return "UNKNOWN";
}


class TCPSegment {
private:
    uint16_t sourcePort;
    uint16_t destinationPort;
    uint32_t sequenceNumber;
    uint32_t acknowledgementNumber;
    TCPFlag flag;
    string payload;

public:
    TCPSegment(
        uint16_t source,
        uint16_t destination,
        uint32_t sequence,
        uint32_t acknowledgement,
        TCPFlag tcpFlag,
        string segmentPayload = ""
    )
        : sourcePort(source),
          destinationPort(destination),
          sequenceNumber(sequence),
          acknowledgementNumber(acknowledgement),
          flag(tcpFlag),
          payload(std::move(segmentPayload)) {}

    uint16_t getSourcePort() const {
        return sourcePort;
    }

    uint16_t getDestinationPort() const {
        return destinationPort;
    }

    uint32_t getSequenceNumber() const {
        return sequenceNumber;
    }

    uint32_t getAcknowledgementNumber() const {
        return acknowledgementNumber;
    }

    TCPFlag getFlag() const {
        return flag;
    }

    const string& getPayload() const {
        return payload;
    }
};


// =============================================================================
// 6. LAYER 3: IP PACKET
// =============================================================================

class IPPacket {
private:
    IPv4Address source;
    IPv4Address destination;
    uint8_t ttl;
    string payload;

public:
    IPPacket(
        IPv4Address sourceAddress,
        IPv4Address destinationAddress,
        string packetPayload,
        uint8_t initialTTL = 64
    )
        : source(std::move(sourceAddress)),
          destination(std::move(destinationAddress)),
          ttl(initialTTL),
          payload(std::move(packetPayload)) {}

    void decrementTTL() {
        if (ttl == 0) {
            throw runtime_error("TTL already expired.");
        }

        --ttl;

        if (ttl == 0) {
            throw runtime_error("Packet TTL expired.");
        }
    }

    const IPv4Address& getSource() const {
        return source;
    }

    const IPv4Address& getDestination() const {
        return destination;
    }

    uint8_t getTTL() const {
        return ttl;
    }

    const string& getPayload() const {
        return payload;
    }
};


// =============================================================================
// 7. LAYER 2: ETHERNET FRAME
// =============================================================================

class EthernetFrame {
private:
    MACAddress source;
    MACAddress destination;
    string payload;

public:
    EthernetFrame(
        MACAddress sourceMAC,
        MACAddress destinationMAC,
        string framePayload
    )
        : source(std::move(sourceMAC)),
          destination(std::move(destinationMAC)),
          payload(std::move(framePayload)) {}

    const MACAddress& getSource() const {
        return source;
    }

    const MACAddress& getDestination() const {
        return destination;
    }

    const string& getPayload() const {
        return payload;
    }
};


// =============================================================================
// 8. LAYER 2 SWITCH
// =============================================================================

class EthernetSwitch {
private:
    map<MACAddress, string> forwardingTable;

public:
    void learn(const MACAddress& sourceMAC, const string& ingressPort) {
        /*
         * Switch learning:
         * When a frame arrives, the switch learns that the source MAC is
         * reachable through the port on which the frame arrived.
         */
        forwardingTable[sourceMAC] = ingressPort;
    }

    optional<string> lookup(const MACAddress& destinationMAC) const {
        auto iterator = forwardingTable.find(destinationMAC);

        if (iterator == forwardingTable.end()) {
            return nullopt;
        }

        return iterator->second;
    }

    void printTable() const {
        cout << "\nSwitch forwarding table:\n";

        for (const auto& [mac, port] : forwardingTable) {
            cout << "  " << mac.str() << " -> " << port << "\n";
        }
    }
};


// =============================================================================
// 9. LAYER 3 ROUTING
// =============================================================================

struct Route {
    uint32_t network;
    uint8_t prefixLength;
    string nextHop;
};


class Router {
private:
    vector<Route> routes;

    static uint32_t mask(uint8_t prefixLength) {
        if (prefixLength == 0) {
            return 0;
        }

        return 0xFFFFFFFFu << (32 - prefixLength);
    }

    static bool matches(
        uint32_t destination,
        const Route& route
    ) {
        uint32_t routeMask = mask(route.prefixLength);

        return (destination & routeMask) ==
               (route.network & routeMask);
    }

public:
    void addRoute(
        const IPv4Address& networkAddress,
        uint8_t prefixLength,
        const string& nextHop
    ) {
        if (prefixLength > 32) {
            throw invalid_argument("Prefix length cannot exceed 32.");
        }

        routes.push_back({
            networkAddress.toInteger(),
            prefixLength,
            nextHop
        });
    }

    optional<Route> lookup(const IPv4Address& destination) const {
        optional<Route> best;

        for (const auto& route : routes) {
            if (!matches(destination.toInteger(), route)) {
                continue;
            }

            if (!best.has_value() ||
                route.prefixLength > best->prefixLength) {
                best = route;
            }
        }

        /*
         * This implements longest-prefix match.
         * A more specific route wins over a broader route.
         */
        return best;
    }
};


// =============================================================================
// 10. ARP TABLE
// =============================================================================

class ARPTable {
private:
    map<string, MACAddress> entries;

public:
    void learn(
        const IPv4Address& ip,
        const MACAddress& mac
    ) {
        entries[ip.str()] = mac;
    }

    optional<MACAddress> resolve(const IPv4Address& ip) const {
        auto iterator = entries.find(ip.str());

        if (iterator == entries.end()) {
            return nullopt;
        }

        return iterator->second;
    }
};


// =============================================================================
// 11. NETWORK HOST
// =============================================================================

class Host {
private:
    string hostname;
    IPv4Address ip;
    MACAddress mac;

public:
    Host(
        string name,
        IPv4Address address,
        MACAddress hardwareAddress
    )
        : hostname(std::move(name)),
          ip(std::move(address)),
          mac(std::move(hardwareAddress)) {}

    const string& name() const {
        return hostname;
    }

    const IPv4Address& address() const {
        return ip;
    }

    const MACAddress& hardwareAddress() const {
        return mac;
    }
};


// =============================================================================
// 12. PHYSICAL LAYER REPRESENTATION
// =============================================================================

string byteToBits(unsigned char value) {
    string result;

    for (int bit = 7; bit >= 0; --bit) {
        result += ((value >> bit) & 1) ? '1' : '0';
    }

    return result;
}


string bytesToBits(const string& data) {
    string result;

    for (unsigned char byte : data) {
        result += byteToBits(byte);
    }

    return result;
}


// =============================================================================
// 13. APPLICATION REQUEST PROCESSOR
// =============================================================================

class WebServer {
private:
    uint16_t listeningPort;

public:
    explicit WebServer(uint16_t port)
        : listeningPort(port) {}

    string process(const TCPSegment& segment) const {
        if (segment.getDestinationPort() != listeningPort) {
            throw runtime_error("Segment sent to a port where this server is not listening.");
        }

        if (segment.getFlag() != TCPFlag::ACK) {
            throw runtime_error("Application payload requires an established TCP session.");
        }

        return
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/plain\r\n"
            "\r\n"
            "OSI case study server response";
    }
};


// =============================================================================
// 14. PACKET CAPTURE RECORD
// =============================================================================

struct PacketCaptureRecord {
    int layer;
    string description;
};


class PacketCapture {
private:
    vector<PacketCaptureRecord> records;

public:
    void add(int layer, string description) {
        records.push_back({layer, std::move(description)});
    }

    void print() const {
        cout << "\nPacket capture timeline:\n";

        for (const auto& record : records) {
            cout
                << "  Layer "
                << record.layer
                << ": "
                << record.description
                << "\n";
        }
    }
};


// =============================================================================
// 15. TCP HANDSHAKE SIMULATION
// =============================================================================

void performTCPHandshake(
    uint16_t clientPort,
    uint16_t serverPort,
    PacketCapture& capture
) {
    const uint32_t clientISN = 1000;
    const uint32_t serverISN = 5000;

    TCPSegment syn(
        clientPort,
        serverPort,
        clientISN,
        0,
        TCPFlag::SYN
    );

    capture.add(
        4,
        "Client -> Server: TCP " +
        tcpFlagName(syn.getFlag()) +
        ", seq=" +
        to_string(syn.getSequenceNumber())
    );

    TCPSegment synAck(
        serverPort,
        clientPort,
        serverISN,
        clientISN + 1,
        TCPFlag::SYN_ACK
    );

    capture.add(
        4,
        "Server -> Client: TCP " +
        tcpFlagName(synAck.getFlag()) +
        ", seq=" +
        to_string(synAck.getSequenceNumber()) +
        ", ack=" +
        to_string(synAck.getAcknowledgementNumber())
    );

    TCPSegment ack(
        clientPort,
        serverPort,
        clientISN + 1,
        serverISN + 1,
        TCPFlag::ACK
    );

    capture.add(
        4,
        "Client -> Server: TCP " +
        tcpFlagName(ack.getFlag()) +
        ", seq=" +
        to_string(ack.getSequenceNumber()) +
        ", ack=" +
        to_string(ack.getAcknowledgementNumber())
    );
}


// =============================================================================
// 16. ENCAPSULATION FUNCTION
// =============================================================================

string encapsulateForTransport(
    const HttpRequest& request,
    const Session& session
) {
    string applicationData = request.serialize();

    string presentationData =
        PresentationCodec::encodeUTF8LikeRepresentation(
            applicationData
        );

    string protectedData =
        PresentationCodec::addTLSMarker(
            presentationData
        );

    return
        "[SESSION=" +
        to_string(session.getId()) +
        "]" +
        protectedData;
}


// =============================================================================
// 17. COMPLETE WEB REQUEST CASE STUDY
// =============================================================================

void runEnterpriseWebRequestCaseStudy() {
    cout << "\n";
    cout << string(78, '=') << "\n";
    cout << "ENTERPRISE WEB REQUEST: COMPLETE OSI CASE STUDY\n";
    cout << string(78, '=') << "\n";

    /*
     * Client:
     *   192.168.10.25
     *
     * Default gateway:
     *   192.168.10.1
     *
     * Web server:
     *   203.0.113.50
     *
     * The server is outside the client's local subnet, so the client sends
     * the first Ethernet frame to its default gateway.
     */

    Host client(
        "Employee-Laptop",
        IPv4Address("192.168.10.25"),
        MACAddress("AA:AA:AA:AA:AA:25")
    );

    Host gateway(
        "Corporate-Gateway",
        IPv4Address("192.168.10.1"),
        MACAddress("AA:AA:AA:AA:AA:01")
    );

    Host server(
        "Web-Server",
        IPv4Address("203.0.113.50"),
        MACAddress("BB:BB:BB:BB:BB:50")
    );

    cout << "\nHosts:\n";
    cout << "  Client  : " << client.address().str()
         << " / " << client.hardwareAddress().str() << "\n";

    cout << "  Gateway : " << gateway.address().str()
         << " / " << gateway.hardwareAddress().str() << "\n";

    cout << "  Server  : " << server.address().str()
         << " / " << server.hardwareAddress().str() << "\n";


    // -------------------------------------------------------------------------
    // Layer 7: Application
    // -------------------------------------------------------------------------

    HttpRequest request(
        "GET",
        "/portfolio",
        {
            {"Host", "portal.example.internal"},
            {"Accept", "text/html"},
            {"User-Agent", "EnterpriseClient/1.0"}
        }
    );

    PacketCapture capture;

    capture.add(
        7,
        "Browser creates HTTP GET /portfolio."
    );

    cout << "\nLayer 7 application request:\n";
    cout << request.serialize() << "\n";


    // -------------------------------------------------------------------------
    // Layer 5: Session
    // -------------------------------------------------------------------------

    Session session(1001);
    session.establish();

    capture.add(
        5,
        "Application session 1001 established."
    );

    cout << "Layer 5 session ID: "
         << session.getId()
         << "\n";


    // -------------------------------------------------------------------------
    // Layer 6: Presentation
    // -------------------------------------------------------------------------

    string transportPayload =
        encapsulateForTransport(request, session);

    capture.add(
        6,
        "Application representation transformed and marked as TLS-protected."
    );

    cout << "Layer 6 representation length: "
         << transportPayload.size()
         << " bytes\n";


    // -------------------------------------------------------------------------
    // Layer 4: TCP
    // -------------------------------------------------------------------------

    constexpr uint16_t clientPort = 51520;
    constexpr uint16_t httpsPort = 443;

    performTCPHandshake(
        clientPort,
        httpsPort,
        capture
    );

    TCPSegment applicationSegment(
        clientPort,
        httpsPort,
        1001,
        5001,
        TCPFlag::ACK,
        transportPayload
    );

    capture.add(
        4,
        "Established TCP segment carries the application payload."
    );


    // -------------------------------------------------------------------------
    // Layer 3: IP
    // -------------------------------------------------------------------------

    IPPacket packet(
        client.address(),
        server.address(),
        applicationSegment.getPayload()
    );

    capture.add(
        3,
        "IPv4 packet created: " +
        packet.getSource().str() +
        " -> " +
        packet.getDestination().str()
    );

    cout << "\nLayer 3 destination: "
         << packet.getDestination().str()
         << "\n";

    cout << "Initial TTL: "
         << static_cast<int>(packet.getTTL())
         << "\n";


    // -------------------------------------------------------------------------
    // Routing
    // -------------------------------------------------------------------------

    Router router;

    router.addRoute(
        IPv4Address("192.168.10.0"),
        24,
        "local-LAN"
    );

    router.addRoute(
        IPv4Address("203.0.113.0"),
        24,
        "WAN-next-hop"
    );

    router.addRoute(
        IPv4Address("0.0.0.0"),
        0,
        "default-internet-gateway"
    );

    auto selectedRoute = router.lookup(server.address());

    if (!selectedRoute.has_value()) {
        throw runtime_error("No route to server.");
    }

    cout << "Selected next hop: "
         << selectedRoute->nextHop
         << "\n";

    capture.add(
        3,
        "Router selected " +
        selectedRoute->nextHop +
        " using longest-prefix matching."
    );

    packet.decrementTTL();

    cout << "TTL after one router hop: "
         << static_cast<int>(packet.getTTL())
         << "\n";


    // -------------------------------------------------------------------------
    // ARP
    // -------------------------------------------------------------------------

    ARPTable arp;

    arp.learn(
        gateway.address(),
        gateway.hardwareAddress()
    );

    auto gatewayMAC = arp.resolve(gateway.address());

    if (!gatewayMAC.has_value()) {
        throw runtime_error("Gateway MAC address could not be resolved.");
    }

    cout << "\nARP result:\n";
    cout << "  " << gateway.address().str()
         << " -> "
         << gatewayMAC->str()
         << "\n";

    capture.add(
        2,
        "ARP resolves gateway IPv4 address to gateway MAC address."
    );


    // -------------------------------------------------------------------------
    // Layer 2: Ethernet
    // -------------------------------------------------------------------------

    EthernetFrame firstHopFrame(
        client.hardwareAddress(),
        gateway.hardwareAddress(),
        packet.getPayload()
    );

    capture.add(
        2,
        "Ethernet frame created for first-hop delivery."
    );

    cout << "\nFirst-hop Ethernet frame:\n";
    cout << "  Source MAC      : "
         << firstHopFrame.getSource().str()
         << "\n";

    cout << "  Destination MAC : "
         << firstHopFrame.getDestination().str()
         << "\n";


    // -------------------------------------------------------------------------
    // Layer 2 switch
    // -------------------------------------------------------------------------

    EthernetSwitch accessSwitch;

    accessSwitch.learn(
        client.hardwareAddress(),
        "access-port-12"
    );

    accessSwitch.learn(
        gateway.hardwareAddress(),
        "uplink-port-1"
    );

    accessSwitch.printTable();

    auto switchPort =
        accessSwitch.lookup(gateway.hardwareAddress());

    if (!switchPort.has_value()) {
        throw runtime_error("Switch does not know gateway destination MAC.");
    }

    cout << "Switch forwards frame through: "
         << *switchPort
         << "\n";


    // -------------------------------------------------------------------------
    // Layer 1: Physical
    // -------------------------------------------------------------------------

    string physicalData =
        firstHopFrame.getPayload();

    string physicalBits =
        bytesToBits(physicalData);

    capture.add(
        1,
        "Ethernet payload represented as physical transmission bits."
    );

    cout << "\nPhysical layer bit sample:\n";
    cout << physicalBits.substr(
        0,
        min<size_t>(96, physicalBits.size())
    );

    if (physicalBits.size() > 96) {
        cout << "...";
    }

    cout << "\n";


    // -------------------------------------------------------------------------
    // Router rebuilds the Layer 2 frame
    // -------------------------------------------------------------------------

    cout << "\nRouter processing:\n";
    cout << "  Incoming Layer 2 destination: "
         << firstHopFrame.getDestination().str()
         << "\n";

    cout << "  End-to-end Layer 3 destination remains: "
         << packet.getDestination().str()
         << "\n";

    cout << "  Router removes the incoming Layer 2 framing and "
            "creates a new Layer 2 frame for the next link.\n";


    EthernetFrame serverSideFrame(
        gateway.hardwareAddress(),
        server.hardwareAddress(),
        packet.getPayload()
    );

    capture.add(
        2,
        "Router creates a new Ethernet frame for the next network."
    );

    cout << "  New source MAC: "
         << serverSideFrame.getSource().str()
         << "\n";

    cout << "  New destination MAC: "
         << serverSideFrame.getDestination().str()
         << "\n";


    // -------------------------------------------------------------------------
    // Server receives the TCP payload
    // -------------------------------------------------------------------------

    WebServer webServer(httpsPort);

    string response =
        webServer.process(applicationSegment);

    capture.add(
        7,
        "Web server processes the HTTP request."
    );

    cout << "\nServer response:\n";
    cout << response << "\n";


    // -------------------------------------------------------------------------
    // Decapsulation timeline
    // -------------------------------------------------------------------------

    cout << "\nDecapsulation at the server:\n";
    cout << "  Layer 1: physical signals become bits.\n";
    cout << "  Layer 2: Ethernet frame is validated and removed.\n";
    cout << "  Layer 3: IP destination is processed.\n";
    cout << "  Layer 4: TCP identifies port 443 and the connection state.\n";
    cout << "  Layer 5: session context is identified.\n";
    cout << "  Layer 6: representation/TLS processing occurs.\n";
    cout << "  Layer 7: HTTP request reaches the web application.\n";


    capture.print();
}


// =============================================================================
// 18. PERFORMANCE AND TRADE-OFF ANALYSIS
// =============================================================================

void printPerformanceAnalysis() {
    cout << "\n";
    cout << string(78, '=') << "\n";
    cout << "PERFORMANCE AND DESIGN TRADE-OFFS\n";
    cout << string(78, '=') << "\n";

    cout
        << "Layer 1: Higher bandwidth can increase throughput, but signal quality\n"
        << "         and physical distance remain important.\n\n"

        << "Layer 2: Switching provides efficient local forwarding. Large broadcast\n"
        << "         domains can increase unnecessary traffic.\n\n"

        << "Layer 3: Routing enables scalability across networks. More hops can add\n"
        << "         latency, and inefficient routes waste capacity.\n\n"

        << "Layer 4: TCP provides reliability but can introduce retransmission and\n"
        << "         congestion-control overhead. UDP has lower protocol overhead.\n\n"

        << "Layer 5: Stateful sessions can improve application continuity but consume\n"
        << "         server resources and require timeout management.\n\n"

        << "Layer 6: Encryption and serialization consume CPU and add processing\n"
        << "         overhead, while providing interoperability and security benefits.\n\n"

        << "Layer 7: Application performance is often dominated by business logic,\n"
        << "         database access, remote APIs and inefficient payload processing.\n";
}


// =============================================================================
// 19. SECURITY ANALYSIS
// =============================================================================

void printSecurityAnalysis() {
    cout << "\n";
    cout << string(78, '=') << "\n";
    cout << "SECURITY ANALYSIS\n";
    cout << string(78, '=') << "\n";

    cout
        << "Layer 1: Restrict physical access to network equipment and cabling.\n"
        << "Layer 2: Use VLAN segmentation, port security and authenticated access.\n"
        << "Layer 3: Apply ACLs, anti-spoofing controls and appropriate routing policies.\n"
        << "Layer 4: Restrict unnecessary ports and monitor connection behavior.\n"
        << "Layer 5: Protect session identifiers and enforce expiration.\n"
        << "Layer 6: Use modern cryptographic protocols and validate certificates.\n"
        << "Layer 7: Validate input, authenticate users and enforce authorization.\n";

    cout
        << "\nSecurity is cross-layer. A secure web application still depends on\n"
        << "secure hosts, networks, transport configuration and physical infrastructure.\n";
}


// =============================================================================
// 20. TROUBLESHOOTING
// =============================================================================

void printTroubleshootingWorkflow() {
    cout << "\n";
    cout << string(78, '=') << "\n";
    cout << "OSI TROUBLESHOOTING WORKFLOW\n";
    cout << string(78, '=') << "\n";

    cout
        << "Example symptom: A user cannot access an internal HTTPS application.\n\n"

        << "Layer 1:\n"
        << "  Check link status, cable, wireless signal and interface state.\n\n"

        << "Layer 2:\n"
        << "  Check VLAN assignment, switch port and local MAC connectivity.\n\n"

        << "Layer 3:\n"
        << "  Check IP configuration, subnet mask, default gateway and routing.\n\n"

        << "Layer 4:\n"
        << "  Check whether TCP port 443 is reachable and whether the server listens.\n\n"

        << "Layer 5:\n"
        << "  Check application session state and timeout behavior.\n\n"

        << "Layer 6:\n"
        << "  Check TLS negotiation, certificate validation and data representation.\n\n"

        << "Layer 7:\n"
        << "  Check DNS, HTTP status codes, authentication and application logic.\n";
}


// =============================================================================
// 21. MAIN
// =============================================================================

int main() {
    try {
        runEnterpriseWebRequestCaseStudy();
        printPerformanceAnalysis();
        printSecurityAnalysis();
        printTroubleshootingWorkflow();

        cout << "\n";
        cout << string(78, '=') << "\n";
        cout << "CASE STUDY COMPLETE\n";
        cout << string(78, '=') << "\n";

        return 0;
    }
    catch (const exception& error) {
        cerr << "\nProgram error: "
             << error.what()
             << "\n";

        return 1;
    }
}
