"""
GraphQL: Queries, Mutations, Schemas, Advantages, and Trade-offs
================================================================

A self-contained study and executable demonstration of GraphQL from
beginner concepts through advanced implementation patterns.

This script intentionally avoids external packages so that the core
ideas can be studied without installing a GraphQL server.

The implementation includes:
- GraphQL terminology and architecture
- Schema concepts
- Object types, scalar types, enums, lists, non-null fields
- Queries
- Nested selections
- Arguments
- Variables
- Aliases
- Fragments
- Mutations
- Input objects
- Validation
- Error handling
- Resolver behavior
- Authorization
- Pagination
- N+1 query analysis and batching
- Query complexity
- Introspection concepts
- Caching considerations
- Versioning considerations
- REST versus GraphQL trade-offs
- A small executable GraphQL-like engine
- A realistic task-management API case study

Run:
    python graphql_learning.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
import json
import time


# ============================================================================
# 1. FUNDAMENTAL TERMINOLOGY
# ============================================================================

def print_section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, default=str))


def explain_fundamentals() -> None:
    print_section("1. GRAPHQL FUNDAMENTALS")

    concepts = {
        "GraphQL": (
            "A typed API query language and execution model. Clients describe "
            "the fields they need, and the server returns data matching that shape."
        ),
        "Schema": (
            "The contract describing the types, fields, arguments, inputs, "
            "enums, and root operations available through an API."
        ),
        "Query": "A read operation.",
        "Mutation": "A state-changing operation.",
        "Resolver": (
            "Application logic responsible for obtaining or computing the value "
            "of a schema field."
        ),
        "Type": "A named structure describing valid data.",
        "Field": "A selectable property exposed by a GraphQL type.",
        "Argument": "An input value attached to a field.",
        "Variable": "A runtime value supplied separately from the query document.",
        "Fragment": "A reusable selection set.",
        "Introspection": "The ability to query information about the schema itself.",
        "Selection set": "The set of fields requested inside braces.",
    }

    for name, definition in concepts.items():
        print(f"{name}: {definition}")


# ============================================================================
# 2. GRAPHQL TYPE SYSTEM
# ============================================================================

class ScalarKind(Enum):
    STRING = "String"
    INT = "Int"
    FLOAT = "Float"
    BOOLEAN = "Boolean"
    ID = "ID"


@dataclass
class GraphQLType:
    name: str
    description: str = ""


@dataclass
class ScalarType(GraphQLType):
    kind: ScalarKind = ScalarKind.STRING


@dataclass
class EnumType(GraphQLType):
    values: Tuple[str, ...] = ()


@dataclass
class FieldDefinition:
    name: str
    type_name: str
    description: str = ""
    arguments: Dict[str, str] = field(default_factory=dict)
    resolver: Optional[Callable[..., Any]] = None


@dataclass
class ObjectType(GraphQLType):
    fields: Dict[str, FieldDefinition] = field(default_factory=dict)


@dataclass
class InputObjectType(GraphQLType):
    fields: Dict[str, str] = field(default_factory=dict)


class GraphQLSchema:
    """
    Minimal schema registry.

    A real GraphQL implementation performs formal parsing, validation,
    execution, coercion, introspection, directives, subscriptions, and
    many other responsibilities. This educational registry focuses on
    the conceptual structure of a schema.
    """

    def __init__(self) -> None:
        self.types: Dict[str, GraphQLType] = {}
        self.query_type: Optional[str] = None
        self.mutation_type: Optional[str] = None

    def register(self, graph_type: GraphQLType) -> None:
        if graph_type.name in self.types:
            raise ValueError(f"Type already exists: {graph_type.name}")
        self.types[graph_type.name] = graph_type

    def set_query_type(self, type_name: str) -> None:
        self.query_type = type_name

    def set_mutation_type(self, type_name: str) -> None:
        self.mutation_type = type_name

    def get_type(self, type_name: str) -> GraphQLType:
        try:
            return self.types[type_name]
        except KeyError:
            raise ValueError(f"Unknown GraphQL type: {type_name}") from None


def demonstrate_type_system() -> None:
    print_section("2. GRAPHQL TYPE SYSTEM")

    scalar_examples = [
        ScalarType("String", "UTF-8 text", ScalarKind.STRING),
        ScalarType("Int", "Signed 32-bit integer in standard GraphQL", ScalarKind.INT),
        ScalarType("Float", "Double-precision floating-point value", ScalarKind.FLOAT),
        ScalarType("Boolean", "true or false", ScalarKind.BOOLEAN),
        ScalarType("ID", "Unique identifier represented as a string-like scalar", ScalarKind.ID),
    ]

    for scalar in scalar_examples:
        print(f"{scalar.name}: {scalar.description}")

    priority = EnumType(
        name="Priority",
        description="Allowed task priorities",
        values=("LOW", "MEDIUM", "HIGH", "CRITICAL"),
    )

    task = ObjectType(
        name="Task",
        description="A task in the task-management system",
        fields={
            "id": FieldDefinition("id", "ID!"),
            "title": FieldDefinition("title", "String!"),
            "completed": FieldDefinition("completed", "Boolean!"),
            "priority": FieldDefinition("priority", "Priority!"),
        },
    )

    print("\nExample enum:")
    print(priority)

    print("\nExample object type:")
    for field_name, definition in task.fields.items():
        print(f"  {field_name}: {definition.type_name}")


# ============================================================================
# 3. NULLABILITY, LISTS, AND TYPE MODIFIERS
# ============================================================================

def explain_type_modifiers() -> None:
    print_section("3. NULLABILITY AND LISTS")

    examples = {
        "String": "A nullable string.",
        "String!": "A non-null string. The field must not return null.",
        "[String]": "A nullable list containing nullable strings.",
        "[String!]": "A nullable list whose elements cannot be null.",
        "[String!]!": "A non-null list whose elements cannot be null.",
        "[Task!]!": "A required list of required Task objects.",
    }

    for syntax, meaning in examples.items():
        print(f"{syntax:<14} -> {meaning}")

    print(
        "\nNullability is part of the schema contract. It influences validation, "
        "execution behavior, and how clients handle failures."
    )


# ============================================================================
# 4. DATA MODEL
# ============================================================================

class Priority(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class User:
    id: str
    name: str
    email: str
    role: str


@dataclass
class Project:
    id: str
    name: str
    owner_id: str


@dataclass
class Task:
    id: str
    title: str
    description: str
    completed: bool
    priority: Priority
    project_id: str
    assignee_id: Optional[str]
    tags: List[str]
    created_at: str


class Repository:
    """In-memory repository used to make resolver behavior observable."""

    def __init__(self) -> None:
        self.users: Dict[str, User] = {
            "u1": User("u1", "Atul", "atul@example.com", "ADMIN"),
            "u2": User("u2", "Priya", "priya@example.com", "MEMBER"),
            "u3": User("u3", "Rahul", "rahul@example.com", "MEMBER"),
        }

        self.projects: Dict[str, Project] = {
            "p1": Project("p1", "GraphQL Platform", "u1"),
            "p2": Project("p2", "Analytics Platform", "u2"),
        }

        self.tasks: Dict[str, Task] = {
            "t1": Task(
                "t1",
                "Design schema",
                "Define the public API contract",
                False,
                Priority.HIGH,
                "p1",
                "u1",
                ["graphql", "architecture"],
                "2026-09-20",
            ),
            "t2": Task(
                "t2",
                "Implement resolvers",
                "Connect schema fields to application logic",
                False,
                Priority.CRITICAL,
                "p1",
                "u2",
                ["graphql", "backend"],
                "2026-09-21",
            ),
            "t3": Task(
                "t3",
                "Write documentation",
                "Explain API behavior and trade-offs",
                True,
                Priority.MEDIUM,
                "p1",
                "u3",
                ["documentation"],
                "2026-09-22",
            ),
            "t4": Task(
                "t4",
                "Create metrics",
                "Track application-level statistics",
                False,
                Priority.LOW,
                "p2",
                None,
                ["analytics"],
                "2026-09-23",
            ),
        }

        self.next_task_number = 5

    def all_tasks(self) -> List[Task]:
        return list(self.tasks.values())

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def create_task(
        self,
        title: str,
        description: str,
        priority: Priority,
        project_id: str,
        assignee_id: Optional[str],
        tags: List[str],
    ) -> Task:
        task_id = f"t{self.next_task_number}"
        self.next_task_number += 1

        task = Task(
            id=task_id,
            title=title,
            description=description,
            completed=False,
            priority=priority,
            project_id=project_id,
            assignee_id=assignee_id,
            tags=tags,
            created_at="2026-09-26",
        )
        self.tasks[task_id] = task
        return task

    def update_task(
        self,
        task_id: str,
        title: Optional[str] = None,
        completed: Optional[bool] = None,
        priority: Optional[Priority] = None,
    ) -> Task:
        task = self.get_task(task_id)

        if task is None:
            raise ValueError("Task does not exist.")

        if title is not None:
            task.title = title

        if completed is not None:
            task.completed = completed

        if priority is not None:
            task.priority = priority

        return task


# ============================================================================
# 5. RESOLVERS
# ============================================================================

class AuthorizationError(Exception):
    """Raised when a caller lacks permission to perform an operation."""


class ValidationError(Exception):
    """Raised when client-provided GraphQL input is invalid."""


@dataclass
class RequestContext:
    user: User
    repository: Repository
    query_complexity_limit: int = 30


class ResolverCounter:
    """Counts resolver/repository calls to illustrate the N+1 problem."""

    def __init__(self) -> None:
        self.project_calls = 0
        self.user_calls = 0

    def reset(self) -> None:
        self.project_calls = 0
        self.user_calls = 0


def require_role(context: RequestContext, *allowed_roles: str) -> None:
    if context.user.role not in allowed_roles:
        raise AuthorizationError(
            f"Role {context.user.role} is not authorized for this operation."
        )


def resolve_tasks(
    context: RequestContext,
    completed: Optional[bool] = None,
    priority: Optional[Priority] = None,
) -> List[Task]:
    tasks = context.repository.all_tasks()

    if completed is not None:
        tasks = [task for task in tasks if task.completed == completed]

    if priority is not None:
        tasks = [task for task in tasks if task.priority == priority]

    return tasks


def resolve_task(context: RequestContext, task_id: str) -> Task:
    task = context.repository.get_task(task_id)

    if task is None:
        raise ValidationError(f"Task '{task_id}' was not found.")

    return task


def resolve_project(
    task: Task,
    context: RequestContext,
    counter: Optional[ResolverCounter] = None,
) -> Optional[Project]:
    if counter:
        counter.project_calls += 1

    return context.repository.projects.get(task.project_id)


def resolve_assignee(
    task: Task,
    context: RequestContext,
    counter: Optional[ResolverCounter] = None,
) -> Optional[User]:
    if task.assignee_id is None:
        return None

    if counter:
        counter.user_calls += 1

    return context.repository.users.get(task.assignee_id)


def resolve_create_task(
    context: RequestContext,
    title: str,
    description: str,
    priority: Priority,
    project_id: str,
    assignee_id: Optional[str],
    tags: List[str],
) -> Task:
    require_role(context, "ADMIN", "MEMBER")

    if not title.strip():
        raise ValidationError("title cannot be empty.")

    if project_id not in context.repository.projects:
        raise ValidationError("project_id does not identify an existing project.")

    if assignee_id is not None and assignee_id not in context.repository.users:
        raise ValidationError("assignee_id does not identify an existing user.")

    if len(tags) > 10:
        raise ValidationError("A task may contain at most 10 tags.")

    return context.repository.create_task(
        title=title.strip(),
        description=description.strip(),
        priority=priority,
        project_id=project_id,
        assignee_id=assignee_id,
        tags=tags,
    )


def resolve_update_task(
    context: RequestContext,
    task_id: str,
    title: Optional[str],
    completed: Optional[bool],
    priority: Optional[Priority],
) -> Task:
    require_role(context, "ADMIN", "MEMBER")

    if title is not None and not title.strip():
        raise ValidationError("title cannot be empty.")

    return context.repository.update_task(
        task_id=task_id,
        title=title.strip() if title is not None else None,
        completed=completed,
        priority=priority,
    )


# ============================================================================
# 6. QUERY EXAMPLES
# ============================================================================

def query_basic_tasks(context: RequestContext) -> Dict[str, Any]:
    """
    Conceptual GraphQL request:

        query {
          tasks {
            id
            title
            completed
          }
        }

    GraphQL lets the client request a precise response shape.
    """

    tasks = resolve_tasks(context)

    return {
        "data": {
            "tasks": [
                {
                    "id": task.id,
                    "title": task.title,
                    "completed": task.completed,
                }
                for task in tasks
            ]
        }
    }


def query_with_arguments(
    context: RequestContext,
    completed: bool,
    priority: Optional[Priority] = None,
) -> Dict[str, Any]:
    """
    Conceptual query:

        query Tasks($completed: Boolean!, $priority: Priority) {
          tasks(completed: $completed, priority: $priority) {
            id
            title
            priority
          }
        }

    Variables keep data separate from the query document.
    """

    tasks = resolve_tasks(
        context,
        completed=completed,
        priority=priority,
    )

    return {
        "data": {
            "tasks": [
                {
                    "id": task.id,
                    "title": task.title,
                    "priority": task.priority.value,
                }
                for task in tasks
            ]
        }
    }


def query_nested_data(
    context: RequestContext,
    counter: Optional[ResolverCounter] = None,
) -> Dict[str, Any]:
    """
    Conceptual nested selection:

        query {
          tasks {
            id
            title
            project {
              id
              name
            }
            assignee {
              id
              name
            }
          }
        }

    Nested fields are resolved independently according to their schema.
    """

    tasks = resolve_tasks(context)

    response_tasks = []

    for task in tasks:
        project = resolve_project(task, context, counter)
        assignee = resolve_assignee(task, context, counter)

        response_tasks.append(
            {
                "id": task.id,
                "title": task.title,
                "project": (
                    {
                        "id": project.id,
                        "name": project.name,
                    }
                    if project
                    else None
                ),
                "assignee": (
                    {
                        "id": assignee.id,
                        "name": assignee.name,
                    }
                    if assignee
                    else None
                ),
            }
        )

    return {"data": {"tasks": response_tasks}}


# ============================================================================
# 7. ALIASES
# ============================================================================

def demonstrate_aliases(context: RequestContext) -> Dict[str, Any]:
    """
    GraphQL aliases allow the same field to appear multiple times under
    different response keys.

    Conceptual query:

        query {
          pending: tasks(completed: false) {
            id
            title
          }
          completed: tasks(completed: true) {
            id
            title
          }
        }
    """

    pending = resolve_tasks(context, completed=False)
    completed = resolve_tasks(context, completed=True)

    return {
        "data": {
            "pending": [{"id": t.id, "title": t.title} for t in pending],
            "completed": [{"id": t.id, "title": t.title} for t in completed],
        }
    }


# ============================================================================
# 8. FRAGMENTS
# ============================================================================

TASK_SUMMARY_FRAGMENT = {
    "id": True,
    "title": True,
    "completed": True,
    "priority": True,
}


def demonstrate_fragment(context: RequestContext) -> Dict[str, Any]:
    """
    Conceptual GraphQL fragment:

        fragment TaskSummary on Task {
          id
          title
          completed
          priority
        }

    Fragments reduce repeated selection definitions in larger documents.
    """

    tasks = resolve_tasks(context)

    return {
        "data": {
            "tasks": [
                {
                    key: (
                        task.priority.value
                        if key == "priority"
                        else getattr(task, key)
                    )
                    for key in TASK_SUMMARY_FRAGMENT
                }
                for task in tasks
            ]
        }
    }


# ============================================================================
# 9. INPUT OBJECTS
# ============================================================================

@dataclass
class CreateTaskInput:
    title: str
    description: str
    priority: Priority
    project_id: str
    assignee_id: Optional[str]
    tags: List[str]


def validate_create_task_input(data: Dict[str, Any]) -> CreateTaskInput:
    required_fields = {
        "title",
        "description",
        "priority",
        "project_id",
    }

    missing = required_fields - data.keys()

    if missing:
        raise ValidationError(
            f"Missing required input fields: {sorted(missing)}"
        )

    try:
        priority = Priority(data["priority"])
    except ValueError:
        raise ValidationError(
            f"Invalid priority: {data['priority']}"
        ) from None

    tags = data.get("tags", [])

    if not isinstance(tags, list):
        raise ValidationError("tags must be a list.")

    return CreateTaskInput(
        title=str(data["title"]),
        description=str(data["description"]),
        priority=priority,
        project_id=str(data["project_id"]),
        assignee_id=(
            str(data["assignee_id"])
            if data.get("assignee_id") is not None
            else None
        ),
        tags=[str(tag) for tag in tags],
    )


# ============================================================================
# 10. MUTATIONS
# ============================================================================

def mutation_create_task(
    context: RequestContext,
    input_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Conceptual mutation:

        mutation CreateTask($input: CreateTaskInput!) {
          createTask(input: $input) {
            id
            title
            priority
            completed
          }
        }

    Mutations represent state changes.
    """

    try:
        validated = validate_create_task_input(input_data)

        task = resolve_create_task(
            context=context,
            title=validated.title,
            description=validated.description,
            priority=validated.priority,
            project_id=validated.project_id,
            assignee_id=validated.assignee_id,
            tags=validated.tags,
        )

        return {
            "data": {
                "createTask": {
                    "id": task.id,
                    "title": task.title,
                    "priority": task.priority.value,
                    "completed": task.completed,
                }
            }
        }

    except (ValidationError, AuthorizationError) as error:
        return {
            "data": None,
            "errors": [{"message": str(error)}],
        }


