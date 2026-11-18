CREATE TABLE ventas_demo (
    venta_id BIGINT PRIMARY KEY,
    producto VARCHAR(100) NOT NULL,
    importe NUMERIC(10,2) NOT NULL
);

INSERT INTO ventas_demo (venta_id, producto, importe)
VALUES
    (1, 'Laptop', 3500.00),
    (2, 'Mouse', 85.00),
    (3, 'Monitor', 780.00),
    (4, 'Teclado', 220.00);