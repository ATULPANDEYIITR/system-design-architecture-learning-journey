#include <algorithm>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Repository cache governance is not the scenario here. This program models
 * a distributed object-storage routing service.
 *
 * Each storage server owns many virtual positions on a 64-bit hash ring.
 * Object identifiers are mapped to the first clockwise virtual position.
 *
 * The case study emphasizes the systems properties of consistent hashing:
 * bounded reassignment during membership changes, weighted capacity,
 * deterministic ownership, and operational membership validation.
 */

struct VirtualNode {
    std::uint64_t position;
    std::string server;
    std::size_t replica;
};

struct Server {
    std::string id;
    std::size_t virtual_nodes;
    std::size_t capacity_units;
};

class ObjectRouter {
private:
    std::vector<VirtualNode> ring_;
    std::map<std::string, Server> servers_;

    static std::uint64_t hash64(const std::string& value) {
        // std::hash is implementation-dependent, so a fixed FNV-1a style
        // function gives this executable deterministic behavior.
        constexpr std::uint64_t offset = 14695981039346656037ULL;
        constexpr std::uint64_t prime = 1099511628211ULL;

        std::uint64_t hash = offset;

        for (unsigned char byte : value) {
            hash ^= static_cast<std::uint64_t>(byte);
            hash *= prime;
        }

        return hash;
    }

    static std::uint64_t virtualPosition(
        const std::string& server,
        std::size_t replica
    ) {
        return hash64(server + "#vn:" + std::to_string(replica));
    }

    void sortRing() {
        std::sort(
            ring_.begin(),
            ring_.end(),
            [](const VirtualNode& left, const VirtualNode& right) {
                if (left.position != right.position) {
                    return left.position < right.position;
                }
                return left.server < right.server;
            }
        );
    }

public:
    void addServer(
        const std::string& id,
        std::size_t virtualNodes,
        std::size_t capacityUnits
    ) {
        if (id.empty()) {
            throw std::invalid_argument("server identifier cannot be empty");
        }

        if (virtualNodes == 0 || capacityUnits == 0) {
            throw std::invalid_argument(
                "virtual-node count and capacity must be positive"
            );
        }

        if (servers_.contains(id)) {
            throw std::logic_error("server already exists: " + id);
        }

        std::set<std::uint64_t> positions;

        for (const auto& entry : ring_) {
            positions.insert(entry.position);
        }

        std::vector<VirtualNode> newNodes;

        for (std::size_t replica = 0; replica < virtualNodes; ++replica) {
            const std::uint64_t position = virtualPosition(id, replica);

            if (!positions.insert(position).second) {
                throw std::runtime_error(
                    "hash collision detected while adding server"
                );
            }

            newNodes.push_back({position, id, replica});
        }

        ring_.insert(ring_.end(), newNodes.begin(), newNodes.end());
        sortRing();

        servers_.emplace(
            id,
            Server{id, virtualNodes, capacityUnits}
        );
    }

    void removeServer(const std::string& id) {
        if (!servers_.contains(id)) {
            throw std::out_of_range("server does not exist: " + id);
        }

        ring_.erase(
            std::remove_if(
                ring_.begin(),
                ring_.end(),
                [&id](const VirtualNode& node) {
                    return node.server == id;
                }
            ),
            ring_.end()
        );

        servers_.erase(id);
    }

    std::string ownerForObject(const std::string& objectId) const {
        if (objectId.empty()) {
            throw std::invalid_argument("object identifier cannot be empty");
        }

        if (ring_.empty()) {
            throw std::runtime_error("no storage servers are available");
        }

        const std::uint64_t hash = hash64(objectId);

        auto iterator = std::lower_bound(
            ring_.begin(),
            ring_.end(),
            hash,
            [](const VirtualNode& node, std::uint64_t value) {
                return node.position < value;
            }
        );

        if (iterator == ring_.end()) {
            iterator = ring_.begin();
        }

        return iterator->server;
    }

    std::map<std::string, std::size_t> distribution(
        const std::vector<std::string>& objects
    ) const {
        std::map<std::string, std::size_t> result;

        for (const auto& [id, server] : servers_) {
            result[id] = 0;
        }

        for (const auto& object : objects) {
            ++result[ownerForObject(object)];
        }

        return result;
    }

    std::vector<std::string> owners(
        const std::vector<std::string>& objects
    ) const {
        std::vector<std::string> result;
        result.reserve(objects.size());

        for (const auto& object : objects) {
            result.push_back(ownerForObject(object));
        }

        return result;
    }

    std::size_t ringSize() const {
        return ring_.size();
    }

    const std::map<std::string, Server>& servers() const {
        return servers_;
    }

