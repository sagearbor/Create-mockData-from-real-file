import pandas as pd
import numpy as np
import random

def generate_synthetic_data():
    # Define the number of rows
    num_rows = 5
    
    # Generate 'id' column with specified unique values
    ids = [1, 2, 3]
    id_values = random.choices(ids, k=num_rows)
    
    # Generate 'name' column with specified values
    names = ["Alice", "Bob", "Charlie"]
    name_values = random.choices(names, k=num_rows)
    
    # Generate 'created_date' column with specified values
    created_dates = ["2024-01-15", "2024-02-20", "2024-03-25"]
    created_date_values = random.choices(created_dates, k=num_rows)
    
    # Generate 'amount' column with specified statistical properties
    amount_values = np.random.normal(loc=175.5, scale=75.125, size=num_rows).clip(100.5, 250.75)
    
    # Create the DataFrame
    df = pd.DataFrame({
        'id': id_values,
        'name': name_values,
        'created_date': created_date_values,
        'amount': amount_values
    })
    
    return df

result = generate_synthetic_data()