#include <algorithm>
#include <array>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

/*
 * IP Address Management Case Study
 * ================================
 *
 * Scenario:
 *   A technical organization is designing an internal network for:
 *
 *     - Engineering
 *     - Security Operations
 *     - Databases
 *     - Application servers
 *     - Management
 *     - Point-to-point router links
 *
 * The program develops an educational IP address management system that:
 *
 *   1. Parses and validates IPv4 addresses.
 *   2. Represents IPv4 addresses as 32-bit integers.
 *   3. Calculates CIDR network information.
 *   4. Determines subnet membership.
 *   5. Allocates variable-sized IPv4 subnets.
 *   6. Performs longest-prefix route matching.
 *   7. Demonstrates IPv6 as a 128-bit address model.
 *   8. Validates common IPv6 forms.
 *   9. Demonstrates address planning and operational constraints.
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic ip_addressing.cpp -o ip_addressing
 *
 * The implementation uses only the C++ standard library.
 */

namespace net {

// ---------------------------------------------------------------------------
// IPv4 address
// ---------------------------------------------------------------------------

class IPv4Address {
public:
    IPv4Address() : value_(0) {}

    explicit IPv4Address(std::uint32_t value) : value_(value) {}

    static IPv4Address parse(const std::string& text) {
        std::array<unsigned int, 4> octets{};
        std::stringstream stream(text);
        std::string part;
        std::size_t index = 0;

        while (std::getline(stream, part, '.')) {
            if (index >= 4 || part.empty()) {
                throw std::invalid_argument("Invalid IPv4 address: " + text);
            }

            for (char character : part) {
                if (character < '0' || character > '9') {
                    throw std::invalid_argument(
                        "IPv4 octet contains a non-digit: " + text
                    );
                }
            }

            unsigned long number = std::stoul(part);

            if (number > 255) {
                throw std::invalid_argument(
                    "IPv4 octet exceeds 255: " + text
                );
            }

            octets[index++] = static_cast<unsigned int>(number);
        }

        if (index != 4) {
            throw std::invalid_argument(
                "IPv4 address must contain four octets: " + text
            );
        }

        std::uint32_t value =
            (octets[0] << 24U) |
            (octets[1] << 16U) |
            (octets[2] << 8U) |
            octets[3];

        return IPv4Address(value);
    }

    std::uint32_t value() const {
        return value_;
    }

    std::string toString() const {
        std::ostringstream output;

        output << ((value_ >> 24U) & 0xffU) << '.'
               << ((value_ >> 16U) & 0xffU) << '.'
               << ((value_ >> 8U) & 0xffU) << '.'
               << (value_ & 0xffU);

        return output.str();
    }

    std::string toBinary() const {
        std::string result;

        for (int bit = 31; bit >= 0; --bit) {
            result += ((value_ >> bit) & 1U) ? '1' : '0';

            if (bit % 8 == 0 && bit != 0) {
                result += ' ';
            }
        }

        return result;
    }

    bool operator==(const IPv4Address& other) const {
        return value_ == other.value_;
    }

private:
    std::uint32_t value_;
};


// ---------------------------------------------------------------------------
// IPv4 network
// ---------------------------------------------------------------------------

class IPv4Network {
public:
    IPv4Network(IPv4Address address, unsigned prefixLength)
        : prefixLength_(prefixLength) {
        if (prefixLength > 32) {
            throw std::invalid_argument(
                "IPv4 prefix must be between 0 and 32."
            );
        }

        mask_ = makeMask(prefixLength_);
        network_ = IPv4Address(address.value() & mask_);
        broadcast_ = IPv4Address(network_.value() | ~mask_);
    }

    static IPv4Network parse(const std::string& cidr) {
        const std::size_t slash = cidr.find('/');

        if (slash == std::string::npos) {
            throw std::invalid_argument(
                "CIDR must contain '/': " + cidr
            );
        }

        const std::string addressPart = cidr.substr(0, slash);
        const std::string prefixPart = cidr.substr(slash + 1);

        if (prefixPart.empty()) {
            throw std::invalid_argument(
                "CIDR prefix is empty: " + cidr
            );
        }

        unsigned long prefix = std::stoul(prefixPart);

        if (prefix > 32) {
            throw std::invalid_argument(
                "IPv4 prefix must be between 0 and 32."
            );
        }

        return IPv4Network(
            IPv4Address::parse(addressPart),
            static_cast<unsigned>(prefix)
        );
    }

