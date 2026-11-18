-- ============================================
-- DATAMIND AI
-- DATOS DE PRUEBA EMPRESARIALES
-- Moneda: Soles (S/)
-- ============================================

-- 1. CLIENTES
INSERT INTO customers
(first_name, last_name, email, phone, city, country)
VALUES
('Ana', 'Torres', 'ana.torres@example.com', '987111001', 'Lima', 'Peru'),
('Carlos', 'Mendoza', 'carlos.mendoza@example.com', '987111002', 'Arequipa', 'Peru'),
('Lucia', 'Ramirez', 'lucia.ramirez@example.com', '987111003', 'Lima', 'Peru'),
('Miguel', 'Flores', 'miguel.flores@example.com', '987111004', 'Cusco', 'Peru'),
('Sofia', 'Castillo', 'sofia.castillo@example.com', '987111005', 'Trujillo', 'Peru'),
('Jose', 'Vargas', 'jose.vargas@example.com', '987111006', 'Lima', 'Peru'),
('Valeria', 'Rojas', 'valeria.rojas@example.com', '987111007', 'Piura', 'Peru'),
('Diego', 'Herrera', 'diego.herrera@example.com', '987111008', 'Lima', 'Peru'),
('Camila', 'Paredes', 'camila.paredes@example.com', '987111009', 'Arequipa', 'Peru'),
('Andres', 'Salazar', 'andres.salazar@example.com', '987111010', 'Chiclayo', 'Peru')
ON CONFLICT (email) DO NOTHING;


-- 2. PRODUCTOS
INSERT INTO products
(sku, product_name, category, description, unit_price, stock_quantity)
VALUES
('P001', 'Laptop Pro', 'Computadoras', 'Laptop para trabajo y negocios', 3500.00, 25),
('P002', 'Mouse Wireless', 'Accesorios', 'Mouse ergonomico inalambrico', 85.00, 100),
('P003', 'Teclado Mecanico', 'Accesorios', 'Teclado mecanico RGB', 220.00, 60),
('P004', 'Monitor 24 pulgadas', 'Monitores', 'Monitor Full HD', 780.00, 35),
('P005', 'Audifonos Bluetooth', 'Audio', 'Audifonos inalambricos', 160.00, 80),
('P006', 'Webcam HD', 'Accesorios', 'Camara para videoconferencias', 140.00, 50),
('P007', 'SSD 1TB', 'Almacenamiento', 'Unidad de almacenamiento SSD', 350.00, 40),
('P008', 'Silla Ergonomica', 'Mobiliario', 'Silla para oficina', 950.00, 20)
ON CONFLICT (sku) DO NOTHING;


-- 3. PEDIDOS
INSERT INTO orders
(order_number, customer_id, order_date, order_status)
SELECT
    v.order_number,
    c.customer_id,
    v.order_date::timestamp,
    v.order_status
FROM (VALUES
    ('PED-001', 'ana.torres@example.com', '2026-09-05', 'completed'),
    ('PED-002', 'carlos.mendoza@example.com', '2026-09-12', 'completed'),
    ('PED-003', 'lucia.ramirez@example.com', '2026-09-18', 'shipped'),
    ('PED-004', 'miguel.flores@example.com', '2026-10-02', 'completed'),
    ('PED-005', 'ana.torres@example.com', '2026-10-08', 'completed'),
    ('PED-006', 'sofia.castillo@example.com', '2026-10-15', 'cancelled'),
    ('PED-007', 'carlos.mendoza@example.com', '2026-10-22', 'completed'),
    ('PED-008', 'jose.vargas@example.com', '2026-10-29', 'paid'),
    ('PED-009', 'lucia.ramirez@example.com', '2026-11-02', 'completed'),
    ('PED-010', 'miguel.flores@example.com', '2026-11-05', 'completed'),
    ('PED-011', 'sofia.castillo@example.com', '2026-11-08', 'shipped'),
    ('PED-012', 'jose.vargas@example.com', '2026-11-10', 'completed'),
    ('PED-013', 'valeria.rojas@example.com', '2026-11-12', 'pending'),
    ('PED-014', 'diego.herrera@example.com', '2026-11-13', 'completed'),
    ('PED-015', 'camila.paredes@example.com', '2026-11-14', 'completed')
) AS v(order_number, email, order_date, order_status)
JOIN customers c ON c.email = v.email
ON CONFLICT (order_number) DO NOTHING;