def mutation_update_task(
    context: RequestContext,
    task_id: str,
    title: Optional[str] = None,
    completed: Optional[bool] = None,
    priority: Optional[str] = None,
) -> Dict[str, Any]:
    """Update mutation with explicit validation and error conversion."""

    try:
        parsed_priority = (
            Priority(priority)
            if priority is not None
            else None
        )

        task = resolve_update_task(
            context=context,
            task_id=task_id,
            title=title,
            completed=completed,
            priority=parsed_priority,
        )

        return {
            "data": {
                "updateTask": {
                    "id": task.id,
                    "title": task.title,
                    "completed": task.completed,
                    "priority": task.priority.value,
                }
            }
        }

    except (ValueError, ValidationError, AuthorizationError) as error:
        return {
            "data": None,
            "errors": [{"message": str(error)}],
        }


# ============================================================================
# 11. ERROR HANDLING
# ============================================================================

def demonstrate_errors(context: RequestContext) -> None:
    print_section("11. GRAPHQL ERRORS")

    successful = query_basic_tasks(context)
    print("Successful operation:")
    print_json(successful)

    print("\nApplication-level validation error:")
    print_json(
        mutation_update_task(
            context=context,
            task_id="does-not-exist",
            completed=True,
        )
    )

    print(
        "\nGraphQL commonly returns a response containing a data member and, "
        "when appropriate, an errors member. Exact behavior depends on the "
        "server implementation and the location of the failure."
    )