    unsigned prefixLength() const {
        return prefixLength_;
    }

    IPv4Address networkAddress() const {
        return network_;
    }

    IPv4Address broadcastAddress() const {
        return broadcast_;
    }

    std::uint32_t mask() const {
        return mask_;
    }

    bool contains(IPv4Address address) const {
        return (address.value() & mask_) == network_.value();
    }

    std::uint64_t totalAddresses() const {
        // A /0 network contains 2^32 addresses. uint64_t prevents overflow.
        return std::uint64_t{1} << (32U - prefixLength_);
    }

    std::uint64_t traditionalUsableHosts() const {
        const std::uint64_t total = totalAddresses();

        if (prefixLength_ <= 30) {
            return total - 2;
        }

        // /31 is widely used for point-to-point links, while /32
        // represents a single host route.
        if (prefixLength_ == 31) {
            return 2;
        }

        return 1;
    }

    IPv4Address firstHost() const {
        if (prefixLength_ <= 30) {
            return IPv4Address(network_.value() + 1);
        }

        return network_;
    }

    IPv4Address lastHost() const {
        if (prefixLength_ <= 30) {
            return IPv4Address(broadcast_.value() - 1);
        }

        return broadcast_;
    }

    std::string toString() const {
        return network_.toString() + "/" +
               std::to_string(prefixLength_);
    }

private:
    static std::uint32_t makeMask(unsigned prefix) {
        if (prefix == 0) {
            return 0;
        }

        if (prefix == 32) {
            return 0xffffffffU;
        }

        return 0xffffffffU << (32U - prefix);
    }

    unsigned prefixLength_;
    std::uint32_t mask_;
    IPv4Address network_;
    IPv4Address broadcast_;
};


// ---------------------------------------------------------------------------
// IPv4 address classification
// ---------------------------------------------------------------------------

enum class IPv4Category {
    Private,
    Loopback,
    LinkLocal,
    Multicast,
    Documentation,
    GlobalCandidate,
    Special
};

std::string categoryName(IPv4Category category) {
    switch (category) {
        case IPv4Category::Private:
            return "private";
        case IPv4Category::Loopback:
            return "loopback";
        case IPv4Category::LinkLocal:
            return "link-local";
        case IPv4Category::Multicast:
            return "multicast";
        case IPv4Category::Documentation:
            return "documentation";
        case IPv4Category::GlobalCandidate:
            return "global/public candidate";
        case IPv4Category::Special:
            return "special-purpose";
    }

    return "unknown";
}

IPv4Category classifyIPv4(IPv4Address address) {
    const IPv4Network privateA =
        IPv4Network::parse("10.0.0.0/8");
    const IPv4Network privateB =
        IPv4Network::parse("172.16.0.0/12");
    const IPv4Network privateC =
        IPv4Network::parse("192.168.0.0/16");
    const IPv4Network loopback =
        IPv4Network::parse("127.0.0.0/8");
    const IPv4Network linkLocal =
        IPv4Network::parse("169.254.0.0/16");
    const IPv4Network multicast =
        IPv4Network::parse("224.0.0.0/4");
    const IPv4Network documentation =
        IPv4Network::parse("192.0.2.0/24");

    if (privateA.contains(address) ||
        privateB.contains(address) ||
        privateC.contains(address)) {
        return IPv4Category::Private;
    }

    if (loopback.contains(address)) {
        return IPv4Category::Loopback;
    }

    if (linkLocal.contains(address)) {
        return IPv4Category::LinkLocal;
    }

    if (multicast.contains(address)) {
        return IPv4Category::Multicast;
    }

    if (documentation.contains(address)) {
        return IPv4Category::Documentation;
    }

    if (address.value() == 0 ||
        address.value() == 0xffffffffU) {
        return IPv4Category::Special;
    }

    return IPv4Category::GlobalCandidate;
}


// ---------------------------------------------------------------------------
// Department requirements
// ---------------------------------------------------------------------------

struct DepartmentRequirement {
    std::string name;
    std::uint32_t hosts;
};

struct Allocation {
    std::string department;
    IPv4Network network;
    std::uint32_t requestedHosts;
};


// ---------------------------------------------------------------------------
// Subnet sizing
// ---------------------------------------------------------------------------

unsigned smallestPrefixForHosts(std::uint32_t requiredHosts) {
    if (requiredHosts == 0) {
        throw std::invalid_argument(
            "Host requirement must be positive."
        );
    }

    for (int prefix = 30; prefix >= 0; --prefix) {
        const std::uint64_t total =
            std::uint64_t{1} << (32U - static_cast<unsigned>(prefix));

        const std::uint64_t usable = total - 2;

        if (usable >= requiredHosts) {
            return static_cast<unsigned>(prefix);
        }
    }

    throw std::overflow_error(
        "Host requirement cannot fit into IPv4."
    );
}


// ---------------------------------------------------------------------------
// VLSM allocator
// ---------------------------------------------------------------------------

class VLSMAllocator {
public:
    explicit VLSMAllocator(IPv4Network baseNetwork)
        : base_(baseNetwork),
          cursor_(baseNetwork.networkAddress().value()) {}

