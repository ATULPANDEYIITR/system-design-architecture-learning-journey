#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Architecture Trade-off and Governance Engine
 *
 * C++17 implementation of:
 * - Architecture domain modeling
 * - Cost and performance analysis
 * - Reliability calculations
 * - Dependency failure propagation
 * - Operational capacity assessment
 * - Weighted architecture evaluation
 * - Pareto dominance
 * - Hard eligibility constraints
 *
 * Compile:
 * g++ -std=c++17 -O2 -Wall -Wextra -pedantic architecture.cpp -o architecture
 */

enum class ArchitectureKind {
    Monolith,
    ModularMonolith,
    Microservices,
    Serverless,
    EventDriven,
    Hybrid
};

enum class DeploymentModel {
    SingleDeployment,
    DistributedDeployment,
    ManagedExecution,
    AsynchronousPipeline
};

struct Metrics {
    double infrastructureCost;
    double operationalCost;
    double latencyMs;
    double throughputRps;
    double availabilityPercent;
    double complexity;
    double scalability;
    double recoveryMinutes;
};

struct Architecture {
    std::string id;
    std::string name;
    ArchitectureKind kind;
    DeploymentModel deployment;
    Metrics metrics;
    std::vector<std::string> dependencies;
};

struct Workload {
    double averageRps;
    double peakMultiplier;
    double payloadKb;
    double latencyLimitMs;

    double peakRps() const {
        return averageRps * peakMultiplier;
    }

    double ingressMbps() const {
        return peakRps() * payloadKb * 8.0 / 1024.0;
    }
};

struct DecisionWeights {
    double cost = 0.25;
    double performance = 0.20;
    double reliability = 0.25;
    double complexity = 0.15;
    double scalability = 0.15;

    void validate() const {
        const double values[] = {
            cost, performance, reliability,
            complexity, scalability
        };

        double sum = 0;

        for (double value : values) {
            if (!std::isfinite(value) || value < 0) {
                throw std::invalid_argument("Invalid decision weight");
            }
            sum += value;
        }

        if (std::abs(sum - 1.0) > 1e-9) {
            throw std::invalid_argument("Weights must sum to one");
        }
    }
};

struct EvaluationPolicy {
    double monthlyBudget;
    double minimumAvailability;
    double minimumThroughput;
    double maximumLatency;
};

struct Evaluation {
    std::string architecture;
    double monthlyCost = 0;
    double annualCost = 0;
    double availability = 0;
    double downtimeHours = 0;
    double costScore = 0;
    double performanceScore = 0;
    double reliabilityScore = 0;
    double complexityScore = 0;
    double scalabilityScore = 0;
    double finalScore = 0;
    bool eligible = false;
    std::vector<std::string> failures;
};

class ArchitectureEngine {
private:
    std::map<std::string, Architecture> architectures;
    std::map<std::string, Evaluation> results;

    Workload workload;
    EvaluationPolicy policy;
    DecisionWeights weights;

    static void requireFinite(
        const std::string& field,
        double value
    ) {
        if (!std::isfinite(value)) {
            throw std::invalid_argument(field + " must be finite");
        }
    }

    static double lowerIsBetter(
        double value,
        double maximum
    ) {
        if (maximum <= 0) {
            return 100;
        }

        return std::clamp(
            100.0 * (1.0 - value / maximum),
            0.0,
            100.0
        );
    }

    static double higherIsBetter(
        double value,
        double maximum
    ) {
        if (maximum <= 0) {
            return 100;
        }

        return std::clamp(
            100.0 * value / maximum,
            0.0,
            100.0
        );
    }

    double calculateAvailability(
        const Architecture& architecture
    ) const {
        double availability =
            architecture.metrics.availabilityPercent / 100.0;

        for (const auto& dependency : architecture.dependencies) {
            const auto it = architectures.find(dependency);

            if (it == architectures.end()) {
                throw std::runtime_error(
                    "Unknown dependency: " + dependency
                );
            }

            availability *=
                it->second.metrics.availabilityPercent / 100.0;
        }

        return availability;
    }

