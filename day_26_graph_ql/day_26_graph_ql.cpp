/*
 * GraphQL Case Study: Enterprise Task Management API
 * ====================================================
 *
 * C++17 implementation of a realistic backend-oriented case study.
 *
 * The program demonstrates the architectural ideas behind a GraphQL API:
 * - typed schemas
 * - object and enum types
 * - queries
 * - arguments
 * - mutations
 * - input validation
 * - resolver-style field execution
 * - nested data
 * - authorization
 * - pagination
 * - batching
 * - query complexity
 * - error handling
 * - schema introspection
 * - performance considerations
 *
 * Compile:
 *     g++ -std=c++17 -O2 graphql_case_study.cpp -o graphql_case_study
 *
 * Run:
 *     ./graphql_case_study
 */

#include <algorithm>
#include <chrono>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

using namespace std;


// ============================================================================
// 1. BASIC UTILITIES
// ============================================================================

void printSection(const string& title) {
    cout << "\n" << string(78, '=') << "\n";
    cout << title << "\n";
    cout << string(78, '=') << "\n";
}


// ============================================================================
// 2. JSON-LIKE RESPONSE MODEL
// ============================================================================

class JsonValue {
public:
    enum class Type {
        Null,
        Boolean,
        Number,
        String,
        Object,
        Array
    };

private:
    Type type_;
    bool booleanValue_ = false;
    double numberValue_ = 0.0;
    string stringValue_;
    map<string, JsonValue> objectValue_;
    vector<JsonValue> arrayValue_;

public:
    JsonValue() : type_(Type::Null) {}

    explicit JsonValue(bool value)
        : type_(Type::Boolean), booleanValue_(value) {}

    explicit JsonValue(double value)
        : type_(Type::Number), numberValue_(value) {}

    explicit JsonValue(int value)
        : type_(Type::Number), numberValue_(value) {}

    explicit JsonValue(string value)
        : type_(Type::String), stringValue_(move(value)) {}

    static JsonValue object() {
        JsonValue value;
        value.type_ = Type::Object;
        return value;
    }

    static JsonValue array() {
        JsonValue value;
        value.type_ = Type::Array;
        return value;
    }

    void set(const string& key, JsonValue value) {
        if (type_ != Type::Object) {
            throw logic_error("Cannot set a property on a non-object.");
        }

        objectValue_[key] = move(value);
    }

    void push(JsonValue value) {
        if (type_ != Type::Array) {
            throw logic_error("Cannot append to a non-array.");
        }

        arrayValue_.push_back(move(value));
    }

    string toString(int indent = 0) const {
        const string padding(indent, ' ');
        const string childPadding(indent + 2, ' ');

        switch (type_) {
            case Type::Null:
                return "null";

            case Type::Boolean:
                return booleanValue_ ? "true" : "false";

            case Type::Number: {
                ostringstream output;
                output << numberValue_;
                return output.str();
            }

            case Type::String:
                return "\"" + escape(stringValue_) + "\"";

            case Type::Array: {
                if (arrayValue_.empty()) {
                    return "[]";
                }

                ostringstream output;
                output << "[\n";

                for (size_t i = 0; i < arrayValue_.size(); ++i) {
                    output << childPadding
                           << arrayValue_[i].toString(indent + 2);

                    if (i + 1 < arrayValue_.size()) {
                        output << ",";
                    }

                    output << "\n";
                }

                output << padding << "]";
                return output.str();
            }

            case Type::Object: {
                if (objectValue_.empty()) {
                    return "{}";
                }

                ostringstream output;
                output << "{\n";

                size_t index = 0;

                for (const auto& [key, value] : objectValue_) {
                    output << childPadding
                           << "\"" << escape(key) << "\": "
                           << value.toString(indent + 2);

                    if (index + 1 < objectValue_.size()) {
                        output << ",";
                    }

                    output << "\n";
                    ++index;
                }

                output << padding << "}";
                return output.str();
            }
        }

        return "null";
    }

private:
    static string escape(const string& value) {
        string result;

        for (char character : value) {
            switch (character) {
                case '\\':
                    result += "\\\\";
                    break;

                case '"':
                    result += "\\\"";
                    break;

                case '\n':
                    result += "\\n";
                    break;

                case '\r':
                    result += "\\r";
                    break;

                case '\t':
                    result += "\\t";
                    break;

                default:
                    result += character;
                    break;
            }
        }

        return result;
    }
};


