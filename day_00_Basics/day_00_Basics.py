# ============================================================
# DAY 00: SYSTEM DESIGN FUNDAMENTALS
# ============================================================

print("DAY 01 - SYSTEM DESIGN FUNDAMENTALS")


# ============================================================
# 1. WHAT IS A SYSTEM?
# ============================================================

print("\n1. WHAT IS A SYSTEM?")

print("A system is a collection of components that work")
print("together to achieve a specific purpose.")

system = "Online Learning Platform"

print("Example System:", system)


# ============================================================
# 2. USERS
# ============================================================

print("\n2. USERS")

users = [
    "Student",
    "Instructor",
    "Administrator"
]

for user in users:
    print("-", user)


# ============================================================
# 3. CLIENT
# ============================================================

print("\n3. CLIENT")

client = {
    "type": "Web Browser",
    "purpose": "Allows users to interact with the system"
}

print("Client Type:", client["type"])
print("Purpose:", client["purpose"])


# ============================================================
# 4. SERVER
# ============================================================

print("\n4. SERVER")

server = {
    "name": "Application Server",
    "responsibility": "Process requests and execute business logic"
}

print("Server:", server["name"])
print("Responsibility:", server["responsibility"])


# ============================================================
# 5. DATABASE
# ============================================================

print("\n5. DATABASE")

database = {
    "name": "Application Database",
    "stores": [
        "Users",
        "Courses",
        "Orders",
        "Payments"
    ]
}

print("Database:", database["name"])
print("Stored Data:")

for data in database["stores"]:
    print("-", data)


# ============================================================
# 6. REQUEST AND RESPONSE
# ============================================================

print("\n6. REQUEST AND RESPONSE")

request = {
    "method": "GET",
    "path": "/courses"
}

response = {
    "status_code": 200,
    "data": ["Python", "SQL", "System Design"]
}

print("Request:")
print(request)

print("\nResponse:")
print(response)


# ============================================================
# 7. BASIC SYSTEM FLOW
# ============================================================

print("\n7. BASIC SYSTEM FLOW")

print("""
User
  ↓
Client
  ↓
Server
  ↓
Database
  ↓
Server
  ↓
Client
  ↓
User
""")


# ============================================================
# 8. SYSTEM COMPONENTS
# ============================================================

print("\n8. SYSTEM COMPONENTS")

components = [
    "Client",
    "Application Server",
    "Database",
    "API",
    "Authentication System"
]

for component in components:
    print("-", component)


# ============================================================
# 9. FUNCTIONAL REQUIREMENT
# ============================================================

print("\n9. FUNCTIONAL REQUIREMENT")

functional_requirement = "Users should be able to search for courses."

print("Requirement:", functional_requirement)


# ============================================================
# 10. NON-FUNCTIONAL REQUIREMENTS
# ============================================================

print("\n10. NON-FUNCTIONAL REQUIREMENTS")

non_functional_requirements = [
    "Performance",
    "Scalability",
    "Availability",
    "Security",
    "Reliability"
]

for requirement in non_functional_requirements:
    print("-", requirement)


# ============================================================
# 11. SCALABILITY
# ============================================================

print("\n11. SCALABILITY")

users_today = 1000
users_future = 100000

print("Current Users:", users_today)
print("Expected Future Users:", users_future)

print("\nA scalable system should be able to handle")
print("increasing users and workload effectively.")


# ============================================================
# 12. SIMPLE SYSTEM DESIGN
# ============================================================

print("\n12. SIMPLE SYSTEM DESIGN")

system_design = {
    "Client": "Web/Mobile Application",
    "API": "Handles communication",
    "Server": "Processes business logic",
    "Database": "Stores application data"
}

for component, responsibility in system_design.items():
    print(component, "->", responsibility)


# ============================================================
# SUMMARY
# ============================================================

print("\n" + "=" * 60)
print("DAY 01 COMPLETED")
print("=" * 60)

print("""
Today you learned:

1. What a system is
2. Users
3. Clients
4. Servers
5. Databases
6. Requests and responses
7. Basic system flow
8. System components
9. Functional requirements
10. Non-functional requirements
11. Scalability
12. Basic system design
""")
