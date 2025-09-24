import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

def generate_synthetic_data():
    num_rows = 100

    # Generate order_id
    order_id = np.random.randint(1001, 1006, size=num_rows)

    # Generate dates
    date_options = ['2024-01-15', '2024-01-16', '2024-01-17']
    date = np.random.choice(date_options, size=num_rows)

    # Generate customer_id
    customer_id_options = ['C001', 'C002', 'C003', 'C004']
    customer_id = np.random.choice(customer_id_options, size=num_rows, p=[0.2, 0.1, 0.1, 0.1])

    # Generate product
    product_options = ['Widget A', 'Widget B', 'Widget C', 'Widget D']
    product = np.random.choice(product_options, size=num_rows, p=[0.2, 0.1, 0.1, 0.1])

    # Generate quantity
    quantity = np.random.randint(1, 6, size=num_rows)

    # Generate price
    price = np.random.normal(loc=41.99, scale=13, size=num_rows).clip(29.99, 59.99)

    # Calculate total
    total = quantity * price

    # Generate testt
    testt = np.random.choice([0, 1], size=num_rows, p=[0.6, 0.4])

    # Create DataFrame
    df = pd.DataFrame({
        'order_id': order_id,
        'date': pd.to_datetime(date),
        'customer_id': customer_id,
        'product': product,
        'quantity': quantity,
        'price': price,
        'total': total,
        'testt': testt
    })

    return df

result = generate_synthetic_data()