// ============================================================================
// 3. DOMAIN TYPES
// ============================================================================

enum class Priority {
    LOW,
    MEDIUM,
    HIGH,
    CRITICAL
};

string priorityToString(Priority priority) {
    switch (priority) {
        case Priority::LOW:
            return "LOW";

        case Priority::MEDIUM:
            return "MEDIUM";

        case Priority::HIGH:
            return "HIGH";

        case Priority::CRITICAL:
            return "CRITICAL";
    }

    return "UNKNOWN";
}

optional<Priority> parsePriority(const string& value) {
    if (value == "LOW") {
        return Priority::LOW;
    }

    if (value == "MEDIUM") {
        return Priority::MEDIUM;
    }

    if (value == "HIGH") {
        return Priority::HIGH;
    }

    if (value == "CRITICAL") {
        return Priority::CRITICAL;
    }

    return nullopt;
}

struct User {
    string id;
    string name;
    string email;
    string role;
};

struct Project {
    string id;
    string name;
    string ownerId;
};

struct Task {
    string id;
    string title;
    string description;
    bool completed;
    Priority priority;
    string projectId;
    optional<string> assigneeId;
    vector<string> tags;
    string createdAt;
};


// ============================================================================
// 4. SCHEMA MODEL
// ============================================================================

struct FieldDefinition {
    string name;
    string typeName;
    map<string, string> arguments;
};

struct ObjectType {
    string name;
    string description;
    map<string, FieldDefinition> fields;
};

struct EnumDefinition {
    string name;
    vector<string> values;
};

struct InputObjectDefinition {
    string name;
    map<string, string> fields;
};

class Schema {
private:
    map<string, ObjectType> objectTypes_;
    map<string, EnumDefinition> enums_;
    map<string, InputObjectDefinition> inputs_;

    string queryType_;
    string mutationType_;

public:
    void addObjectType(ObjectType type) {
        if (objectTypes_.contains(type.name)) {
            throw logic_error("Duplicate object type: " + type.name);
        }

        objectTypes_.emplace(type.name, move(type));
    }

    void addEnum(EnumDefinition definition) {
        if (enums_.contains(definition.name)) {
            throw logic_error("Duplicate enum: " + definition.name);
        }

        enums_.emplace(definition.name, move(definition));
    }

    void addInput(InputObjectDefinition definition) {
        if (inputs_.contains(definition.name)) {
            throw logic_error("Duplicate input object: " + definition.name);
        }

        inputs_.emplace(definition.name, move(definition));
    }

    void setQueryType(string typeName) {
        queryType_ = move(typeName);
    }

    void setMutationType(string typeName) {
        mutationType_ = move(typeName);
    }

    JsonValue introspection() const {
        JsonValue result = JsonValue::object();

        result.set("queryType", JsonValue(queryType_));
        result.set("mutationType", JsonValue(mutationType_));

        JsonValue types = JsonValue::array();

        for (const auto& [name, type] : objectTypes_) {
            JsonValue object = JsonValue::object();

            object.set("name", JsonValue(name));
            object.set("kind", JsonValue("OBJECT"));

            JsonValue fields = JsonValue::array();

            for (const auto& [fieldName, field] : type.fields) {
                JsonValue fieldObject = JsonValue::object();

                fieldObject.set("name", JsonValue(fieldName));
                fieldObject.set("type", JsonValue(field.typeName));

                JsonValue arguments = JsonValue::object();

                for (const auto& [argumentName, argumentType] :
                     field.arguments) {
                    arguments.set(
                        argumentName,
                        JsonValue(argumentType)
                    );
                }

                fieldObject.set("arguments", move(arguments));
                fields.push(move(fieldObject));
            }

            object.set("fields", move(fields));
            types.push(move(object));
        }

        for (const auto& [name, definition] : enums_) {
            JsonValue object = JsonValue::object();

            object.set("name", JsonValue(name));
            object.set("kind", JsonValue("ENUM"));

            JsonValue values = JsonValue::array();

            for (const auto& value : definition.values) {
                values.push(JsonValue(value));
            }

            object.set("values", move(values));
            types.push(move(object));
        }

        for (const auto& [name, definition] : inputs_) {
            JsonValue object = JsonValue::object();

            object.set("name", JsonValue(name));
            object.set("kind", JsonValue("INPUT_OBJECT"));

            JsonValue fields = JsonValue::object();

            for (const auto& [fieldName, fieldType] : definition.fields) {
                fields.set(fieldName, JsonValue(fieldType));
            }

            object.set("inputFields", move(fields));
            types.push(move(object));
        }

        result.set("types", move(types));

        return result;
    }
};