# ============================================================================
# 12. AUTHORIZATION
# ============================================================================

def demonstrate_authorization(repository: Repository) -> None:
    print_section("12. AUTHORIZATION")

    admin_context = RequestContext(repository.users["u1"], repository)

    member_context = RequestContext(repository.users["u2"], repository)

    guest = User("u4", "Guest", "guest@example.com", "GUEST")
    repository.users[guest.id] = guest
    guest_context = RequestContext(guest, repository)

    input_data = {
        "title": "Security review",
        "description": "Review authorization behavior",
        "priority": "HIGH",
        "project_id": "p1",
        "assignee_id": "u1",
        "tags": ["security"],
    }

    print("Admin mutation:")
    print_json(mutation_create_task(admin_context, input_data))

    print("\nMember mutation:")
    print_json(mutation_create_task(member_context, input_data))

    print("\nGuest mutation:")
    print_json(mutation_create_task(guest_context, input_data))

    print(
        "\nAuthorization should be enforced by application logic, not merely "
        "assumed because a field exists in the GraphQL schema."
    )


# ============================================================================
# 13. N+1 QUERY PROBLEM
# ============================================================================

class BatchLoader:
    """
    Simple DataLoader-like implementation.

    Instead of resolving each user separately, IDs are collected and loaded
    together. Production DataLoader implementations also address caching and
    request-scoped batching.
    """

    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.request_count = 0

    def load_many(self, user_ids: Iterable[str]) -> Dict[str, User]:
        self.request_count += 1

        unique_ids = set(user_ids)

        return {
            user_id: self.repository.users[user_id]
            for user_id in unique_ids
            if user_id in self.repository.users
        }


