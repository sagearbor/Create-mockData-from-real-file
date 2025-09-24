import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

def generate_synthetic_data():
    num_rows = 100
    
    # Generate order_id
    order_id = np.random.randint(1001, 1006, size=num_rows)
    
    # Generate date
    date_choices = ['2024-01-15', '2024-01-16', '2024-01-17']
    date = np.random.choice(date_choices, size=num_rows, p=[0.02, 0.02, 0.01])
    
    # Generate customer_id
    customer_id_choices = ['C001', 'C002', 'C003', 'C004']
    customer_id = np.random.choice(customer_id_choices, size=num_rows, p=[0.02, 0.01, 0.01, 0.01])
    
    # Generate product
    product_choices = ['Widget A', 'Widget B', 'Widget C', 'Widget D']
    product = np.random.choice(product_choices, size=num_rows, p=[0.02, 0.01, 0.01, 0.01])
    
    # Generate quantity
    quantity = np.random.randint(1, 6, size=num_rows)
    
    # Generate price
    price = np.random.normal(loc=41.99, scale=13.04, size=num_rows).clip(29.99, 59.99)
    
    # Calculate total
    total = quantity * price
    
    # Generate testt
    testt_choices = ['1', '0', '`']
    testt = np.random.choice(testt_choices, size=num_rows, p=[0.02, 0.02, 0.01])
    
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