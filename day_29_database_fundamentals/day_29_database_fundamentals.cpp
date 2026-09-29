/*
 * Database Fundamentals: Tables, Records, Schemas, and Queries
 *
 * C++17 industry-style case study:
 * Employee Operations Database
 *
 * The program models a small relational database system in memory. It
 * demonstrates how database concepts can be represented in a strongly typed
 * systems language:
 *
 *   - schemas
 *   - tables and records
 *   - primary keys
 *   - foreign keys
 *   - uniqueness
 *   - validation
 *   - CRUD operations
 *   - filtering and sorting
 *   - joins
 *   - aggregation
 *   - transactions and rollback
 *   - indexes
 *   - normalization
 *   - complexity and design trade-offs
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic database_fundamentals.cpp -o database_fundamentals
 */

#include <algorithm>
#include <cmath>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using namespace std;

class DatabaseError : public runtime_error {
public:
    explicit DatabaseError(const string& message)
        : runtime_error(message) {}
};

class ConstraintError : public DatabaseError {
public:
    explicit ConstraintError(const string& message)
        : DatabaseError(message) {}
};

class TransactionError : public DatabaseError {
public:
    explicit TransactionError(const string& message)
        : DatabaseError(message) {}
};

struct Department {
    int id;
    string name;
    double budget;
};

struct Employee {
    int id;
    int departmentId;
    string firstName;
    string lastName;
    string email;
    double salary;
    bool active;
};

struct Project {
    int id;
    string name;
    double budget;
    string status;
};

struct EmployeeProject {
    int employeeId;
    int projectId;
    string assignedOn;
    string role;
};

struct Account {
    int id;
    string owner;
    double balance;
};

class EmployeeDatabase {
private:
    vector<Department> departments;
    vector<Employee> employees;
    vector<Project> projects;
    vector<EmployeeProject> assignments;
    vector<Account> accounts;

    unordered_map<int, size_t> employeeIndex;
    unordered_map<int, size_t> departmentIndex;
    unordered_map<int, size_t> projectIndex;

    bool transactionActive = false;

    vector<Department> savedDepartments;
    vector<Employee> savedEmployees;
    vector<Project> savedProjects;
    vector<EmployeeProject> savedAssignments;
    vector<Account> savedAccounts;

    void rebuildIndexes() {
        employeeIndex.clear();
        departmentIndex.clear();
        projectIndex.clear();

        for (size_t i = 0; i < employees.size(); ++i) {
            employeeIndex[employees[i].id] = i;
        }

        for (size_t i = 0; i < departments.size(); ++i) {
            departmentIndex[departments[i].id] = i;
        }

        for (size_t i = 0; i < projects.size(); ++i) {
            projectIndex[projects[i].id] = i;
        }
    }

    bool employeeEmailExists(const string& email, int ignoredId = -1) const {
        return any_of(
            employees.begin(),
            employees.end(),
            [&](const Employee& employee) {
                return employee.id != ignoredId &&
                       employee.email == email;
            }
        );
    }

    void validateDepartment(const Department& department) const {
        if (department.id <= 0) {
            throw ConstraintError("Department ID must be positive.");
        }

        if (department.name.empty()) {
            throw ConstraintError("Department name cannot be empty.");
        }

        if (department.budget < 0) {
            throw ConstraintError("Department budget cannot be negative.");
        }

        for (const auto& existing : departments) {
            if (existing.id == department.id) {
                throw ConstraintError("Duplicate department primary key.");
            }

            if (existing.name == department.name) {
                throw ConstraintError("Duplicate department name.");
            }
        }
    }

    void validateEmployee(const Employee& employee, int ignoredId = -1) const {
        if (employee.id <= 0) {
            throw ConstraintError("Employee ID must be positive.");
        }

        if (employee.firstName.empty() || employee.lastName.empty()) {
            throw ConstraintError("Employee name cannot be empty.");
        }

        if (employee.email.empty()) {
            throw ConstraintError("Employee email cannot be empty.");
        }

        if (employee.salary < 0) {
            throw ConstraintError("Employee salary cannot be negative.");
        }

        if (!departmentIndex.contains(employee.departmentId)) {
            throw ConstraintError("Employee references an unknown department.");
        }

        if (employeeEmailExists(employee.email, ignoredId)) {
            throw ConstraintError("Employee email must be unique.");
        }

        auto existing = employeeIndex.find(employee.id);

        if (existing != employeeIndex.end() && employee.id != ignoredId) {
            throw ConstraintError("Duplicate employee primary key.");
        }
    }