// ============================================================================
// 5. REPOSITORY
// ============================================================================

class Repository {
private:
    unordered_map<string, User> users_;
    unordered_map<string, Project> projects_;
    unordered_map<string, Task> tasks_;

    int nextTaskNumber_ = 5;

public:
    Repository() {
        users_.emplace(
            "u1",
            User{
                "u1",
                "Atul",
                "atul@example.com",
                "ADMIN"
            }
        );

        users_.emplace(
            "u2",
            User{
                "u2",
                "Priya",
                "priya@example.com",
                "MEMBER"
            }
        );

        users_.emplace(
            "u3",
            User{
                "u3",
                "Rahul",
                "rahul@example.com",
                "MEMBER"
            }
        );

        projects_.emplace(
            "p1",
            Project{
                "p1",
                "GraphQL Platform",
                "u1"
            }
        );

        projects_.emplace(
            "p2",
            Project{
                "p2",
                "Analytics Platform",
                "u2"
            }
        );

        tasks_.emplace(
            "t1",
            Task{
                "t1",
                "Design schema",
                "Define the public API contract",
                false,
                Priority::HIGH,
                "p1",
                string("u1"),
                {"graphql", "architecture"},
                "2026-09-20"
            }
        );

        tasks_.emplace(
            "t2",
            Task{
                "t2",
                "Implement resolvers",
                "Connect schema fields to application logic",
                false,
                Priority::CRITICAL,
                "p1",
                string("u2"),
                {"graphql", "backend"},
                "2026-09-21"
            }
        );

        tasks_.emplace(
            "t3",
            Task{
                "t3",
                "Write documentation",
                "Explain API behavior and trade-offs",
                true,
                Priority::MEDIUM,
                "p1",
                string("u3"),
                {"documentation"},
                "2026-09-22"
            }
        );

        tasks_.emplace(
            "t4",
            Task{
                "t4",
                "Create metrics",
                "Track application-level statistics",
                false,
                Priority::LOW,
                "p2",
                nullopt,
                {"analytics"},
                "2026-09-23"
            }
        );
    }

    const unordered_map<string, User>& users() const {
        return users_;
    }

    const unordered_map<string, Project>& projects() const {
        return projects_;
    }

    vector<Task> allTasks() const {
        vector<Task> result;

        result.reserve(tasks_.size());

        for (const auto& [id, task] : tasks_) {
            result.push_back(task);
        }

        sort(
            result.begin(),
            result.end(),
            [](const Task& left, const Task& right) {
                return left.id < right.id;
            }
        );

        return result;
    }

    optional<Task> getTask(const string& id) const {
        auto iterator = tasks_.find(id);

        if (iterator == tasks_.end()) {
            return nullopt;
        }

        return iterator->second;
    }

    optional<Project> getProject(const string& id) const {
        auto iterator = projects_.find(id);

        if (iterator == projects_.end()) {
            return nullopt;
        }

        return iterator->second;
    }

    optional<User> getUser(const string& id) const {
        auto iterator = users_.find(id);

        if (iterator == users_.end()) {
            return nullopt;
        }

        return iterator->second;
    }

    Task createTask(
        string title,
        string description,
        Priority priority,
        string projectId,
        optional<string> assigneeId,
        vector<string> tags
    ) {
        string id = "t" + to_string(nextTaskNumber_++);

        Task task{
            id,
            move(title),
            move(description),
            false,
            priority,
            move(projectId),
            move(assigneeId),
            move(tags),
            "2026-09-26"
        };

        tasks_.emplace(id, task);

        return task;
    }

    Task updateTask(
        const string& id,
        optional<string> title,
        optional<bool> completed,
        optional<Priority> priority
    ) {
        auto iterator = tasks_.find(id);

        if (iterator == tasks_.end()) {
            throw invalid_argument("Task does not exist: " + id);
        }

        Task& task = iterator->second;

        if (title.has_value()) {
            task.title = *title;
        }

        if (completed.has_value()) {
            task.completed = *completed;
        }

        if (priority.has_value()) {
            task.priority = *priority;
        }

        return task;
    }
};


