"""
Database Normalization: 1NF, 2NF, 3NF, and Denormalization

A self-contained executable learning and simulation program.

The program uses a realistic order-management dataset to demonstrate:
- An unnormalized relation with repeating groups.
- First Normal Form (1NF): atomic values and elimination of repeating groups.
- Second Normal Form (2NF): removal of partial dependencies from composite keys.
- Third Normal Form (3NF): removal of transitive dependencies.
- Functional dependencies and candidate keys.
- Lossless decomposition checks.
- Dependency-preservation reasoning.
- Denormalization for read-heavy workloads.
- Validation and anomaly detection.
- A small query-performance simulation comparing normalized and denormalized designs.

No external packages are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict
from copy import deepcopy
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Shared relational helpers
# ---------------------------------------------------------------------------

def print_title(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def print_rows(rows: Iterable[dict[str, Any]], columns: list[str] | None = None) -> None:
    rows = list(rows)
    if not rows:
        print("(no rows)")
        return

    if columns is None:
        columns = list(rows[0].keys())

    widths = {
        column: max(
            len(column),
            *(len(str(row.get(column, ""))) for row in rows),
        )
        for column in columns
    }

    header = " | ".join(column.ljust(widths[column]) for column in columns)
    separator = "-+-".join("-" * widths[column] for column in columns)

    print(header)
    print(separator)
    for row in rows:
        print(" | ".join(str(row.get(column, "")).ljust(widths[column]) for column in columns))


def distinct_values(rows: Iterable[dict[str, Any]], column: str) -> set[Any]:
    return {row.get(column) for row in rows}


def duplicate_keys(
    rows: Iterable[dict[str, Any]],
    columns: tuple[str, ...],
) -> dict[tuple[Any, ...], int]:
    counts: dict[tuple[Any, ...], int] = defaultdict(int)

    for row in rows:
        key = tuple(row.get(column) for column in columns)
        counts[key] += 1

    return {key: count for key, count in counts.items() if count > 1}


# ---------------------------------------------------------------------------
# Functional dependency model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FunctionalDependency:
    determinant: frozenset[str]
    dependent: frozenset[str]

    def __str__(self) -> str:
        left = ", ".join(sorted(self.determinant))
        right = ", ".join(sorted(self.dependent))
        return f"{left} -> {right}"


def attribute_closure(
    attributes: set[str],
    dependencies: list[FunctionalDependency],
) -> set[str]:
    """
    Compute the closure X+ of an attribute set X.

    If X determines Y, then Y is added to the closure. The process repeats
    until no dependency can add a new attribute.
    """
    closure = set(attributes)

    changed = True
    while changed:
        changed = False

        for dependency in dependencies:
            if dependency.determinant.issubset(closure):
                before = len(closure)
                closure.update(dependency.dependent)
                changed = changed or len(closure) != before

    return closure


def is_superkey(
    attributes: set[str],
    relation_attributes: set[str],
    dependencies: list[FunctionalDependency],
) -> bool:
    return attribute_closure(attributes, dependencies) == relation_attributes


def candidate_keys(
    relation_attributes: set[str],
    dependencies: list[FunctionalDependency],
) -> list[frozenset[str]]:
    """
    Find candidate keys by exhaustive search.

    This is intentionally designed for a small teaching relation. Real schema
    design tools use more efficient algorithms when relations have many
    attributes.
    """
    attributes = sorted(relation_attributes)
    keys: list[frozenset[str]] = []

    from itertools import combinations

    for size in range(1, len(attributes) + 1):
        for combination in combinations(attributes, size):
            candidate = frozenset(combination)

            if any(existing.issubset(candidate) for existing in keys):
                continue

            if is_superkey(set(candidate), relation_attributes, dependencies):
                keys.append(candidate)

    return keys


def describe_dependencies(
    dependencies: list[FunctionalDependency],
) -> None:
    for dependency in dependencies:
        print(f"  {dependency}")


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

def find_update_anomalies(
    rows: list[dict[str, Any]],
    determinant: str,
    dependent: str,
) -> list[tuple[Any, set[Any]]]:
    """
    Find determinants associated with multiple dependent values.

    If a business rule says determinant -> dependent, multiple dependent
    values indicate inconsistent data or a violated functional dependency.
    """
    values: dict[Any, set[Any]] = defaultdict(set)

    for row in rows:
        values[row[determinant]].add(row[dependent])

    return [
        (key, dependent_values)
        for key, dependent_values in values.items()
        if len(dependent_values) > 1
    ]


# ---------------------------------------------------------------------------
# Original unnormalized order dataset
# ---------------------------------------------------------------------------

def create_unnormalized_orders() -> list[dict[str, Any]]:
    """
    The source design stores multiple products inside one order row.

    This violates 1NF because ProductIDs, ProductNames, Quantities, and Prices
    contain repeating groups rather than one atomic value per cell.
    """
    return [
        {
            "OrderID": 1001,
            "CustomerID": "C101",
            "CustomerName": "Asha Sharma",
            "CustomerCity": "Lucknow",
            "ProductIDs": "P10,P20",
            "ProductNames": "Keyboard,Mouse",
            "Quantities": "2,1",
            "UnitPrices": "1800.00,700.00",
        },
        {
            "OrderID": 1002,
            "CustomerID": "C102",
            "CustomerName": "Ravi Kumar",
            "CustomerCity": "Delhi",
            "ProductIDs": "P20,P30",
            "ProductNames": "Mouse,Monitor",
            "Quantities": "1,1",
            "UnitPrices": "700.00,12000.00",
        },
    ]


def demonstrate_unnormalized_form() -> None:
    print_title("Unnormalized relation: repeating groups")

    rows = create_unnormalized_orders()
    print_rows(rows)

    print(
        "\nThe product columns encode multiple values in a single cell. "
        "A relational tuple should represent one value at each attribute position."
    )


# ---------------------------------------------------------------------------
# 1NF
# ---------------------------------------------------------------------------

def convert_to_1nf(
    unnormalized: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert the repeating product groups into one row per order line.

    Customer information is intentionally still repeated. That is acceptable
    for 1NF: 1NF concerns atomic values and repeating groups, not yet
    partial or transitive dependency removal.
    """
    normalized_rows: list[dict[str, Any]] = []

    for order in unnormalized:
        product_ids = order["ProductIDs"].split(",")
        product_names = order["ProductNames"].split(",")
        quantities = [int(value) for value in order["Quantities"].split(",")]
        prices = [float(value) for value in order["UnitPrices"].split(",")]

        lengths = {
            len(product_ids),
            len(product_names),
            len(quantities),
            len(prices),
        }

        if len(lengths) != 1:
            raise ValueError(
                f"Order {order['OrderID']} contains misaligned repeating groups"
            )

        for product_id, product_name, quantity, price in zip(
            product_ids,
            product_names,
            quantities,
            prices,
        ):
            if quantity <= 0:
                raise ValueError("Quantity must be positive")
            if price < 0:
                raise ValueError("Unit price cannot be negative")

            normalized_rows.append(
                {
                    "OrderID": order["OrderID"],
                    "CustomerID": order["CustomerID"],
                    "CustomerName": order["CustomerName"],
                    "CustomerCity": order["CustomerCity"],
                    "ProductID": product_id,
                    "ProductName": product_name,
                    "Quantity": quantity,
                    "UnitPrice": price,
                }
            )

    return normalized_rows