    void validateProject(const Project& project) const {
        if (project.id <= 0) {
            throw ConstraintError("Project ID must be positive.");
        }

        if (project.name.empty()) {
            throw ConstraintError("Project name cannot be empty.");
        }

        if (project.budget < 0) {
            throw ConstraintError("Project budget cannot be negative.");
        }

        const set<string> allowedStatuses{
            "planned",
            "active",
            "completed"
        };

        if (!allowedStatuses.contains(project.status)) {
            throw ConstraintError("Invalid project status.");
        }

        for (const auto& existing : projects) {
            if (existing.id == project.id) {
                throw ConstraintError("Duplicate project primary key.");
            }

            if (existing.name == project.name) {
                throw ConstraintError("Duplicate project name.");
            }
        }
    }

    void validateAssignment(const EmployeeProject& assignment) const {
        if (!employeeIndex.contains(assignment.employeeId)) {
            throw ConstraintError("Assignment references an unknown employee.");
        }

        if (!projectIndex.contains(assignment.projectId)) {
            throw ConstraintError("Assignment references an unknown project.");
        }

        if (assignment.role.empty()) {
            throw ConstraintError("Assignment role cannot be empty.");
        }

        for (const auto& existing : assignments) {
            if (existing.employeeId == assignment.employeeId &&
                existing.projectId == assignment.projectId) {
                throw ConstraintError(
                    "The employee/project pair must be unique."
                );
            }
        }
    }

public:
    EmployeeDatabase() = default;

    void insertDepartment(const Department& department) {
        validateDepartment(department);
        departments.push_back(department);
        rebuildIndexes();
    }

    void insertEmployee(const Employee& employee) {
        validateEmployee(employee);
        employees.push_back(employee);
        rebuildIndexes();
    }

    void insertProject(const Project& project) {
        validateProject(project);
        projects.push_back(project);
        rebuildIndexes();
    }

    void insertAssignment(const EmployeeProject& assignment) {
        validateAssignment(assignment);
        assignments.push_back(assignment);
    }

    void insertAccount(const Account& account) {
        if (account.id <= 0) {
            throw ConstraintError("Account ID must be positive.");
        }

        if (account.balance < 0) {
            throw ConstraintError("Account balance cannot be negative.");
        }

        for (const auto& existing : accounts) {
            if (existing.id == account.id) {
                throw ConstraintError("Duplicate account ID.");
            }
        }

        accounts.push_back(account);
    }

    optional<Employee> findEmployee(int id) const {
        auto it = employeeIndex.find(id);

        if (it == employeeIndex.end()) {
            return nullopt;
        }

        return employees[it->second];
    }

    vector<Employee> activeEmployees() const {
        vector<Employee> result;

        for (const auto& employee : employees) {
            if (employee.active) {
                result.push_back(employee);
            }
        }

        sort(
            result.begin(),
            result.end(),
            [](const Employee& left, const Employee& right) {
                if (left.lastName != right.lastName) {
                    return left.lastName < right.lastName;
                }

                return left.firstName < right.firstName;
            }
        );

        return result;
    }

    vector<Employee> employeesWithSalaryAtLeast(double minimumSalary) const {
        vector<Employee> result;

        for (const auto& employee : employees) {
            if (employee.salary >= minimumSalary) {
                result.push_back(employee);
            }
        }

        sort(
            result.begin(),
            result.end(),
            [](const Employee& left, const Employee& right) {
                return left.salary > right.salary;
            }
        );

        return result;
    }

    map<int, pair<int, double>> departmentStatistics() const {
        map<int, pair<int, double>> statistics;

        for (const auto& employee : employees) {
            auto& entry = statistics[employee.departmentId];
            entry.first += 1;
            entry.second += employee.salary;
        }

        return statistics;
    }

    struct EmployeeDepartmentRow {
        string employee;
        string department;
        double salary;
    };

