/*
===============================================================================
CLEAN ARCHITECTURE: DEPENDENCY INVERSION AND BOUNDARIES
===============================================================================

Enterprise order-processing architecture governance database.

PostgreSQL 14+

Implements:
- Architecture components
- Architectural layers
- Dependency relationships
- Dependency direction policies
- Circular dependency detection
- Architecture violations
- Repositories and branches of architectural versions
- Application use cases
- Input and output ports
- Adapter implementations
- Dependency injection registrations
- Orders and order items
- Payment processing
- Application events
- Architecture validation reports
- Transactional workflow processing

The database distinguishes:
1. Domain rules
2. Application orchestration
3. Adapter contracts
4. Infrastructure implementations
5. Architecture governance

Execute the complete script in a PostgreSQL database.
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS clean_architecture;

SET search_path TO clean_architecture, public;


-- ============================================================================
-- 1. ENUM TYPES
-- ============================================================================

CREATE TYPE architecture_layer AS ENUM (
    'DOMAIN',
    'APPLICATION',
    'ADAPTER',
    'INFRASTRUCTURE'
);

CREATE TYPE component_kind AS ENUM (
    'ENTITY',
    'VALUE_OBJECT',
    'USE_CASE',
    'INPUT_PORT',
    'OUTPUT_PORT',
    'INTERFACE_ADAPTER',
    'REPOSITORY',
    'DATABASE',
    'EXTERNAL_SERVICE',
    'COMPOSITION_ROOT',
    'EVENT_PUBLISHER'
);

CREATE TYPE dependency_kind AS ENUM (
    'SOURCE_CODE',
    'INTERFACE_IMPLEMENTATION',
    'RUNTIME_INJECTION',
    'EVENT_CONTRACT'
);

CREATE TYPE validation_status AS ENUM (
    'VALID',
    'INVALID',
    'PENDING'
);

CREATE TYPE order_status AS ENUM (
    'PENDING',
    'PAID',
    'CANCELLED'
);

CREATE TYPE payment_status AS ENUM (
    'INITIATED',
    'SUCCEEDED',
    'FAILED'
);


-- ============================================================================
-- 2. ARCHITECTURE GOVERNANCE
-- ============================================================================

CREATE TABLE architecture_projects (
    project_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    project_name VARCHAR(150) NOT NULL UNIQUE,

    description TEXT NOT NULL,

    version VARCHAR(30) NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_project_version
        CHECK (version ~ '^[0-9]+(\.[0-9]+){1,2}$')
);


CREATE TABLE architecture_components (
    component_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    project_id BIGINT NOT NULL
        REFERENCES architecture_projects(project_id),

    component_name VARCHAR(150) NOT NULL,

    layer architecture_layer NOT NULL,

    component_type component_kind NOT NULL,

    package_name VARCHAR(250) NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    description TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (project_id, component_name),

    UNIQUE (component_id, project_id)
);


CREATE TABLE architecture_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    source_layer architecture_layer NOT NULL,

    target_layer architecture_layer NOT NULL,

    is_allowed BOOLEAN NOT NULL,

    policy_reason TEXT NOT NULL,

    UNIQUE (source_layer, target_layer)
);


-- Domain cannot depend on outer layers.
-- Application depends on domain.
-- Adapters implement application-facing contracts.
-- Infrastructure supplies concrete implementations.

INSERT INTO architecture_policies (
    source_layer,
    target_layer,
    is_allowed,
    policy_reason
)
VALUES
(
    'DOMAIN',
    'DOMAIN',
    FALSE,
    'Domain components must not introduce implementation dependencies.'
),
(
    'DOMAIN',
    'APPLICATION',
    FALSE,
    'Domain must not depend on application orchestration.'
),
(
    'DOMAIN',
    'ADAPTER',
    FALSE,
    'Domain must not depend on interface adapters.'
),
(
    'DOMAIN',
    'INFRASTRUCTURE',
    FALSE,
    'Domain must not depend on infrastructure.'
),
(
    'APPLICATION',
    'DOMAIN',
    TRUE,
    'Application use cases depend on domain rules.'
),
(
    'APPLICATION',
    'APPLICATION',
    TRUE,
    'Application components may collaborate through explicit contracts.'
),
(
    'APPLICATION',
    'ADAPTER',
    FALSE,
    'Application must not depend on concrete adapters.'
),
(
    'APPLICATION',
    'INFRASTRUCTURE',
    FALSE,
    'Application must not depend on infrastructure implementations.'
),
(
    'ADAPTER',
    'DOMAIN',
    TRUE,
    'Adapters may translate domain representations.'
),
(
    'ADAPTER',
    'APPLICATION',
    TRUE,
    'Adapters implement application-facing ports.'
),
(
    'ADAPTER',
    'ADAPTER',
    TRUE,
    'Adapters may coordinate through explicit adapter contracts.'
),
(
    'ADAPTER',
    'INFRASTRUCTURE',
    FALSE,
    'Adapters must not reverse application dependency direction.'
),
(
    'INFRASTRUCTURE',
    'DOMAIN',
    TRUE,
    'Infrastructure may implement domain-facing persistence mappings.'
),
(
    'INFRASTRUCTURE',
    'APPLICATION',
    TRUE,
    'Infrastructure implements application output ports.'
),
(
    'INFRASTRUCTURE',
    'ADAPTER',
    TRUE,
    'Infrastructure may support interface adapters.'
),
(
    'INFRASTRUCTURE',
    'INFRASTRUCTURE',
    TRUE,
    'Infrastructure implementations may collaborate.'
)
ON CONFLICT (source_layer, target_layer)
DO UPDATE SET
    is_allowed = EXCLUDED.is_allowed,
    policy_reason = EXCLUDED.policy_reason;


CREATE TABLE component_dependencies (
    dependency_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    project_id BIGINT NOT NULL,

    source_component_id BIGINT NOT NULL,

    target_component_id BIGINT NOT NULL,

    dependency_type dependency_kind NOT NULL,

    description TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (source_component_id, project_id)
        REFERENCES architecture_components(component_id, project_id),

    FOREIGN KEY (target_component_id, project_id)
        REFERENCES architecture_components(component_id, project_id),

    CHECK (source_component_id <> target_component_id),

    UNIQUE (
        source_component_id,
        target_component_id,
        dependency_type
    )
);


CREATE INDEX idx_dependencies_source
ON component_dependencies(source_component_id);

CREATE INDEX idx_dependencies_target
ON component_dependencies(target_component_id);


CREATE TABLE architecture_validation_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    project_id BIGINT NOT NULL
        REFERENCES architecture_projects(project_id),

    status validation_status NOT NULL DEFAULT 'PENDING',

    checked_dependencies INTEGER NOT NULL DEFAULT 0,

    violation_count INTEGER NOT NULL DEFAULT 0,

    executed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (checked_dependencies >= 0),

    CHECK (violation_count >= 0)
);


CREATE TABLE architecture_violations (
    violation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    run_id BIGINT NOT NULL
        REFERENCES architecture_validation_runs(run_id)
        ON DELETE CASCADE,

    dependency_id BIGINT NOT NULL
        REFERENCES component_dependencies(dependency_id),

    violation_message TEXT NOT NULL,

    detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (run_id, dependency_id)
);


-- ============================================================================
-- 3. APPLICATION PORTS AND ADAPTER REGISTRATION
-- ============================================================================

CREATE TABLE application_ports (
    port_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    component_id BIGINT NOT NULL
        REFERENCES architecture_components(component_id),

    port_name VARCHAR(150) NOT NULL,

    port_direction VARCHAR(10) NOT NULL,

    contract_description TEXT NOT NULL,

    UNIQUE (component_id, port_name),

    CHECK (port_direction IN ('INPUT', 'OUTPUT'))
);


CREATE TABLE adapter_implementations (
    implementation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    port_id BIGINT NOT NULL
        REFERENCES application_ports(port_id),

    adapter_component_id BIGINT NOT NULL
        REFERENCES architecture_components(component_id),

    implementation_name VARCHAR(150) NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (port_id, adapter_component_id)
);


CREATE TABLE dependency_injections (
    injection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    project_id BIGINT NOT NULL
        REFERENCES architecture_projects(project_id),

    consumer_component_id BIGINT NOT NULL
        REFERENCES architecture_components(component_id),

    port_id BIGINT NOT NULL
        REFERENCES application_ports(port_id),

    implementation_id BIGINT NOT NULL
        REFERENCES adapter_implementations(implementation_id),

    registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (consumer_component_id, port_id)
);


-- ============================================================================
-- 4. ORDER DOMAIN
-- ============================================================================

CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    customer_code VARCHAR(50) NOT NULL UNIQUE,

    customer_name VARCHAR(150) NOT NULL,

    email VARCHAR(255) NOT NULL UNIQUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    sku VARCHAR(60) NOT NULL UNIQUE,

    product_name VARCHAR(150) NOT NULL,

    unit_price NUMERIC(14,2) NOT NULL,

    currency CHAR(3) NOT NULL DEFAULT 'INR',

    active BOOLEAN NOT NULL DEFAULT TRUE,

    CHECK (unit_price >= 0),

    CHECK (currency ~ '^[A-Z]{3}$')
);


CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    order_reference VARCHAR(60) NOT NULL UNIQUE,

    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id),

    status order_status NOT NULL DEFAULT 'PENDING',

    total_amount NUMERIC(16,2) NOT NULL DEFAULT 0,

    currency CHAR(3) NOT NULL DEFAULT 'INR',

    version INTEGER NOT NULL DEFAULT 1,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (total_amount >= 0),

    CHECK (version >= 1),

    CHECK (currency ~ '^[A-Z]{3}$')
);


CREATE TABLE order_items (
    order_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    order_id BIGINT NOT NULL
        REFERENCES orders(order_id)
        ON DELETE CASCADE,

    product_id BIGINT NOT NULL
        REFERENCES products(product_id),

    quantity INTEGER NOT NULL,

    unit_price NUMERIC(14,2) NOT NULL,

    subtotal NUMERIC(16,2)
        GENERATED ALWAYS AS (
            quantity * unit_price
        ) STORED,

    CHECK (quantity BETWEEN 1 AND 1000),

    CHECK (unit_price >= 0)
);


CREATE INDEX idx_orders_customer
ON orders(customer_id);

CREATE INDEX idx_orders_status_created
ON orders(status, created_at DESC);

CREATE INDEX idx_order_items_order
ON order_items(order_id);


-- ============================================================================
-- 5. PAYMENT AND APPLICATION EVENTS
-- ============================================================================

CREATE TABLE payments (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    order_id BIGINT NOT NULL
        REFERENCES orders(order_id),

    provider_reference VARCHAR(120) UNIQUE,

    idempotency_key VARCHAR(120) NOT NULL UNIQUE,

    amount NUMERIC(16,2) NOT NULL,

    currency CHAR(3) NOT NULL,

    status payment_status NOT NULL DEFAULT 'INITIATED',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (amount > 0)
);


CREATE INDEX idx_payments_order_status
ON payments(order_id, status);


CREATE TABLE application_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    aggregate_type VARCHAR(100) NOT NULL,

    aggregate_id BIGINT NOT NULL,

    event_type VARCHAR(100) NOT NULL,

    payload JSONB NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    published_at TIMESTAMPTZ
);


CREATE INDEX idx_events_unpublished
ON application_events(created_at)
WHERE published_at IS NULL;


-- ============================================================================
-- 6. ARCHITECTURE VALIDATION TRIGGER
-- ============================================================================

CREATE OR REPLACE FUNCTION enforce_dependency_policy()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    source_layer architecture_layer;
    target_layer architecture_layer;
    permitted BOOLEAN;
BEGIN

    SELECT layer
    INTO source_layer
    FROM architecture_components
    WHERE component_id = NEW.source_component_id
      AND project_id = NEW.project_id
      AND is_active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Source component is missing or inactive.';
    END IF;

    SELECT layer
    INTO target_layer
    FROM architecture_components
    WHERE component_id = NEW.target_component_id
      AND project_id = NEW.project_id
      AND is_active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Target component is missing or inactive.';
    END IF;

    SELECT is_allowed
    INTO permitted
    FROM architecture_policies
    WHERE source_layer = source_layer
      AND target_layer = target_layer;

    /*
     * Explicitly qualify policy columns to avoid ambiguity
     * between local PL/pgSQL variables and table fields.
     */

    SELECT p.is_allowed
    INTO permitted
    FROM architecture_policies AS p
    WHERE p.source_layer = enforce_dependency_policy.source_layer
      AND p.target_layer = enforce_dependency_policy.target_layer;

    IF permitted IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION
            'Dependency direction violation: % -> %',
            source_layer,
            target_layer;
    END IF;

    RETURN NEW;