-- 4. DETALLES DE PEDIDOS
INSERT INTO order_details
(order_id, product_id, quantity, unit_price)
SELECT
    o.order_id,
    p.product_id,
    v.quantity,
    v.unit_price
FROM (VALUES
    ('PED-001', 'P001', 1, 3500.00),
    ('PED-001', 'P002', 2, 85.00),
    ('PED-002', 'P004', 1, 780.00),
    ('PED-002', 'P003', 1, 220.00),
    ('PED-003', 'P003', 2, 220.00),
    ('PED-003', 'P005', 1, 160.00),
    ('PED-004', 'P001', 1, 3500.00),
    ('PED-004', 'P007', 1, 350.00),
    ('PED-005', 'P002', 1, 85.00),
    ('PED-005', 'P006', 1, 140.00),
    ('PED-006', 'P008', 1, 950.00),
    ('PED-007', 'P004', 2, 780.00),
    ('PED-008', 'P005', 2, 160.00),
    ('PED-008', 'P002', 1, 85.00),
    ('PED-009', 'P007', 2, 350.00),
    ('PED-010', 'P001', 1, 3500.00),
    ('PED-010', 'P002', 1, 85.00),
    ('PED-011', 'P008', 1, 950.00),
    ('PED-011', 'P003', 1, 220.00),
    ('PED-012', 'P004', 1, 780.00),
    ('PED-012', 'P006', 1, 140.00),
    ('PED-013', 'P005', 1, 160.00),
    ('PED-014', 'P003', 1, 220.00),
    ('PED-014', 'P002', 2, 85.00),
    ('PED-015', 'P008', 1, 950.00)
) AS v(order_number, sku, quantity, unit_price)
JOIN orders o ON o.order_number = v.order_number
JOIN products p ON p.sku = v.sku
WHERE NOT EXISTS (
    SELECT 1
    FROM order_details od
    WHERE od.order_id = o.order_id
      AND od.product_id = p.product_id
);


-- 5. PAGOS
INSERT INTO payments
(order_id, payment_date, amount, payment_method, payment_status)
SELECT
    o.order_id,
    v.payment_date::timestamp,
    v.amount,
    v.payment_method,
    v.payment_status
FROM (VALUES
    ('PED-001', '2026-09-05', 3670.00, 'credit_card', 'completed'),
    ('PED-002', '2026-09-12', 1000.00, 'bank_transfer', 'completed'),
    ('PED-003', '2026-09-18', 600.00, 'digital_wallet', 'completed'),
    ('PED-004', '2026-10-02', 3850.00, 'credit_card', 'completed'),
    ('PED-005', '2026-10-08', 225.00, 'digital_wallet', 'completed'),
    ('PED-006', '2026-10-15', 950.00, 'credit_card', 'refunded'),
    ('PED-007', '2026-10-22', 1560.00, 'bank_transfer', 'completed'),
    ('PED-008', '2026-10-29', 405.00, 'cash', 'completed'),
    ('PED-009', '2026-11-02', 700.00, 'debit_card', 'completed'),
    ('PED-010', '2026-11-05', 3585.00, 'credit_card', 'completed'),
    ('PED-011', '2026-11-08', 1170.00, 'digital_wallet', 'completed'),
    ('PED-012', '2026-11-10', 920.00, 'bank_transfer', 'completed'),
    ('PED-013', '2026-11-12', 160.00, 'cash', 'pending'),
    ('PED-014', '2026-11-13', 390.00, 'credit_card', 'completed'),
    ('PED-015', '2026-11-14', 950.00, 'digital_wallet', 'completed')
) AS v(order_number, payment_date, amount, payment_method, payment_status)
JOIN orders o ON o.order_number = v.order_number
WHERE NOT EXISTS (
    SELECT 1
    FROM payments p
    WHERE p.order_id = o.order_id
);