    vector<EmployeeDepartmentRow> employeeDepartmentJoin() const {
        vector<EmployeeDepartmentRow> result;

        for (const auto& employee : employees) {
            auto departmentIt = departmentIndex.find(employee.departmentId);

            if (departmentIt == departmentIndex.end()) {
                continue;
            }

            const auto& department = departments[departmentIt->second];

            result.push_back({
                employee.firstName + " " + employee.lastName,
                department.name,
                employee.salary
            });
        }

        sort(
            result.begin(),
            result.end(),
            [](const EmployeeDepartmentRow& left,
               const EmployeeDepartmentRow& right) {
                if (left.department != right.department) {
                    return left.department < right.department;
                }

                return left.employee < right.employee;
            }
        );

        return result;
    }

    struct ProjectAssignmentRow {
        string employee;
        string project;
        string role;
    };

    vector<ProjectAssignmentRow> employeeProjectJoin() const {
        vector<ProjectAssignmentRow> result;

        for (const auto& assignment : assignments) {
            auto employeeIt = employeeIndex.find(assignment.employeeId);
            auto projectIt = projectIndex.find(assignment.projectId);

            if (employeeIt == employeeIndex.end() ||
                projectIt == projectIndex.end()) {
                continue;
            }

            const auto& employee = employees[employeeIt->second];
            const auto& project = projects[projectIt->second];

            result.push_back({
                employee.firstName + " " + employee.lastName,
                project.name,
                assignment.role
            });
        }

        return result;
    }

    void updateSalary(int employeeId, double newSalary) {
        if (newSalary < 0) {
            throw ConstraintError("Salary cannot be negative.");
        }

        auto it = employeeIndex.find(employeeId);

        if (it == employeeIndex.end()) {
            throw DatabaseError("Employee does not exist.");
        }

        employees[it->second].salary = newSalary;
    }

    void deleteEmployee(int employeeId) {
        auto it = employeeIndex.find(employeeId);

        if (it == employeeIndex.end()) {
            throw DatabaseError("Employee does not exist.");
        }

        /*
         * In this simplified model the application explicitly removes
         * dependent assignments. A production database would normally use
         * a foreign-key action such as ON DELETE CASCADE or RESTRICT.
         */
        assignments.erase(
            remove_if(
                assignments.begin(),
                assignments.end(),
                [&](const EmployeeProject& assignment) {
                    return assignment.employeeId == employeeId;
                }
            ),
            assignments.end()
        );

        employees.erase(employees.begin() + static_cast<long>(it->second));
        rebuildIndexes();
    }

    void beginTransaction() {
        if (transactionActive) {
            throw TransactionError("Transaction already active.");
        }

        savedDepartments = departments;
        savedEmployees = employees;
        savedProjects = projects;
        savedAssignments = assignments;
        savedAccounts = accounts;

        transactionActive = true;
    }

    void commit() {
        if (!transactionActive) {
            throw TransactionError("No active transaction.");
        }

        transactionActive = false;
        savedDepartments.clear();
        savedEmployees.clear();
        savedProjects.clear();
        savedAssignments.clear();
        savedAccounts.clear();
    }

    void rollback() {
        if (!transactionActive) {
            throw TransactionError("No active transaction.");
        }

        departments = savedDepartments;
        employees = savedEmployees;
        projects = savedProjects;
        assignments = savedAssignments;
        accounts = savedAccounts;

        rebuildIndexes();

        transactionActive = false;
        savedDepartments.clear();
        savedEmployees.clear();
        savedProjects.clear();
        savedAssignments.clear();
        savedAccounts.clear();
    }

    template <typename Function>
    void transaction(Function operation) {
        beginTransaction();

        try {
            operation();
            commit();
        } catch (...) {
            rollback();
            throw;
        }
    }

    void transfer(int senderId, int receiverId, double amount) {
        if (amount <= 0) {
            throw ConstraintError("Transfer amount must be positive.");
        }

        auto senderIt = findAccount(senderId);
        auto receiverIt = findAccount(receiverId);

        if (!senderIt.has_value() || !receiverIt.has_value()) {
            throw DatabaseError("Account does not exist.");
        }

        if (senderIt->get().balance < amount) {
            throw ConstraintError("Insufficient funds.");
        }

        senderIt->get().balance -= amount;
        receiverIt->get().balance += amount;
    }

