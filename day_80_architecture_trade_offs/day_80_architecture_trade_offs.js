'use strict';

/**
 * Architecture Trade-off Evaluator
 *
 * Event-driven architecture evaluation using Node.js built-in modules.
 *
 * Features:
 * - Architecture profiles
 * - Resource and operational cost modeling
 * - Workload-based performance evaluation
 * - Reliability and dependency analysis
 * - Policy constraints
 * - Pareto frontier calculation
 * - Asynchronous scenario evaluation
 * - Event-driven decision notifications
 * - JSON report persistence
 *
 * Runtime: Node.js 18+
 */

const fs = require('node:fs/promises');
const path = require('node:path');
const EventEmitter = require('node:events');
const crypto = require('node:crypto');

const ArchitectureKind = Object.freeze({
    MONOLITH: 'MONOLITH',
    MODULAR_MONOLITH: 'MODULAR_MONOLITH',
    MICROSERVICES: 'MICROSERVICES',
    SERVERLESS: 'SERVERLESS',
    EVENT_DRIVEN: 'EVENT_DRIVEN',
    HYBRID: 'HYBRID'
});

class DomainError extends Error {
    constructor(message, code = 'DOMAIN_ERROR') {
        super(message);
        this.name = 'DomainError';
        this.code = code;
    }
}

function requireFinite(name, value, minimum = 0) {
    if (!Number.isFinite(value) || value < minimum) {
        throw new DomainError(
            `${name} must be finite and at least ${minimum}`,
            'INVALID_METRIC'
        );
    }
}

function validateProfile(profile) {
    if (!profile || typeof profile !== 'object') {
        throw new DomainError('Architecture profile must be an object');
    }

    if (!profile.id || !profile.name) {
        throw new DomainError('Architecture ID and name are required');
    }

    if (!Object.values(ArchitectureKind).includes(profile.kind)) {
        throw new DomainError('Unknown architecture kind');
    }

    const m = profile.metrics;

    if (!m) {
        throw new DomainError('Metrics are required');
    }

    requireFinite('infrastructureCost', m.infrastructureCost);
    requireFinite('operationsCost', m.operationsCost);
    requireFinite('latencyMs', m.latencyMs);
    requireFinite('throughputRps', m.throughputRps);
    requireFinite('complexity', m.complexity, 1);
    requireFinite('scalability', m.scalability, 1);

    if (m.complexity > 10 || m.scalability > 10) {
        throw new DomainError('Complexity and scalability must not exceed 10');
    }

    if (!Number.isFinite(m.availability) ||
        m.availability <= 0 ||
        m.availability > 100) {
        throw new DomainError('Availability must be in (0, 100]');
    }

    if (profile.dependencies !== undefined &&
        !Array.isArray(profile.dependencies)) {
        throw new DomainError('Dependencies must be an array');
    }

    return Object.freeze({
        ...profile,
        metrics: Object.freeze({ ...m }),
        dependencies: Object.freeze([...(profile.dependencies || [])])
    });
}

class ArchitectureRegistry {
    #profiles = new Map();

    register(profile) {
        const validated = validateProfile(profile);

        if (this.#profiles.has(validated.id)) {
            throw new DomainError(`Duplicate architecture ID: ${validated.id}`);
        }

        this.#profiles.set(validated.id, validated);
        return validated;
    }

    get(id) {
        const profile = this.#profiles.get(id);

        if (!profile) {
            throw new DomainError(`Unknown architecture: ${id}`);
        }

        return profile;
    }

    list() {
        return [...this.#profiles.values()];
    }
}

class Workload {
    constructor({
        requestsPerSecond,
        peakMultiplier,
        payloadKb,
        concurrentUsers,
        latencyTargetMs
    }) {
        requireFinite('requestsPerSecond', requestsPerSecond);
        requireFinite('peakMultiplier', peakMultiplier, 1);
        requireFinite('payloadKb', payloadKb);
        requireFinite('concurrentUsers', concurrentUsers);
        requireFinite('latencyTargetMs', latencyTargetMs, 1);

        this.requestsPerSecond = requestsPerSecond;
        this.peakMultiplier = peakMultiplier;
        this.payloadKb = payloadKb;
        this.concurrentUsers = concurrentUsers;
        this.latencyTargetMs = latencyTargetMs;

        Object.freeze(this);
    }