END;
$$;


CREATE TRIGGER trg_enforce_dependency_policy
BEFORE INSERT OR UPDATE ON component_dependencies
FOR EACH ROW
EXECUTE FUNCTION enforce_dependency_policy();


-- ============================================================================
-- 7. ORDER TOTAL VALIDATION
-- ============================================================================

CREATE OR REPLACE FUNCTION refresh_order_total()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    affected_order_id BIGINT;
    calculated_total NUMERIC(16,2);
BEGIN

    affected_order_id := COALESCE(NEW.order_id, OLD.order_id);

    SELECT COALESCE(SUM(subtotal), 0)
    INTO calculated_total
    FROM order_items
    WHERE order_id = affected_order_id;

    UPDATE orders
    SET total_amount = calculated_total,
        version = version + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE order_id = affected_order_id
      AND status = 'PENDING';

    RETURN COALESCE(NEW, OLD);
END;
$$;


CREATE TRIGGER trg_refresh_order_total
AFTER INSERT OR UPDATE OR DELETE ON order_items
FOR EACH ROW
EXECUTE FUNCTION refresh_order_total();


-- ============================================================================
-- 8. DOMAIN STATE TRANSITION VALIDATION
-- ============================================================================

CREATE OR REPLACE FUNCTION enforce_order_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN

    IF OLD.status = 'PAID'
       AND NEW.status <> 'PAID' THEN

        RAISE EXCEPTION
            'Paid orders cannot be transitioned to another state.';
    END IF;

    IF OLD.status = 'CANCELLED'
       AND NEW.status <> 'CANCELLED' THEN

        RAISE EXCEPTION
            'Cancelled orders cannot be reopened directly.';
    END IF;

    IF OLD.status = 'PENDING'
       AND NEW.status NOT IN ('PENDING', 'PAID', 'CANCELLED') THEN

        RAISE EXCEPTION
            'Invalid order state transition.';
    END IF;

    RETURN NEW;