    optional<reference_wrapper<Account>> findAccount(int id) {
        for (auto& account : accounts) {
            if (account.id == id) {
                return account;
            }
        }

        return nullopt;
    }

    const vector<Account>& getAccounts() const {
        return accounts;
    }

    const vector<Employee>& getEmployees() const {
        return employees;
    }

    const vector<Department>& getDepartments() const {
        return departments;
    }

    const vector<Project>& getProjects() const {
        return projects;
    }

    size_t employeeCount() const {
        return employees.size();
    }
};

void printSection(const string& title) {
    cout << "\n" << string(78, '=') << "\n";
    cout << title << "\n";
    cout << string(78, '=') << "\n";
}

void printEmployees(const vector<Employee>& employees) {
    cout << left
         << setw(8) << "ID"
         << setw(15) << "First"
         << setw(15) << "Last"
         << setw(12) << "Salary"
         << setw(10) << "Active"
         << "\n";

    cout << string(60, '-') << "\n";

    for (const auto& employee : employees) {
        cout << left
             << setw(8) << employee.id
             << setw(15) << employee.firstName
             << setw(15) << employee.lastName
             << setw(12) << fixed << setprecision(2) << employee.salary
             << setw(10) << (employee.active ? "yes" : "no")
             << "\n";
    }
}

void seedDatabase(EmployeeDatabase& database) {
    printSection("1. BUILDING THE DATABASE SCHEMA");

    database.insertDepartment({1, "Engineering", 2000000});
    database.insertDepartment({2, "Finance", 1200000});
    database.insertDepartment({3, "Operations", 900000});
    database.insertDepartment({4, "Research", 1500000});

    database.insertEmployee({
        101, 1, "Asha", "Sharma",
        "asha@example.com", 120000, true
    });

    database.insertEmployee({
        102, 1, "Ravi", "Kumar",
        "ravi@example.com", 95000, true
    });

    database.insertEmployee({
        103, 2, "Neha", "Singh",
        "neha@example.com", 110000, true
    });

    database.insertEmployee({
        104, 2, "Arjun", "Mehta",
        "arjun@example.com", 85000, true
    });

    database.insertEmployee({
        105, 3, "Priya", "Verma",
        "priya@example.com", 78000, false
    });

    database.insertEmployee({
        106, 4, "Kabir", "Das",
        "kabir@example.com", 135000, true
    });

    database.insertProject({201, "Data Platform", 500000, "active"});
    database.insertProject({202, "Risk Engine", 350000, "active"});
    database.insertProject({203, "Automation", 180000, "completed"});

    database.insertAssignment({
        101, 201, "2025-01-10", "Architect"
    });

    database.insertAssignment({
        102, 201, "2025-02-01", "Developer"
    });

    database.insertAssignment({
        103, 202, "2025-03-15", "Analyst"
    });

    database.insertAssignment({
        106, 202, "2025-03-20", "Researcher"
    });

    database.insertAssignment({
        102, 203, "2024-01-01", "Developer"
    });

    cout << "Departments: " << database.getDepartments().size() << "\n";
    cout << "Employees: " << database.employeeCount() << "\n";
    cout << "Projects: " << database.getProjects().size() << "\n";
}

void basicQueries(const EmployeeDatabase& database) {
    printSection("2. SELECT-LIKE QUERIES");

    cout << "\nActive employees:\n";
    printEmployees(database.activeEmployees());

    cout << "\nEmployees with salary >= 100000:\n";
    printEmployees(
        database.employeesWithSalaryAtLeast(100000)
    );

    cout << "\nEmployee lookup by primary key:\n";

    auto employee = database.findEmployee(101);

    if (employee.has_value()) {
        cout << employee->firstName
             << " "
             << employee->lastName
             << " earns "
             << employee->salary
             << "\n";
    }

    cout << "\nMissing employee:\n";

    auto missing = database.findEmployee(9999);

    cout << (missing.has_value() ? "Found" : "Not found") << "\n";
}