    get peakRequestsPerSecond() {
        return this.requestsPerSecond * this.peakMultiplier;
    }

    get approximateIngressMbps() {
        return this.peakRequestsPerSecond * this.payloadKb * 8 / 1024;
    }
}

class DecisionPolicy {
    constructor({
        budget,
        minimumAvailability,
        minimumThroughput,
        maximumLatency,
        weights
    }) {
        for (const [name, value] of Object.entries({
            budget,
            minimumAvailability,
            minimumThroughput,
            maximumLatency
        })) {
            requireFinite(name, value);
        }

        if (minimumAvailability <= 0 || minimumAvailability > 100) {
            throw new DomainError('Minimum availability must be in (0, 100]');
        }

        if (maximumLatency <= 0) {
            throw new DomainError('Maximum latency must be positive');
        }

        const keys = ['cost', 'performance', 'reliability', 'complexity', 'scalability'];

        if (!weights || keys.some(key => !Number.isFinite(weights[key]) || weights[key] < 0)) {
            throw new DomainError('Invalid decision weights');
        }

        const total = keys.reduce((sum, key) => sum + weights[key], 0);

        if (Math.abs(total - 1) > 1e-9) {
            throw new DomainError('Weights must sum to 1');
        }

        this.budget = budget;
        this.minimumAvailability = minimumAvailability;
        this.minimumThroughput = minimumThroughput;
        this.maximumLatency = maximumLatency;
        this.weights = Object.freeze({ ...weights });

        Object.freeze(this);
    }
}

class DependencyAnalyzer {
    static calculateAvailability(dependencies) {
        // Serial independent dependencies form a multiplicative availability chain.
        return dependencies.reduce((result, dependency) => {
            if (!Number.isFinite(dependency.availability) ||
                dependency.availability <= 0 ||
                dependency.availability > 1) {
                throw new DomainError('Invalid dependency availability');
            }

            return result * dependency.availability;
        }, 1);
    }

    static validateGraph(nodes) {
        const graph = new Map(nodes.map(node => [node.id, node.dependencies || []]));
        const visited = new Set();
        const active = new Set();

        function visit(id) {
            if (active.has(id)) {
                throw new DomainError(`Dependency cycle detected at ${id}`);
            }

            if (visited.has(id)) {
                return;
            }

            active.add(id);

            for (const dependency of graph.get(id) || []) {
                if (!graph.has(dependency)) {
                    throw new DomainError(`Missing dependency: ${dependency}`);
                }
                visit(dependency);
            }

            active.delete(id);
            visited.add(id);
        }

        for (const id of graph.keys()) {
            visit(id);
        }

        return true;
    }
}

class ArchitectureEvaluator extends EventEmitter {
    constructor(registry, policy, workload) {
        super();

        this.registry = registry;
        this.policy = policy;
        this.workload = workload;
    }

    evaluate(profile) {
        const m = profile.metrics;
        const policy = this.policy;

        const monthlyCost = m.infrastructureCost + m.operationsCost;

        const effectiveAvailability = profile.dependencies.length
            ? m.availability / 100 *
              DependencyAnalyzer.calculateAvailability(
                  profile.dependencies.map(availability => ({ availability }))
              )
            : m.availability / 100;

        const failures = [];

        if (monthlyCost > policy.budget) {
            failures.push('BUDGET_EXCEEDED');
        }

        if (effectiveAvailability * 100 < policy.minimumAvailability) {
            failures.push('AVAILABILITY_BELOW_POLICY');
        }

        if (m.throughputRps < policy.minimumThroughput) {
            failures.push('INSUFFICIENT_THROUGHPUT');
        }

        if (m.latencyMs > policy.maximumLatency) {
            failures.push('LATENCY_LIMIT_EXCEEDED');
        }

        if (m.throughputRps < this.workload.peakRequestsPerSecond) {
            failures.push('WORKLOAD_CAPACITY_INSUFFICIENT');
        }

        const costScore = 100 / (1 + monthlyCost / Math.max(policy.budget, 1));

        const latencyScore = Math.max(
            0,
            Math.min(100, 100 * policy.maximumLatency / Math.max(
                policy.maximumLatency,
                m.latencyMs
            ))
        );

        const throughputScore = Math.min(
            100,
            100 * m.throughputRps /
                Math.max(this.workload.peakRequestsPerSecond, 1)
        );

        const performanceScore = (latencyScore + throughputScore) / 2;

        const reliabilityScore = effectiveAvailability * 100;
        const complexityScore = 100 * (11 - m.complexity) / 10;
        const scalabilityScore = m.scalability * 10;

        const w = policy.weights;

        const weightedScore =
            costScore * w.cost +
            performanceScore * w.performance +
            reliabilityScore * w.reliability +
            complexityScore * w.complexity +
            scalabilityScore * w.scalability;

        const result = Object.freeze({
            architectureId: profile.id,
            architectureName: profile.name,
            monthlyCost,
            annualCost: monthlyCost * 12,
            effectiveAvailability: effectiveAvailability * 100,
            annualDowntimeHours: 8760 * (1 - effectiveAvailability),
            costScore,
            performanceScore,
            reliabilityScore,
            complexityScore,
            scalabilityScore,
            weightedScore,
            eligible: failures.length === 0,
            failures
        });

        this.emit('evaluated', result);
        return result;
    }