    void validateArchitecture(const Architecture& architecture) const {
        if (architecture.id.empty() || architecture.name.empty()) {
            throw std::invalid_argument(
                "Architecture ID and name are required"
            );
        }

        const auto& m = architecture.metrics;

        const double nonNegative[] = {
            m.infrastructureCost,
            m.operationalCost,
            m.latencyMs,
            m.throughputRps,
            m.recoveryMinutes
        };

        for (double value : nonNegative) {
            requireFinite("Metric", value);

            if (value < 0) {
                throw std::invalid_argument(
                    "Metrics cannot be negative"
                );
            }
        }

        if (m.availabilityPercent <= 0 ||
            m.availabilityPercent > 100) {
            throw std::invalid_argument(
                "Availability must be in (0, 100]"
            );
        }

        if (m.complexity < 1 || m.complexity > 10 ||
            m.scalability < 1 || m.scalability > 10) {
            throw std::invalid_argument(
                "Complexity and scalability must be in [1, 10]"
            );
        }
    }

public:
    ArchitectureEngine(
        Workload workloadValue,
        EvaluationPolicy policyValue,
        DecisionWeights weightsValue
    )
        : workload(workloadValue),
          policy(policyValue),
          weights(weightsValue) {

        weights.validate();

        if (workload.averageRps < 0 ||
            workload.peakMultiplier < 1 ||
            workload.payloadKb < 0 ||
            workload.latencyLimitMs <= 0 ||
            policy.monthlyBudget < 0 ||
            policy.minimumAvailability <= 0 ||
            policy.minimumAvailability > 100 ||
            policy.maximumLatency <= 0 ||
            policy.minimumThroughput < 0) {
            throw std::invalid_argument(
                "Invalid workload or evaluation policy"
            );
        }
    }

    void addArchitecture(const Architecture& architecture) {
        validateArchitecture(architecture);

        if (architectures.count(architecture.id)) {
            throw std::invalid_argument(
                "Duplicate architecture ID"
            );
        }

        architectures.emplace(architecture.id, architecture);
    }

    void validateDependencies() const {
        enum class VisitState {
            Unvisited,
            Visiting,
            Visited
        };

        std::map<std::string, VisitState> states;

        for (const auto& entry : architectures) {
            states[entry.first] = VisitState::Unvisited;
        }

        std::function<void(const std::string&)> visit =
            [&](const std::string& id) {

            if (states[id] == VisitState::Visiting) {
                throw std::runtime_error(
                    "Dependency cycle detected: " + id
                );
            }

            if (states[id] == VisitState::Visited) {
                return;
            }

            states[id] = VisitState::Visiting;

            for (const auto& dependency :
                 architectures.at(id).dependencies) {

                if (!architectures.count(dependency)) {
                    throw std::runtime_error(
                        "Missing dependency: " + dependency
                    );
                }

                visit(dependency);
            }

            states[id] = VisitState::Visited;
        };

        for (const auto& entry : architectures) {
            visit(entry.first);
        }
    }