    std::vector<Allocation> allocate(
        std::vector<DepartmentRequirement> requirements
    ) {
        // Largest-first allocation reduces fragmentation and is a common
        // practical strategy for simple sequential VLSM planning.
        std::sort(
            requirements.begin(),
            requirements.end(),
            [](const DepartmentRequirement& left,
               const DepartmentRequirement& right) {
                return left.hosts > right.hosts;
            }
        );

        std::vector<Allocation> result;

        const std::uint64_t baseEnd =
            static_cast<std::uint64_t>(
                base_.broadcastAddress().value()
            );

        for (const auto& requirement : requirements) {
            const unsigned prefix =
                smallestPrefixForHosts(requirement.hosts);

            const std::uint64_t size =
                std::uint64_t{1} << (32U - prefix);

            // CIDR networks must begin on an address aligned to their
            // block size.
            const std::uint64_t aligned =
                ((static_cast<std::uint64_t>(cursor_) + size - 1) / size)
                * size;

            if (aligned + size - 1 > baseEnd) {
                throw std::runtime_error(
                    "Base network cannot satisfy all requirements."
                );
            }

            IPv4Network subnet(
                IPv4Address(
                    static_cast<std::uint32_t>(aligned)
                ),
                prefix
            );

            result.push_back(
                Allocation{
                    requirement.name,
                    subnet,
                    requirement.hosts
                }
            );

            cursor_ = subnet.broadcastAddress().value() + 1U;
        }

        return result;
    }

private:
    IPv4Network base_;
    std::uint32_t cursor_;
};


// ---------------------------------------------------------------------------
// Routing
// ---------------------------------------------------------------------------

struct Route {
    IPv4Network network;
    std::string nextHop;
};

std::optional<Route> longestPrefixMatch(
    IPv4Address destination,
    const std::vector<Route>& routes
) {
    const Route* best = nullptr;

    for (const auto& route : routes) {
        if (!route.network.contains(destination)) {
            continue;
        }

        if (best == nullptr ||
            route.network.prefixLength() >
                best->network.prefixLength()) {
            best = &route;
        }
    }

    if (best == nullptr) {
        return std::nullopt;
    }

    return *best;
}


// ---------------------------------------------------------------------------
// IPv6 representation
// ---------------------------------------------------------------------------

class IPv6Address {
public:
    IPv6Address() : groups_{} {}

    explicit IPv6Address(const std::array<std::uint16_t, 8>& groups)
        : groups_(groups) {}