END;
$$;


CREATE TRIGGER trg_enforce_order_transition
BEFORE UPDATE OF status ON orders
FOR EACH ROW
EXECUTE FUNCTION enforce_order_transition();


-- ============================================================================
-- 9. ARCHITECTURE VALIDATION PROCEDURE
-- ============================================================================

CREATE OR REPLACE PROCEDURE validate_architecture(
    IN p_project_id BIGINT,
    INOUT p_run_id BIGINT DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    dependency_record RECORD;
    permitted BOOLEAN;
    violation_total INTEGER := 0;
    dependency_total INTEGER := 0;
BEGIN

    INSERT INTO architecture_validation_runs (
        project_id,
        status
    )
    VALUES (
        p_project_id,
        'PENDING'
    )
    RETURNING run_id INTO p_run_id;

    FOR dependency_record IN
        SELECT
            d.dependency_id,
            d.source_component_id,
            d.target_component_id,
            source.layer AS source_layer,
            target.layer AS target_layer,
            source.component_name AS source_name,
            target.component_name AS target_name
        FROM component_dependencies d
        JOIN architecture_components source
            ON source.component_id = d.source_component_id
        JOIN architecture_components target
            ON target.component_id = d.target_component_id
        WHERE d.project_id = p_project_id
          AND source.is_active = TRUE
          AND target.is_active = TRUE
    LOOP

        dependency_total := dependency_total + 1;

        SELECT p.is_allowed
        INTO permitted
        FROM architecture_policies p
        WHERE p.source_layer = dependency_record.source_layer
          AND p.target_layer = dependency_record.target_layer;

        IF permitted IS DISTINCT FROM TRUE THEN

            violation_total := violation_total + 1;

            INSERT INTO architecture_violations (
                run_id,
                dependency_id,
                violation_message
            )
            VALUES (
                p_run_id,
                dependency_record.dependency_id,
                format(
                    '%s (%s) cannot depend on %s (%s)',
                    dependency_record.source_name,
                    dependency_record.source_layer,
                    dependency_record.target_name,
                    dependency_record.target_layer
                )
            );

        END IF;
    END LOOP;

    UPDATE architecture_validation_runs
    SET checked_dependencies = dependency_total,
        violation_count = violation_total,
        status = CASE
            WHEN violation_total = 0 THEN 'VALID'
            ELSE 'INVALID'
        END
    WHERE run_id = p_run_id;

END;
$$;


-- ============================================================================
-- 10. CIRCULAR DEPENDENCY ANALYSIS
-- ============================================================================

CREATE OR REPLACE FUNCTION find_dependency_cycles(
    p_project_id BIGINT
)
RETURNS TABLE (
    component_path TEXT
)
LANGUAGE SQL
STABLE
AS $$
    WITH RECURSIVE traversal AS (

        SELECT
            d.source_component_id AS start_id,
            d.target_component_id AS current_id,
            ARRAY[
                d.source_component_id,
                d.target_component_id
            ]::BIGINT[] AS visited,
            FALSE AS cycle_found
        FROM component_dependencies d
        WHERE d.project_id = p_project_id

        UNION ALL

        SELECT
            t.start_id,
            d.target_component_id,
            t.visited || d.target_component_id,
            d.target_component_id = t.start_id
        FROM traversal t
        JOIN component_dependencies d
          ON d.source_component_id = t.current_id
         AND d.project_id = p_project_id
        WHERE NOT t.cycle_found
          AND (
              d.target_component_id = t.start_id
              OR NOT d.target_component_id = ANY(t.visited)
          )
    )
    SELECT DISTINCT
        array_to_string(
            ARRAY(
                SELECT c.component_name
                FROM unnest(t.visited) WITH ORDINALITY
                    AS visited_component(component_id, position)
                JOIN architecture_components c
                    ON c.component_id =
                       visited_component.component_id
                ORDER BY visited_component.position
            ),
            ' -> '
        ) AS component_path
    FROM traversal t
    WHERE t.cycle_found;
$$;


-- ============================================================================
-- 11. ORDER PROCESSING PROCEDURE
-- ============================================================================

CREATE OR REPLACE PROCEDURE process_order_payment(
    IN p_order_id BIGINT,
    IN p_idempotency_key VARCHAR(120),
    IN p_payment_success BOOLEAN
)
LANGUAGE plpgsql
AS $$
DECLARE
    current_order orders%ROWTYPE;
    payment_id_value BIGINT;
BEGIN

    SELECT *
    INTO current_order
    FROM orders
    WHERE order_id = p_order_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order does not exist.';
    END IF;

    IF current_order.status <> 'PENDING' THEN
        RAISE EXCEPTION
            'Only pending orders can be processed.';
    END IF;

    IF current_order.total_amount <= 0 THEN
        RAISE EXCEPTION
            'Order total must be positive.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM payments
        WHERE idempotency_key = p_idempotency_key
    ) THEN
        RAISE EXCEPTION
            'Idempotency key has already been used.';
    END IF;

    INSERT INTO payments (
        order_id,
        idempotency_key,
        amount,
        currency,
        status
    )
    VALUES (
        p_order_id,
        p_idempotency_key,
        current_order.total_amount,
        current_order.currency,
        CASE
            WHEN p_payment_success THEN 'SUCCEEDED'
            ELSE 'FAILED'
        END
    )
    RETURNING payment_id INTO payment_id_value;

    IF p_payment_success THEN

        UPDATE orders
        SET status = 'PAID',
            version = version + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE order_id = p_order_id;

        INSERT INTO application_events (
            aggregate_type,
            aggregate_id,
            event_type,
            payload
        )
        VALUES (
            'ORDER',
            p_order_id,
            'ORDER_PAID',
            jsonb_build_object(
                'order_id', p_order_id,
                'payment_id', payment_id_value,
                'amount', current_order.total_amount,
                'currency', current_order.currency
            )
        );

    ELSE

        UPDATE orders
        SET status = 'CANCELLED',
            version = version + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE order_id = p_order_id;

        INSERT INTO application_events (
            aggregate_type,
            aggregate_id,
            event_type,
            payload
        )
        VALUES (
            'ORDER',
            p_order_id,
            'PAYMENT_FAILED',
            jsonb_build_object(
                'order_id', p_order_id,
                'payment_id', payment_id_value
            )
        );

    END IF;