void demonstrateJoins(const EmployeeDatabase& database) {
    printSection("3. RELATIONAL JOINS");

    cout << left
         << setw(25) << "Employee"
         << setw(20) << "Department"
         << setw(12) << "Salary"
         << "\n";

    cout << string(57, '-') << "\n";

    for (const auto& row : database.employeeDepartmentJoin()) {
        cout << left
             << setw(25) << row.employee
             << setw(20) << row.department
             << setw(12) << fixed << setprecision(2) << row.salary
             << "\n";
    }

    cout << "\nEmployee/project many-to-many relationship:\n";

    for (const auto& row : database.employeeProjectJoin()) {
        cout << row.employee
             << " -> "
             << row.project
             << " ["
             << row.role
             << "]\n";
    }

    cout << R"(
A relational join combines rows through keys.

The employee -> department relationship is many-to-one:
many employees can belong to one department.

The employee -> project relationship is many-to-many:
one employee can work on multiple projects and one project can have
multiple employees. The employee_project junction table represents
that relationship.
)";
}

void demonstrateAggregation(const EmployeeDatabase& database) {
    printSection("4. AGGREGATION AND GROUPING");

    const auto statistics = database.departmentStatistics();

    cout << left
         << setw(15) << "Department"
         << setw(15) << "Employees"
         << setw(15) << "Average"
         << setw(15) << "Payroll"
         << "\n";

    cout << string(60, '-') << "\n";

    for (const auto& [departmentId, values] : statistics) {
        const int count = values.first;
        const double payroll = values.second;
        const double average = payroll / count;

        cout << left
             << setw(15) << departmentId
             << setw(15) << count
             << setw(15) << fixed << setprecision(2) << average
             << setw(15) << payroll
             << "\n";
    }

    cout << R"(
COUNT corresponds to counting records.
SUM calculates a total.
AVG calculates a mean.
MIN and MAX identify boundary values.

GROUP BY conceptually changes a collection of rows into groups on which
aggregate functions can operate.
)";
}

void demonstrateCrud(EmployeeDatabase& database) {
    printSection("5. CRUD OPERATIONS");

    cout << "Initial employee count: "
         << database.employeeCount()
         << "\n";

    database.insertEmployee({
        107, 3, "Isha", "Roy",
        "isha@example.com", 72000, true
    });

    cout << "After INSERT: "
         << database.employeeCount()
         << "\n";

    database.updateSalary(107, 75000);

    auto updated = database.findEmployee(107);

    if (updated.has_value()) {
        cout << "After UPDATE: "
             << updated->salary
             << "\n";
    }

    database.deleteEmployee(107);

    cout << "After DELETE: "
         << database.employeeCount()
         << "\n";
}

void demonstrateConstraints(EmployeeDatabase& database) {
    printSection("6. CONSTRAINTS AND FAILURE CONDITIONS");

    try {
        database.insertEmployee({
            999,
            1,
            "Duplicate",
            "Email",
            "asha@example.com",
            50000,
            true
        });
    } catch (const ConstraintError& error) {
        cout << "Duplicate email rejected: "
             << error.what()
             << "\n";
    }

    try {
        database.insertEmployee({
            998,
            1,
            "Negative",
            "Salary",
            "negative@example.com",
            -100,
            true
        });
    } catch (const ConstraintError& error) {
        cout << "Negative salary rejected: "
             << error.what()
             << "\n";
    }

    try {
        database.insertEmployee({
            997,
            999,
            "Unknown",
            "Department",
            "unknown@example.com",
            50000,
            true
        });
    } catch (const ConstraintError& error) {
        cout << "Foreign-key violation rejected: "
             << error.what()
             << "\n";
    }
}

void demonstrateTransactions(EmployeeDatabase& database) {
    printSection("7. TRANSACTIONS");

    database.insertAccount({1, "Alice", 1000});
    database.insertAccount({2, "Bob", 500});

    cout << "Before transfer:\n";

    for (const auto& account : database.getAccounts()) {
        cout << account.owner
             << ": "
             << fixed
             << setprecision(2)
             << account.balance
             << "\n";
    }

    database.transaction([&database]() {
        database.transfer(1, 2, 200);
    });

    cout << "\nAfter successful transaction:\n";

    for (const auto& account : database.getAccounts()) {
        cout << account.owner
             << ": "
             << fixed
             << setprecision(2)
             << account.balance
             << "\n";
    }

    try {
        database.transaction([&database]() {
            database.transfer(1, 2, 5000);
        });
    } catch (const exception& error) {
        cout << "\nFailed transaction rolled back: "
             << error.what()
             << "\n";
    }

    cout << "\nAfter failed transaction:\n";

    for (const auto& account : database.getAccounts()) {
        cout << account.owner
             << ": "
             << fixed
             << setprecision(2)
             << account.balance
             << "\n";
    }

    cout << R"(
The transaction wrapper captures the previous state, executes all operations,
and restores the previous state if any operation throws an exception.

A production database provides stronger transaction and concurrency
semantics than this educational in-memory implementation.
)";
}