def demonstrate_n_plus_one(context: RequestContext) -> None:
    print_section("13. N+1 QUERY PROBLEM")

    counter = ResolverCounter()

    query_nested_data(context, counter)

    print(f"Individual project lookups: {counter.project_calls}")
    print(f"Individual user lookups:    {counter.user_calls}")

    tasks = resolve_tasks(context)

    loader = BatchLoader(context.repository)

    user_ids = [
        task.assignee_id
        for task in tasks
        if task.assignee_id is not None
    ]

    users = loader.load_many(user_ids)

    print(f"\nBatched user requests:      {loader.request_count}")
    print(f"Users returned by batch:    {len(users)}")

    print(
        "\nThe N+1 problem occurs when resolving one parent collection causes "
        "one additional database request per child. Batching can reduce many "
        "small requests into a smaller number of grouped operations."
    )


# ============================================================================
# 14. PAGINATION
# ============================================================================

def offset_pagination(
    context: RequestContext,
    offset: int,
    limit: int,
) -> Dict[str, Any]:
    """
    Offset pagination is easy to understand:

        tasks(offset: 20, limit: 10)

    It can become inefficient or inconsistent for rapidly changing datasets.
    """

    if offset < 0 or limit <= 0:
        raise ValidationError("offset must be >= 0 and limit must be > 0.")

    tasks = resolve_tasks(context)
    page = tasks[offset: offset + limit]

    return {
        "items": [
            {"id": task.id, "title": task.title}
            for task in page
        ],
        "offset": offset,
        "limit": limit,
        "total": len(tasks),
    }