END;
$$;


-- ============================================================================
-- 12. REPORTING VIEWS
-- ============================================================================

CREATE OR REPLACE VIEW architecture_dependency_report AS
SELECT
    p.project_name,
    source.component_name AS source_component,
    source.layer AS source_layer,
    target.component_name AS target_component,
    target.layer AS target_layer,
    d.dependency_type,
    policy.is_allowed,
    CASE
        WHEN policy.is_allowed THEN 'ALLOWED'
        ELSE 'VIOLATION'
    END AS dependency_result
FROM component_dependencies d
JOIN architecture_projects p
    ON p.project_id = d.project_id
JOIN architecture_components source
    ON source.component_id = d.source_component_id
JOIN architecture_components target
    ON target.component_id = d.target_component_id
LEFT JOIN architecture_policies policy
    ON policy.source_layer = source.layer
   AND policy.target_layer = target.layer;


CREATE OR REPLACE VIEW order_summary AS
SELECT
    o.order_id,
    o.order_reference,
    c.customer_name,
    o.status,
    COUNT(oi.order_item_id) AS item_count,
    o.total_amount,
    o.currency,
    o.version,
    o.created_at
FROM orders o
JOIN customers c
    ON c.customer_id = o.customer_id
LEFT JOIN order_items oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_reference,
    c.customer_name,
    o.status,
    o.total_amount,
    o.currency,
    o.version,
    o.created_at;