    static IPv6Address parse(const std::string& input) {
        if (input.empty()) {
            throw std::invalid_argument("IPv6 address is empty.");
        }

        const std::size_t doubleColon = input.find("::");

        if (doubleColon != std::string::npos &&
            input.find("::", doubleColon + 2) != std::string::npos) {
            throw std::invalid_argument(
                "IPv6 address may contain :: only once."
            );
        }

        std::vector<std::uint16_t> groups;

        auto parseGroups = [](const std::string& part) {
            std::vector<std::uint16_t> parsed;

            if (part.empty()) {
                return parsed;
            }

            std::stringstream stream(part);
            std::string group;

            while (std::getline(stream, group, ':')) {
                if (group.empty() ||
                    group.size() > 4) {
                    throw std::invalid_argument(
                        "Invalid IPv6 hexadecimal group."
                    );
                }

                unsigned int value = 0;

                for (char character : group) {
                    unsigned int digit;

                    if (character >= '0' && character <= '9') {
                        digit = static_cast<unsigned int>(
                            character - '0'
                        );
                    } else if (
                        character >= 'a' && character <= 'f'
                    ) {
                        digit = static_cast<unsigned int>(
                            character - 'a' + 10
                        );
                    } else if (
                        character >= 'A' && character <= 'F'
                    ) {
                        digit = static_cast<unsigned int>(
                            character - 'A' + 10
                        );
                    } else {
                        throw std::invalid_argument(
                            "Invalid hexadecimal IPv6 group."
                        );
                    }

                    value = (value * 16U) + digit;
                }

                parsed.push_back(
                    static_cast<std::uint16_t>(value)
                );
            }

            return parsed;
        };

        if (doubleColon == std::string::npos) {
            groups = parseGroups(input);

            if (groups.size() != 8) {
                throw std::invalid_argument(
                    "Uncompressed IPv6 must contain eight groups."
                );
            }
        } else {
            const std::string left =
                input.substr(0, doubleColon);
            const std::string right =
                input.substr(doubleColon + 2);

            const auto leftGroups = parseGroups(left);
            const auto rightGroups = parseGroups(right);

            if (leftGroups.size() + rightGroups.size() >= 8) {
                throw std::invalid_argument(
                    ":: must replace at least one zero group."
                );
            }

            groups.insert(
                groups.end(),
                leftGroups.begin(),
                leftGroups.end()
            );

            const std::size_t missing =
                8 - leftGroups.size() - rightGroups.size();

            for (std::size_t i = 0; i < missing; ++i) {
                groups.push_back(0);
            }

            groups.insert(
                groups.end(),
                rightGroups.begin(),
                rightGroups.end()
            );
        }

        std::array<std::uint16_t, 8> result{};

        for (std::size_t i = 0; i < 8; ++i) {
            result[i] = groups[i];
        }

        return IPv6Address(result);
    }

    std::string expanded() const {
        std::ostringstream output;

        for (std::size_t i = 0; i < groups_.size(); ++i) {
            if (i != 0) {
                output << ':';
            }

            output << std::hex
                   << std::setw(4)
                   << std::setfill('0')
                   << groups_[i];
        }

        return output.str();
    }

    std::string compressed() const {
        // Find the longest zero run. A single zero group is not compressed
        // because canonical formatting reserves :: for runs of two or more.
        std::size_t bestStart = 8;
        std::size_t bestLength = 0;

        for (std::size_t i = 0; i < 8;) {
            if (groups_[i] != 0) {
                ++i;
                continue;
            }

            const std::size_t start = i;

            while (i < 8 && groups_[i] == 0) {
                ++i;
            }

            const std::size_t length = i - start;

            if (length > bestLength) {
                bestStart = start;
                bestLength = length;
            }
        }

        if (bestLength < 2) {
            bestStart = 8;
        }

        std::ostringstream output;

        for (std::size_t i = 0; i < 8; ++i) {
            if (bestStart != 8 &&
                i == bestStart) {
                if (i == 0) {
                    output << "::";
                } else {
                    output << ':';
                    output << ':';
                }

                i += bestLength - 1;
                continue;
            }

            if (i != 0 &&
                !(bestStart != 8 &&
                  i == bestStart + bestLength)) {
                output << ':';
            }

            output << std::hex << std::nouppercase
                   << groups_[i];
        }

        return output.str();
    }

    bool inPrefix(
        const IPv6Address& network,
        unsigned prefixLength
    ) const {
        if (prefixLength > 128) {
            throw std::invalid_argument(
                "IPv6 prefix must be between 0 and 128."
            );
        }

        const unsigned fullGroups = prefixLength / 16;
        const unsigned remainingBits = prefixLength % 16;

        for (unsigned i = 0; i < fullGroups; ++i) {
            if (groups_[i] != network.groups_[i]) {
                return false;
            }
        }

        if (remainingBits == 0) {
            return true;
        }

        const std::uint16_t mask =
            static_cast<std::uint16_t>(
                0xffffU << (16U - remainingBits)
            );

        return (groups_[fullGroups] & mask) ==
               (network.groups_[fullGroups] & mask);
    }

private:
    std::array<std::uint16_t, 8> groups_;
};


// ---------------------------------------------------------------------------
// IP address management case study
// ---------------------------------------------------------------------------

class NetworkPlanner {
public:
    explicit NetworkPlanner(const std::string& baseCIDR)
        : base_(IPv4Network::parse(baseCIDR)) {}