    std::vector<Evaluation> evaluate() {
        if (architectures.empty()) {
            throw std::runtime_error(
                "No architectures available"
            );
        }

        validateDependencies();

        double maxCost = 0;
        double maxLatency = 0;
        double maxThroughput = 0;
        double maxComplexity = 0;
        double maxScalability = 0;

        for (const auto& [id, architecture] : architectures) {
            const auto& m = architecture.metrics;

            maxCost = std::max(
                maxCost,
                m.infrastructureCost + m.operationalCost
            );

            maxLatency = std::max(maxLatency, m.latencyMs);
            maxThroughput = std::max(maxThroughput, m.throughputRps);
            maxComplexity = std::max(maxComplexity, m.complexity);
            maxScalability = std::max(maxScalability, m.scalability);
        }

        results.clear();

        for (const auto& [id, architecture] : architectures) {
            const auto& m = architecture.metrics;

            Evaluation result;

            result.architecture = architecture.name;
            result.monthlyCost =
                m.infrastructureCost + m.operationalCost;
            result.annualCost = result.monthlyCost * 12;

            const double availability =
                calculateAvailability(architecture);

            result.availability = availability * 100;
            result.downtimeHours = 8760 * (1 - availability);

            result.costScore =
                lowerIsBetter(result.monthlyCost, maxCost);

            const double latencyScore =
                lowerIsBetter(m.latencyMs, maxLatency);

            const double throughputScore =
                higherIsBetter(m.throughputRps, maxThroughput);

            result.performanceScore =
                (latencyScore + throughputScore) / 2;

            result.reliabilityScore = result.availability;

            result.complexityScore =
                lowerIsBetter(m.complexity, maxComplexity);

            result.scalabilityScore =
                higherIsBetter(m.scalability, maxScalability);

            const double values[] = {
                result.costScore,
                result.performanceScore,
                result.reliabilityScore,
                result.complexityScore,
                result.scalabilityScore
            };

            const double weightValues[] = {
                weights.cost,
                weights.performance,
                weights.reliability,
                weights.complexity,
                weights.scalability
            };

            for (int i = 0; i < 5; ++i) {
                result.finalScore += values[i] * weightValues[i];
            }

            if (result.monthlyCost > policy.monthlyBudget) {
                result.failures.push_back("BUDGET_EXCEEDED");
            }

            if (result.availability < policy.minimumAvailability) {
                result.failures.push_back("AVAILABILITY_TOO_LOW");
            }

            if (m.throughputRps < policy.minimumThroughput ||
                m.throughputRps < workload.peakRps()) {
                result.failures.push_back("INSUFFICIENT_CAPACITY");
            }

            if (m.latencyMs > policy.maximumLatency) {
                result.failures.push_back("LATENCY_LIMIT_EXCEEDED");
            }

            result.eligible = result.failures.empty();

            results.emplace(id, result);
        }

        std::vector<Evaluation> ordered;

        for (const auto& entry : results) {
            ordered.push_back(entry.second);
        }

        std::sort(
            ordered.begin(),
            ordered.end(),
            [](const Evaluation& a, const Evaluation& b) {
                if (a.eligible != b.eligible) {
                    return a.eligible > b.eligible;
                }

                return a.finalScore > b.finalScore;
            }
        );

        return ordered;
    }

    std::vector<std::string> paretoFrontier() const {
        std::vector<std::string> frontier;

        for (const auto& [idA, a] : architectures) {
            bool dominated = false;

            for (const auto& [idB, b] : architectures) {
                if (idA == idB) {
                    continue;
                }

                const auto& x = a.metrics;
                const auto& y = b.metrics;

                const double costA =
                    x.infrastructureCost + x.operationalCost;
                const double costB =
                    y.infrastructureCost + y.operationalCost;

                const bool noWorse =
                    costB <= costA &&
                    y.latencyMs <= x.latencyMs &&
                    y.availabilityPercent >= x.availabilityPercent &&
                    y.throughputRps >= x.throughputRps;

                const bool strictlyBetter =
                    costB < costA ||
                    y.latencyMs < x.latencyMs ||
                    y.availabilityPercent > x.availabilityPercent ||
                    y.throughputRps > x.throughputRps;

                if (noWorse && strictlyBetter) {
                    dominated = true;
                    break;
                }
            }

            if (!dominated) {
                frontier.push_back(a.name);
            }
        }

        return frontier;
    }

    const Workload& getWorkload() const {
        return workload;
    }
};

std::string kindName(ArchitectureKind kind) {
    switch (kind) {
        case ArchitectureKind::Monolith:
            return "Monolith";
        case ArchitectureKind::ModularMonolith:
            return "Modular Monolith";
        case ArchitectureKind::Microservices:
            return "Microservices";
        case ArchitectureKind::Serverless:
            return "Serverless";
        case ArchitectureKind::EventDriven:
            return "Event-Driven";
        case ArchitectureKind::Hybrid:
            return "Hybrid";
    }

    return "Unknown";
}