def cursor_pagination(
    context: RequestContext,
    after_id: Optional[str],
    first: int,
) -> Dict[str, Any]:
    """
    Cursor-style pagination models a position in the result set.

    A production cursor should usually be opaque rather than exposing a
    database implementation detail directly.
    """

    if first <= 0:
        raise ValidationError("first must be greater than zero.")

    tasks = sorted(resolve_tasks(context), key=lambda task: task.id)

    start_index = 0

    if after_id is not None:
        ids = [task.id for task in tasks]

        if after_id not in ids:
            raise ValidationError("Unknown cursor.")

        start_index = ids.index(after_id) + 1

    page = tasks[start_index:start_index + first]
    has_next_page = start_index + first < len(tasks)

    edges = [
        {
            "cursor": task.id,
            "node": {
                "id": task.id,
                "title": task.title,
            },
        }
        for task in page
    ]

    return {
        "edges": edges,
        "pageInfo": {
            "hasNextPage": has_next_page,
            "startCursor": page[0].id if page else None,
            "endCursor": page[-1].id if page else None,
        },
    }


def demonstrate_pagination(context: RequestContext) -> None:
    print_section("14. PAGINATION")

    print("Offset pagination:")
    print_json(offset_pagination(context, offset=0, limit=2))

    print("\nCursor pagination:")
    print_json(cursor_pagination(context, after_id=None, first=2))


# ============================================================================
# 15. QUERY COMPLEXITY AND DEPTH
# ============================================================================