def validate_atomic_values(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []

    for index, row in enumerate(rows):
        for key, value in row.items():
            if isinstance(value, (list, tuple, set, dict)):
                errors.append(
                    f"Row {index} attribute {key} contains a collection"
                )

            if value is None:
                errors.append(
                    f"Row {index} attribute {key} contains NULL"
                )

    return errors


def demonstrate_1nf() -> list[dict[str, Any]]:
    print_title("First Normal Form (1NF)")

    rows = convert_to_1nf(create_unnormalized_orders())
    print_rows(rows)

    errors = validate_atomic_values(rows)

    print("\nAtomic-value validation:")
    if errors:
        for error in errors:
            print(f"  ERROR: {error}")
    else:
        print("  PASS: every displayed attribute contains one atomic value.")

    print(
        "\nThe table is now suitable for one order-line tuple per product. "
        "Customer and product facts are still repeated, which is expected "
        "before the dependency analysis used for 2NF and 3NF."
    )

    return rows


# ---------------------------------------------------------------------------
# 2NF
# ---------------------------------------------------------------------------

def decompose_to_2nf(
    rows_1nf: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Decompose the 1NF relation around its composite candidate key:

        (OrderID, ProductID)

    Customer attributes depend only on OrderID.
    Product attributes depend only on ProductID.
    Quantity belongs to the complete order-line key.

    Those partial dependencies violate 2NF.
    """
    customers: dict[str, dict[str, Any]] = {}
    products: dict[str, dict[str, Any]] = {}
    order_lines: dict[tuple[int, str], dict[str, Any]] = {}

    for row in rows_1nf:
        customer_id = row["CustomerID"]
        product_id = row["ProductID"]
        order_id = row["OrderID"]

        customer = {
            "CustomerID": customer_id,
            "CustomerName": row["CustomerName"],
            "CustomerCity": row["CustomerCity"],
        }

        product = {
            "ProductID": product_id,
            "ProductName": row["ProductName"],
            "UnitPrice": row["UnitPrice"],
        }

        line_key = (order_id, product_id)

        if customer_id in customers and customers[customer_id] != customer:
            raise ValueError(
                f"Customer {customer_id} has inconsistent descriptive attributes"
            )

        if product_id in products and products[product_id] != product:
            raise ValueError(
                f"Product {product_id} has inconsistent descriptive attributes"
            )

        if line_key in order_lines:
            raise ValueError(f"Duplicate order line detected: {line_key}")

        customers[customer_id] = customer
        products[product_id] = product

        order_lines[line_key] = {
            "OrderID": order_id,
            "ProductID": product_id,
            "Quantity": row["Quantity"],
        }

    return {
        "Customers": list(customers.values()),
        "Products": list(products.values()),
        "OrderLines": list(order_lines.values()),
    }


def demonstrate_2nf(rows_1nf: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    print_title("Second Normal Form (2NF)")

    tables = decompose_to_2nf(rows_1nf)

    print("\nCustomers")
    print_rows(tables["Customers"])

    print("\nProducts")
    print_rows(tables["Products"])

    print("\nOrderLines")
    print_rows(tables["OrderLines"])

    print(
        "\nThe composite order-line key is (OrderID, ProductID). "
        "Customer attributes depend on OrderID alone, while product attributes "
        "depend on ProductID alone. Separating those facts removes partial "
        "dependencies."
    )

    return tables


# ---------------------------------------------------------------------------
# 3NF
# ---------------------------------------------------------------------------

@dataclass
class Product3NF:
    product_id: str
    product_name: str
    category_id: str


@dataclass
class Category3NF:
    category_id: str
    category_name: str


def create_2nf_product_table_with_category() -> list[dict[str, Any]]:
    """
    Introduce a realistic 2NF design that still has a 3NF problem.

    ProductID -> CategoryID
    CategoryID -> CategoryName

    Therefore:
    ProductID -> CategoryID -> CategoryName

    CategoryName is transitively dependent on ProductID.
    """
    return [
        {
            "ProductID": "P10",
            "ProductName": "Keyboard",
            "CategoryID": "CAT1",
            "CategoryName": "Peripherals",
        },
        {
            "ProductID": "P20",
            "ProductName": "Mouse",
            "CategoryID": "CAT1",
            "CategoryName": "Peripherals",
        },
        {
            "ProductID": "P30",
            "ProductName": "Monitor",
            "CategoryID": "CAT2",
            "CategoryName": "Displays",
        },
    ]


def decompose_to_3nf(
    product_rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    categories: dict[str, dict[str, Any]] = {}
    products: dict[str, dict[str, Any]] = {}

    for row in product_rows:
        category_id = row["CategoryID"]

        if (
            category_id in categories
            and categories[category_id]["CategoryName"] != row["CategoryName"]
        ):
            raise ValueError(
                f"Category {category_id} has conflicting names"
            )

        categories[category_id] = {
            "CategoryID": category_id,
            "CategoryName": row["CategoryName"],
        }

        products[row["ProductID"]] = {
            "ProductID": row["ProductID"],
            "ProductName": row["ProductName"],
            "CategoryID": category_id,
        }

    return {
        "Categories": list(categories.values()),
        "Products": list(products.values()),
    }


def demonstrate_3nf() -> None:
    print_title("Third Normal Form (3NF)")

    product_rows = create_2nf_product_table_with_category()

    print("2NF product relation with a transitive dependency:")
    print_rows(product_rows)

    dependencies = [
        FunctionalDependency(
            frozenset({"ProductID"}),
            frozenset({"ProductName", "CategoryID"}),
        ),
        FunctionalDependency(
            frozenset({"CategoryID"}),
            frozenset({"CategoryName"}),
        ),
    ]

    print("\nFunctional dependencies:")
    describe_dependencies(dependencies)

    closure = attribute_closure({"ProductID"}, {
        # The set conversion is only to make the example concise.
        # The function accepts a list, so we recreate it below.
    } if False else dependencies)

    print(f"\nProductID closure: {sorted(closure)}")
    print(
        "CategoryName is reachable through CategoryID, so it is transitively "
        "dependent on ProductID."
    )

    tables = decompose_to_3nf(product_rows)

    print("\nProducts after 3NF decomposition:")
    print_rows(tables["Products"])

    print("\nCategories after 3NF decomposition:")
    print_rows(tables["Categories"])

    print(
        "\nCategoryName is now stored where CategoryID determines it directly. "
        "Changing a category name therefore requires one category row rather "
        "than every product belonging to that category."
    )


# ---------------------------------------------------------------------------
# Formal normal-form analysis
# ---------------------------------------------------------------------------

def demonstrate_formal_dependency_analysis() -> None:
    print_title("Functional Dependencies and Candidate Keys")

    relation = {
        "OrderID",
        "ProductID",
        "CustomerID",
        "CustomerName",
        "ProductName",
        "Quantity",
    }

    dependencies = [
        FunctionalDependency(
            frozenset({"OrderID"}),
            frozenset({"CustomerID"}),
        ),
        FunctionalDependency(
            frozenset({"CustomerID"}),
            frozenset({"CustomerName"}),
        ),
        FunctionalDependency(
            frozenset({"ProductID"}),
            frozenset({"ProductName"}),
        ),
        FunctionalDependency(
            frozenset({"OrderID", "ProductID"}),
            frozenset({"Quantity"}),
        ),
    ]

    print("Relation attributes:")
    print("  " + ", ".join(sorted(relation)))

    print("\nFunctional dependencies:")
    describe_dependencies(dependencies)

    key_list = candidate_keys(relation, dependencies)

    print("\nCandidate keys:")
    for key in key_list:
        print("  {" + ", ".join(sorted(key)) + "}")

    order_product_closure = attribute_closure(
        {"OrderID", "ProductID"},
        dependencies,
    )

    print(
        "\nClosure of {OrderID, ProductID}: "
        + ", ".join(sorted(order_product_closure))
    )

    print(
        "\nBecause the composite key determines every attribute, it is a "
        "superkey. The smaller determinant sets OrderID and ProductID do not "
        "individually determine the complete relation."
    )


# ---------------------------------------------------------------------------
# Lossless decomposition check
# ---------------------------------------------------------------------------

def natural_join(
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Perform a small natural join using all common attribute names.

    This is deliberately simple and is intended for demonstration rather
    than high-volume query processing.
    """
    if not left_rows or not right_rows:
        return []

    common = set(left_rows[0]).intersection(right_rows[0])
    output: list[dict[str, Any]] = []

    for left in left_rows:
        for right in right_rows:
            if all(left[key] == right[key] for key in common):
                merged = dict(left)
                merged.update(right)
                output.append(merged)

    return output


def demonstrate_lossless_join() -> None:
    print_title("Lossless Decomposition")

    original = [
        {"ProductID": "P10", "ProductName": "Keyboard", "CategoryID": "CAT1", "CategoryName": "Peripherals"},
        {"ProductID": "P20", "ProductName": "Mouse", "CategoryID": "CAT1", "CategoryName": "Peripherals"},
        {"ProductID": "P30", "ProductName": "Monitor", "CategoryID": "CAT2", "CategoryName": "Displays"},
    ]

    products = [
        {"ProductID": row["ProductID"], "ProductName": row["ProductName"], "CategoryID": row["CategoryID"]}
        for row in original
    ]

    categories = [
        {"CategoryID": "CAT1", "CategoryName": "Peripherals"},
        {"CategoryID": "CAT2", "CategoryName": "Displays"},
    ]

    reconstructed = natural_join(products, categories)

    print("Original relation:")
    print_rows(original)

    print("\nReconstructed by joining Products and Categories:")
    print_rows(reconstructed)

    original_set = {tuple(sorted(row.items())) for row in original}
    reconstructed_set = {tuple(sorted(row.items())) for row in reconstructed}

    print(
        "\nLossless reconstruction:",
        "PASS" if original_set == reconstructed_set else "FAIL",
    )

    print(
        "\nThe decomposition is lossless for the shown data because the shared "
        "CategoryID connects each product to its single category row without "
        "creating spurious product-category combinations."
    )


# ---------------------------------------------------------------------------
# Data anomaly demonstrations
# ---------------------------------------------------------------------------

def demonstrate_anomalies() -> None:
    print_title("Insertion, Update, and Deletion Anomalies")

    duplicated_product_rows = [
        {"ProductID": "P20", "ProductName": "Mouse", "Category": "Peripherals"},
        {"ProductID": "P20", "ProductName": "Mouse", "Category": "Peripherals"},
        {"ProductID": "P30", "ProductName": "Monitor", "Category": "Displays"},
    ]

    print("Repeated product facts in a combined relation:")
    print_rows(duplicated_product_rows)

    duplicates = duplicate_keys(duplicated_product_rows, ("ProductID",))
    print(f"\nDuplicate ProductID values: {duplicates}")

    inconsistent = [
        {"ProductID": "P20", "ProductName": "Mouse", "Category": "Peripherals"},
        {"ProductID": "P20", "ProductName": "Wireless Mouse", "Category": "Peripherals"},
    ]

    anomalies = find_update_anomalies(
        inconsistent,
        "ProductID",
        "ProductName",
    )

    print("\nFunctional dependency violation:")
    print_rows(inconsistent)
    print(f"Detected P20 -> ProductName inconsistency: {anomalies}")

    print(
        "\nInsertion anomaly: in a tightly combined order table, a product may "
        "be impossible to record until an order exists.\n"
        "Update anomaly: one product's descriptive fact may need to be changed "
        "in many order rows.\n"
        "Deletion anomaly: deleting the last order for a product can also "
        "accidentally remove the only stored product information."
    )


# ---------------------------------------------------------------------------
# Normalized transactional model
# ---------------------------------------------------------------------------

@dataclass
class Customer:
    customer_id: str
    name: str
    city: str


@dataclass
class Product:
    product_id: str
    name: str
    category_id: str
    price: float


@dataclass
class Category:
    category_id: str
    name: str


@dataclass
class OrderLine:
    order_id: int
    product_id: str
    quantity: int


@dataclass
class Order:
    order_id: int
    customer_id: str
    lines: list[OrderLine] = field(default_factory=list)


class NormalizedOrderDatabase:
    """
    An in-memory relational-style model representing a 3NF-oriented design.

    Separate dictionaries simulate primary-key access. Foreign-key validation
    prevents orphan references.
    """

    def __init__(self) -> None:
        self.customers: dict[str, Customer] = {}
        self.categories: dict[str, Category] = {}
        self.products: dict[str, Product] = {}
        self.orders: dict[int, Order] = {}

    def add_customer(self, customer: Customer) -> None:
        if customer.customer_id in self.customers:
            raise ValueError("Customer ID already exists")
        self.customers[customer.customer_id] = customer

    def add_category(self, category: Category) -> None:
        if category.category_id in self.categories:
            raise ValueError("Category ID already exists")
        self.categories[category.category_id] = category

    def add_product(self, product: Product) -> None:
        if product.product_id in self.products:
            raise ValueError("Product ID already exists")

        if product.category_id not in self.categories:
            raise ValueError(
                f"Foreign-key violation: unknown category {product.category_id}"
            )

        if product.price < 0:
            raise ValueError("Product price cannot be negative")

        self.products[product.product_id] = product

    def add_order(self, order: Order) -> None:
        if order.order_id in self.orders:
            raise ValueError("Order ID already exists")

        if order.customer_id not in self.customers:
            raise ValueError(
                f"Foreign-key violation: unknown customer {order.customer_id}"
            )

        seen_products: set[str] = set()

        for line in order.lines:
            if line.order_id != order.order_id:
                raise ValueError("Order-line key does not match parent order")

            if line.product_id in seen_products:
                raise ValueError(
                    "Duplicate ProductID inside the same order"
                )

            if line.product_id not in self.products:
                raise ValueError(
                    f"Foreign-key violation: unknown product {line.product_id}"
                )

            if line.quantity <= 0:
                raise ValueError("Order quantity must be positive")

            seen_products.add(line.product_id)

        self.orders[order.order_id] = order

    def order_total(self, order_id: int) -> float:
        if order_id not in self.orders:
            raise KeyError(f"Unknown order {order_id}")

        order = self.orders[order_id]
        total = 0.0

        for line in order.lines:
            product = self.products[line.product_id]
            total += product.price * line.quantity

        return total

    def customer_order_report(self, customer_id: str) -> list[dict[str, Any]]:
        if customer_id not in self.customers:
            raise KeyError(f"Unknown customer {customer_id}")

        report: list[dict[str, Any]] = []
        customer = self.customers[customer_id]

        for order in self.orders.values():
            if order.customer_id != customer_id:
                continue

            for line in order.lines:
                product = self.products[line.product_id]
                category = self.categories[product.category_id]

                report.append(
                    {
                        "OrderID": order.order_id,
                        "Customer": customer.name,
                        "City": customer.city,
                        "Product": product.name,
                        "Category": category.name,
                        "Quantity": line.quantity,
                        "UnitPrice": product.price,
                        "LineTotal": product.price * line.quantity,
                    }
                )

        return report


def demonstrate_normalized_database() -> None:
    print_title("3NF-Oriented Transactional Model")

    database = NormalizedOrderDatabase()

    database.add_customer(Customer("C101", "Asha Sharma", "Lucknow"))
    database.add_customer(Customer("C102", "Ravi Kumar", "Delhi"))

    database.add_category(Category("CAT1", "Peripherals"))
    database.add_category(Category("CAT2", "Displays"))

    database.add_product(Product("P10", "Keyboard", "CAT1", 1800.0))
    database.add_product(Product("P20", "Mouse", "CAT1", 700.0))
    database.add_product(Product("P30", "Monitor", "CAT2", 12000.0))

    database.add_order(
        Order(
            order_id=1001,
            customer_id="C101",
            lines=[
                OrderLine(1001, "P10", 2),
                OrderLine(1001, "P20", 1),
            ],
        )
    )

    database.add_order(
        Order(
            order_id=1002,
            customer_id="C102",
            lines=[
                OrderLine(1002, "P20", 1),
                OrderLine(1002, "P30", 1),
            ],
        )
    )

    print("Order 1001 total:", f"{database.order_total(1001):,.2f}")

    print("\nCustomer C101 report:")
    print_rows(database.customer_order_report("C101"))


# ---------------------------------------------------------------------------
# Denormalization
# ---------------------------------------------------------------------------

@dataclass
class DenormalizedOrderSnapshot:
    """
    A read-optimized representation.

    CustomerName, ProductName, CategoryName, and UnitPrice are intentionally
    copied into the order-line snapshot. This trades write consistency and
    storage duplication for fewer joins during common reporting queries.
    """
    order_id: int
    customer_id: str
    customer_name: str
    product_id: str
    product_name: str
    category_name: str
    quantity: int
    unit_price: float

    @property
    def line_total(self) -> float:
        return self.quantity * self.unit_price


def build_denormalized_sales_snapshot(
    database: NormalizedOrderDatabase,
) -> list[DenormalizedOrderSnapshot]:
    snapshot: list[DenormalizedOrderSnapshot] = []

    for order in database.orders.values():
        customer = database.customers[order.customer_id]

        for line in order.lines:
            product = database.products[line.product_id]
            category = database.categories[product.category_id]

            snapshot.append(
                DenormalizedOrderSnapshot(
                    order_id=order.order_id,
                    customer_id=customer.customer_id,
                    customer_name=customer.name,
                    product_id=product.product_id,
                    product_name=product.name,
                    category_name=category.name,
                    quantity=line.quantity,
                    unit_price=product.price,
                )
            )

    return snapshot


def demonstrate_denormalization(database: NormalizedOrderDatabase) -> None:
    print_title("Denormalization for Read-Heavy Workloads")

    snapshot = build_denormalized_sales_snapshot(database)

    print("Read-optimized sales snapshot:")
    print_rows(
        [
            {
                "OrderID": row.order_id,
                "Customer": row.customer_name,
                "Product": row.product_name,
                "Category": row.category_name,
                "Qty": row.quantity,
                "UnitPrice": row.unit_price,
                "LineTotal": row.line_total,
            }
            for row in snapshot
        ]
    )

    print(
        "\nThe snapshot intentionally duplicates descriptive values. It can "
        "make reporting simpler and reduce join work, but updates now require "
        "careful synchronization between the authoritative normalized tables "
        "and the derived representation."
    )


# ---------------------------------------------------------------------------
# Consistency validation for denormalized data
# ---------------------------------------------------------------------------

def validate_snapshot(
    database: NormalizedOrderDatabase,
    snapshot: list[DenormalizedOrderSnapshot],
) -> list[str]:
    errors: list[str] = []

    for row in snapshot:
        if row.order_id not in database.orders:
            errors.append(f"Snapshot references missing order {row.order_id}")
            continue

        order = database.orders[row.order_id]

        if order.customer_id != row.customer_id:
            errors.append(
                f"Order {row.order_id}: customer ID differs from source"
            )

        source_customer = database.customers[order.customer_id]

        if row.customer_name != source_customer.name:
            errors.append(
                f"Order {row.order_id}: stale customer name"
            )

        if row.product_id not in database.products:
            errors.append(
                f"Order {row.order_id}: missing product {row.product_id}"
            )
            continue

        source_product = database.products[row.product_id]
        source_category = database.categories[source_product.category_id]

        if row.product_name != source_product.name:
            errors.append(
                f"Product {row.product_id}: stale product name"
            )

        if row.category_name != source_category.name:
            errors.append(
                f"Product {row.product_id}: stale category name"
            )

        if row.unit_price != source_product.price:
            errors.append(
                f"Product {row.product_id}: stale unit price"
            )

    return errors


def demonstrate_denormalization_consistency(
    database: NormalizedOrderDatabase,
) -> None:
    print_title("Denormalized Data Consistency")

    snapshot = build_denormalized_sales_snapshot(database)

    database.products["P20"].price = 750.0

    errors = validate_snapshot(database, snapshot)

    print("Source product P20 price changed to 750.00.")
    print("Existing snapshot validation:")

    if errors:
        for error in errors:
            print(f"  STALE: {error}")
    else:
        print("  PASS")

    refreshed = build_denormalized_sales_snapshot(database)

    print("\nAfter refreshing the derived snapshot:")
    errors_after_refresh = validate_snapshot(database, refreshed)
    print(
        "  PASS" if not errors_after_refresh
        else "\n".join(f"  ERROR: {error}" for error in errors_after_refresh)
    )


# ---------------------------------------------------------------------------
# Comparative query-cost simulation
# ---------------------------------------------------------------------------

def generate_synthetic_database(
    customer_count: int = 500,
    product_count: int = 1000,
    order_count: int = 5000,
) -> NormalizedOrderDatabase:
    """
    Generate deterministic data without external dependencies.

    The values are intentionally simple, while the row counts are large
    enough to illustrate why indexes and join strategy matter.
    """
    database = NormalizedOrderDatabase()

    for index in range(1, customer_count + 1):
        customer_id = f"C{index:05d}"
        database.add_customer(
            Customer(
                customer_id,
                f"Customer {index}",
                f"City {index % 25}",
            )
        )

    for index in range(1, 21):
        database.add_category(
            Category(
                f"CAT{index:03d}",
                f"Category {index}",
            )
        )

    for index in range(1, product_count + 1):
        product_id = f"P{index:05d}"
        database.add_product(
            Product(
                product_id,
                f"Product {index}",
                f"CAT{(index % 20) + 1:03d}",
                float(100 + (index % 5000)),
            )
        )

    for order_id in range(1, order_count + 1):
        customer_id = f"C{((order_id - 1) % customer_count) + 1:05d}"

        first_product = ((order_id * 7) % product_count) + 1
        second_product = ((order_id * 13) % product_count) + 1

        lines = [
            OrderLine(
                order_id,
                f"P{first_product:05d}",
                (order_id % 4) + 1,
            )
        ]

        if second_product != first_product:
            lines.append(
                OrderLine(
                    order_id,
                    f"P{second_product:05d}",
                    ((order_id + 1) % 3) + 1,
                )
            )

        database.add_order(
            Order(
                order_id,
                customer_id,
                lines,
            )
        )

    return database


def count_normalized_report_work(
    database: NormalizedOrderDatabase,
) -> int:
    """
    Count logical row traversals for a simple normalized reporting strategy.

    This is not a database-engine benchmark. It demonstrates that a report
    requires traversing orders and resolving foreign-key relationships.
    """
    work = 0

    for order in database.orders.values():
        work += 1

        if order.customer_id in database.customers:
            work += 1

        for line in order.lines:
            work += 1

            if line.product_id in database.products:
                work += 1

                product = database.products[line.product_id]
                if product.category_id in database.categories:
                    work += 1

    return work


def count_denormalized_report_work(
    snapshot: list[DenormalizedOrderSnapshot],
) -> int:
    """
    A denormalized report can read each already-expanded row directly.
    """
    return len(snapshot)


def demonstrate_query_tradeoff() -> None:
    print_title("Normalization Versus Denormalization: Workload Trade-off")

    database = generate_synthetic_database(
        customer_count=100,
        product_count=250,
        order_count=1000,
    )

    snapshot = build_denormalized_sales_snapshot(database)

    normalized_work = count_normalized_report_work(database)
    denormalized_work = count_denormalized_report_work(snapshot)

    print(f"Orders: {len(database.orders):,}")
    print(f"Products: {len(database.products):,}")
    print(f"Customers: {len(database.customers):,}")
    print(f"Denormalized snapshot rows: {len(snapshot):,}")

    print(f"\nLogical normalized traversal units: {normalized_work:,}")
    print(f"Logical denormalized row reads: {denormalized_work:,}")

    print(
        "\nThis is a conceptual comparison, not a substitute for measuring a "
        "real database. Real performance depends on indexes, cardinality, "
        "join algorithms, cache behavior, storage layout, query plans, "
        "concurrency, and workload shape."
    )


# ---------------------------------------------------------------------------
# Edge cases and validation
# ---------------------------------------------------------------------------

def demonstrate_validation_failures() -> None:
    print_title("Normalization-Related Validation and Failure Cases")

    database = NormalizedOrderDatabase()
    database.add_category(Category("CAT1", "Peripherals"))

    cases: list[tuple[str, Any]] = [
        (
            "Product referencing an unknown category",
            lambda: database.add_product(
                Product("P99", "Invalid Product", "CAT404", 100.0)
            ),
        ),
        (
            "Negative product price",
            lambda: database.add_product(
                Product("P98", "Invalid Price", "CAT1", -10.0)
            ),
        ),
    ]

    for description, operation in cases:
        try:
            operation()
        except (ValueError, KeyError) as error:
            print(f"{description}: correctly rejected -> {error}")

    database.add_product(Product("P10", "Keyboard", "CAT1", 1800.0))
    database.add_customer(Customer("C101", "Asha Sharma", "Lucknow"))

    try:
        database.add_order(
            Order(
                2001,
                "C101",
                [
                    OrderLine(2001, "P10", 1),
                    OrderLine(2001, "P10", 2),
                ],
            )
        )
    except ValueError as error:
        print(f"Duplicate order-line key: correctly rejected -> {error}")

    try:
        database.add_order(
            Order(
                2002,
                "C101",
                [OrderLine(2002, "P404", 1)],
            )
        )
    except ValueError as error:
        print(f"Unknown product foreign key: correctly rejected -> {error}")


# ---------------------------------------------------------------------------
# Practical design checklist encoded as executable validation
# ---------------------------------------------------------------------------

def evaluate_design_rules() -> dict[str, bool]:
    """
    Evaluate concrete properties of the example 3NF-oriented design.

    These checks are intentionally tied to the model rather than being
    generic claims about every relational schema.
    """
    database = NormalizedOrderDatabase()

    database.add_category(Category("CAT1", "Peripherals"))
    database.add_customer(Customer("C1", "Customer One", "Lucknow"))
    database.add_product(Product("P1", "Keyboard", "CAT1", 1800.0))
    database.add_order(
        Order(
            1,
            "C1",
            [OrderLine(1, "P1", 2)],
        )
    )

    return {
        "primary identifiers are unique": (
            len(database.customers) == len(set(database.customers))
            and len(database.products) == len(set(database.products))
            and len(database.orders) == len(set(database.orders))
        ),
        "product category foreign key exists": all(
            product.category_id in database.categories
            for product in database.products.values()
        ),
        "order customer foreign key exists": all(
            order.customer_id in database.customers
            for order in database.orders.values()
        ),
        "order-line product foreign keys exist": all(
            line.product_id in database.products
            for order in database.orders.values()
            for line in order.lines
        ),
    }


def demonstrate_design_rules() -> None:
    print_title("Concrete Integrity Checks")

    results = evaluate_design_rules()

    for rule, passed in results.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {rule}")


# ---------------------------------------------------------------------------
# Main demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    print_title("Database Normalization Case Study")
    print(
        "Scenario: a transactional order system evolving from a repeating-group "
        "design to 1NF, 2NF, 3NF, and a deliberately denormalized reporting view."
    )

    demonstrate_unnormalized_form()

    rows_1nf = demonstrate_1nf()

    tables_2nf = demonstrate_2nf(rows_1nf)

    demonstrate_3nf()

    demonstrate_formal_dependency_analysis()

    demonstrate_lossless_join()

    demonstrate_anomalies()

    demonstrate_normalized_database()

    database = NormalizedOrderDatabase()

    database.add_customer(Customer("C101", "Asha Sharma", "Lucknow"))
    database.add_category(Category("CAT1", "Peripherals"))
    database.add_product(Product("P10", "Keyboard", "CAT1", 1800.0))
    database.add_order(
        Order(
            1001,
            "C101",
            [OrderLine(1001, "P10", 2)],
        )
    )

    demonstrate_denormalization(database)
    demonstrate_denormalization_consistency(database)
    demonstrate_query_tradeoff()
    demonstrate_validation_failures()
    demonstrate_design_rules()

    print_title("Execution Complete")
    print(
        "The example separates atomicity, partial-dependency removal, "
        "transitive-dependency removal, and workload-driven denormalization "
        "so that each design decision can be evaluated independently."
    )


if __name__ == "__main__":
    main()
