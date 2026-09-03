"""Static synthetic catalogues.

Everything here is invented data — clearly synthetic identities, no real
personal information, no real payment details.
"""

# Merchant seeded for the demo dataset.
SEED_MERCHANT = {
    "name": "NovaCart Commerce",
    "external_id": "novacart_commerce",
    "currency": "INR",
    "timezone": "Asia/Kolkata",
}

# Synthetic given names (clearly invented, varied for readability).
GIVEN_NAMES = [
    "Aarav", "Ananya", "Arjun", "Diya", "Ishaan", "Kavya", "Kabir", "Meera",
    "Nikhil", "Priyanka", "Rohan", "Sanya", "Vihaan", "Tanvi", "Aditya",
    "Riya", "Dev", "Ira", "Reyansh", "Anika", "Vivaan", "Naina", "Aryan",
    "Ishita", "Yash", "Pooja", "Sam", "Nora", "Ethan", "Mia", "Liam",
    "Ava", "Noah", "Zara", "Omar", "Lena", "Hana", "Kenji", "Mateo",
]

FAMILY_NAMES = [
    "Sharma", "Iyer", "Patel", "Reddy", "Khan", "Mehta", "Nair", "Gupta",
    "Joshi", "Kulkarni", "Desai", "Rao", "Bhat", "Menon", "Kapoor",
    "Chopra", "Malhotra", "Sinha", "Banerjee", "Pillai", "Wood", "Silva",
    "Rossi", "Müller", "Kim", "Tanaka", "Okafor", "Costa", "Novak", "Diallo",
]

# Product catalogue: (name, unit_price INR). All prices are made up.
PRODUCT_CATALOGUE = [
    ("Wireless Earbuds Pro", 1999),
    ("Stainless Steel Water Bottle", 549),
    ("Cotton T-Shirt (Pack of 3)", 999),
    ("Desk Organizer", 799),
    ("USB-C Fast Charger 65W", 1299),
    ("Ceramic Coffee Mug 350ml", 449),
    ("Yoga Mat 6mm", 899),
    ("Bluetooth Speaker Mini", 1599),
    ("Notebook A5 (Pack of 5)", 349),
    ("LED Desk Lamp", 1199),
    ("Running Shoes", 2499),
    ("Backpack 25L Waterproof", 1799),
    ("Digital Kitchen Scale", 999),
    ("Sunglasses Polarized", 1499),
    ("Indoor Plant Pot Set", 1199),
    ("Electric Kettle 1.5L", 1399),
    ("Resistance Bands Set", 699),
    ("Laptop Stand Aluminum", 1099),
    ("Air Fryer 4L", 4999),
    ("Memory Foam Pillow", 1299),
    ("Smartphone Gimbal", 3999),
    ("Water Filter Pitcher", 1499),
    ("Hanging Wall Clock", 899),
    ("Bath Towel Set (Pack of 4)", 1099),
    ("Mechanical Keyboard 87-Key", 3499),
    ("Travel Duffel Bag", 2199),
    ("Espresso Maker Manual", 2999),
    ("Kids Building Blocks 500pc", 1599),
    ("Standing Desk Converter", 7999),
    ("Dual Monitor Arm", 2499),
]

# Delivery carriers (made up usage of common logistics partners).
CARRIERS = ["Delhivery", "BlueDart", "Ekart", "Shadowfax", "XpressBees"]

# Payment methods with relative weights (UPI dominant, Indian e-commerce).
PAYMENT_METHODS = [
    ("UPI", 55),
    ("CARD", 25),
    ("NETBANKING", 12),
    ("WALLET", 8),
]

# Customer message templates keyed by intent; {order} / {product} placeholders.
MESSAGE_TEMPLATES: dict[str, list[str]] = {
    "status_enquiry": [
        "Hi, I paid for {product} ({order}) two days ago — when will it ship?",
        "Hello, can I get a status update on order {order}? It still shows pending.",
        "Order {order} was charged to my card but I haven't received any update.",
    ],
    "complaint": [
        "This is the second time I'm following up on {order}. I paid and nothing happened — very unhappy.",
        "I ordered {product} ({order}) and it never arrived. I want this resolved.",
        "Order {order}: paid in full but no delivery after several days. Please escalate.",
    ],
    "refund_query": [
        "I was told my refund for {order} was initiated. How long will it take?",
        "When will the money be back for cancelled order {order}?",
    ],
    "confirmation": [
        "Thanks — order {order} has been confirmed. Will keep an eye out for delivery.",
        "Great, expected delivery for {order} looks on time. Thank you!",
    ],
    "delivery_update": [
        "My order {order} shows delayed in transit — can you confirm a new date?",
    ],
}

# Product id indexes that start the dataset with zero available stock
# (used by the INVENTORY_FAILURE / COMPOUND_FAILURE journeys).
OUT_OF_STOCK_PRODUCT_INDEXES = [6, 13, 21]

# Bulk restock happens whenever no product has sellable stock.
RESTOCK_QUANTITY = 500
RESTOCK_PRODUCT_INDEXES = [0, 3, 5, 9, 11, 16, 18, 24]