// ============================================================================
// 6. REQUEST CONTEXT AND AUTHORIZATION
// ============================================================================

struct RequestContext {
    User currentUser;
    Repository& repository;
    int queryComplexityLimit = 30;
};

void requireRole(
    const RequestContext& context,
    const set<string>& allowedRoles
) {
    if (!allowedRoles.contains(context.currentUser.role)) {
        throw runtime_error(
            "Role " + context.currentUser.role
            + " is not authorized for this operation."
        );
    }
}


// ============================================================================
// 7. RESOLVER METRICS
// ============================================================================

struct ResolverMetrics {
    int projectLookups = 0;
    int userLookups = 0;

    void reset() {
        projectLookups = 0;
        userLookups = 0;
    }
};


// ============================================================================
// 8. FIELD RESOLVERS
// ============================================================================

optional<Project> resolveProject(
    const RequestContext& context,
    const Task& task,
    ResolverMetrics* metrics = nullptr
) {
    if (metrics != nullptr) {
        metrics->projectLookups++;
    }

    return context.repository.getProject(task.projectId);
}

optional<User> resolveAssignee(
    const RequestContext& context,
    const Task& task,
    ResolverMetrics* metrics = nullptr
) {
    if (!task.assigneeId.has_value()) {
        return nullopt;
    }

    if (metrics != nullptr) {
        metrics->userLookups++;
    }

    return context.repository.getUser(*task.assigneeId);
}


// ============================================================================
// 9. TASK SERIALIZATION
// ============================================================================

JsonValue serializeTask(
    const RequestContext& context,
    const Task& task,
    bool includeNested,
    ResolverMetrics* metrics = nullptr
) {
    JsonValue object = JsonValue::object();

    object.set("id", JsonValue(task.id));
    object.set("title", JsonValue(task.title));
    object.set("description", JsonValue(task.description));
    object.set("completed", JsonValue(task.completed));
    object.set(
        "priority",
        JsonValue(priorityToString(task.priority))
    );

    JsonValue tags = JsonValue::array();

    for (const auto& tag : task.tags) {
        tags.push(JsonValue(tag));
    }

    object.set("tags", move(tags));

    if (includeNested) {
        auto project = resolveProject(context, task, metrics);

        if (project.has_value()) {
            JsonValue projectObject = JsonValue::object();

            projectObject.set("id", JsonValue(project->id));
            projectObject.set("name", JsonValue(project->name));

            object.set("project", move(projectObject));
        } else {
            object.set("project", JsonValue());
        }

        auto assignee = resolveAssignee(context, task, metrics);

        if (assignee.has_value()) {
            JsonValue assigneeObject = JsonValue::object();

            assigneeObject.set("id", JsonValue(assignee->id));
            assigneeObject.set("name", JsonValue(assignee->name));

            object.set("assignee", move(assigneeObject));
        } else {
            object.set("assignee", JsonValue());
        }
    }

    return object;
}


// ============================================================================
// 10. QUERY RESOLVER
// ============================================================================

vector<Task> resolveTasks(
    const RequestContext& context,
    optional<bool> completed = nullopt,
    optional<Priority> priority = nullopt
) {
    vector<Task> tasks = context.repository.allTasks();

    tasks.erase(
        remove_if(
            tasks.begin(),
            tasks.end(),
            [&](const Task& task) {
                if (
                    completed.has_value() &&
                    task.completed != *completed
                ) {
                    return true;
                }

                if (
                    priority.has_value() &&
                    task.priority != *priority
                ) {
                    return true;
                }

                return false;
            }
        ),
        tasks.end()
    );

    return tasks;
}

JsonValue queryTasks(
    const RequestContext& context,
    optional<bool> completed = nullopt,
    optional<Priority> priority = nullopt,
    bool includeNested = false
) {
    JsonValue response = JsonValue::object();
    JsonValue data = JsonValue::object();
    JsonValue tasks = JsonValue::array();

    for (const auto& task :
         resolveTasks(context, completed, priority)) {
        tasks.push(
            serializeTask(
                context,
                task,
                includeNested
            )
        );
    }

    data.set("tasks", move(tasks));
    response.set("data", move(data));

    return response;
}


// ============================================================================
// 11. MUTATION INPUT
// ============================================================================