-- ============================================================================
-- 13. SAMPLE ARCHITECTURE
-- ============================================================================

INSERT INTO architecture_projects (
    project_name,
    description,
    version
)
VALUES (
    'Enterprise Order Management',
    'Order processing with clean architecture boundaries.',
    '1.0.0'
)
ON CONFLICT (project_name) DO NOTHING;


INSERT INTO architecture_components (
    project_id,
    component_name,
    layer,
    component_type,
    package_name,
    description
)
SELECT
    p.project_id,
    components.component_name,
    components.layer,
    components.component_type,
    components.package_name,
    components.description
FROM architecture_projects p
CROSS JOIN (
    VALUES
    (
        'Order',
        'DOMAIN'::architecture_layer,
        'ENTITY'::component_kind,
        'domain.order',
        'Order aggregate and state transitions.'
    ),
    (
        'Money',
        'DOMAIN'::architecture_layer,
        'VALUE_OBJECT'::component_kind,
        'domain.money',
        'Immutable monetary value.'
    ),
    (
        'PlaceOrderService',
        'APPLICATION'::architecture_layer,
        'USE_CASE'::component_kind,
        'application.order',
        'Coordinates order placement.'
    ),
    (
        'OrderRepository',
        'APPLICATION'::architecture_layer,
        'OUTPUT_PORT'::component_kind,
        'application.ports',
        'Order persistence abstraction.'
    ),
    (
        'PaymentGateway',
        'APPLICATION'::architecture_layer,
        'OUTPUT_PORT'::component_kind,
        'application.ports',
        'Payment processing abstraction.'
    ),
    (
        'OrderInputPort',
        'APPLICATION'::component_kind::architecture_layer,
        'INPUT_PORT'::component_kind,
        'application.ports',
        'Order creation input boundary.'
    ),
    (
        'OrderController',
        'ADAPTER'::architecture_layer,
        'INTERFACE_ADAPTER'::component_kind,
        'adapter.http',
        'Translates HTTP requests into application commands.'
    ),
    (
        'PostgresOrderRepository',
        'INFRASTRUCTURE'::architecture_layer,
        'REPOSITORY'::component_kind,
        'infrastructure.persistence',
        'Concrete relational persistence adapter.'
    ),
    (
        'ExternalPaymentProvider',
        'INFRASTRUCTURE'::architecture_layer,
        'EXTERNAL_SERVICE'::component_kind,
        'infrastructure.payment',
        'External payment implementation.'
    ),
    (
        'ApplicationBootstrap',
        'INFRASTRUCTURE'::architecture_layer,
        'COMPOSITION_ROOT'::component_kind,
        'infrastructure.bootstrap',
        'Composition root for dependency injection.'
    )
) AS components(
    component_name,
    layer,
    component_type,
    package_name,
    description
)
WHERE p.project_name = 'Enterprise Order Management'
ON CONFLICT (project_id, component_name) DO NOTHING;


