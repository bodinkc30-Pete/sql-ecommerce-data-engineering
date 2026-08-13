from pathlib import Path
import sqlite3
import time


PROJECT_ROOT = Path(__file__).resolve().parent.parent

BENCHMARK_DB_PATH = (
    PROJECT_ROOT
    / "database"
    / "performance_benchmark.db"
)

ROW_COUNT = 100_000
TEST_ROUNDS = 20


DAILY_SALES_QUERY = """
SELECT
    order_date,
    COUNT(*) AS orders,
    SUM(order_total) AS revenue
FROM orders
WHERE order_status = 'COMPLETED'
GROUP BY order_date
ORDER BY order_date;
"""


PAYMENT_DAILY_QUERY = """
SELECT
    payment_date,
    payment_status,
    SUM(payment_amount) AS amount
FROM payments
GROUP BY
    payment_date,
    payment_status
ORDER BY payment_date;
"""


def measure_query(
    connection: sqlite3.Connection,
    query: str,
    rounds: int,
) -> float:
    connection.execute(query).fetchall()

    started_at = time.perf_counter()

    for _ in range(rounds):
        connection.execute(query).fetchall()

    elapsed = time.perf_counter() - started_at

    return elapsed / rounds


def show_plan(
    connection: sqlite3.Connection,
    name: str,
    query: str,
) -> None:
    print(f"\n=== {name} QUERY PLAN ===")

    rows = connection.execute(
        "EXPLAIN QUERY PLAN " + query
    ).fetchall()

    for row in rows:
        print(tuple(row))


def create_tables(
    connection: sqlite3.Connection,
) -> None:
    connection.executescript(
        """
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS payments;

        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            order_date TEXT NOT NULL,
            order_status TEXT NOT NULL,
            order_total REAL NOT NULL
        );

        CREATE TABLE payments (
            payment_id INTEGER PRIMARY KEY,
            order_id INTEGER NOT NULL,
            payment_date TEXT NOT NULL,
            payment_status TEXT NOT NULL,
            payment_amount REAL NOT NULL
        );
        """
    )


def insert_test_data(
    connection: sqlite3.Connection,
) -> None:
    print(
        f"[INFO] Creating {ROW_COUNT:,} orders "
        f"and {ROW_COUNT:,} payments..."
    )

    order_statuses = (
        "PENDING",
        "PROCESSING",
        "COMPLETED",
        "CANCELLED",
        "REFUNDED",
    )

    payment_statuses = (
        "PENDING",
        "PAID",
        "FAILED",
        "REFUNDED",
        "CANCELLED",
    )

    orders = []
    payments = []

    for row_id in range(1, ROW_COUNT + 1):
        day = ((row_id - 1) % 365) + 1

        month = ((day - 1) // 30) + 1
        month = min(month, 12)

        day_of_month = ((day - 1) % 28) + 1

        date_value = (
            f"2026-{month:02d}-{day_of_month:02d}"
        )

        orders.append(
            (
                row_id,
                (row_id % 20_000) + 1,
                date_value,
                order_statuses[
                    row_id
                    % len(order_statuses)
                ],
                float(
                    (row_id % 10_000)
                    / 10
                    + 1
                ),
            )
        )

        payments.append(
            (
                row_id,
                row_id,
                date_value,
                payment_statuses[
                    row_id
                    % len(payment_statuses)
                ],
                float(
                    (row_id % 10_000)
                    / 10
                    + 1
                ),
            )
        )

    connection.executemany(
        """
        INSERT INTO orders (
            order_id,
            customer_id,
            order_date,
            order_status,
            order_total
        )
        VALUES (?, ?, ?, ?, ?);
        """,
        orders,
    )

    connection.executemany(
        """
        INSERT INTO payments (
            payment_id,
            order_id,
            payment_date,
            payment_status,
            payment_amount
        )
        VALUES (?, ?, ?, ?, ?);
        """,
        payments,
    )

    connection.commit()


def create_current_indexes(
    connection: sqlite3.Connection,
) -> None:
    connection.executescript(
        """
        CREATE INDEX idx_orders_order_status
        ON orders(order_status);

        CREATE INDEX idx_orders_order_date
        ON orders(order_date);

        CREATE INDEX idx_payments_payment_date
        ON payments(payment_date);

        CREATE INDEX idx_payments_payment_status
        ON payments(payment_status);
        """
    )


def create_candidate_indexes(
    connection: sqlite3.Connection,
) -> None:
    connection.executescript(
        """
        CREATE INDEX idx_orders_status_date
        ON orders(
            order_status,
            order_date
        );

        CREATE INDEX idx_payments_date_status
        ON payments(
            payment_date,
            payment_status
        );
        """
    )


def main() -> None:
    if BENCHMARK_DB_PATH.exists():
        BENCHMARK_DB_PATH.unlink()

    with sqlite3.connect(
        BENCHMARK_DB_PATH
    ) as connection:
        create_tables(connection)
        insert_test_data(connection)

        print("\n[BASELINE] Current indexes")
        create_current_indexes(connection)

        connection.execute("ANALYZE;")

        show_plan(
            connection,
            "DAILY_SALES BEFORE",
            DAILY_SALES_QUERY,
        )

        show_plan(
            connection,
            "PAYMENT_DAILY BEFORE",
            PAYMENT_DAILY_QUERY,
        )

        daily_before = measure_query(
            connection,
            DAILY_SALES_QUERY,
            TEST_ROUNDS,
        )

        payment_before = measure_query(
            connection,
            PAYMENT_DAILY_QUERY,
            TEST_ROUNDS,
        )

        print(
            "\n[CANDIDATE] Adding composite indexes"
        )

        create_candidate_indexes(connection)
        connection.execute("ANALYZE;")

        show_plan(
            connection,
            "DAILY_SALES AFTER",
            DAILY_SALES_QUERY,
        )

        show_plan(
            connection,
            "PAYMENT_DAILY AFTER",
            PAYMENT_DAILY_QUERY,
        )

        daily_after = measure_query(
            connection,
            DAILY_SALES_QUERY,
            TEST_ROUNDS,
        )

        payment_after = measure_query(
            connection,
            PAYMENT_DAILY_QUERY,
            TEST_ROUNDS,
        )

        print("\n" + "=" * 60)
        print("[BENCHMARK RESULTS]")
        print(
            f"Rows per table: {ROW_COUNT:,}"
        )
        print(
            f"Rounds per query: {TEST_ROUNDS}"
        )

        print(
            "\nDAILY_SALES"
        )
        print(
            f"  Before: "
            f"{daily_before * 1000:.3f} ms"
        )
        print(
            f"  After : "
            f"{daily_after * 1000:.3f} ms"
        )
        print(
            f"  Speedup: "
            f"{daily_before / daily_after:.2f}x"
        )

        print(
            "\nPAYMENT_DAILY"
        )
        print(
            f"  Before: "
            f"{payment_before * 1000:.3f} ms"
        )
        print(
            f"  After : "
            f"{payment_after * 1000:.3f} ms"
        )
        print(
            f"  Speedup: "
            f"{payment_before / payment_after:.2f}x"
        )

        print("=" * 60)

    print(
        "\n[INFO] Benchmark database:"
    )
    print(BENCHMARK_DB_PATH)


if __name__ == "__main__":
    main()