struct CreateTaskInput {
    string title;
    string description;
    Priority priority;
    string projectId;
    optional<string> assigneeId;
    vector<string> tags;
};

void validateCreateTaskInput(
    const RequestContext& context,
    const CreateTaskInput& input
) {
    if (input.title.empty()) {
        throw invalid_argument("title cannot be empty.");
    }

    if (input.projectId.empty()) {
        throw invalid_argument("projectId cannot be empty.");
    }

    if (!context.repository.getProject(input.projectId).has_value()) {
        throw invalid_argument(
            "projectId does not identify an existing project."
        );
    }

    if (input.assigneeId.has_value()) {
        if (
            !context.repository
                .getUser(*input.assigneeId)
                .has_value()
        ) {
            throw invalid_argument(
                "assigneeId does not identify an existing user."
            );
        }
    }

    if (input.tags.size() > 10) {
        throw invalid_argument(
            "A task may contain at most 10 tags."
        );
    }
}


// ============================================================================
// 12. MUTATION RESOLVERS
// ============================================================================

JsonValue createTaskMutation(
    const RequestContext& context,
    const CreateTaskInput& input
) {
    try {
        requireRole(
            context,
            {"ADMIN", "MEMBER"}
        );

        validateCreateTaskInput(context, input);

        Task task = context.repository.createTask(
            input.title,
            input.description,
            input.priority,
            input.projectId,
            input.assigneeId,
            input.tags
        );

        JsonValue response = JsonValue::object();
        JsonValue data = JsonValue::object();

        data.set(
            "createTask",
            serializeTask(
                context,
                task,
                false
            )
        );

        response.set("data", move(data));

        return response;
    }
    catch (const exception& error) {
        JsonValue response = JsonValue::object();
        response.set("data", JsonValue());

        JsonValue errors = JsonValue::array();
        JsonValue errorObject = JsonValue::object();

        errorObject.set(
            "message",
            JsonValue(error.what())
        );

        errors.push(move(errorObject));
        response.set("errors", move(errors));

        return response;
    }
}

JsonValue updateTaskMutation(
    const RequestContext& context,
    const string& taskId,
    optional<string> title,
    optional<bool> completed,
    optional<Priority> priority
) {
    try {
        requireRole(
            context,
            {"ADMIN", "MEMBER"}
        );

        if (title.has_value() && title->empty()) {
            throw invalid_argument(
                "title cannot be empty."
            );
        }

        Task task = context.repository.updateTask(
            taskId,
            title,
            completed,
            priority
        );

        JsonValue response = JsonValue::object();
        JsonValue data = JsonValue::object();

        data.set(
            "updateTask",
            serializeTask(
                context,
                task,
                false
            )
        );

        response.set("data", move(data));

        return response;
    }
    catch (const exception& error) {
        JsonValue response = JsonValue::object();
        response.set("data", JsonValue());

        JsonValue errors = JsonValue::array();
        JsonValue errorObject = JsonValue::object();

        errorObject.set(
            "message",
            JsonValue(error.what())
        );

        errors.push(move(errorObject));
        response.set("errors", move(errors));

        return response;
    }
}


// ============================================================================
// 13. CURSOR PAGINATION
// ============================================================================

JsonValue cursorPagination(
    const RequestContext& context,
    optional<string> after,
    size_t first
) {
    if (first == 0) {
        throw invalid_argument(
            "first must be greater than zero."
        );
    }

    vector<Task> tasks =
        context.repository.allTasks();

    size_t startIndex = 0;

    if (after.has_value()) {
        auto iterator = find_if(
            tasks.begin(),
            tasks.end(),
            [&](const Task& task) {
                return task.id == *after;
            }
        );

        if (iterator == tasks.end()) {
            throw invalid_argument(
                "Unknown cursor."
            );
        }

        startIndex =
            static_cast<size_t>(
                distance(tasks.begin(), iterator)
            ) + 1;
    }

    const size_t endIndex =
        min(startIndex + first, tasks.size());

    JsonValue response = JsonValue::object();
    JsonValue edges = JsonValue::array();

    for (size_t index = startIndex; index < endIndex; ++index) {
        JsonValue edge = JsonValue::object();

        edge.set(
            "cursor",
            JsonValue(tasks[index].id)
        );

        edge.set(
            "node",
            serializeTask(
                context,
                tasks[index],
                false
            )
        );

        edges.push(move(edge));
    }

    JsonValue pageInfo = JsonValue::object();

    pageInfo.set(
        "hasNextPage",
        JsonValue(endIndex < tasks.size())
    );

    if (startIndex < endIndex) {
        pageInfo.set(
            "startCursor",
            JsonValue(tasks[startIndex].id)
        );

        pageInfo.set(
            "endCursor",
            JsonValue(tasks[endIndex - 1].id)
        );
    } else {
        pageInfo.set(
            "startCursor",
            JsonValue()
        );

        pageInfo.set(
            "endCursor",
            JsonValue()
        );
    }

    response.set("edges", move(edges));
    response.set("pageInfo", move(pageInfo));

    return response;
}