-- ============================================================================
-- 14. SAMPLE DEPENDENCY RELATIONSHIPS
-- ============================================================================

INSERT INTO component_dependencies (
    project_id,
    source_component_id,
    target_component_id,
    dependency_type,
    description
)
SELECT
    p.project_id,
    source.component_id,
    target.component_id,
    'SOURCE_CODE',
    relationship.description
FROM architecture_projects p
JOIN (
    VALUES
    (
        'PlaceOrderService',
        'Order',
        'Application use case uses the domain aggregate.'
    ),
    (
        'PlaceOrderService',
        'OrderRepository',
        'Application use case uses a persistence port.'
    ),
    (
        'PlaceOrderService',
        'PaymentGateway',
        'Application use case uses a payment port.'
    ),
    (
        'OrderController',
        'OrderInputPort',
        'HTTP adapter invokes the input boundary.'
    ),
    (
        'PostgresOrderRepository',
        'OrderRepository',
        'Infrastructure implements the output port.'
    ),
    (
        'ExternalPaymentProvider',
        'PaymentGateway',
        'External adapter implements payment abstraction.'
    ),
    (
        'ApplicationBootstrap',
        'PostgresOrderRepository',
        'Composition root constructs the database adapter.'
    )
) AS relationship(source_name, target_name, description)
ON TRUE
JOIN architecture_components source
    ON source.project_id = p.project_id
   AND source.component_name = relationship.source_name
JOIN architecture_components target
    ON target.project_id = p.project_id
   AND target.component_name = relationship.target_name
WHERE p.project_name = 'Enterprise Order Management'
ON CONFLICT (
    source_component_id,
    target_component_id,
    dependency_type
) DO NOTHING;


-- ============================================================================
-- 15. SAMPLE PORT IMPLEMENTATIONS
-- ============================================================================

INSERT INTO application_ports (
    component_id,
    port_name,
    port_direction,
    contract_description
)
SELECT
    component_id,
    component_name,
    'OUTPUT',
    description
FROM architecture_components
WHERE component_name IN (
    'OrderRepository',
    'PaymentGateway'
)
ON CONFLICT (component_id, port_name) DO NOTHING;


INSERT INTO application_ports (
    component_id,
    port_name,
    port_direction,
    contract_description
)
SELECT
    component_id,
    'PlaceOrder',
    'INPUT',
    'Accepts a validated order placement command.'
FROM architecture_components
WHERE component_name = 'OrderInputPort'
ON CONFLICT (component_id, port_name) DO NOTHING;


INSERT INTO adapter_implementations (
    port_id,
    adapter_component_id,
    implementation_name
)
SELECT
    port.port_id,
    adapter.component_id,
    implementation.implementation_name