@dataclass
class QueryField:
    name: str
    children: List["QueryField"] = field(default_factory=list)
    cost: int = 1


def calculate_query_cost(
    field: QueryField,
    depth: int = 1,
) -> Tuple[int, int]:
    """
    A production GraphQL server can limit query depth and estimated cost.

    This does not replace authorization or rate limiting. It is a resource
    protection mechanism.
    """

    total_cost = field.cost
    maximum_depth = depth

    for child in field.children:
        child_cost, child_depth = calculate_query_cost(child, depth + 1)
        total_cost += child_cost
        maximum_depth = max(maximum_depth, child_depth)

    return total_cost, maximum_depth


def demonstrate_query_complexity(context: RequestContext) -> None:
    print_section("15. QUERY COMPLEXITY")

    safe_query = QueryField(
        "tasks",
        children=[
            QueryField("id"),
            QueryField("title"),
            QueryField(
                "project",
                children=[
                    QueryField("id"),
                    QueryField("name"),
                ],
            ),
        ],
        cost=3,
    )

    expensive_query = QueryField(
        "tasks",
        children=[
            QueryField(
                "project",
                children=[
                    QueryField(
                        "owner",
                        children=[
                            QueryField(
                                "tasks",
                                children=[
                                    QueryField(
                                        "project",
                                        children=[QueryField("owner")],
                                        cost=10,
                                    )
                                ],
                                cost=10,
                            )
                        ],
                        cost=10,
                    )
                ],
                cost=10,
            )
        ],
        cost=10,
    )

    for label, query in [
        ("Safe query", safe_query),
        ("Potentially expensive query", expensive_query),
    ]:
        cost, depth = calculate_query_cost(query)
        allowed = cost <= context.query_complexity_limit

        print(
            f"{label}: cost={cost}, depth={depth}, "
            f"allowed={allowed}"
        )


# ============================================================================
# 16. INTROSPECTION
# ============================================================================

def build_demo_schema() -> GraphQLSchema:
    schema = GraphQLSchema()

    for scalar in [
        ScalarType("String", "Text", ScalarKind.STRING),
        ScalarType("Int", "Integer", ScalarKind.INT),
        ScalarType("Boolean", "Boolean", ScalarKind.BOOLEAN),
        ScalarType("ID", "Identifier", ScalarKind.ID),
    ]:
        schema.register(scalar)

    schema.register(
        EnumType(
            "Priority",
            "Task priority",
            ("LOW", "MEDIUM", "HIGH", "CRITICAL"),
        )
    )

    schema.register(
        ObjectType(
            "Task",
            "Task object",
            {
                "id": FieldDefinition("id", "ID!"),
                "title": FieldDefinition("title", "String!"),
                "completed": FieldDefinition("completed", "Boolean!"),
                "priority": FieldDefinition("priority", "Priority!"),
            },
        )
    )

    schema.register(
        ObjectType(
            "Query",
            "Root read operations",
            {
                "tasks": FieldDefinition(
                    "tasks",
                    "[Task!]!",
                    arguments={
                        "completed": "Boolean",
                        "priority": "Priority",
                    },
                ),
                "task": FieldDefinition(
                    "task",
                    "Task",
                    arguments={"id": "ID!"},
                ),
            },
        )
    )

    schema.register(
        ObjectType(
            "Mutation",
            "Root state-changing operations",
            {
                "createTask": FieldDefinition(
                    "createTask",
                    "Task!",
                    arguments={"input": "CreateTaskInput!"},
                ),
                "updateTask": FieldDefinition(
                    "updateTask",
                    "Task!",
                    arguments={"id": "ID!"},
                ),
            },
        )
    )

    schema.register(
        InputObjectType(
            "CreateTaskInput",
            "Input required to create a task",
            {
                "title": "String!",
                "description": "String!",
                "priority": "Priority!",
                "project_id": "ID!",
                "assignee_id": "ID",
                "tags": "[String!]",
            },
        )
    )

    schema.set_query_type("Query")
    schema.set_mutation_type("Mutation")

    return schema


def introspect_schema(schema: GraphQLSchema) -> Dict[str, Any]:
    """
    Simplified introspection representation.

    Real GraphQL servers expose a standardized introspection system using
    meta-fields such as __schema and __type.
    """

    result = {
        "queryType": schema.query_type,
        "mutationType": schema.mutation_type,
        "types": [],
    }

    for type_name, graph_type in sorted(schema.types.items()):
        entry: Dict[str, Any] = {
            "name": type_name,
            "kind": type(graph_type).__name__,
        }

        if isinstance(graph_type, ObjectType):
            entry["fields"] = {
                field_name: {
                    "type": definition.type_name,
                    "arguments": definition.arguments,
                }
                for field_name, definition in graph_type.fields.items()
            }

        if isinstance(graph_type, InputObjectType):
            entry["inputFields"] = graph_type.fields

        if isinstance(graph_type, EnumType):
            entry["values"] = graph_type.values

        result["types"].append(entry)

    return result