    void printRingSample(std::size_t limit) const {
        const std::size_t count = std::min(limit, ring_.size());

        for (std::size_t index = 0; index < count; ++index) {
            const auto& node = ring_[index];

            std::cout
                << "position=" << node.position
                << " server=" << node.server
                << " replica=" << node.replica
                << '\n';
        }
    }
};

std::vector<std::string> makeObjects(std::size_t count) {
    std::vector<std::string> objects;
    objects.reserve(count);

    for (std::size_t index = 0; index < count; ++index) {
        objects.push_back(
            "tenant-" + std::to_string(index % 500) +
            "/object-" + std::to_string(index)
        );
    }

    return objects;
}

std::size_t countMoved(
    const std::vector<std::string>& before,
    const std::vector<std::string>& after
) {
    if (before.size() != after.size()) {
        throw std::invalid_argument("ownership vectors differ in size");
    }

    return static_cast<std::size_t>(
        std::count_if(
            before.begin(),
            before.end(),
            [index = std::size_t{0}, &after](
                const std::string& owner
            ) mutable {
                const bool moved = owner != after[index];
                ++index;
                return moved;
            }
        )
    );
}

void printDistribution(
    const std::map<std::string, std::size_t>& distribution
) {
    const auto total = std::accumulate(
        distribution.begin(),
        distribution.end(),
        std::size_t{0},
        [](std::size_t sum, const auto& entry) {
            return sum + entry.second;
        }
    );

    for (const auto& [server, count] : distribution) {
        const double percentage =
            total == 0
                ? 0.0
                : static_cast<double>(count) * 100.0 /
                    static_cast<double>(total);

        std::cout
            << std::left << std::setw(14)
            << server
            << std::right << std::setw(8)
            << count
            << "  "
            << std::fixed << std::setprecision(2)
            << percentage
            << "%\n";
    }
}

int main() {
    try {
        std::cout << "=== Distributed object router ===\n";

        ObjectRouter router;

        // Heterogeneous machines receive different virtual-node counts.
        // More virtual positions give a server a larger expected ring share.
        router.addServer("storage-a", 128, 100);
        router.addServer("storage-b", 128, 100);
        router.addServer("storage-c", 256, 200);

        const auto objects = makeObjects(100000);

        std::cout << "\nRing size: "
                  << router.ringSize()
                  << " virtual positions\n";

        std::cout << "\nInitial distribution:\n";
        printDistribution(router.distribution(objects));

        std::cout << "\nSample ring positions:\n";
        router.printRingSample(8);

        std::cout << "\nSelected ownership:\n";

        for (const std::string& object : {
            "tenant-42/object-100",
            "tenant-42/object-101",
            "tenant-7/object-9000",
            "tenant-99/object-70000"
        }) {
            std::cout
                << object
                << " -> "
                << router.ownerForObject(object)
                << '\n';
        }

        const auto before = router.owners(objects);

        std::cout << "\nAdding storage-d:\n";
        router.addServer("storage-d", 128, 100);

        const auto after = router.owners(objects);
        const std::size_t moved = countMoved(before, after);

        std::cout
            << "Objects moved: "
            << moved
            << "/"
            << objects.size()
            << " ("
            << std::fixed
            << std::setprecision(2)
            << static_cast<double>(moved) * 100.0 /
                static_cast<double>(objects.size())
            << "%)\n";

        std::cout << "\nDistribution after addition:\n";
        printDistribution(router.distribution(objects));

        std::cout << "\nRemoving storage-b:\n";
        router.removeServer("storage-b");

        std::cout << "\nDistribution after removal:\n";
        printDistribution(router.distribution(objects));

        std::cout << "\nFailure and validation checks:\n";

        try {
            router.addServer("storage-a", 64, 50);
        } catch (const std::exception& error) {
            std::cout << "Duplicate server rejected: "
                      << error.what()
                      << '\n';
        }

        try {
            router.ownerForObject("");
        } catch (const std::exception& error) {
            std::cout << "Empty object rejected: "
                      << error.what()
                      << '\n';
        }

        try {
            router.removeServer("missing");
        } catch (const std::exception& error) {
            std::cout << "Unknown server rejected: "
                      << error.what()
                      << '\n';
        }

        /*
         * The lookup is O(log V), where V is the number of virtual nodes.
         * Membership changes require rebuilding or updating the ordered ring,
         * while only the key ranges affected by changed ownership need data
         * movement. Virtual nodes improve statistical balance but consume
         * additional memory and make membership updates more expensive.
         */
        std::cout << "\nSystems characteristics:\n";
        std::cout << "Lookup: O(log V) using lower_bound\n";
        std::cout << "Virtual nodes: improve distribution at metadata cost\n";
        std::cout << "Topology changes: affect local ring intervals\n";
        std::cout << "Replication: separate from primary ownership selection\n";

    } catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