FROM (
    VALUES
    (
        'OrderRepository',
        'PostgresOrderRepository',
        'PostgreSQL Order Persistence'
    ),
    (
        'PaymentGateway',
        'ExternalPaymentProvider',
        'External Payment Gateway'
    )
) AS implementation(
    port_name,
    adapter_name,
    implementation_name
)
JOIN application_ports port
    ON port.port_name = implementation.port_name
JOIN architecture_components adapter
    ON adapter.component_name = implementation.adapter_name
ON CONFLICT (port_id, adapter_component_id) DO NOTHING;


-- ============================================================================
-- 16. SAMPLE DEPENDENCY INJECTION
-- ============================================================================

INSERT INTO dependency_injections (
    project_id,
    consumer_component_id,
    port_id,
    implementation_id
)
SELECT
    p.project_id,
    consumer.component_id,
    port.port_id,
    implementation.implementation_id
FROM architecture_projects p
JOIN architecture_components consumer
    ON consumer.project_id = p.project_id
   AND consumer.component_name = 'PlaceOrderService'
JOIN application_ports port
    ON port.port_name IN (
        'OrderRepository',
        'PaymentGateway'
    )
JOIN adapter_implementations implementation
    ON implementation.port_id = port.port_id
WHERE p.project_name = 'Enterprise Order Management'
ON CONFLICT (consumer_component_id, port_id) DO NOTHING;


-- ============================================================================
-- 17. SAMPLE BUSINESS DATA
-- ============================================================================

INSERT INTO customers (
    customer_code,
    customer_name,
    email
)
VALUES
(
    'CUST-100',
    'Enterprise Customer One',
    'customer100@example.com'
),
(
    'CUST-200',
    'Enterprise Customer Two',
    'customer200@example.com'
)
ON CONFLICT DO NOTHING;


INSERT INTO products (
    sku,
    product_name,
    unit_price,
    currency
)
VALUES
(
    'LAPTOP-001',
    'Business Laptop',
    65000.00,
    'INR'
),
(
    'MOUSE-001',
    'Wireless Mouse',
    750.00,
    'INR'
),
(
    'BOOK-001',
    'Technical Book',
    500.00,
    'INR'
)
ON CONFLICT (sku) DO NOTHING;


INSERT INTO orders (
    order_reference,
    customer_id,
    currency
)
SELECT
    'ORD-1001',
    customer_id,
    'INR'
FROM customers
WHERE customer_code = 'CUST-100'
ON CONFLICT (order_reference) DO NOTHING;


INSERT INTO orders (
    order_reference,
    customer_id,
    currency
)
SELECT
    'ORD-2001',
    customer_id,
    'INR'
FROM customers
WHERE customer_code = 'CUST-200'
ON CONFLICT (order_reference) DO NOTHING;


INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    unit_price
)
SELECT
    o.order_id,
    p.product_id,
    item.quantity,
    p.unit_price
FROM orders o
JOIN (
    VALUES
    ('LAPTOP-001', 1),
    ('MOUSE-001', 2)
) AS item(sku, quantity)
    ON TRUE
JOIN products p
    ON p.sku = item.sku
WHERE o.order_reference = 'ORD-1001'
AND NOT EXISTS (
    SELECT 1
    FROM order_items existing
    WHERE existing.order_id = o.order_id
      AND existing.product_id = p.product_id
);


INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    unit_price
)
SELECT
    o.order_id,
    p.product_id,
    1,
    p.unit_price
FROM orders o
JOIN products p
    ON p.sku = 'BOOK-001'
WHERE o.order_reference = 'ORD-2001'
AND NOT EXISTS (
    SELECT 1
    FROM order_items existing
    WHERE existing.order_id = o.order_id
      AND existing.product_id = p.product_id
);


-- ============================================================================
-- 18. APPLICATION WORKFLOW EXECUTION
-- ============================================================================

DO $$
DECLARE
    successful_order_id BIGINT;
    failed_order_id BIGINT;
BEGIN

    SELECT order_id
    INTO successful_order_id
    FROM orders
    WHERE order_reference = 'ORD-1001'
    FOR UPDATE;

    SELECT order_id
    INTO failed_order_id
    FROM orders
    WHERE order_reference = 'ORD-2001'
    FOR UPDATE;

    IF (
        SELECT status
        FROM orders
        WHERE order_id = successful_order_id
    ) = 'PENDING' THEN

        CALL process_order_payment(
            successful_order_id,
            'PAYMENT-ORD-1001',
            TRUE
        );

    END IF;

    IF (
        SELECT status
        FROM orders
        WHERE order_id = failed_order_id
    ) = 'PENDING' THEN

        CALL process_order_payment(
            failed_order_id,
            'PAYMENT-ORD-2001',
            FALSE
        );

    END IF;

END;
$$;


-- ============================================================================
-- 19. ARCHITECTURE VALIDATION
-- ============================================================================