void demonstrateIndexReasoning() {
    printSection("8. INDEX AND COMPLEXITY REASONING");

    cout << R"(
The employeeIndex unordered_map provides approximately O(1) average lookup
by employee ID.

Without such an index, searching an unsorted vector requires O(n) scanning.

Sorting a collection is generally O(n log n).

An SQL database can implement indexes using structures such as B-trees,
hash indexes, bitmap indexes, or engine-specific structures. The correct
choice depends on the database engine and workload.

Indexes are not free:
  - they require storage;
  - writes must maintain index structures;
  - excessive indexes increase write cost;
  - a poorly selected index may not improve a query.

A production database should use query-plan analysis and representative
workloads rather than assumptions alone.
)";
}

void demonstrateNormalization() {
    printSection("9. NORMALIZATION DESIGN");

    cout << R"(
A poorly designed table might contain:

OrderID | CustomerName | CustomerEmail | Product1 | Product2

This creates repeating groups and duplicated customer information.

A normalized design separates:

customers
    customer_id
    name
    email

orders
    order_id
    customer_id
    order_date

products
    product_id
    name
    price

order_items
    order_id
    product_id
    quantity

1NF focuses on atomic values and eliminating repeating groups.

2NF addresses partial dependency on part of a composite candidate key.

3NF addresses transitive dependencies between non-key attributes.

Normalization improves consistency and reduces update anomalies. It can
increase the number of joins, so production systems sometimes deliberately
denormalize selected data after measuring a real workload.
)";
}

void demonstrateSecurity() {
    printSection("10. DATABASE SECURITY");

    cout << R"(
Important database security controls include:

1. Parameterized SQL queries to prevent SQL injection.
2. Least-privilege database accounts.
3. Strong authentication and authorization.
4. Protected credentials and secret management.
5. Network restrictions around database servers.
6. Encryption in transit where appropriate.
7. Encryption at rest where appropriate.
8. Secure backups and backup access controls.
9. Auditing of security-sensitive operations.
10. Safe error messages that do not expose internal details.
11. Regular patching of the database engine.
12. Careful handling of personal and confidential information.

Authentication determines identity.
Authorization determines allowed actions.

Application validation and database constraints serve different purposes.
Both can be necessary for a reliable system.
)";
}

void demonstrateArchitecture() {
    printSection("11. INDUSTRY-STYLE ARCHITECTURE");

    cout << R"(
A production application commonly separates responsibilities:

Presentation/API layer
    Receives requests and returns responses.

Application/service layer
    Applies business rules and coordinates operations.

Repository/data-access layer
    Encapsulates SQL and database-driver interaction.

Database
    Enforces persistence, constraints, indexes, transactions, and queries.

Migration system
    Applies version-controlled schema changes.

Observability
    Measures latency, failures, query performance, and resource usage.

This case study combines several of those ideas in one C++ process while
keeping the persistence layer in memory so the program remains portable
and self-contained.
)";
}

int main() {
    try {
        EmployeeDatabase database;

        seedDatabase(database);
        basicQueries(database);
        demonstrateJoins(database);
        demonstrateAggregation(database);
        demonstrateCrud(database);
        demonstrateConstraints(database);
        demonstrateTransactions(database);
        demonstrateIndexReasoning();
        demonstrateNormalization();
        demonstrateSecurity();
        demonstrateArchitecture();

        printSection("12. CASE STUDY COMPLETE");

        cout << R"(
The case study demonstrated a relational employee/project system with
typed records, primary and foreign keys, validation, CRUD operations,
joins, aggregation, transactions, rollback, indexes, normalization,
security considerations, and layered architecture.

The implementation is intentionally an educational in-memory model.
A production system would normally delegate persistence, concurrency,
durability, isolation, recovery, and query optimization to a mature
database engine.
)"
             << "\n";

        return 0;
    } catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << "\n";
        return 1;
    }
}
