import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

def generate_synthetic_data():
    num_rows = 100
    
    customer_ids = [f'C00{str(i).zfill(1)}' for i in range(1, 6)]
    names = ['John Smith', 'Jane Doe', 'Bob Johnson', 'Alice Brown', 'Charlie Wilson']
    emails = ['john.smith@email.com', 'jane.doe@email.com', 'bob.j@email.com', 'alice.b@email.com', 'charlie.w@email.com']
    phones = ['555-0101', '555-0102', '555-0103', '555-0104', '555-0105']
    cities = ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix']
    registration_dates = pd.to_datetime(['2023-01-15', '2023-02-20', '2023-03-10', '2023-04-05', '2023-05-12'])
    status = ['Active', 'Inactive']
    
    data = {
        'customer_id': np.random.choice(customer_ids, num_rows),
        'name': np.random.choice(names, num_rows),
        'email': np.random.choice(emails, num_rows),
        'phone': np.random.choice(phones, num_rows),
        'city': np.random.choice(cities, num_rows),
        'registration_date': np.random.choice(registration_dates, num_rows),
        'status': np.random.choice(status, num_rows, p=[0.8, 0.2]),
        'testt': np.random.choice([0, 1], num_rows, p=[0.4, 0.6]),
        'test2': [np.nan] * num_rows
    }
    
    return pd.DataFrame(data)

result = generate_synthetic_data()