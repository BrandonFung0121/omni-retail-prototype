"""Static product catalog with deliberate popularity/margin variance.

A hand-authored catalog (rather than fully random names) keeps the
generated dataset readable and lets us control which products are
"popular" vs. "slow movers", and which have thin vs. healthy margins.
"""

# (name, category, selling_price, cost, popularity_weight)
# popularity_weight is relative demand: a higher number means the
# product is chosen more often when orders are generated.
PRODUCT_CATALOG = [
    ("Everyday Cotton T-Shirt", "Apparel", 19.99, 6.50, 30),
    ("Classic Denim Jeans", "Apparel", 54.99, 21.00, 18),
    ("Lightweight Rain Jacket", "Apparel", 79.99, 32.00, 10),
    ("Merino Wool Sweater", "Apparel", 89.99, 38.00, 6),
    ("Athletic Performance Socks (3-pack)", "Apparel", 14.99, 4.20, 22),
    ("Wireless Earbuds Pro", "Electronics", 129.99, 55.00, 25),
    ("Portable Bluetooth Speaker", "Electronics", 59.99, 24.00, 16),
    ("Smart Fitness Watch", "Electronics", 199.99, 92.00, 14),
    ("USB-C Fast Charger 65W", "Electronics", 34.99, 11.00, 20),
    ("4K Streaming Media Stick", "Electronics", 49.99, 19.00, 9),
    ("Noise-Cancelling Headphones", "Electronics", 249.99, 110.00, 7),
    ("Stainless Steel Water Bottle", "Home & Kitchen", 24.99, 7.50, 28),
    ("Ceramic Non-Stick Cookware Set", "Home & Kitchen", 149.99, 62.00, 8),
    ("Programmable Coffee Maker", "Home & Kitchen", 69.99, 27.00, 12),
    ("Bamboo Cutting Board Set", "Home & Kitchen", 29.99, 9.00, 15),
    ("Electric Kettle", "Home & Kitchen", 39.99, 14.00, 11),
    ("Scented Soy Candle Trio", "Home & Kitchen", 22.99, 6.00, 19),
    ("Hydrating Face Serum", "Beauty", 32.99, 9.50, 21),
    ("Natural Bristle Hairbrush", "Beauty", 16.99, 4.50, 13),
    ("SPF 50 Daily Sunscreen", "Beauty", 18.99, 5.20, 24),
    ("Yoga Mat with Carry Strap", "Sports", 34.99, 11.50, 17),
    ("Adjustable Dumbbell Set", "Sports", 119.99, 48.00, 5),
    ("Insulated Sports Backpack", "Accessories", 44.99, 16.00, 10),
    ("Polarized Sunglasses", "Accessories", 27.99, 8.00, 14),
]
