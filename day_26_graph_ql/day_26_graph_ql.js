/*
 * GraphQL: Queries, Mutations, Schemas, Advantages, and Trade-offs
 * =================================================================
 *
 * Self-contained JavaScript study implementation.
 *
 * This file models GraphQL concepts without requiring an external GraphQL
 * package. It demonstrates the client/server ideas, schema structures,
 * resolver behavior, variables, aliases, fragments, mutations, validation,
 * authorization, pagination, batching, query-cost analysis, and production
 * concerns.
 *
 * Run with:
 *     node graphql_learning.js
 */

"use strict";

// ============================================================================
// 1. FUNDAMENTALS
// ============================================================================

function printSection(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function printJSON(value) {
    console.log(JSON.stringify(value, null, 2));
}

function explainFundamentals() {
    printSection("1. GRAPHQL FUNDAMENTALS");

    const concepts = {
        GraphQL:
            "A typed API query language and execution model in which clients describe the fields they need.",
        Schema:
            "A contract describing types, fields, arguments, inputs, and root operations.",
        Query:
            "A read operation.",
        Mutation:
            "A state-changing operation.",
        Resolver:
            "Application logic that obtains or computes a field value.",
        Variable:
            "A runtime input supplied separately from a query document.",
        Fragment:
            "A reusable selection set.",
        Introspection:
            "A mechanism for querying information about the schema.",
        Alias:
            "A response name that lets a field appear under a different key."
    };

    for (const [name, definition] of Object.entries(concepts)) {
        console.log(`${name}: ${definition}`);
    }
}


// ============================================================================
// 2. SCHEMA REPRESENTATION
// ============================================================================

class FieldDefinition {
    constructor(name, typeName, description = "", argumentsDefinition = {}) {
        this.name = name;
        this.typeName = typeName;
        this.description = description;
        this.arguments = argumentsDefinition;
    }
}

class ObjectType {
    constructor(name, description, fields = {}) {
        this.name = name;
        this.description = description;
        this.fields = fields;
    }
}

class EnumType {
    constructor(name, values) {
        this.name = name;
        this.values = values;
    }
}

class InputObjectType {
    constructor(name, fields) {
        this.name = name;
        this.fields = fields;
    }
}

class Schema {
    constructor() {
        this.types = new Map();
        this.queryType = null;
        this.mutationType = null;
    }

    register(type) {
        if (this.types.has(type.name)) {
            throw new Error(`Duplicate type: ${type.name}`);
        }

        this.types.set(type.name, type);
    }

    setQueryType(typeName) {
        this.queryType = typeName;
    }

    setMutationType(typeName) {
        this.mutationType = typeName;
    }
}

function buildSchema() {
    const schema = new Schema();

    schema.register(new EnumType(
        "Priority",
        ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    ));

    schema.register(new ObjectType(
        "Task",
        "A task managed by the application.",
        {
            id: new FieldDefinition("id", "ID!"),
            title: new FieldDefinition("title", "String!"),
            description: new FieldDefinition("description", "String!"),
            completed: new FieldDefinition("completed", "Boolean!"),
            priority: new FieldDefinition("priority", "Priority!"),
            tags: new FieldDefinition("tags", "[String!]!")
        }
    ));

    schema.register(new InputObjectType(
        "CreateTaskInput",
        {
            title: "String!",
            description: "String!",
            priority: "Priority!",
            projectId: "ID!",
            assigneeId: "ID",
            tags: "[String!]"
        }
    ));

    schema.register(new ObjectType(
        "Query",
        "Root read operations.",
        {
            tasks: new FieldDefinition(
                "tasks",
                "[Task!]!",
                "Return tasks.",
                {
                    completed: "Boolean",
                    priority: "Priority"
                }
            ),
            task: new FieldDefinition(
                "task",
                "Task",
                "Return one task.",
                {
                    id: "ID!"
                }
            )
        }
    ));

    schema.register(new ObjectType(
        "Mutation",
        "Root write operations.",
        {
            createTask: new FieldDefinition(
                "createTask",
                "Task!",
                "Create a task.",
                {
                    input: "CreateTaskInput!"
                }
            ),
            updateTask: new FieldDefinition(
                "updateTask",
                "Task!",
                "Update a task.",
                {
                    id: "ID!",
                    completed: "Boolean",
                    title: "String",
                    priority: "Priority"
                }
            )
        }
    ));

    schema.setQueryType("Query");
    schema.setMutationType("Mutation");

    return schema;
}


// ============================================================================
// 3. DATA MODEL
// ============================================================================

class User {
    constructor(id, name, email, role) {
        this.id = id;
        this.name = name;
        this.email = email;
        this.role = role;
    }
}

class Project {
    constructor(id, name, ownerId) {
        this.id = id;
        this.name = name;
        this.ownerId = ownerId;
    }
}

class Task {
    constructor(
        id,
        title,
        description,
        completed,
        priority,
        projectId,
        assigneeId,
        tags,
        createdAt
    ) {
        this.id = id;
        this.title = title;
        this.description = description;
        this.completed = completed;
        this.priority = priority;
        this.projectId = projectId;
        this.assigneeId = assigneeId;
        this.tags = tags;
        this.createdAt = createdAt;
    }
}

class Repository {
    constructor() {
        this.users = new Map([
            ["u1", new User("u1", "Atul", "atul@example.com", "ADMIN")],
            ["u2", new User("u2", "Priya", "priya@example.com", "MEMBER")],
            ["u3", new User("u3", "Rahul", "rahul@example.com", "MEMBER")]
        ]);

        this.projects = new Map([
            ["p1", new Project("p1", "GraphQL Platform", "u1")],
            ["p2", new Project("p2", "Analytics Platform", "u2")]
        ]);

        this.tasks = new Map([
            [
                "t1",
                new Task(
                    "t1",
                    "Design schema",
                    "Define the public API contract",
                    false,
                    "HIGH",
                    "p1",
                    "u1",
                    ["graphql", "architecture"],
                    "2026-09-20"
                )
            ],
            [
                "t2",
                new Task(
                    "t2",
                    "Implement resolvers",
                    "Connect schema fields to application logic",
                    false,
                    "CRITICAL",
                    "p1",
                    "u2",
                    ["graphql", "backend"],
                    "2026-09-21"
                )
            ],
            [
                "t3",
                new Task(
                    "t3",
                    "Write documentation",
                    "Explain API behavior and trade-offs",
                    true,
                    "MEDIUM",
                    "p1",
                    "u3",
                    ["documentation"],
                    "2026-09-22"
                )
            ],
            [
                "t4",
                new Task(
                    "t4",
                    "Create metrics",
                    "Track application-level statistics",
                    false,
                    "LOW",
                    "p2",
                    null,
                    ["analytics"],
                    "2026-09-23"
                )
            ]
        ]);

        this.nextTaskNumber = 5;
    }

    allTasks() {
        return [...this.tasks.values()];
    }

    getTask(id) {
        return this.tasks.get(id) || null;
    }

    createTask(input) {
        const id = `t${this.nextTaskNumber++}`;

        const task = new Task(
            id,
            input.title,
            input.description,
            false,
            input.priority,
            input.projectId,
            input.assigneeId ?? null,
            input.tags ?? [],
            "2026-09-26"
        );

        this.tasks.set(id, task);
        return task;
    }

    updateTask(id, changes) {
        const task = this.getTask(id);

        if (!task) {
            throw new ValidationError(`Task '${id}' was not found.`);
        }

        if (changes.title !== undefined) {
            task.title = changes.title;
        }

        if (changes.completed !== undefined) {
            task.completed = changes.completed;
        }

        if (changes.priority !== undefined) {
            task.priority = changes.priority;
        }

        return task;
    }
}


// ============================================================================
// 4. ERRORS AND CONTEXT
// ============================================================================

class ValidationError extends Error {
    constructor(message) {
        super(message);
        this.name = "ValidationError";
    }
}

class AuthorizationError extends Error {
    constructor(message) {
        super(message);
        this.name = "AuthorizationError";
    }
}

class RequestContext {
    constructor(user, repository, queryComplexityLimit = 30) {
        this.user = user;
        this.repository = repository;
        this.queryComplexityLimit = queryComplexityLimit;
    }
}

function requireRole(context, ...allowedRoles) {
    if (!allowedRoles.includes(context.user.role)) {
        throw new AuthorizationError(
            `Role ${context.user.role} is not authorized.`
        );
    }
}


// ============================================================================
// 5. QUERY RESOLVERS
// ============================================================================

function resolveTasks(context, { completed = null, priority = null } = {}) {
    let tasks = context.repository.allTasks();

    if (completed !== null) {
        tasks = tasks.filter(task => task.completed === completed);
    }

    if (priority !== null) {
        tasks = tasks.filter(task => task.priority === priority);
    }

    return tasks;
}

function resolveTask(context, id) {
    const task = context.repository.getTask(id);

    if (!task) {
        throw new ValidationError(`Task '${id}' was not found.`);
    }

    return task;
}

function resolveProject(context, task) {
    return context.repository.projects.get(task.projectId) || null;
}

function resolveAssignee(context, task) {
    if (!task.assigneeId) {
        return null;
    }

    return context.repository.users.get(task.assigneeId) || null;
}


// ============================================================================
// 6. RESPONSE SELECTION
// ============================================================================

function selectTaskFields(context, task, fields) {
    const result = {};

    for (const field of fields) {
        switch (field) {
            case "id":
                result.id = task.id;
                break;

            case "title":
                result.title = task.title;
                break;

            case "description":
                result.description = task.description;
                break;

            case "completed":
                result.completed = task.completed;
                break;

            case "priority":
                result.priority = task.priority;
                break;

            case "tags":
                result.tags = [...task.tags];
                break;

            case "project": {
                const project = resolveProject(context, task);

                result.project = project
                    ? {
                        id: project.id,
                        name: project.name
                    }
                    : null;

                break;
            }

            case "assignee": {
                const user = resolveAssignee(context, task);

                result.assignee = user
                    ? {
                        id: user.id,
                        name: user.name
                    }
                    : null;

                break;
            }

            default:
                throw new ValidationError(
                    `Unknown Task field: ${field}`
                );
        }
    }

    return result;
}


// ============================================================================
// 7. QUERY EXAMPLES
// ============================================================================

function basicQuery(context) {
    /*
     * Conceptual GraphQL:
     *
     * query {
     *   tasks {
     *     id
     *     title
     *     completed
     *   }
     * }
     *
     * The client determines the selected fields.
     */

    const tasks = resolveTasks(context);

    return {
        data: {
            tasks: tasks.map(task =>
                selectTaskFields(
                    context,
                    task,
                    ["id", "title", "completed"]
                )
            )
        }
    };
}

function variableQuery(context, variables) {
    /*
     * Conceptual GraphQL:
     *
     * query Tasks($completed: Boolean!, $priority: Priority) {
     *   tasks(completed: $completed, priority: $priority) {
     *     id
     *     title
     *     priority
     *   }
     * }
     *
     * Variables separate runtime values from the operation document.
     */

    if (typeof variables.completed !== "boolean") {
        throw new ValidationError(
            "The completed variable must be a Boolean."
        );
    }

    const tasks = resolveTasks(context, {
        completed: variables.completed,
        priority: variables.priority ?? null
    });

    return {
        data: {
            tasks: tasks.map(task =>
                selectTaskFields(
                    context,
                    task,
                    ["id", "title", "priority"]
                )
            )
        }
    };
}

function nestedQuery(context) {
    /*
     * Conceptual nested query:
     *
     * query {
     *   tasks {
     *     id
     *     title
     *     project { id name }
     *     assignee { id name }
     *   }
     * }
     */

    return {
        data: {
            tasks: resolveTasks(context).map(task =>
                selectTaskFields(
                    context,
                    task,
                    ["id", "title", "project", "assignee"]
                )
            )
        }
    };
}


// ============================================================================
// 8. ALIASES
// ============================================================================

function aliasesQuery(context) {
    /*
     * Conceptual GraphQL:
     *
     * query {
     *   pending: tasks(completed: false) { id title }
     *   completed: tasks(completed: true) { id title }
     * }
     */

    const pending = resolveTasks(context, { completed: false });
    const completed = resolveTasks(context, { completed: true });

    return {
        data: {
            pending: pending.map(task =>
                selectTaskFields(context, task, ["id", "title"])
            ),
            completed: completed.map(task =>
                selectTaskFields(context, task, ["id", "title"])
            )
        }
    };
}


// ============================================================================
// 9. FRAGMENTS
// ============================================================================

const taskSummaryFragment = [
    "id",
    "title",
    "completed",
    "priority"
];

function fragmentQuery(context) {
    /*
     * Conceptual fragment:
     *
     * fragment TaskSummary on Task {
     *   id
     *   title
     *   completed
     *   priority
     * }
     *
     * Fragments provide reusable selection sets.
     */

    return {
        data: {
            tasks: resolveTasks(context).map(task =>
                selectTaskFields(
                    context,
                    task,
                    taskSummaryFragment
                )
            )
        }
    };
}


// ============================================================================
// 10. INPUT VALIDATION
// ============================================================================

function validateCreateTaskInput(input) {
    if (!input || typeof input !== "object") {
        throw new ValidationError("input must be an object.");
    }

    for (const field of ["title", "description", "priority", "projectId"]) {
        if (
            input[field] === undefined ||
            input[field] === null
        ) {
            throw new ValidationError(
                `Missing required field: ${field}`
            );
        }
    }

    if (typeof input.title !== "string" || !input.title.trim()) {
        throw new ValidationError("title must be a non-empty string.");
    }

    if (
        !["LOW", "MEDIUM", "HIGH", "CRITICAL"]
            .includes(input.priority)
    ) {
        throw new ValidationError(
            `Invalid priority: ${input.priority}`
        );
    }

    if (input.tags !== undefined && !Array.isArray(input.tags)) {
        throw new ValidationError("tags must be an array.");
    }

    if ((input.tags ?? []).length > 10) {
        throw new ValidationError(
            "A task may contain at most 10 tags."
        );
    }

    return {
        title: input.title.trim(),
        description: String(input.description).trim(),
        priority: input.priority,
        projectId: String(input.projectId),
        assigneeId:
            input.assigneeId === undefined || input.assigneeId === null
                ? null
                : String(input.assigneeId),
        tags: (input.tags ?? []).map(String)
    };
}


// ============================================================================
// 11. MUTATIONS
// ============================================================================

function createTaskMutation(context, rawInput) {
    /*
     * Conceptual GraphQL:
     *
     * mutation CreateTask($input: CreateTaskInput!) {
     *   createTask(input: $input) {
     *     id
     *     title
     *     priority
     *     completed
     *   }
     * }
     */

    try {
        requireRole(context, "ADMIN", "MEMBER");

        const input = validateCreateTaskInput(rawInput);

        if (!context.repository.projects.has(input.projectId)) {
            throw new ValidationError(
                "projectId does not identify an existing project."
            );
        }

        if (
            input.assigneeId !== null &&
            !context.repository.users.has(input.assigneeId)
        ) {
            throw new ValidationError(
                "assigneeId does not identify an existing user."
            );
        }

        const task = context.repository.createTask(input);

        return {
            data: {
                createTask: selectTaskFields(
                    context,
                    task,
                    ["id", "title", "priority", "completed"]
                )
            }
        };
    } catch (error) {
        return {
            data: null,
            errors: [{ message: error.message }]
        };
    }
}

function updateTaskMutation(context, id, changes) {
    try {
        requireRole(context, "ADMIN", "MEMBER");

        if (
            changes.title !== undefined &&
            (
                typeof changes.title !== "string" ||
                !changes.title.trim()
            )
        ) {
            throw new ValidationError(
                "title must be a non-empty string."
            );
        }

        if (
            changes.priority !== undefined &&
            !["LOW", "MEDIUM", "HIGH", "CRITICAL"]
                .includes(changes.priority)
        ) {
            throw new ValidationError("Invalid priority.");
        }

        const task = context.repository.updateTask(id, {
            ...changes,
            title:
                changes.title === undefined
                    ? undefined
                    : changes.title.trim()
        });

        return {
            data: {
                updateTask: selectTaskFields(
                    context,
                    task,
                    ["id", "title", "completed", "priority"]
                )
            }
        };
    } catch (error) {
        return {
            data: null,
            errors: [{ message: error.message }]
        };
    }
}


// ============================================================================
// 12. N+1 AND BATCHING
// ============================================================================

class ResolverCounter {
    constructor() {
        this.projectCalls = 0;
        this.userCalls = 0;
    }
}

function nestedQueryWithCounter(context, counter) {
    return {
        data: {
            tasks: resolveTasks(context).map(task => {
                counter.projectCalls++;
                const project = resolveProject(context, task);

                let assignee = null;

                if (task.assigneeId) {
                    counter.userCalls++;
                    assignee = resolveAssignee(context, task);
                }

                return {
                    id: task.id,
                    title: task.title,
                    project: project
                        ? { id: project.id, name: project.name }
                        : null,
                    assignee: assignee
                        ? { id: assignee.id, name: assignee.name }
                        : null
                };
            })
        }
    };
}

class BatchLoader {
    constructor(repository) {
        this.repository = repository;
        this.batchRequests = 0;
    }

    loadMany(ids) {
        this.batchRequests++;

        const uniqueIds = [...new Set(ids)];

        return new Map(
            uniqueIds
                .filter(id => this.repository.users.has(id))
                .map(id => [id, this.repository.users.get(id)])
        );
    }
}

function demonstrateBatching(context) {
    printSection("12. N+1 QUERY PROBLEM AND BATCHING");

    const counter = new ResolverCounter();

    nestedQueryWithCounter(context, counter);

    console.log(
        `Individual project resolver calls: ${counter.projectCalls}`
    );
    console.log(
        `Individual user resolver calls:    ${counter.userCalls}`
    );

    const userIds = resolveTasks(context)
        .map(task => task.assigneeId)
        .filter(Boolean);

    const loader = new BatchLoader(context.repository);
    const users = loader.loadMany(userIds);

    console.log(`Batched user requests:             ${loader.batchRequests}`);
    console.log(`Users returned:                     ${users.size}`);

    console.log(
        "Batching is useful because nested GraphQL selection can otherwise "
        + "trigger one backend operation for each parent object."
    );
}


// ============================================================================
// 13. PAGINATION
// ============================================================================

function offsetPagination(context, offset, limit) {
    if (!Number.isInteger(offset) || offset < 0) {
        throw new ValidationError("offset must be a non-negative integer.");
    }

    if (!Number.isInteger(limit) || limit <= 0) {
        throw new ValidationError("limit must be a positive integer.");
    }

    const tasks = resolveTasks(context);
    const items = tasks.slice(offset, offset + limit);

    return {
        items: items.map(task => ({
            id: task.id,
            title: task.title
        })),
        offset,
        limit,
        total: tasks.length
    };
}

function cursorPagination(context, afterId, first) {
    if (!Number.isInteger(first) || first <= 0) {
        throw new ValidationError("first must be a positive integer.");
    }

    const tasks = resolveTasks(context)
        .sort((a, b) => a.id.localeCompare(b.id));

    let startIndex = 0;

    if (afterId !== null) {
        const index = tasks.findIndex(task => task.id === afterId);

        if (index === -1) {
            throw new ValidationError("Unknown cursor.");
        }

        startIndex = index + 1;
    }

    const page = tasks.slice(startIndex, startIndex + first);

    return {
        edges: page.map(task => ({
            cursor: task.id,
            node: {
                id: task.id,
                title: task.title
            }
        })),
        pageInfo: {
            hasNextPage: startIndex + first < tasks.length,
            startCursor: page[0]?.id ?? null,
            endCursor: page[page.length - 1]?.id ?? null
        }
    };
}


// ============================================================================
// 14. QUERY COMPLEXITY
// ============================================================================

class QueryField {
    constructor(name, cost = 1, children = []) {
        this.name = name;
        this.cost = cost;
        this.children = children;
    }
}

function calculateQueryCost(field, depth = 1) {
    let cost = field.cost;
    let maxDepth = depth;

    for (const child of field.children) {
        const result = calculateQueryCost(child, depth + 1);

        cost += result.cost;
        maxDepth = Math.max(maxDepth, result.depth);
    }

    return {
        cost,
        depth: maxDepth
    };
}

function demonstrateQueryComplexity(context) {
    printSection("14. QUERY COMPLEXITY AND DEPTH");

    const safeQuery = new QueryField(
        "tasks",
        3,
        [
            new QueryField("id"),
            new QueryField("title"),
            new QueryField(
                "project",
                2,
                [
                    new QueryField("id"),
                    new QueryField("name")
                ]
            )
        ]
    );

    const expensiveQuery = new QueryField(
        "tasks",
        10,
        [
            new QueryField(
                "project",
                10,
                [
                    new QueryField(
                        "owner",
                        10,
                        [
                            new QueryField(
                                "tasks",
                                10,
                                [
                                    new QueryField("project", 10)
                                ]
                            )
                        ]
                    )
                ]
            )
        ]
    );

    for (const [label, query] of [
        ["Safe query", safeQuery],
        ["Potentially expensive query", expensiveQuery]
    ]) {
        const result = calculateQueryCost(query);

        console.log(
            `${label}: cost=${result.cost}, `
            + `depth=${result.depth}, `
            + `allowed=${result.cost <= context.queryComplexityLimit}`
        );
    }
}


// ============================================================================
// 15. INTROSPECTION
// ============================================================================

function introspectSchema(schema) {
    return {
        queryType: schema.queryType,
        mutationType: schema.mutationType,
        types: [...schema.types.values()].map(type => {
            const result = {
                name: type.name,
                kind: type.constructor.name
            };

            if (type instanceof ObjectType) {
                result.fields = Object.fromEntries(
                    Object.entries(type.fields).map(
                        ([name, field]) => [
                            name,
                            {
                                type: field.typeName,
                                arguments: field.arguments
                            }
                        ]
                    )
                );
            }

            if (type instanceof EnumType) {
                result.values = type.values;
            }

            if (type instanceof InputObjectType) {
                result.inputFields = type.fields;
            }

            return result;
        })
    };
}

function demonstrateIntrospection(schema) {
    printSection("15. INTROSPECTION");
    printJSON(introspectSchema(schema));
}


// ============================================================================
// 16. AUTHORIZATION AND FIELD SECURITY
// ============================================================================

function visibleEmail(requestingUser, targetUser) {
    const canSeeEmail =
        requestingUser.role === "ADMIN" ||
        requestingUser.id === targetUser.id;

    return canSeeEmail ? targetUser.email : null;
}

function demonstrateAuthorization(repository) {
    printSection("16. AUTHORIZATION");

    const admin = repository.users.get("u1");

    repository.users.set(
        "u4",
        new User("u4", "Guest", "guest@example.com", "GUEST")
    );

    const guest = repository.users.get("u4");

    for (const user of repository.users.values()) {
        console.log(
            `Admin viewing ${user.name}:`,
            visibleEmail(admin, user)
        );

        console.log(
            `Guest viewing ${user.name}:`,
            visibleEmail(guest, user)
        );
    }

    const guestContext = new RequestContext(guest, repository);

    const result = createTaskMutation(
        guestContext,
        {
            title: "Unauthorized task",
            description: "Should fail",
            priority: "LOW",
            projectId: "p1"
        }
    );

    console.log("\nGuest mutation:");
    printJSON(result);
}


// ============================================================================
// 17. ASYNCHRONOUS RESOLVER EXAMPLE
// ============================================================================

function delay(milliseconds) {
    return new Promise(resolve => {
        setTimeout(resolve, milliseconds);
    });
}

async function asyncResolverExample(context) {
    /*
     * GraphQL execution commonly interacts with asynchronous data sources.
     * JavaScript promises are therefore particularly relevant to resolver
     * implementations.
     */

    await delay(1);

    return resolveTasks(context).map(task => ({
        id: task.id,
        title: task.title
    }));
}


// ============================================================================
// 18. ERROR PARTIALITY
// ============================================================================

function demonstrateErrors(context) {
    printSection("18. ERROR HANDLING");

    try {
        resolveTask(context, "missing");
    } catch (error) {
        console.log("Expected resolver error:");
        console.log(error.message);
    }

    const mutationResult = updateTaskMutation(
        context,
        "missing",
        { completed: true }
    );

    console.log("\nMutation response containing errors:");
    printJSON(mutationResult);

    console.log(
        "\nGraphQL response processing must distinguish transport failures, "
        + "validation failures, resolver failures, authorization failures, "
        + "and partial data where the server permits it."
    );
}


// ============================================================================
// 19. REST VERSUS GRAPHQL
// ============================================================================

function compareRestAndGraphQL() {
    printSection("19. REST VERSUS GRAPHQL");

    const comparison = [
        ["Data selection", "Endpoint response shape", "Client selection set"],
        ["Schema", "Often documented separately", "Central typed schema"],
        ["Nested data", "May require multiple requests", "Naturally expressible"],
        ["Caching", "Strong HTTP cache semantics", "Requires operation-aware design"],
        ["Complexity control", "Often endpoint-based", "Query depth/cost controls"],
        ["Server implementation", "Often simpler per endpoint", "More execution machinery"],
        ["Evolution", "Endpoint/version strategies", "Additive fields and deprecation"]
    ];

    console.log(
        `${"Dimension".padEnd(22)}`
        + `${"REST".padEnd(32)}`
        + "GraphQL"
    );

    console.log("-".repeat(90));

    for (const [dimension, rest, graphql] of comparison) {
        console.log(
            `${dimension.padEnd(22)}`
            + `${rest.padEnd(32)}`
            + graphql
        );
    }
}


// ============================================================================
// 20. ADVANTAGES AND TRADE-OFFS
// ============================================================================

function explainTradeoffs() {
    printSection("20. ADVANTAGES AND TRADE-OFFS");

    const advantages = [
        "Typed schema",
        "Precise client field selection",
        "Nested related-data selection",
        "Reusable fragments",
        "Typed variables and inputs",
        "Introspection",
        "Unified API over multiple data sources"
    ];

    const tradeoffs = [
        "Resolver execution complexity",
        "Potential N+1 backend requests",
        "Variable query resource consumption",
        "More deliberate caching strategy",
        "Field-level authorization complexity",
        "Need for depth and cost controls",
        "Schema governance requirements"
    ];

    console.log("Potential advantages:");
    for (const item of advantages) {
        console.log(`  + ${item}`);
    }

    console.log("\nImportant trade-offs:");
    for (const item of tradeoffs) {
        console.log(`  - ${item}`);
    }
}


// ============================================================================
// 21. SECURITY CHECKLIST
// ============================================================================

function printSecurityChecklist() {
    printSection("21. GRAPHQL SECURITY");

    const controls = [
        "Authenticate protected operations.",
        "Authorize fields and objects.",
        "Validate input values.",
        "Limit query depth.",
        "Limit query complexity.",
        "Restrict excessive pagination.",
        "Apply rate limits.",
        "Use request timeouts.",
        "Protect sensitive fields.",
        "Avoid leaking internal errors.",
        "Monitor resolver and backend resource usage.",
        "Consider persisted or allow-listed operations.",
        "Treat introspection as a deployment/security consideration."
    ];

    controls.forEach(
        (control, index) => console.log(`${index + 1}. ${control}`)
    );
}


// ============================================================================
// 22. PRODUCTION DESIGN
// ============================================================================

function printProductionConsiderations() {
    printSection("22. PRODUCTION DESIGN");

    const areas = {
        "Schema design":
            "Use stable domain concepts and deliberate nullability.",
        "Resolvers":
            "Keep field resolution focused and delegate complex business logic.",
        "Data access":
            "Use batching, caching, efficient queries, and indexes.",
        "Authorization":
            "Enforce permissions consistently for fields and objects.",
        "Observability":
            "Measure operation latency, resolver cost, errors, and backend calls.",
        "Evolution":
            "Prefer additive changes and controlled deprecation.",
        "Caching":
            "Design separately for HTTP, operation, resolver, and client caching.",
        "Operations":
            "Use rate limits, timeouts, query budgets, and monitoring."
    };

    for (const [area, description] of Object.entries(areas)) {
        console.log(`${area}: ${description}`);
    }
}


// ============================================================================
// 23. COMPLETE CASE STUDY
// ============================================================================

async function runCaseStudy() {
    printSection("23. TASK MANAGEMENT GRAPHQL CASE STUDY");

    const repository = new Repository();

    const context = new RequestContext(
        repository.users.get("u1"),
        repository
    );

    console.log("\nBasic query:");
    printJSON(basicQuery(context));

    console.log("\nVariable-based query:");
    printJSON(
        variableQuery(context, {
            completed: false,
            priority: "HIGH"
        })
    );

    console.log("\nNested query:");
    printJSON(nestedQuery(context));

    console.log("\nAliases:");
    printJSON(aliasesQuery(context));

    console.log("\nFragment-style selection:");
    printJSON(fragmentQuery(context));

    console.log("\nCreate mutation:");

    const createResult = createTaskMutation(
        context,
        {
            title: "Run integration tests",
            description: "Verify complete GraphQL behavior",
            priority: "HIGH",
            projectId: "p1",
            assigneeId: "u3",
            tags: ["testing", "graphql"]
        }
    );

    printJSON(createResult);

    const createdId =
        createResult.data?.createTask?.id;

    console.log("\nUpdate mutation:");

    printJSON(
        updateTaskMutation(
            context,
            createdId,
            {
                completed: true
            }
        )
    );

    console.log("\nOffset pagination:");

    printJSON(
        offsetPagination(context, 0, 3)
    );

    console.log("\nCursor pagination:");

    printJSON(
        cursorPagination(context, null, 3)
    );

    console.log("\nAsynchronous resolver:");
    printJSON(
        await asyncResolverExample(context)
    );

    demonstrateBatching(context);
    demonstrateQueryComplexity(context);
    demonstrateAuthorization(repository);
    demonstrateErrors(context);
}


// ============================================================================
// 24. MAIN
// ============================================================================

async function main() {
    explainFundamentals();

    printSection("2. SCHEMA");
    const schema = buildSchema();

    for (const type of schema.types.values()) {
        console.log(`${type.constructor.name}: ${type.name}`);
    }

    demonstrateIntrospection(schema);
    await runCaseStudy();

    compareRestAndGraphQL();
    explainTradeoffs();
    printSecurityChecklist();
    printProductionConsiderations();

    printSection("25. STUDY NOTES");

    console.log(
        "GraphQL centers the API contract around a typed schema. "
        + "Queries describe reads, mutations describe state changes, "
        + "and resolvers connect fields to application data sources. "
        + "The flexibility of client-selected data creates corresponding "
        + "responsibilities for authorization, batching, caching, resource "
        + "limits, observability, and schema governance."
    );
}

main().catch(error => {
    console.error("Unhandled application error:", error);
    process.exitCode = 1;
});