// ============================================================================
// 14. BATCH LOADING
// ============================================================================

class UserBatchLoader {
private:
    Repository& repository_;
    int batchRequests_ = 0;

public:
    explicit UserBatchLoader(Repository& repository)
        : repository_(repository) {}

    map<string, User> loadMany(
        const vector<string>& ids
    ) {
        ++batchRequests_;

        set<string> uniqueIds(
            ids.begin(),
            ids.end()
        );

        map<string, User> result;

        for (const auto& id : uniqueIds) {
            auto user = repository_.getUser(id);

            if (user.has_value()) {
                result.emplace(id, *user);
            }
        }

        return result;
    }

    int batchRequests() const {
        return batchRequests_;
    }
};


// ============================================================================
// 15. QUERY COMPLEXITY
// ============================================================================

struct QueryNode {
    string name;
    int cost = 1;
    vector<QueryNode> children;
};

struct ComplexityResult {
    int cost;
    int depth;
};

ComplexityResult calculateComplexity(
    const QueryNode& node,
    int depth = 1
) {
    int totalCost = node.cost;
    int maximumDepth = depth;

    for (const auto& child : node.children) {
        ComplexityResult childResult =
            calculateComplexity(
                child,
                depth + 1
            );

        totalCost += childResult.cost;

        maximumDepth =
            max(
                maximumDepth,
                childResult.depth
            );
    }

    return {
        totalCost,
        maximumDepth
    };
}


// ============================================================================
// 16. NESTED QUERY DEMONSTRATION
// ============================================================================

void demonstrateNPlusOne(
    const RequestContext& context
) {
    printSection(
        "N+1 QUERY PROBLEM AND BATCHING"
    );

    ResolverMetrics metrics;

    for (const auto& task :
         context.repository.allTasks()) {
        resolveProject(
            context,
            task,
            &metrics
        );

        resolveAssignee(
            context,
            task,
            &metrics
        );
    }

    cout
        << "Individual project lookups: "
        << metrics.projectLookups
        << "\n";

    cout
        << "Individual user lookups:    "
        << metrics.userLookups
        << "\n";

    vector<string> userIds;

    for (const auto& task :
         context.repository.allTasks()) {
        if (task.assigneeId.has_value()) {
            userIds.push_back(*task.assigneeId);
        }
    }

    UserBatchLoader loader(
        context.repository
    );

    auto users =
        loader.loadMany(userIds);

    cout
        << "Batched user requests:      "
        << loader.batchRequests()
        << "\n";

    cout
        << "Users returned by batch:    "
        << users.size()
        << "\n";

    cout
        << "Batching can replace repeated "
        << "child lookups with grouped access."
        << "\n";
}


// ============================================================================
// 17. SCHEMA CREATION
// ============================================================================