    async evaluateAll({ concurrency = 3 } = {}) {
        if (!Number.isInteger(concurrency) || concurrency < 1) {
            throw new DomainError('Concurrency must be a positive integer');
        }

        const profiles = this.registry.list();
        const results = new Array(profiles.length);
        let nextIndex = 0;

        const workers = Array.from(
            { length: Math.min(concurrency, profiles.length) },
            async () => {
                while (true) {
                    const index = nextIndex++;

                    if (index >= profiles.length) {
                        return;
                    }

                    // Yield to the event loop so large evaluations remain responsive.
                    await new Promise(resolve => setImmediate(resolve));

                    results[index] = this.evaluate(profiles[index]);
                }
            }
        );

        await Promise.all(workers);

        return results.sort(
            (a, b) => Number(b.eligible) - Number(a.eligible) ||
                b.weightedScore - a.weightedScore
        );
    }
}

class ParetoAnalyzer {
    /*
     * A dominates B if it is no worse in every objective
     * and strictly better in at least one objective.
     *
     * Objectives:
     * - Lower cost
     * - Lower latency
     * - Higher availability
     * - Higher throughput
     */

    static dominates(a, b) {
        const noWorse =
            a.monthlyCost <= b.monthlyCost &&
            a.metrics.latencyMs <= b.metrics.latencyMs &&
            a.metrics.availability >= b.metrics.availability &&
            a.metrics.throughputRps >= b.metrics.throughputRps;

        const strictlyBetter =
            a.monthlyCost < b.monthlyCost ||
            a.metrics.latencyMs < b.metrics.latencyMs ||
            a.metrics.availability > b.metrics.availability ||
            a.metrics.throughputRps > b.metrics.throughputRps;

        return noWorse && strictlyBetter;
    }