DO $$
DECLARE
    current_project_id BIGINT;
    current_run_id BIGINT;
BEGIN

    SELECT project_id
    INTO current_project_id
    FROM architecture_projects
    WHERE project_name = 'Enterprise Order Management';

    CALL validate_architecture(
        current_project_id,
        current_run_id
    );

    RAISE NOTICE
        'Architecture validation run: %',
        current_run_id;

END;
$$;


-- ============================================================================
-- 20. RETRIEVAL QUERIES
-- ============================================================================

SELECT
    order_reference,
    customer_name,
    status,
    item_count,
    total_amount,
    currency
FROM order_summary
ORDER BY created_at DESC;


SELECT
    component_name,
    layer,
    component_type,
    package_name
FROM architecture_components
WHERE is_active = TRUE
ORDER BY
    CASE layer
        WHEN 'DOMAIN' THEN 1
        WHEN 'APPLICATION' THEN 2
        WHEN 'ADAPTER' THEN 3
        WHEN 'INFRASTRUCTURE' THEN 4
    END,
    component_name;


SELECT
    consumer.component_name AS consumer,
    port.port_name,
    implementation.implementation_name
FROM dependency_injections injection
JOIN architecture_components consumer
    ON consumer.component_id = injection.consumer_component_id
JOIN application_ports port
    ON port.port_id = injection.port_id
JOIN adapter_implementations implementation
    ON implementation.implementation_id =
       injection.implementation_id
ORDER BY consumer.component_name;


-- ============================================================================
-- 21. VALIDATION REPORT
-- ============================================================================

SELECT
    run_id,
    status,
    checked_dependencies,
    violation_count,
    executed_at
FROM architecture_validation_runs
ORDER BY run_id DESC;


SELECT
    violation_id,
    violation_message,
    detected_at
FROM architecture_violations
ORDER BY violation_id;


-- ============================================================================
-- 22. DEPENDENCY DIRECTION REPORT
-- ============================================================================

SELECT
    source_component,
    source_layer,
    target_component,
    target_layer,
    dependency_result
FROM architecture_dependency_report
ORDER BY
    source_layer,
    source_component;


-- ============================================================================
-- 23. CIRCULAR DEPENDENCY QUERY
-- ============================================================================

SELECT *
FROM find_dependency_cycles(
    (
        SELECT project_id
        FROM architecture_projects
        WHERE project_name = 'Enterprise Order Management'
    )
);


-- ============================================================================
-- 24. AGGREGATION AND EVALUATION
-- ============================================================================

SELECT
    layer,
    COUNT(*) AS component_count,
    COUNT(*) FILTER (
        WHERE is_active
    ) AS active_components
FROM architecture_components
GROUP BY layer
ORDER BY layer;


SELECT
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_value
FROM orders
GROUP BY status
ORDER BY status;


SELECT
    p.status,
    COUNT(*) AS payment_count,
    SUM(p.amount) AS processed_amount
FROM payments p
GROUP BY p.status
ORDER BY p.status;


-- ============================================================================
-- 25. APPLICATION EVENT OUTBOX REPORT
-- ============================================================================

SELECT
    event_id,
    aggregate_type,
    aggregate_id,
    event_type,
    payload,
    created_at
FROM application_events
WHERE published_at IS NULL
ORDER BY created_at;


-- ============================================================================
-- 26. TRANSACTIONAL WORKFLOW EXAMPLE
-- ============================================================================

/*
A real application should execute payment state transitions,
event creation, and order updates within a controlled transaction.

The outbox pattern ensures the event record is committed with
the business state change.

External event delivery occurs after transaction commit.
*/

COMMIT;


/*
===============================================================================
SECURITY AND PERFORMANCE NOTES
===============================================================================

1. The database records architecture contracts and their dependencies.
2. The architecture policy trigger prevents newly inserted invalid edges.
3. Historical validation detects violations in the stored dependency graph.
4. Recursive graph traversal detects circular dependency paths.
5. Composite foreign keys keep dependency relationships within projects.
6. CHECK constraints enforce basic monetary and quantity rules.
7. Row locking protects concurrent payment transitions.
8. Idempotency keys prevent duplicate payment records.
9. Partial indexes accelerate unpublished event retrieval.
10. JSONB stores structured event payloads.
11. Application credentials should receive only the necessary table,
    sequence, procedure, and schema privileges.
12. External payment execution must not be performed directly inside
    a long-running database transaction.
13. A production outbox dispatcher should publish events with retries,
    delivery tracking, and idempotent consumers.
14. Architecture metadata should be populated from authoritative
    build or source-analysis results rather than manually trusted.
15. Application-level monetary calculations should use decimal arithmetic.
===============================================================================
*/