void runTests() {
    ArchitectureEngine engine(
        {100, 2, 32, 200},
        {6000, 99.0, 100, 200},
        {}
    );

    engine.addArchitecture({
        "test",
        "Test Architecture",
        ArchitectureKind::ModularMonolith,
        DeploymentModel::SingleDeployment,
        {100, 100, 50, 500, 99.95, 3, 7, 10},
        {}
    });

    const auto results = engine.evaluate();

    if (results.size() != 1 || !results.front().eligible) {
        throw std::runtime_error("Evaluation test failed");
    }

    if (std::abs(
        engine.getWorkload().ingressMbps() - 50.0
    ) > 1e-9) {
        throw std::runtime_error("Network estimation test failed");
    }
}

int main() {
    try {
        runTests();

        const Workload workload{
            1200,
            2.0,
            32,
            200
        };

        const EvaluationPolicy policy{
            6000,
            99.9,
            1500,
            200
        };

        const DecisionWeights weights{
            0.25,
            0.20,
            0.25,
            0.15,
            0.15
        };

        ArchitectureEngine engine(
            workload,
            policy,
            weights
        );

        engine.addArchitecture({
            "modular",
            "Modular Monolith",
            ArchitectureKind::ModularMonolith,
            DeploymentModel::SingleDeployment,
            {1200, 800, 95, 1800, 99.95, 3.5, 6.5, 20},
            {}
        });

        engine.addArchitecture({
            "microservices",
            "Microservices",
            ArchitectureKind::Microservices,
            DeploymentModel::DistributedDeployment,
            {4200, 3500, 125, 3500, 99.90, 8.5, 9.5, 35},
            {}
        });

        engine.addArchitecture({
            "serverless",
            "Serverless",
            ArchitectureKind::Serverless,
            DeploymentModel::ManagedExecution,
            {850, 1100, 160, 2200, 99.90, 5.5, 9.0, 15},
            {}
        });

        engine.addArchitecture({
            "event-driven",
            "Event-Driven",
            ArchitectureKind::EventDriven,
            DeploymentModel::AsynchronousPipeline,
            {2600, 2400, 140, 4200, 99.95, 7.5, 9.0, 25},
            {}
        });

        const auto evaluations = engine.evaluate();

        std::cout << std::fixed << std::setprecision(2);

        std::cout << "\nARCHITECTURE TRADE-OFF ENGINE\n";
        std::cout << std::string(110, '=') << "\n";

        std::cout
            << std::left << std::setw(27) << "Architecture"
            << std::right << std::setw(12) << "Monthly"
            << std::setw(12) << "Annual"
            << std::setw(14) << "Availability"
            << std::setw(12) << "Score"
            << std::setw(13) << "Eligibility"
            << "\n";

        for (const auto& result : evaluations) {
            std::cout
                << std::left << std::setw(27) << result.architecture
                << std::right << std::setw(12) << result.monthlyCost
                << std::setw(12) << result.annualCost
                << std::setw(13) << result.availability << "%"
                << std::setw(12) << result.finalScore
                << std::setw(13)
                << (result.eligible ? "PASS" : "FAIL")
                << "\n";

            for (const auto& failure : result.failures) {
                std::cout << "    Constraint: " << failure << "\n";
            }
        }

        std::cout << "\nWORKLOAD CAPACITY\n";
        std::cout
            << "Peak requests/second: "
            << workload.peakRps() << "\n";

        std::cout
            << "Estimated ingress: "
            << workload.ingressMbps() << " Mbps\n";

        std::cout << "\nPARETO FRONTIER\n";

        for (const auto& name : engine.paretoFrontier()) {
            std::cout << "- " << name << "\n";
        }

        std::cout << "\nValidation tests passed.\n";
        return 0;

    } catch (const std::exception& exception) {
        std::cerr
            << "Architecture engine error: "
            << exception.what()
            << "\n";

        return 1;
    }
}
