'use strict';

const crypto = require('node:crypto');
const { EventEmitter } = require('node:events');

const EventType = Object.freeze({
    ORDER_CREATED: 'order.created',
    PAYMENT_AUTHORIZED: 'payment.authorized',
    ORDER_CONFIRMED: 'order.confirmed',
    ORDER_CANCELLED: 'order.cancelled'
});

class DomainEvent {
    constructor({ type, aggregateId, payload, producer, eventId = crypto.randomUUID() }) {
        if (!type || !Object.values(EventType).includes(type)) {
            throw new TypeError('Invalid event type');
        }
        if (!aggregateId || !aggregateId.trim()) {
            throw new TypeError('aggregateId cannot be empty');
        }
        if (!producer || !producer.trim()) {
            throw new TypeError('producer cannot be empty');
        }

        this.eventId = eventId;
        this.type = type;
        this.aggregateId = aggregateId;
        this.payload = Object.freeze({ ...payload });
        this.producer = producer;
        this.occurredAt = new Date().toISOString();

        Object.freeze(this);
    }
}

class EventBroker extends EventEmitter {
    constructor() {
        super();
        this.queue = [];
        this.deadLetters = [];
        this.processed = new Set();
    }

    publish(event) {
        if (!(event instanceof DomainEvent)) {
            throw new TypeError('Only DomainEvent instances can be published');
        }

        this.queue.push(event);
    }

    subscribe(eventType, consumerName, handler) {
        if (!consumerName || !consumerName.trim()) {
            throw new TypeError('consumerName cannot be empty');
        }

        this.on(eventType, async (event) => {
            const deliveryKey = `${event.eventId}:${consumerName}`;

            if (this.processed.has(deliveryKey)) {
                return;
            }

            try {
                await handler(event);
                this.processed.add(deliveryKey);
            } catch (error) {
                this.deadLetters.push({
                    event,
                    consumerName,
                    reason: error.message
                });
            }
        });
    }

    async drain() {
        while (this.queue.length > 0) {
            const event = this.queue.shift();

            // Promise-based dispatch allows consumers to perform asynchronous I/O.
            await this.emitAsync(event.type, event);
        }
    }

    async emitAsync(type, event) {
        const listeners = this.listeners(type);

        await Promise.all(
            listeners.map(listener => listener(event))
        );
    }

    pendingCount() {
        return this.queue.length;
    }
}

class OrderService {
    constructor(broker) {
        this.broker = broker;
        this.orders = new Map();
    }

    createOrder(customerId, amount) {
        if (!customerId || !customerId.trim()) {
            throw new Error('customerId is required');
        }

        if (!Number.isFinite(amount) || amount <= 0) {
            throw new Error('amount must be a positive finite number');
        }

        const orderId = crypto.randomUUID();

        const order = Object.freeze({
            orderId,
            customerId,
            amount: Number(amount.toFixed(2)),
            status: 'CREATED'
        });

        this.orders.set(orderId, order);

        this.broker.publish(
            new DomainEvent({
                type: EventType.ORDER_CREATED,
                aggregateId: orderId,
                payload: {
                    customerId,
                    amount: order.amount
                },
                producer: 'order-service'
            })
        );

        return orderId;
    }
}

class PaymentService {
    constructor(broker) {
        this.authorized = new Set();

        broker.subscribe(
            EventType.ORDER_CREATED,
            'payment-service',
            async (event) => {
                const amount = event.payload.amount;

                if (!Number.isFinite(amount) || amount <= 0) {
                    throw new Error('Invalid payment amount');
                }

                // Idempotency prevents duplicate payment authorization.
                if (this.authorized.has(event.aggregateId)) {
                    return;
                }

                this.authorized.add(event.aggregateId);
                console.log(
                    `[payment-service] Authorized ${event.aggregateId}: ${amount.toFixed(2)}`
                );
            }
        );
    }
}

class NotificationService {
    constructor(broker) {
        this.messages = [];

        broker.subscribe(
            EventType.ORDER_CREATED,
            'notification-service',
            async (event) => {
                const message = `Order ${event.aggregateId} was created`;
                this.messages.push(message);
                console.log(`[notification-service] ${message}`);
            }
        );

        broker.subscribe(
            EventType.ORDER_CONFIRMED,
            'notification-service',
            async (event) => {
                const message = `Order ${event.aggregateId} was confirmed`;
                this.messages.push(message);
                console.log(`[notification-service] ${message}`);
            }
        );
    }
}

class AnalyticsService {
    constructor(broker) {
        this.counts = new Map();

        for (const type of Object.values(EventType)) {
            broker.subscribe(type, 'analytics-service', async (event) => {
                this.counts.set(
                    event.type,
                    (this.counts.get(event.type) || 0) + 1
                );
            });
        }
    }
}

async function main() {
    const broker = new EventBroker();

    const paymentService = new PaymentService(broker);
    const notificationService = new NotificationService(broker);
    const analyticsService = new AnalyticsService(broker);

    const orderService = new OrderService(broker);

    const orderId = orderService.createOrder('customer-1001', 1499.50);

    console.log(`Pending events: ${broker.pendingCount()}`);

    await broker.drain();

    console.log(`Authorized payments: ${paymentService.authorized.size}`);
    console.log(`Notifications: ${notificationService.messages.length}`);
    console.log(
        `Analytics: ${JSON.stringify(Object.fromEntries(analyticsService.counts))}`
    );

    // A new consumer can be introduced without modifying OrderService.
    const auditLog = [];

    broker.subscribe(
        EventType.ORDER_CREATED,
        'audit-service',
        async (event) => {
            auditLog.push({
                eventId: event.eventId,
                aggregateId: event.aggregateId
            });
        }
    );

    const secondOrder = orderService.createOrder('customer-1002', 250);
    await broker.drain();

    console.log(`Second order: ${secondOrder}`);
    console.log(`Audit entries: ${auditLog.length}`);

    try {
        orderService.createOrder('', 100);
    } catch (error) {
        console.log(`[validation] ${error.message}`);
    }

    const confirmed = new DomainEvent({
        type: EventType.ORDER_CONFIRMED,
        aggregateId: orderId,
        payload: { confirmedBy: 'workflow-service' },
        producer: 'workflow-service'
    });

    broker.publish(confirmed);
    await broker.drain();

    // Simulate a failing downstream consumer.
    broker.subscribe(
        EventType.ORDER_CONFIRMED,
        'unavailable-service',
        async () => {
            throw new Error('Downstream service unavailable');
        }
    );

    broker.publish(
        new DomainEvent({
            type: EventType.ORDER_CONFIRMED,
            aggregateId: orderId,
            payload: { confirmedBy: 'workflow-service' },
            producer: 'workflow-service'
        })
    );

    await broker.drain();

    console.log(`Dead-lettered deliveries: ${broker.deadLetters.length}`);

    /*
     * Production design considerations:
     * - Replace the in-memory queue with a durable broker.
     * - Use retry policies and dead-letter queues.
     * - Preserve ordering only where the business aggregate requires it.
     * - Add correlation and causation identifiers for distributed tracing.
     * - Avoid secrets and unnecessary personal data in event payloads.
     * - Authenticate publishers and authorize consumer subscriptions.
     * - Measure queue depth, processing latency, failures, and consumer lag.
     */
}

main().catch(error => {
    console.error(`[fatal] ${error.message}`);
    process.exitCode = 1;
});