Schema createSchema() {
    Schema schema;

    schema.addEnum(
        EnumDefinition{
            "Priority",
            {
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL"
            }
        }
    );

    schema.addObjectType(
        ObjectType{
            "Task",
            "A task in the management system.",
            {
                {
                    "id",
                    FieldDefinition{
                        "id",
                        "ID!",
                        {}
                    }
                },
                {
                    "title",
                    FieldDefinition{
                        "title",
                        "String!",
                        {}
                    }
                },
                {
                    "description",
                    FieldDefinition{
                        "description",
                        "String!",
                        {}
                    }
                },
                {
                    "completed",
                    FieldDefinition{
                        "completed",
                        "Boolean!",
                        {}
                    }
                },
                {
                    "priority",
                    FieldDefinition{
                        "priority",
                        "Priority!",
                        {}
                    }
                },
                {
                    "project",
                    FieldDefinition{
                        "project",
                        "Project",
                        {}
                    }
                },
                {
                    "assignee",
                    FieldDefinition{
                        "assignee",
                        "User",
                        {}
                    }
                }
            }
        }
    );

    schema.addObjectType(
        ObjectType{
            "Project",
            "A project containing tasks.",
            {
                {
                    "id",
                    FieldDefinition{
                        "id",
                        "ID!",
                        {}
                    }
                },
                {
                    "name",
                    FieldDefinition{
                        "name",
                        "String!",
                        {}
                    }
                }
            }
        }
    );

    schema.addObjectType(
        ObjectType{
            "User",
            "An API user.",
            {
                {
                    "id",
                    FieldDefinition{
                        "id",
                        "ID!",
                        {}
                    }
                },
                {
                    "name",
                    FieldDefinition{
                        "name",
                        "String!",
                        {}
                    }
                }
            }
        }
    );

    schema.addObjectType(
        ObjectType{
            "Query",
            "Root read operations.",
            {
                {
                    "tasks",
                    FieldDefinition{
                        "tasks",
                        "[Task!]!",
                        {
                            {"completed", "Boolean"},
                            {"priority", "Priority"}
                        }
                    }
                },
                {
                    "task",
                    FieldDefinition{
                        "task",
                        "Task",
                        {{"id", "ID!"}}
                    }
                }
            }
        }
    );

    schema.addObjectType(
        ObjectType{
            "Mutation",
            "Root write operations.",
            {
                {
                    "createTask",
                    FieldDefinition{
                        "createTask",
                        "Task!",
                        {{"input", "CreateTaskInput!"}}
                    }
                },
                {
                    "updateTask",
                    FieldDefinition{
                        "updateTask",
                        "Task!",
                        {
                            {"id", "ID!"},
                            {"completed", "Boolean"},
                            {"title", "String"},
                            {"priority", "Priority"}
                        }
                    }
                }
            }
        }
    );

    schema.addInput(
        InputObjectDefinition{
            "CreateTaskInput",
            {
                {"title", "String!"},
                {"description", "String!"},
                {"priority", "Priority!"},
                {"projectId", "ID!"},
                {"assigneeId", "ID"},
                {"tags", "[String!]"}
            }
        }
    );

    schema.setQueryType("Query");
    schema.setMutationType("Mutation");

    return schema;
}


// ============================================================================
// 18. AUTHORIZATION CASE STUDY
// ============================================================================

void demonstrateAuthorization(
    Repository& repository
) {
    printSection("AUTHORIZATION");

    User guest{
        "u4",
        "Guest",
        "guest@example.com",
        "GUEST"
    };

    RequestContext guestContext{
        guest,
        repository
    };

    CreateTaskInput input{
        "Unauthorized task",
        "This mutation should fail.",
        Priority::LOW,
        "p1",
        nullopt,
        {"security"}
    };

    JsonValue result =
        createTaskMutation(
            guestContext,
            input
        );

    cout << result.toString() << "\n";
}


// ============================================================================
// 19. COMPLEXITY DEMONSTRATION
// ============================================================================

void demonstrateComplexity(
    const RequestContext& context
) {
    printSection(
        "QUERY COMPLEXITY AND DEPTH"
    );

    QueryNode safe{
        "tasks",
        3,
        {
            {"id", 1, {}},
            {"title", 1, {}},
            {
                "project",
                2,
                {
                    {"id", 1, {}},
                    {"name", 1, {}}
                }
            }
        }
    };

    QueryNode expensive{
        "tasks",
        10,
        {
            {
                "project",
                10,
                {
                    {
                        "owner",
                        10,
                        {
                            {
                                "tasks",
                                10,
                                {
                                    {"project", 10, {}}
                                }
                            }
                        }
                    }
                }
            }
        }
    };

    for (const auto& [label, query] :
         vector<pair<string, QueryNode>>{
             {"Safe query", safe},
             {"Potentially expensive query", expensive}
         }) {
        ComplexityResult result =
            calculateComplexity(query);

        cout
            << label
            << ": cost="
            << result.cost
            << ", depth="
            << result.depth
            << ", allowed="
            << boolalpha
            << (
                result.cost <=
                context.queryComplexityLimit
            )
            << "\n";
    }
}


// ============================================================================
// 20. PERFORMANCE MEASUREMENT
// ============================================================================