    std::vector<Allocation> buildPlan(
        std::vector<DepartmentRequirement> requirements
    ) const {
        VLSMAllocator allocator(base_);
        return allocator.allocate(std::move(requirements));
    }

    const IPv4Network& base() const {
        return base_;
    }

private:
    IPv4Network base_;
};


// ---------------------------------------------------------------------------
// Demonstration functions
// ---------------------------------------------------------------------------

void printIPv4Basics() {
    std::cout << "\n";
    std::cout << std::string(78, '=') << '\n';
    std::cout << "IPv4 FUNDAMENTALS\n";
    std::cout << std::string(78, '=') << '\n';

    const IPv4Address address =
        IPv4Address::parse("192.168.10.25");

    std::cout << "Address : " << address.toString() << '\n';
    std::cout << "Binary  : " << address.toBinary() << '\n';

    std::cout << "\nIPv4 uses 32 bits, represented as four 8-bit octets.\n";
    std::cout << "Possible IPv4 bit patterns: 2^32 = 4,294,967,296\n";
}


void printSubnetExamples() {
    std::cout << "\n";
    std::cout << std::string(78, '=') << '\n';
    std::cout << "CIDR SUBNET CALCULATIONS\n";
    std::cout << std::string(78, '=') << '\n';

    for (const std::string& cidr : {
        "192.168.10.25/24",
        "10.20.30.40/26",
        "172.16.8.15/28",
        "192.0.2.0/31",
        "203.0.113.17/32"
    }) {
        const IPv4Network network =
            IPv4Network::parse(cidr);

        std::cout << "\nInput: " << cidr << '\n';
        std::cout << "  Network       : "
                  << network.networkAddress().toString()
                  << "/" << network.prefixLength() << '\n';
        std::cout << "  Broadcast     : "
                  << network.broadcastAddress().toString() << '\n';
        std::cout << "  Total         : "
                  << network.totalAddresses() << '\n';
        std::cout << "  Usable hosts  : "
                  << network.traditionalUsableHosts() << '\n';
        std::cout << "  First host    : "
                  << network.firstHost().toString() << '\n';
        std::cout << "  Last host     : "
                  << network.lastHost().toString() << '\n';
    }
}


void printAddressCategories() {
    std::cout << "\n";
    std::cout << std::string(78, '=') << '\n';
    std::cout << "IPv4 ADDRESS CATEGORIES\n";
    std::cout << std::string(78, '=') << '\n';

    for (const std::string& addressText : {
        "10.1.2.3",
        "172.16.10.20",
        "192.168.1.10",
        "8.8.8.8",
        "127.0.0.1",
        "169.254.10.20",
        "224.0.0.1",
        "192.0.2.10"
    }) {
        const IPv4Address address =
            IPv4Address::parse(addressText);

        std::cout << "  "
                  << std::left
                  << std::setw(16)
                  << addressText
                  << " -> "
                  << categoryName(classifyIPv4(address))
                  << '\n';
    }

    std::cout << "\nPrivate IPv4 ranges:\n";
    std::cout << "  10.0.0.0/8\n";
    std::cout << "  172.16.0.0/12\n";
    std::cout << "  192.168.0.0/16\n";

    std::cout << "\nPrivate addressing is not the same as encryption or authentication.\n";
}


void runOrganizationPlan() {
    std::cout << "\n";
    std::cout << std::string(78, '=') << '\n';
    std::cout << "INDUSTRY-STYLE NETWORK ADDRESS PLAN\n";
    std::cout << std::string(78, '=') << '\n';

    std::cout << "Scenario: a company owns an internal 10.50.0.0/24 network.\n";
    std::cout << "Different teams have different host requirements.\n\n";

    NetworkPlanner planner("10.50.0.0/24");

    std::vector<DepartmentRequirement> requirements = {
        {"Engineering", 100},
        {"Security Operations", 50},
        {"Databases", 25},
        {"Application Servers", 25},
        {"Management", 10},
        {"Router Links", 2}
    };

    try {
        const auto allocations =
            planner.buildPlan(requirements);

        std::cout
            << std::left
            << std::setw(24) << "Department"
            << std::setw(20) << "Subnet"
            << std::setw(14) << "Requested"
            << "Usable\n";

        std::cout << std::string(70, '-') << '\n';

        for (const auto& allocation : allocations) {
            std::cout
                << std::left
                << std::setw(24) << allocation.department
                << std::setw(20) << allocation.network.toString()
                << std::setw(14) << allocation.requestedHosts
                << allocation.network.traditionalUsableHosts()
                << '\n';
        }
    } catch (const std::exception& error) {
        std::cerr
            << "Address-plan error: "
            << error.what()
            << '\n';
    }
}


void demonstrateRouting() {
    std::cout << "\n";
    std::cout << std::string(78, '=') << '\n';
    std::cout << "LONGEST-PREFIX ROUTING\n";
    std::cout << std::string(78, '=') << '\n';

    std::vector<Route> routes = {
        {IPv4Network::parse("0.0.0.0/0"), "Internet gateway"},
        {IPv4Network::parse("10.0.0.0/8"), "Router A"},
        {IPv4Network::parse("10.20.0.0/16"), "Router B"},
        {IPv4Network::parse("10.20.30.0/24"), "Router C"},
        {IPv4Network::parse("10.20.30.128/25"), "Router D"}
    };

    for (const std::string& destinationText : {
        "8.8.8.8",
        "10.5.6.7",
        "10.20.10.5",
        "10.20.30.10",
        "10.20.30.200"
    }) {
        const IPv4Address destination =
            IPv4Address::parse(destinationText);

        const auto result =
            longestPrefixMatch(destination, routes);

        std::cout
            << "  "
            << std::setw(16)
            << destinationText
            << " -> ";

        if (result) {
            std::cout
                << std::setw(22)
                << result->network.toString()
                << " -> "
                << result->nextHop;
        } else {
            std::cout << "no route";
        }

        std::cout << '\n';
    }

    std::cout
        << "\nRouting uses the most specific matching prefix.\n";
}


void demonstrateIPv6() {
    std::cout << "\n";
    std::cout << std::string(78, '=') << '\n';
    std::cout << "IPv6 ADDRESSING\n";
    std::cout << std::string(78, '=') << '\n';

    for (const std::string& text : {
        "2001:0db8:0000:0000:0000:0000:0000:0001",
        "2001:db8::1",
        "fe80::1",
        "fc00::1",
        "::1",
        "::"
    }) {
        try {
            const IPv6Address address =
                IPv6Address::parse(text);

            std::cout << "\nInput    : " << text << '\n';
            std::cout << "Expanded : " << address.expanded() << '\n';
            std::cout << "Compressed: " << address.compressed() << '\n';
        } catch (const std::exception& error) {
            std::cout
                << "\nInvalid IPv6 input: "
                << text
                << " -> "
                << error.what()
                << '\n';
        }
    }

    std::cout << "\nIPv6 uses 128 bits.\n";
    std::cout << "Number of possible addresses: 2^128.\n";

    std::cout << "\nCommon IPv6 categories:\n";
    std::cout << "  2000::/3   Global unicast range\n";
    std::cout << "  fe80::/10  Link-local\n";
    std::cout << "  fc00::/7   Unique-local\n";
    std::cout << "  ff00::/8   Multicast\n";
    std::cout << "  ::1/128    Loopback\n";
    std::cout << "  ::/128     Unspecified\n";

    const IPv6Address documentation =
        IPv6Address::parse("2001:db8::1234");

    const IPv6Address prefix =
        IPv6Address::parse("2001:db8::");

    std::cout
        << "\nPrefix membership test:\n"
        << "  "
        << documentation.compressed()
        << " in 2001:db8::/32 -> "
        << std::boolalpha
        << documentation.inPrefix(prefix, 32)
        << '\n';
}


void demonstrateArchitecture() {
    std::cout << "\n";
    std::cout << std::string(78, '=') << '\n';
    std::cout << "PRACTICAL ARCHITECTURE CONSIDERATIONS\n";
    std::cout << std::string(78, '=') << '\n';

    std::cout << "Private IPv4 example:\n";
    std::cout << "  Laptop       192.168.1.20\n";
    std::cout << "  Database     192.168.1.30\n";
    std::cout << "  Router LAN   192.168.1.1\n";
    std::cout << "  Router WAN   public IPv4 address\n";

    std::cout << "\nNAT/PAT can translate private traffic for external connectivity.\n";

    std::cout << "\nDual-stack example:\n";
    std::cout << "  IPv4: 192.168.10.20\n";
    std::cout << "  IPv6: 2001:db8:10:20::20\n";

    std::cout << "\nSecurity requirements:\n";
    std::cout << "  - firewall policies for IPv4 and IPv6\n";
    std::cout << "  - ingress and egress filtering\n";
    std::cout << "  - network segmentation\n";
    std::cout << "  - route-control validation\n";
    std::cout << "  - monitoring and logging\n";
    std::cout << "  - least-privilege connectivity\n";
}


void runTests() {
    std::cout << "\n";
    std::cout << std::string(78, '=') << '\n';
    std::cout << "AUTOMATED TESTS\n";
    std::cout << std::string(78, '=') << '\n';

    const IPv4Address address =
        IPv4Address::parse("192.168.1.1");

    if (address.toString() != "192.168.1.1") {
        throw std::runtime_error("IPv4 round-trip test failed.");
    }

    const IPv4Network subnet =
        IPv4Network::parse("192.168.10.25/24");

    if (subnet.networkAddress().toString() != "192.168.10.0") {
        throw std::runtime_error("Network-address test failed.");
    }

    if (subnet.broadcastAddress().toString() != "192.168.10.255") {
        throw std::runtime_error("Broadcast-address test failed.");
    }

    if (subnet.traditionalUsableHosts() != 254) {
        throw std::runtime_error("Host-count test failed.");
    }

    if (!subnet.contains(
            IPv4Address::parse("192.168.10.100"))) {
        throw std::runtime_error("Membership test failed.");
    }

    if (subnet.contains(
            IPv4Address::parse("192.168.11.100"))) {
        throw std::runtime_error("Non-membership test failed.");
    }

    const IPv6Address ipv6 =
        IPv6Address::parse("2001:db8::1");

    if (ipv6.expanded() !=
        "2001:0db8:0000:0000:0000:0000:0000:0001") {
        throw std::runtime_error("IPv6 expansion test failed.");
    }

    if (ipv6.compressed() != "2001:db8::1") {
        throw std::runtime_error("IPv6 compression test failed.");
    }

    const IPv6Address ipv6Network =
        IPv6Address::parse("2001:db8::");

    if (!ipv6.inPrefix(ipv6Network, 32)) {
        throw std::runtime_error("IPv6 prefix test failed.");
    }

    const auto route = longestPrefixMatch(
        IPv4Address::parse("10.20.30.200"),
        {
            {IPv4Network::parse("10.0.0.0/8"), "A"},
            {IPv4Network::parse("10.20.0.0/16"), "B"},
            {IPv4Network::parse("10.20.30.0/24"), "C"},
            {IPv4Network::parse("10.20.30.128/25"), "D"}
        }
    );

    if (!route || route->nextHop != "D") {
        throw std::runtime_error(
            "Longest-prefix-match test failed."
        );
    }

    std::cout << "All tests passed.\n";
}

} // namespace net


int main() {
    try {
        std::cout << std::string(78, '=') << '\n';
        std::cout << "IP ADDRESSING NETWORK PLANNING CASE STUDY\n";
        std::cout << "IPv4, IPv6, Public and Private IP Addresses\n";
        std::cout << std::string(78, '=') << '\n';

        net::printIPv4Basics();
        net::printSubnetExamples();
        net::printAddressCategories();
        net::runOrganizationPlan();
        net::demonstrateRouting();
        net::demonstrateIPv6();
        net::demonstrateArchitecture();
        net::runTests();

        std::cout << "\n";
        std::cout << std::string(78, '=') << '\n';
        std::cout << "CASE STUDY COMPLETE\n";
        std::cout << std::string(78, '=') << '\n';

        std::cout
            << "The implementation modeled address validation, CIDR "
            << "subnetting, VLSM allocation, routing, IPv6 representation "
            << "and dual-stack planning.\n";

        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }
}