def demonstrate_introspection() -> None:
    print_section("16. INTROSPECTION")

    schema = build_demo_schema()
    result = introspect_schema(schema)

    print_json(result)


# ============================================================================
# 17. DIRECTIVE-LIKE BEHAVIOR
# ============================================================================

def redact_email(email: str, can_view_email: bool) -> Optional[str]:
    """
    Schema directives can be used for metadata and behavior.

    This function models one possible authorization-related transformation.
    A real server should enforce sensitive-field authorization in a robust
    application layer rather than trusting clients.
    """

    return email if can_view_email else None


def demonstrate_sensitive_field_control(context: RequestContext) -> None:
    print_section("17. FIELD-LEVEL SECURITY")

    for user in context.repository.users.values():
        can_view_email = (
            context.user.role == "ADMIN"
            or context.user.id == user.id
        )

        print(
            user.name,
            "->",
            redact_email(user.email, can_view_email),
        )


# ============================================================================
# 18. REST VERSUS GRAPHQL
# ============================================================================

def compare_rest_and_graphql() -> None:
    print_section("18. REST VERSUS GRAPHQL")

    comparison = [
        (
            "Data selection",
            "Often endpoint-defined",
            "Client selects fields",
        ),
        (
            "Endpoint model",
            "Usually multiple resource endpoints",
            "Often one GraphQL endpoint",
        ),
        (
            "Schema",
            "May use OpenAPI or other contracts",
            "Schema is central to GraphQL",
        ),
        (
            "Over-fetching",
            "Can occur depending on endpoint design",
            "Client can request a smaller selection",
        ),
        (
            "Under-fetching",
            "May require multiple requests",
            "Nested selections can combine related data",
        ),
        (
            "HTTP caching",
            "Naturally aligned with HTTP semantics",
            "Requires more deliberate operation-aware caching",
        ),
        (
            "Operational simplicity",
            "Often straightforward",
            "Requires query parsing, validation, and execution",
        ),
        (
            "Resource protection",
            "Endpoint-specific controls",
            "Query depth and complexity controls may be necessary",
        ),
    ]

    print(f"{'Dimension':<24} {'REST':<34} GraphQL")
    print("-" * 92)

    for dimension, rest, graphql in comparison:
        print(f"{dimension:<24} {rest:<34} {graphql}")


# ============================================================================
# 19. ADVANTAGES AND TRADE-OFFS
# ============================================================================

def explain_advantages_and_tradeoffs() -> None:
    print_section("19. ADVANTAGES AND TRADE-OFFS")

    advantages = [
        "Strong schema contract",
        "Client-controlled field selection",
        "Natural support for nested related data",
        "Typed variables and inputs",
        "Introspection",
        "Reusable fragments",
        "Potentially fewer client round trips for related data",
        "A unified API surface over multiple backend systems",
    ]

    tradeoffs = [
        "More complex server execution model",
        "Query complexity can vary substantially",
        "Caching requires careful design",
        "N+1 resolver problems can occur",
        "Authorization can become field- and object-specific",
        "Deep or expensive queries can consume significant resources",
        "Schema evolution requires disciplined deprecation practices",
        "A single endpoint does not automatically mean a simple backend",
    ]

    print("Potential advantages:")
    for item in advantages:
        print(f"  + {item}")

    print("\nImportant trade-offs:")
    for item in tradeoffs:
        print(f"  - {item}")


# ============================================================================
# 20. PERFORMANCE
# ============================================================================

def benchmark_selection_shapes(context: RequestContext) -> None:
    print_section("20. PERFORMANCE CONSIDERATIONS")

    start = time.perf_counter()
    for _ in range(10_000):
        query_basic_tasks(context)
    basic_duration = time.perf_counter() - start

    start = time.perf_counter()
    for _ in range(10_000):
        query_nested_data(context)
    nested_duration = time.perf_counter() - start

    print(f"10,000 basic query executions:   {basic_duration:.6f} seconds")
    print(f"10,000 nested query executions:  {nested_duration:.6f} seconds")

    print(
        "\nThis microbenchmark measures only this in-memory demonstration. "
        "It does not represent database, network, serialization, or production "
        "GraphQL-server performance."
    )


# ============================================================================
# 21. SECURITY CHECKLIST
# ============================================================================

def print_security_checklist() -> None:
    print_section("21. GRAPHQL SECURITY")

    controls = [
        "Authenticate every request where protected data is involved.",
        "Authorize fields and objects according to the caller's permissions.",
        "Validate scalar and input values.",
        "Limit query depth.",
        "Limit query complexity or estimated execution cost.",
        "Apply rate limits and resource budgets.",
        "Prevent excessive pagination sizes.",
        "Protect introspection appropriately for the deployment context.",
        "Avoid exposing sensitive fields accidentally.",
        "Use timeouts and cancellation for expensive work.",
        "Monitor resolver and backend query behavior.",
        "Avoid leaking internal database errors directly to clients.",
        "Use persisted or allow-listed operations where the threat model requires them.",
    ]

    for index, control in enumerate(controls, start=1):
        print(f"{index:>2}. {control}")


