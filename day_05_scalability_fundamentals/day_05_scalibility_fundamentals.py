"""
GREATEST COMMON DIVISOR (GCD)
=============================

A comprehensive, executable study guide covering the Greatest Common Divisor
from absolute beginner concepts through advanced algorithms, mathematical
properties, implementation techniques, edge cases, complexity analysis,
testing, and practical applications.

The script uses only Python's standard library.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from math import gcd as math_gcd
from random import randint, seed
from time import perf_counter
from typing import Iterable, List, Sequence, Tuple


# ============================================================================
# 1. FUNDAMENTAL DEFINITIONS
# ============================================================================

def demonstrate_basic_divisibility() -> None:
    """
    A divisor of n is an integer d for which n % d == 0.

    Example:
        3 divides 12 because 12 % 3 == 0.
        5 does not divide 12 because 12 % 5 != 0.
    """
    number = 12
    candidates = [1, 2, 3, 4, 5, 6, 12]

    print("\n1. DIVISIBILITY")
    print(f"Number: {number}")

    for candidate in candidates:
        print(
            f"{candidate:2} is a divisor of {number}: "
            f"{number % candidate == 0}"
        )


def divisors(number: int) -> List[int]:
    """
    Return all positive divisors of an integer.

    This simple implementation is intentionally based on trial division so
    that the connection between divisors and GCD is visible.

    For negative numbers, divisors are based on abs(number).
    Zero has infinitely many divisors in the mathematical sense, so it is
    rejected here.
    """
    number = abs(number)

    if number == 0:
        raise ValueError("Zero has infinitely many divisors.")

    return [candidate for candidate in range(1, number + 1) if number % candidate == 0]


def demonstrate_divisors() -> None:
    print("\n2. DIVISORS")

    for number in [12, 18, 25]:
        print(f"Divisors of {number}: {divisors(number)}")


# ============================================================================
# 2. GREATEST COMMON DIVISOR: DEFINITION
# ============================================================================

def gcd_by_definition(a: int, b: int) -> int:
    """
    Compute the GCD by explicitly finding common positive divisors.

    The greatest common divisor of a and b is the largest positive integer
    that divides both numbers.

    This is useful pedagogically but is not efficient for large inputs.
    """
    a = abs(a)
    b = abs(b)

    if a == 0 and b == 0:
        raise ValueError("GCD(0, 0) is undefined.")

    limit = min(a, b)

    # If one value is zero, every positive divisor of the nonzero value
    # divides both values.
    if limit == 0:
        return max(a, b)

    common_divisors = [
        candidate
        for candidate in range(1, limit + 1)
        if a % candidate == 0 and b % candidate == 0
    ]

    return max(common_divisors)


def demonstrate_definition() -> None:
    print("\n3. GCD BY DEFINITION")

    a, b = 18, 24
    print(f"Divisors of {a}: {divisors(a)}")
    print(f"Divisors of {b}: {divisors(b)}")
    print(f"GCD({a}, {b}) = {gcd_by_definition(a, b)}")


# ============================================================================
# 3. BRUTE-FORCE GCD
# ============================================================================

def gcd_brute_force(a: int, b: int) -> int:
    """
    Compute GCD by checking every possible integer from 1 through min(a, b).

    Complexity:
        Time:  O(min(|a|, |b|))
        Space: O(1)

    This method is easy to understand but scales poorly.
    """
    a = abs(a)
    b = abs(b)

    if a == 0 and b == 0:
        raise ValueError("GCD(0, 0) is undefined.")

    for candidate in range(min(a, b), 0, -1):
        if a % candidate == 0 and b % candidate == 0:
            return candidate

    return max(a, b)


# ============================================================================
# 4. EUCLIDEAN ALGORITHM
# ============================================================================

def gcd_euclidean(a: int, b: int) -> int:
    """
    Compute the GCD using the Euclidean algorithm.

    Fundamental identity:

        gcd(a, b) = gcd(b, a mod b)

    Repeatedly replacing (a, b) with (b, a % b) eventually produces zero.
    The remaining nonzero value is the GCD.

    Example:

        gcd(48, 18)

        48 % 18 = 12
        18 % 12 = 6
        12 % 6  = 0

        Therefore GCD = 6.

    Complexity:
        Time:  O(log(min(|a|, |b|))) for the arithmetic-operation model.
        Space: O(1) for the iterative implementation.
    """
    a = abs(a)
    b = abs(b)

    if a == 0 and b == 0:
        raise ValueError("GCD(0, 0) is undefined.")

    while b != 0:
        a, b = b, a % b

    return a


def demonstrate_euclidean_algorithm() -> None:
    print("\n4. EUCLIDEAN ALGORITHM")

    a, b = 48, 18
    print(f"Computing GCD({a}, {b})")

    while b != 0:
        remainder = a % b
        print(f"{a} % {b} = {remainder}")
        a, b = b, remainder

    print(f"GCD = {a}")


# ============================================================================
# 5. RECURSIVE EUCLIDEAN ALGORITHM
# ============================================================================

def gcd_recursive(a: int, b: int) -> int:
    """
    Recursive form of the Euclidean algorithm.

    Mathematical recurrence:

        gcd(a, b) = gcd(b, a % b)

    Base case:

        gcd(a, 0) = |a|

    Python recursion introduces call-stack overhead, so the iterative
    implementation is generally preferable for production code.
    """
    a = abs(a)
    b = abs(b)

    if a == 0 and b == 0:
        raise ValueError("GCD(0, 0) is undefined.")

    if b == 0:
        return a

    return gcd_recursive(b, a % b)


# ============================================================================
# 6. BINARY GCD / STEIN'S ALGORITHM
# ============================================================================

def gcd_binary(a: int, b: int) -> int:
    """
    Compute GCD using Stein's binary GCD algorithm.

    It replaces division and remainder operations with operations involving:

        * parity checks
        * subtraction
        * powers of two

    Key rules:

        gcd(0, b) = |b|

        gcd(2a, 2b) = 2 * gcd(a, b)

        gcd(2a, b) = gcd(a, b) when b is odd

        gcd(a, b) = gcd(|a-b|, min(a,b)) for suitable reduced values.

    Python's built-in integers are arbitrary precision, so the performance
    trade-offs differ from fixed-width machine integer implementations.
    """
    a = abs(a)
    b = abs(b)

    if a == 0 and b == 0:
        raise ValueError("GCD(0, 0) is undefined.")

    if a == 0:
        return b

    if b == 0:
        return a

    common_power_of_two = 0

    # Remove common factors of 2 from both values.
    while ((a | b) & 1) == 0:
        a >>= 1
        b >>= 1
        common_power_of_two += 1

    # Make a odd.
    while (a & 1) == 0:
        a >>= 1

    while b != 0:
        # Make b odd.
        while (b & 1) == 0:
            b >>= 1

        # Keep the smaller value in a.
        if a > b:
            a, b = b, a

        b -= a

    return a << common_power_of_two


# ============================================================================
# 7. HANDLING ZERO AND NEGATIVE VALUES
# ============================================================================

def demonstrate_edge_cases() -> None:
    print("\n5. ZERO AND NEGATIVE VALUES")

    test_cases = [
        (0, 15),
        (15, 0),
        (-15, 25),
        (15, -25),
        (-15, -25),
        (1, 999),
    ]

    for a, b in test_cases:
        print(f"GCD({a}, {b}) = {gcd_euclidean(a, b)}")

    print("GCD(0, 0) is mathematically undefined.")

    try:
        gcd_euclidean(0, 0)
    except ValueError as error:
        print(f"Handled exception: {error}")


# ============================================================================
# 8. GCD OF MORE THAN TWO NUMBERS
# ============================================================================

def gcd_many(numbers: Iterable[int]) -> int:
    """
    Compute the GCD of an iterable of integers.

    Associativity allows:

        gcd(a, b, c) = gcd(gcd(a, b), c)

    An empty collection has no mathematically defined GCD in this
    implementation, so ValueError is raised.
    """
    numbers = list(numbers)

    if not numbers:
        raise ValueError("GCD of an empty collection is undefined.")

    result = 0

    for number in numbers:
        result = gcd_euclidean(result, number)

    return result


def demonstrate_gcd_many() -> None:
    print("\n6. GCD OF MULTIPLE NUMBERS")

    numbers = [84, 126, 210, 294]
    print(f"Numbers: {numbers}")
    print(f"GCD = {gcd_many(numbers)}")


# ============================================================================
# 9. BUILT-IN PYTHON GCD
# ============================================================================

def demonstrate_python_math_gcd() -> None:
    """
    Python's math.gcd is implemented efficiently and accepts multiple
    arguments in modern Python versions.

    For production Python programs, math.gcd is normally preferable to
    reimplementing the Euclidean algorithm unless the implementation itself
    is part of the educational or algorithmic requirement.
    """
    print("\n7. PYTHON'S STANDARD-LIBRARY GCD")

    print(f"math.gcd(48, 18) = {math_gcd(48, 18)}")
    print(f"math.gcd(84, 126, 210) = {math_gcd(84, 126, 210)}")


# ============================================================================
# 10. RELATIONSHIP BETWEEN GCD AND LCM
# ============================================================================

def lcm(a: int, b: int) -> int:
    """
    Compute the Least Common Multiple.

    For nonzero integers:

        lcm(a, b) = |a * b| / gcd(a, b)

    The multiplication is performed after division by the GCD to reduce
    unnecessary intermediate magnitude.

    Special case:

        lcm(a, 0) = 0
    """
    if a == 0 or b == 0:
        return 0

    return abs((a // gcd_euclidean(a, b)) * b)


def lcm_many(numbers: Iterable[int]) -> int:
    """
    Compute the LCM of multiple integers.

    Zero causes the final LCM to become zero.
    """
    numbers = list(numbers)

    if not numbers:
        raise ValueError("LCM of an empty collection is undefined.")

    result = 1

    for number in numbers:
        result = lcm(result, number)

    return result


def demonstrate_gcd_lcm_relationship() -> None:
    print("\n8. GCD AND LCM")

    a, b = 12, 18
    g = gcd_euclidean(a, b)
    multiple = lcm(a, b)

    print(f"GCD({a}, {b}) = {g}")
    print(f"LCM({a}, {b}) = {multiple}")
    print(f"GCD * LCM = {g * multiple}")
    print(f"|a * b| = {abs(a * b)}")


# ============================================================================
# 11. COPRIME NUMBERS
# ============================================================================

def are_coprime(a: int, b: int) -> bool:
    """
    Two integers are coprime if their GCD is exactly 1.

    Coprime numbers do not need to be prime themselves.

    Example:
        8 and 15 are coprime.
        8 is not prime and 15 is not prime.
    """
    return gcd_euclidean(a, b) == 1


def demonstrate_coprime() -> None:
    print("\n9. COPRIME NUMBERS")

    examples = [(8, 15), (12, 18), (35, 64), (21, 49)]

    for a, b in examples:
        print(f"{a} and {b} are coprime: {are_coprime(a, b)}")


# ============================================================================
# 12. PRIME FACTORIZATION CONNECTION
# ============================================================================

def prime_factorization(number: int) -> dict[int, int]:
    """
    Return the prime factorization of a nonzero integer.

    Example:

        60 = 2^2 * 3^1 * 5^1

    The GCD can be obtained from the minimum exponent of every prime
    appearing in both factorizations.

    This implementation is intended to demonstrate the mathematical
    relationship, not to be the fastest factorization algorithm.
    """
    number = abs(number)

    if number < 2:
        return {}

    factors: dict[int, int] = {}
    candidate = 2

    while candidate * candidate <= number:
        while number % candidate == 0:
            factors[candidate] = factors.get(candidate, 0) + 1
            number //= candidate

        candidate = 3 if candidate == 2 else candidate + 2

    if number > 1:
        factors[number] = factors.get(number, 0) + 1

    return factors


def gcd_from_prime_factorization(a: int, b: int) -> int:
    """
    Compute GCD from prime factorizations.

    For each prime p:

        exponent_GCD(p) = min(exponent_a(p), exponent_b(p))
    """
    if a == 0 and b == 0:
        raise ValueError("GCD(0, 0) is undefined.")

    if a == 0:
        return abs(b)

    if b == 0:
        return abs(a)

    factors_a = prime_factorization(a)
    factors_b = prime_factorization(b)

    result = 1

    for prime, exponent_a in factors_a.items():
        if prime in factors_b:
            result *= prime ** min(exponent_a, factors_b[prime])

    return result


def demonstrate_prime_factorization() -> None:
    print("\n10. PRIME FACTORIZATION AND GCD")

    a, b = 360, 504

    print(f"{a} factorization: {prime_factorization(a)}")
    print(f"{b} factorization: {prime_factorization(b)}")
    print(f"GCD from factorization = {gcd_from_prime_factorization(a, b)}")
    print(f"GCD from Euclidean algorithm = {gcd_euclidean(a, b)}")


# ============================================================================
# 13. GCD OF FRACTIONS
# ============================================================================

@dataclass(frozen=True)
class Fraction:
    """
    A minimal exact rational-number representation.

    Fractions are normalized using the GCD.

    Examples:

        Fraction(6, 8) becomes 3/4.
        Fraction(-6, -8) becomes 3/4.
        Fraction(6, -8) becomes -3/4.
    """

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if self.denominator == 0:
            raise ValueError("Denominator cannot be zero.")

        numerator = self.numerator
        denominator = self.denominator

        common = gcd_euclidean(numerator, denominator)

        numerator //= common
        denominator //= common

        if denominator < 0:
            numerator = -numerator
            denominator = -denominator

        object.__setattr__(self, "numerator", numerator)
        object.__setattr__(self, "denominator", denominator)

    def __str__(self) -> str:
        return f"{self.numerator}/{self.denominator}"


def demonstrate_fraction_reduction() -> None:
    print("\n11. GCD AND FRACTION REDUCTION")

    examples = [
        (6, 8),
        (42, 56),
        (-18, -24),
        (18, -24),
    ]

    for numerator, denominator in examples:
        fraction = Fraction(numerator, denominator)
        print(f"{numerator}/{denominator} -> {fraction}")


# ============================================================================
# 14. REDUCING RATIOS
# ============================================================================

def reduce_ratio(a: int, b: int) -> Tuple[int, int]:
    """
    Reduce an integer ratio to lowest terms.

    Example:

        48:18 -> 8:3
    """
    if a == 0 and b == 0:
        raise ValueError("A 0:0 ratio cannot be reduced to a unique ratio.")

    common = gcd_euclidean(a, b)

    return a // common, b // common


def demonstrate_ratio_reduction() -> None:
    print("\n12. REDUCING RATIOS")

    examples = [(48, 18), (100, 250), (17, 19), (0, 25)]

    for a, b in examples:
        print(f"{a}:{b} -> {reduce_ratio(a, b)[0]}:{reduce_ratio(a, b)[1]}")


# ============================================================================
# 15. GCD OF POLYNOMIAL-LIKE COEFFICIENT LISTS
# ============================================================================

def gcd_of_coefficients(coefficients: Sequence[int]) -> int:
    """
    Find the common integer factor shared by all polynomial coefficients.

    Example:

        6x^2 + 12x + 18

    has coefficient GCD 6.

    This is useful when identifying a common numerical factor before
    algebraic simplification.
    """
    if not coefficients:
        raise ValueError("At least one coefficient is required.")

    return gcd_many(coefficients)


def demonstrate_coefficient_gcd() -> None:
    print("\n13. GCD OF POLYNOMIAL COEFFICIENTS")

    coefficients = [24, 36, 60, 84]
    print(f"Coefficients: {coefficients}")
    print(f"Common coefficient factor: {gcd_of_coefficients(coefficients)}")


# ============================================================================
# 16. EXTENDED EUCLIDEAN ALGORITHM
# ============================================================================

def extended_gcd(a: int, b: int) -> Tuple[int, int, int]:
    """
    Compute (g, x, y) such that:

        g = gcd(a, b)
        ax + by = g

    This is Bézout's identity.

    Example:

        a = 30
        b = 12

        gcd = 6

        One valid solution is:
            30(1) + 12(-2) = 6

    The returned coefficients can be negative.
    """
    original_a = a
    original_b = b

    old_r, r = abs(a), abs(b)
    old_s, s = 1, 0
    old_t, t = 0, 1

    while r != 0:
        quotient = old_r // r

        old_r, r = r, old_r - quotient * r
        old_s, s = s, old_s - quotient * s
        old_t, t = t, old_t - quotient * t

    x = old_s if original_a >= 0 else -old_s
    y = old_t if original_b >= 0 else -old_t

    return old_r, x, y


def demonstrate_extended_gcd() -> None:
    print("\n14. EXTENDED EUCLIDEAN ALGORITHM")

    a, b = 30, 12
    g, x, y = extended_gcd(a, b)

    print(f"GCD({a}, {b}) = {g}")
    print(f"Bezout coefficients: x = {x}, y = {y}")
    print(f"{a}({x}) + {b}({y}) = {a * x + b * y}")


# ============================================================================
# 17. MODULAR MULTIPLICATIVE INVERSE
# ============================================================================

def modular_inverse(a: int, modulus: int) -> int:
    """
    Find x such that:

        a*x ≡ 1 (mod modulus)

    Such an inverse exists exactly when:

        gcd(a, modulus) = 1

    The extended Euclidean algorithm supplies the coefficient needed to
    construct the inverse.
    """
    if modulus <= 0:
        raise ValueError("Modulus must be positive.")

    g, x, _ = extended_gcd(a, modulus)

    if g != 1:
        raise ValueError(
            f"No modular inverse exists because gcd({a}, {modulus}) != 1."
        )

    return x % modulus


def demonstrate_modular_inverse() -> None:
    print("\n15. MODULAR MULTIPLICATIVE INVERSE")

    a, modulus = 3, 11
    inverse = modular_inverse(a, modulus)

    print(f"Inverse of {a} modulo {modulus}: {inverse}")
    print(f"({a} * {inverse}) % {modulus} = {(a * inverse) % modulus}")

    try:
        modular_inverse(6, 15)
    except ValueError as error:
        print(f"Handled non-invertible case: {error}")


# ============================================================================
# 18. SOLVING LINEAR DIOPHANTINE EQUATIONS
# ============================================================================

def solve_linear_diophantine(
    a: int,
    b: int,
    c: int,
) -> Tuple[int, int] | None:
    """
    Find one integer solution (x, y) to:

        ax + by = c

    An integer solution exists exactly when:

        gcd(a, b) divides c

    The extended Euclidean algorithm provides the initial solution.
    """
    if a == 0 and b == 0:
        return (0, 0) if c == 0 else None

    g, x, y = extended_gcd(a, b)

    if c % g != 0:
        return None

    multiplier = c // g

    return x * multiplier, y * multiplier


def demonstrate_diophantine_equation() -> None:
    print("\n16. LINEAR DIOPHANTINE EQUATIONS")

    a, b, c = 15, 25, 5
    solution = solve_linear_diophantine(a, b, c)

    print(f"Equation: {a}x + {b}y = {c}")

    if solution is None:
        print("No integer solution exists.")
    else:
        x, y = solution
        print(f"One solution: x = {x}, y = {y}")
        print(f"Verification: {a * x + b * y} = {c}")

    impossible = solve_linear_diophantine(6, 10, 7)
    print(f"6x + 10y = 7 has solution: {impossible is not None}")


# ============================================================================
# 19. GCD AND MODULAR EQUATIONS
# ============================================================================

def solve_linear_congruence(
    a: int,
    b: int,
    modulus: int,
) -> List[int]:
    """
    Solve:

        a*x ≡ b (mod modulus)

    Let:

        g = gcd(a, modulus)

    A solution exists exactly when g divides b.

    After dividing by g:

        (a/g)x ≡ (b/g) (mod modulus/g)

    The reduced coefficient a/g is coprime with modulus/g, so a modular
    inverse exists.

    The returned solutions are represented in [0, modulus).
    """
    if modulus <= 0:
        raise ValueError("Modulus must be positive.")

    g = gcd_euclidean(a, modulus)

    if b % g != 0:
        return []

    reduced_a = a // g
    reduced_b = b // g
    reduced_modulus = modulus // g

    inverse = modular_inverse(reduced_a, reduced_modulus)
    base_solution = (inverse * reduced_b) % reduced_modulus

    return [
        (base_solution + k * reduced_modulus) % modulus
        for k in range(g)
    ]


def demonstrate_linear_congruence() -> None:
    print("\n17. LINEAR CONGRUENCES")

    a, b, modulus = 6, 8, 14
    solutions = solve_linear_congruence(a, b, modulus)

    print(f"Solve {a}x ≡ {b} (mod {modulus})")
    print(f"Solutions in [0, {modulus}): {solutions}")

    for x in solutions:
        print(
            f"x={x}: ({a}*{x}) % {modulus} = "
            f"{(a * x) % modulus}"
        )


# ============================================================================
# 20. GCD AND FIBONACCI NUMBERS
# ============================================================================

def fibonacci(number: int) -> int:
    """
    Compute the nth Fibonacci number iteratively.

    The Fibonacci sequence is closely related to the Euclidean algorithm:
    consecutive Fibonacci numbers form worst-case inputs for the number
    of Euclidean iterations.

    F(0)=0, F(1)=1.
    """
    if number < 0:
        raise ValueError("Fibonacci index must be non-negative.")

    previous, current = 0, 1

    for _ in range(number):
        previous, current = current, previous + current

    return previous


def demonstrate_fibonacci_connection() -> None:
    print("\n18. GCD AND FIBONACCI NUMBERS")

    pairs = [
        (fibonacci(index), fibonacci(index + 1))
        for index in range(2, 8)
    ]

    for a, b in pairs:
        print(f"GCD({a}, {b}) = {gcd_euclidean(a, b)}")


# ============================================================================
# 21. GCD PROPERTY TESTING
# ============================================================================

def verify_gcd_properties(a: int, b: int) -> dict[str, bool]:
    """
    Verify important mathematical properties for a pair of integers.

    Properties demonstrated:

        1. Symmetry:
           gcd(a,b) = gcd(b,a)

        2. Non-negativity:
           gcd(a,b) >= 0

        3. Divisibility:
           gcd(a,b) divides both a and b

        4. Euclidean identity:
           gcd(a,b) = gcd(b,a%b) when b != 0

        5. Multiplication:
           gcd(ka,kb) = |k|gcd(a,b)
    """
    if a == 0 and b == 0:
        raise ValueError("Cannot test GCD properties for (0, 0).")

    g = gcd_euclidean(a, b)

    symmetry = g == gcd_euclidean(b, a)
    non_negative = g >= 0

    divides_a = a % g == 0
    divides_b = b % g == 0

    euclidean_identity = (
        True
        if b == 0
        else g == gcd_euclidean(b, a % b)
    )

    k = 7
    scaling_property = (
        gcd_euclidean(k * a, k * b) == abs(k) * g
    )

    return {
        "symmetry": symmetry,
        "non_negative": non_negative,
        "divides_a": divides_a,
        "divides_b": divides_b,
        "euclidean_identity": euclidean_identity,
        "scaling_property": scaling_property,
    }


# ============================================================================
# 22. ALGORITHM COMPARISON
# ============================================================================

def compare_algorithms() -> None:
    """
    Compare several implementations on moderate random inputs.

    Timing is illustrative rather than a formal benchmark. Hardware,
    Python version, integer size, and system load influence results.
    """
    print("\n19. ALGORITHM COMPARISON")

    seed(42)

    test_cases = [
        (randint(10**4, 10**5), randint(10**4, 10**5))
        for _ in range(100)
    ]

    algorithms = [
        ("Brute force", gcd_brute_force),
        ("Euclidean", gcd_euclidean),
        ("Recursive Euclidean", gcd_recursive),
        ("Binary GCD", gcd_binary),
        ("math.gcd", math_gcd),
    ]

    for name, algorithm in algorithms:
        start = perf_counter()

        for a, b in test_cases:
            algorithm(a, b)

        elapsed = perf_counter() - start

        print(f"{name:20} {elapsed:.8f} seconds")


# ============================================================================
# 23. VALIDATION AND PROPERTY-BASED TESTING
# ============================================================================

def run_consistency_tests() -> None:
    """
    Compare independent implementations across many inputs.

    Testing multiple implementations against each other is useful because
    the brute-force version provides a simple reference implementation for
    relatively small values.
    """
    print("\n20. CONSISTENCY TESTS")

    for a in range(-25, 26):
        for b in range(-25, 26):
            if a == 0 and b == 0:
                continue

            expected = gcd_brute_force(a, b)

            assert gcd_euclidean(a, b) == expected
            assert gcd_recursive(a, b) == expected
            assert gcd_binary(a, b) == expected
            assert math_gcd(a, b) == expected
            assert gcd_from_prime_factorization(a, b) == expected

    print("All implementation consistency tests passed.")


def test_edge_cases() -> None:
    """
    Explicit tests for important boundary conditions.
    """
    print("\n21. EDGE-CASE TESTS")

    cases = [
        (0, 1, 1),
        (1, 0, 1),
        (0, 17, 17),
        (-17, 0, 17),
        (-24, 18, 6),
        (24, -18, 6),
        (-24, -18, 6),
        (1, 1, 1),
        (17, 19, 1),
        (100, 10, 10),
    ]

    for a, b, expected in cases:
        actual = gcd_euclidean(a, b)
        assert actual == expected, (
            f"GCD({a}, {b}) expected {expected}, got {actual}"
        )

    print("All edge-case tests passed.")


# ============================================================================
# 24. PRACTICAL APPLICATION: PACKING EQUAL-SIZED SQUARES
# ============================================================================

def largest_square_tile_side(length: int, width: int) -> int:
    """
    Given a rectangular area with integer side lengths, find the largest
    square tile side length that can exactly cover the rectangle.

    The answer is:

        gcd(length, width)

    because that is the largest integer length dividing both dimensions.
    """
    if length <= 0 or width <= 0:
        raise ValueError("Dimensions must be positive.")

    return gcd_euclidean(length, width)


def demonstrate_tile_problem() -> None:
    print("\n22. PRACTICAL APPLICATION: SQUARE TILES")

    length, width = 48, 18
    side = largest_square_tile_side(length, width)

    print(f"Rectangle: {length} x {width}")
    print(f"Largest square tile side: {side}")
    print(f"Number of tiles: {(length // side) * (width // side)}")


# ============================================================================
# 25. PRACTICAL APPLICATION: REPEATING CYCLES
# ============================================================================

def cycle_alignment_period(period_a: int, period_b: int) -> int:
    """
    Return the smallest positive time unit at which two repeating events
    return to their joint starting alignment.

    This is an LCM problem rather than a GCD problem.

    GCD is still essential because:

        LCM(a,b) = |ab| / GCD(a,b)
    """
    return lcm(period_a, period_b)


def demonstrate_cycle_alignment() -> None:
    print("\n23. PRACTICAL APPLICATION: REPEATING CYCLES")

    first_cycle = 12
    second_cycle = 18

    alignment = cycle_alignment_period(first_cycle, second_cycle)

    print(f"Cycles: {first_cycle} and {second_cycle}")
    print(f"First common alignment after: {alignment}")


# ============================================================================
# 26. PRACTICAL APPLICATION: DATA NORMALIZATION
# ============================================================================

def normalize_integer_vector(values: Sequence[int]) -> Tuple[int, ...]:
    """
    Divide every element of an integer vector by the vector's common GCD.

    Example:

        [18, 24, 30] -> [3, 4, 5]

    This technique is useful when representing integer ratios or normalized
    coefficient vectors.
    """
    if not values:
        raise ValueError("Vector cannot be empty.")

    common = gcd_many(values)

    if common == 0:
        return tuple(values)

    return tuple(value // common for value in values)


def demonstrate_vector_normalization() -> None:
    print("\n24. PRACTICAL APPLICATION: INTEGER VECTOR NORMALIZATION")

    vector = [18, 24, 30]
    print(f"Original vector: {vector}")
    print(f"Normalized vector: {normalize_integer_vector(vector)}")


# ============================================================================
# 27. GCD OF LARGE INTEGER VALUES
# ============================================================================

def demonstrate_large_integers() -> None:
    """
    Python integers can grow beyond fixed machine-word sizes.

    The Euclidean algorithm remains conceptually unchanged, although the
    cost of arithmetic operations depends on the number of bits in the
    operands.
    """
    print("\n25. LARGE INTEGER GCD")

    a = (10**100 + 1) * 37
    b = (10**100 + 1) * 91

    result = gcd_euclidean(a, b)

    print(f"GCD of two approximately 100-digit-derived values: {result}")
    print(f"Expected common factor: {10**100 + 1} * GCD(37, 91)")
    print(f"Verification: {result == (10**100 + 1) * math_gcd(37, 91)}")


# ============================================================================
# 28. ADVANCED: GCD OVER A RANGE
# ============================================================================

def gcd_range(start: int, end: int) -> int:
    """
    Compute the GCD of every integer in the inclusive range [start, end].

    Example:

        gcd(12, 13, 14, 15) = 1

    The result usually becomes 1 quickly, but the function demonstrates
    repeated use of the associative GCD operation.
    """
    if start > end:
        raise ValueError("Start must not exceed end.")

    result = 0

    for value in range(start, end + 1):
        result = gcd_euclidean(result, value)

        if result == 1:
            break

    return result


def demonstrate_gcd_range() -> None:
    print("\n26. GCD OVER A RANGE")

    for start, end in [(1, 10), (12, 15), (20, 24), (100, 105)]:
        print(f"GCD of integers from {start} through {end}: {gcd_range(start, end)}")


# ============================================================================
# 29. ADVANCED: GCD AND BEZOUT'S IDENTITY
# ============================================================================

def demonstrate_bezout_identity() -> None:
    print("\n27. BÉZOUT'S IDENTITY")

    examples = [(56, 15), (99, 78), (120, 45)]

    for a, b in examples:
        g, x, y = extended_gcd(a, b)

        print(
            f"{a}({x}) + {b}({y}) = {a * x + b * y}; "
            f"GCD = {g}"
        )


# ============================================================================
# 30. ADVANCED: CRT-RELATED COPRIMALITY CHECK
# ============================================================================

def are_pairwise_coprime(numbers: Sequence[int]) -> bool:
    """
    Return True only when every pair of numbers has GCD 1.

    Pairwise coprimality is stronger than merely having GCD 1 across the
    entire collection.

    Example:

        [6, 10, 15]

    has GCD 1 across all three numbers, but is NOT pairwise coprime because:

        gcd(6,10) = 2
        gcd(6,15) = 3
        gcd(10,15) = 5
    """
    for index in range(len(numbers)):
        for other_index in range(index + 1, len(numbers)):
            if gcd_euclidean(numbers[index], numbers[other_index]) != 1:
                return False

    return True


def demonstrate_pairwise_coprime() -> None:
    print("\n28. PAIRWISE COPRIMALITY")

    examples = [
        [8, 9, 25],
        [6, 10, 15],
        [5, 7, 11],
    ]

    for numbers in examples:
        print(
            f"{numbers} pairwise coprime: "
            f"{are_pairwise_coprime(numbers)}"
        )


# ============================================================================
# 31. GCD AND THE CHINESE REMAINDER THEOREM CONTEXT
# ============================================================================

def crt_compatibility_condition(
    remainder_a: int,
    modulus_a: int,
    remainder_b: int,
    modulus_b: int,
) -> bool:
    """
    Check the compatibility condition for two congruences:

        x ≡ remainder_a (mod modulus_a)
        x ≡ remainder_b (mod modulus_b)

    A solution exists exactly when:

        remainder_a ≡ remainder_b (mod gcd(modulus_a, modulus_b))

    This function checks the condition without solving the complete CRT.
    """
    if modulus_a <= 0 or modulus_b <= 0:
        raise ValueError("Moduli must be positive.")

    common = gcd_euclidean(modulus_a, modulus_b)

    return (remainder_a - remainder_b) % common == 0


def demonstrate_crt_condition() -> None:
    print("\n29. GCD IN CHINESE REMAINDER THEOREM COMPATIBILITY")

    cases = [
        (2, 6, 5, 9),
        (2, 6, 8, 9),
        (1, 4, 3, 6),
        (1, 4, 2, 6),
    ]

    for ra, ma, rb, mb in cases:
        compatible = crt_compatibility_condition(ra, ma, rb, mb)

        print(
            f"x ≡ {ra} (mod {ma}), x ≡ {rb} (mod {mb}) "
            f"-> compatible: {compatible}"
        )


# ============================================================================
# 32. GCD ALGORITHM SELECTION
# ============================================================================

def algorithm_selection_guide() -> None:
    """
    Print a conceptual comparison of common approaches.
    """
    print("\n30. ALGORITHM SELECTION")

    comparison = [
        (
            "Brute force",
            "O(min(a,b))",
            "Very simple",
            "Teaching only / small values",
        ),
        (
            "Euclidean iterative",
            "O(log(min(a,b)))",
            "Fast and simple",
            "General-purpose implementation",
        ),
        (
            "Euclidean recursive",
            "O(log(min(a,b)))",
            "Elegant recurrence",
            "Teaching / mathematical code",
        ),
        (
            "Binary GCD",
            "Near-logarithmic",
            "Uses shifts/subtraction",
            "Specialized low-level contexts",
        ),
        (
            "math.gcd",
            "Highly optimized",
            "Standard library",
            "Production Python code",
        ),
    ]

    print(
        f"{'Algorithm':20} {'Time':20} {'Strength':30} {'Typical use'}"
    )
    print("-" * 100)

    for row in comparison:
        print(
            f"{row[0]:20} {row[1]:20} "
            f"{row[2]:30} {row[3]}"
        )


# ============================================================================
# 33. COMMON MISTAKES
# ============================================================================

def demonstrate_common_mistakes() -> None:
    """
    Show incorrect patterns conceptually and then use correct alternatives.

    The incorrect implementations are not executed because some are
    intentionally unsafe or logically incomplete.
    """
    print("\n31. COMMON MISTAKES")

    print("Mistake 1: Forgetting negative inputs.")
    print("Correct:", gcd_euclidean(-48, 18))

    print("\nMistake 2: Treating GCD(0, 0) as an ordinary numeric case.")
    print("Correct behavior: raise an exception because it is undefined.")

    print("\nMistake 3: Using multiplication before division in LCM.")
    print(
        "Safer expression:",
        "abs((a // gcd(a,b)) * b)"
    )

    print("\nMistake 4: Confusing GCD and LCM.")
    print("GCD finds the greatest shared divisor.")
    print("LCM finds the least positive shared multiple.")

    print("\nMistake 5: Assuming a list with overall GCD 1 is pairwise coprime.")
    print("[6, 10, 15] has overall GCD 1 but is not pairwise coprime.")


# ============================================================================
# 34. PERFORMANCE CONSIDERATIONS
# ============================================================================

def performance_notes() -> None:
    """
    Explain why algorithmic complexity matters without requiring a benchmark.
    """
    print("\n32. PERFORMANCE CONSIDERATIONS")

    print(
        "Brute-force GCD may examine every integer up to the smaller operand."
    )
    print(
        "The Euclidean algorithm reduces the problem dramatically through "
        "remainder operations."
    )
    print(
        "For Python production code, math.gcd is normally preferred because "
        "it is implemented as optimized standard-library functionality."
    )
    print(
        "For extremely large integers, the cost of integer arithmetic itself "
        "also matters, not just the number of Euclidean iterations."
    )


# ============================================================================
# 35. SECURITY AND ROBUSTNESS CONSIDERATIONS
# ============================================================================

def security_considerations() -> None:
    """
    GCD itself is not generally a security-sensitive operation, but GCD
    appears in cryptographic algorithms and number-theoretic protocols.

    Timing behavior can become relevant in cryptographic contexts. A generic
    educational implementation should not automatically be treated as a
    constant-time cryptographic primitive.
    """
    print("\n33. SECURITY CONSIDERATIONS")

    print(
        "GCD is fundamental to cryptography, including RSA-related "
        "number-theoretic operations."
    )
    print(
        "The existence of a fast GCD algorithm does not make an entire "
        "cryptographic implementation secure."
    )
    print(
        "When implementing cryptographic protocols, use established "
        "cryptographic libraries and carefully designed primitives."
    )
    print(
        "Do not assume that ordinary Python arithmetic or algorithmic "
        "implementations provide constant-time behavior."
    )


# ============================================================================
# 36. COMPLETE STUDY EXAMPLE
# ============================================================================

def complete_study_example() -> None:
    """
    Combine several GCD concepts in one workflow.

    Scenario:
        A system has integer quantities that should be represented in their
        smallest common ratio. The same GCD is also used to derive an LCM,
        test coprimality, and normalize the values.
    """
    print("\n34. COMPLETE STUDY EXAMPLE")

    quantities = [84, 126, 210]

    common = gcd_many(quantities)
    normalized = normalize_integer_vector(quantities)

    print(f"Quantities: {quantities}")
    print(f"Common divisor: {common}")
    print(f"Normalized ratio: {normalized}")

    pair_a, pair_b = quantities[0], quantities[1]
    pair_gcd = gcd_euclidean(pair_a, pair_b)
    pair_lcm = lcm(pair_a, pair_b)

    print(f"GCD({pair_a}, {pair_b}) = {pair_gcd}")
    print(f"LCM({pair_a}, {pair_b}) = {pair_lcm}")

    print(
        f"Pairwise coprime: "
        f"{are_pairwise_coprime(quantities)}"
    )


# ============================================================================
# 37. MAIN EXECUTION
# ============================================================================

def main() -> None:
    """
    Execute the complete GCD study program.
    """
    print("=" * 80)
    print("GREATEST COMMON DIVISOR (GCD) - COMPLETE PYTHON STUDY GUIDE")
    print("=" * 80)

    demonstrate_basic_divisibility()
    demonstrate_divisors()
    demonstrate_definition()
    demonstrate_euclidean_algorithm()
    demonstrate_edge_cases()
    demonstrate_gcd_many()
    demonstrate_python_math_gcd()
    demonstrate_gcd_lcm_relationship()
    demonstrate_coprime()
    demonstrate_prime_factorization()
    demonstrate_fraction_reduction()
    demonstrate_ratio_reduction()
    demonstrate_coefficient_gcd()
    demonstrate_extended_gcd()
    demonstrate_modular_inverse()
    demonstrate_diophantine_equation()
    demonstrate_linear_congruence()
    demonstrate_fibonacci_connection()

    properties = verify_gcd_properties(84, 126)

    print("\nPROPERTY VERIFICATION")
    for property_name, passed in properties.items():
        print(f"{property_name:25}: {passed}")

    compare_algorithms()
    run_consistency_tests()
    test_edge_cases()

    demonstrate_tile_problem()
    demonstrate_cycle_alignment()
    demonstrate_vector_normalization()
    demonstrate_large_integers()
    demonstrate_gcd_range()
    demonstrate_bezout_identity()
    demonstrate_pairwise_coprime()
    demonstrate_crt_condition()
    algorithm_selection_guide()
    demonstrate_common_mistakes()
    performance_notes()
    security_considerations()
    complete_study_example()

    print("\n" + "=" * 80)
    print("GCD STUDY PROGRAM COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()