void benchmarkQueries(
    const RequestContext& context
) {
    printSection("PERFORMANCE CONSIDERATIONS");

    constexpr int iterations = 100000;

    auto start =
        chrono::steady_clock::now();

    for (int i = 0; i < iterations; ++i) {
        volatile auto result =
            queryTasks(
                context,
                nullopt,
                nullopt,
                false
            );

        (void)result;
    }

    auto end =
        chrono::steady_clock::now();

    auto elapsed =
        chrono::duration_cast<
            chrono::microseconds
        >(end - start).count();

    cout
        << iterations
        << " in-memory query executions: "
        << elapsed
        << " microseconds\n";

    cout
        << "This benchmark measures only the "
        << "educational in-memory implementation. "
        << "It is not a production GraphQL benchmark.\n";
}


// ============================================================================
// 21. ERROR HANDLING
// ============================================================================

void demonstrateErrors(
    const RequestContext& context
) {
    printSection("ERROR HANDLING");

    try {
        resolveTasks(
            context,
            nullopt,
            nullopt
        );

        context.repository.getTask(
            "missing"
        );

        throw invalid_argument(
            "Task 'missing' was not found."
        );
    }
    catch (const exception& error) {
        cout
            << "Expected error: "
            << error.what()
            << "\n";
    }

    try {
        CreateTaskInput invalidInput{
            "",
            "Invalid task",
            Priority::HIGH,
            "p1",
            nullopt,
            {}
        };

        validateCreateTaskInput(
            context,
            invalidInput
        );
    }
    catch (const exception& error) {
        cout
            << "Validation error: "
            << error.what()
            << "\n";
    }
}


// ============================================================================
// 22. FULL CASE STUDY
// ============================================================================

void runCaseStudy() {
    Repository repository;

    User currentUser =
        *repository.getUser("u1");

    RequestContext context{
        currentUser,
        repository,
        30
    };

    printSection(
        "GRAPHQL TASK MANAGEMENT CASE STUDY"
    );

    cout
        << "Basic query response:\n";

    cout
        << queryTasks(
            context
        ).toString()
        << "\n";

    cout
        << "\nFiltered query response:\n";

    cout
        << queryTasks(
            context,
            false,
            Priority::HIGH
        ).toString()
        << "\n";

    cout
        << "\nNested query response:\n";

    cout
        << queryTasks(
            context,
            nullopt,
            nullopt,
            true
        ).toString()
        << "\n";

    CreateTaskInput createInput{
        "Run integration tests",
        "Verify the complete API behavior.",
        Priority::HIGH,
        "p1",
        string("u3"),
        {"testing", "graphql"}
    };

    cout
        << "\nCreate mutation response:\n";

    JsonValue createResult =
        createTaskMutation(
            context,
            createInput
        );

    cout
        << createResult.toString()
        << "\n";

    cout
        << "\nUpdate mutation response:\n";

    cout
        << updateTaskMutation(
            context,
            "t5",
            nullopt,
            true,
            nullopt
        ).toString()
        << "\n";

    cout
        << "\nCursor pagination response:\n";

    cout
        << cursorPagination(
            context,
            nullopt,
            3
        ).toString()
        << "\n";

    demonstrateNPlusOne(context);
    demonstrateComplexity(context);
    demonstrateAuthorization(repository);
    demonstrateErrors(context);
    benchmarkQueries(context);
}


// ============================================================================
// 23. MAIN
// ============================================================================

int main() {
    try {
        printSection("GRAPHQL SCHEMA INTROSPECTION");

        Schema schema = createSchema();

        cout
            << schema.introspection().toString()
            << "\n";

        runCaseStudy();

        printSection(
            "GRAPHQL ARCHITECTURAL TRADE-OFFS"
        );

        cout
            << "Advantages include a typed schema, "
            << "client-selected fields, nested selection, "
            << "reusable fragments, and a unified API contract.\n\n";

        cout
            << "Trade-offs include resolver complexity, "
            << "N+1 backend access, variable query cost, "
            << "cache design, authorization complexity, "
            << "and schema governance requirements.\n\n";

        cout
            << "A production system should combine schema design "
            << "with authentication, authorization, validation, "
            << "query budgets, batching, caching, monitoring, "
            << "timeouts, and controlled schema evolution.\n";
    }
    catch (const exception& error) {
        cerr
            << "Fatal application error: "
            << error.what()
            << "\n";

        return 1;
    }

    return 0;
}