    static frontier(profiles) {
        return profiles.filter(candidate =>
            !profiles.some(other =>
                other.id !== candidate.id &&
                this.dominates(other, candidate)
            )
        );
    }
}

class DecisionReportStore {
    static async save(results, destination) {
        const report = {
            generatedAt: new Date().toISOString(),
            reportId: crypto.randomUUID(),
            results
        };

        const absolutePath = path.resolve(destination);
        const temporaryPath = `${absolutePath}.${crypto.randomUUID()}.tmp`;

        try {
            await fs.writeFile(
                temporaryPath,
                JSON.stringify(report, null, 2),
                { encoding: 'utf8', mode: 0o600, flag: 'wx' }
            );

            await fs.rename(temporaryPath, absolutePath);
        } catch (error) {
            await fs.rm(temporaryPath, { force: true }).catch(() => {});
            throw error;
        }

        return absolutePath;
    }
}

function createSampleRegistry() {
    const registry = new ArchitectureRegistry();

    registry.register({
        id: 'modular',
        name: 'Modular Monolith',
        kind: ArchitectureKind.MODULAR_MONOLITH,
        metrics: {
            infrastructureCost: 1200,
            operationsCost: 800,
            latencyMs: 95,
            throughputRps: 1800,
            availability: 99.95,
            complexity: 3,
            scalability: 6
        }
    });

    registry.register({
        id: 'microservices',
        name: 'Microservices',
        kind: ArchitectureKind.MICROSERVICES,
        metrics: {
            infrastructureCost: 4200,
            operationsCost: 3500,
            latencyMs: 125,
            throughputRps: 3500,
            availability: 99.90,
            complexity: 9,
            scalability: 10
        }
    });

    registry.register({
        id: 'serverless',
        name: 'Serverless',
        kind: ArchitectureKind.SERVERLESS,
        metrics: {
            infrastructureCost: 850,
            operationsCost: 1100,
            latencyMs: 160,
            throughputRps: 2200,
            availability: 99.90,
            complexity: 5,
            scalability: 9
        }
    });

    registry.register({
        id: 'event-driven',
        name: 'Event-Driven',
        kind: ArchitectureKind.EVENT_DRIVEN,
        metrics: {
            infrastructureCost: 2600,
            operationsCost: 2400,
            latencyMs: 140,
            throughputRps: 4200,
            availability: 99.95,
            complexity: 7,
            scalability: 9
        }
    });

    return registry;
}

async function main() {
    const registry = createSampleRegistry();

    const workload = new Workload({
        requestsPerSecond: 1200,
        peakMultiplier: 2,
        payloadKb: 32,
        concurrentUsers: 10000,
        latencyTargetMs: 200
    });

    const policy = new DecisionPolicy({
        budget: 6000,
        minimumAvailability: 99.9,
        minimumThroughput: 1500,
        maximumLatency: 200,
        weights: {
            cost: 0.25,
            performance: 0.20,
            reliability: 0.25,
            complexity: 0.15,
            scalability: 0.15
        }
    });

    const evaluator = new ArchitectureEvaluator(
        registry,
        policy,
        workload
    );

    evaluator.on('evaluated', result => {
        console.log(
            `Evaluated ${result.architectureName}: ` +
            `${result.eligible ? 'ELIGIBLE' : 'REJECTED'}`
        );
    });

    const results = await evaluator.evaluateAll({ concurrency: 2 });

    console.log('\nARCHITECTURE EVALUATION');
    console.log('='.repeat(90));

    for (const result of results) {
        console.log({
            architecture: result.architectureName,
            monthlyCost: result.monthlyCost,
            annualCost: result.annualCost,
            availability: result.effectiveAvailability.toFixed(4),
            score: result.weightedScore.toFixed(2),
            eligible: result.eligible,
            failures: result.failures
        });
    }

    console.log('\nWORKLOAD');
    console.log({
        peakRps: workload.peakRequestsPerSecond,
        approximateIngressMbps: workload.approximateIngressMbps.toFixed(2)
    });

    const frontier = ParetoAnalyzer.frontier(registry.list());

    console.log('\nPARETO FRONTIER');

    for (const profile of frontier) {
        console.log(`- ${profile.name}`);
    }

    const reportPath = await DecisionReportStore.save(
        results,
        'architecture_evaluation_report.json'
    );

    console.log(`\nReport saved: ${reportPath}`);
}

async function runTests() {
    const availability = DependencyAnalyzer.calculateAvailability([
        0.999,
        0.999
    ]);

    if (Math.abs(availability - 0.998001) > 1e-9) {
        throw new Error('Dependency availability test failed');
    }

    let cycleDetected = false;

    try {
        DependencyAnalyzer.validateGraph([
            { id: 'a', dependencies: ['b'] },
            { id: 'b', dependencies: ['a'] }
        ]);
    } catch (error) {
        cycleDetected = true;
    }

    if (!cycleDetected) {
        throw new Error('Dependency cycle test failed');
    }

    const registry = createSampleRegistry();

    if (registry.list().length !== 4) {
        throw new Error('Registry test failed');
    }

    console.log('All JavaScript validation tests passed.');
}

if (require.main === module) {
    runTests()
        .then(main)
        .catch(error => {
            console.error('Architecture evaluation failed:', error.message);
            process.exitCode = 1;
        });
}

module.exports = {
    ArchitectureKind,
    ArchitectureRegistry,
    Workload,
    DecisionPolicy,
    ArchitectureEvaluator,
    DependencyAnalyzer,
    ParetoAnalyzer,
    DecisionReportStore
};