# ============================================================================
# 22. DEBUGGING
# ============================================================================

def demonstrate_debugging(context: RequestContext) -> None:
    print_section("22. DEBUGGING GRAPHQL")

    try:
        resolve_task(context, "missing-id")
    except ValidationError as error:
        print("Caught expected application error:")
        print(f"  {error}")

    try:
        validate_create_task_input(
            {
                "title": "Invalid task",
                "description": "Missing priority",
                "project_id": "p1",
            }
        )
    except ValidationError as error:
        print("\nCaught expected validation error:")
        print(f"  {error}")

    print(
        "\nUseful debugging dimensions include the operation document, "
        "variables, schema validation, resolver execution, downstream "
        "database calls, authorization, serialization, and response errors."
    )


# ============================================================================
# 23. PRODUCTION DESIGN
# ============================================================================

def print_production_considerations() -> None:
    print_section("23. PRODUCTION DESIGN CONSIDERATIONS")

    areas = {
        "Schema design": (
            "Model stable domain concepts, choose nullability deliberately, "
            "and expose meaningful names."
        ),
        "Resolvers": (
            "Keep resolvers focused on orchestration and delegate business "
            "rules to application services where appropriate."
        ),
        "Data access": (
            "Use batching, caching, appropriate indexes, and efficient queries."
        ),
        "Authorization": (
            "Enforce access policies consistently at the application/domain layer."
        ),
        "Observability": (
            "Measure operation names, latency, resolver cost, backend calls, "
            "errors, and resource usage."
        ),
        "Evolution": (
            "Prefer additive changes and use deprecation before removing fields."
        ),
        "Caching": (
            "Consider HTTP, response, resolver, and normalized client caches "
            "as separate concerns."
        ),
        "Operations": (
            "Use timeouts, rate limits, query budgets, persisted operations, "
            "and appropriate deployment controls."
        ),
    }

    for area, explanation in areas.items():
        print(f"{area}: {explanation}")


# ============================================================================
# 24. COMPLETE CASE STUDY
# ============================================================================

def run_case_study() -> None:
    print_section("24. COMPLETE TASK MANAGEMENT CASE STUDY")

    repository = Repository()
    context = RequestContext(
        user=repository.users["u1"],
        repository=repository,
        query_complexity_limit=30,
    )

    print("Initial tasks:")
    print_json(query_basic_tasks(context))

    print("\nFiltered tasks using arguments:")
    print_json(
        query_with_arguments(
            context,
            completed=False,
            priority=Priority.HIGH,
        )
    )

    print("\nNested task data:")
    print_json(query_nested_data(context))

    print("\nAliases:")
    print_json(demonstrate_aliases(context))

    print("\nFragment-style response:")
    print_json(demonstrate_fragment(context))

    print("\nCreate mutation:")
    create_result = mutation_create_task(
        context,
        {
            "title": "Run integration tests",
            "description": "Verify the complete GraphQL API behavior",
            "priority": "HIGH",
            "project_id": "p1",
            "assignee_id": "u3",
            "tags": ["testing", "graphql"],
        },
    )
    print_json(create_result)

    created_id = create_result["data"]["createTask"]["id"]

    print("\nUpdate mutation:")
    print_json(
        mutation_update_task(
            context,
            task_id=created_id,
            completed=True,
        )
    )

    print("\nPagination:")
    print_json(cursor_pagination(context, after_id=None, first=3))


# ============================================================================
# 25. MAIN PROGRAM
# ============================================================================

def main() -> None:
    explain_fundamentals()
    demonstrate_type_system()
    explain_type_modifiers()

    repository = Repository()
    context = RequestContext(
        user=repository.users["u1"],
        repository=repository,
    )

    run_case_study()
    demonstrate_errors(context)
    demonstrate_authorization(repository)
    demonstrate_n_plus_one(context)
    demonstrate_pagination(context)
    demonstrate_query_complexity(context)
    demonstrate_introspection()
    demonstrate_sensitive_field_control(context)
    compare_rest_and_graphql()
    explain_advantages_and_tradeoffs()
    benchmark_selection_shapes(context)
    print_security_checklist()
    demonstrate_debugging(context)
    print_production_considerations()

    print_section("26. STUDY NOTES")
    print(
        "The central GraphQL idea is that a typed schema defines what can be "
        "requested, while the client supplies a selection describing the "
        "response shape. Queries read data, mutations change state, and "
        "resolvers connect schema fields to application behavior."
    )


if __name__ == "__main__":
    main()
