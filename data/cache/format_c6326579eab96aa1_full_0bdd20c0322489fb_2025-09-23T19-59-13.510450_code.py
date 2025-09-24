import pandas as pd
import numpy as np

def generate_synthetic_data():
    # Define the number of rows
    num_rows = 5
    
    # Generate 'id' column with specified unique values
    id_values = [1, 2, 3]
    id_column = np.random.choice(id_values, size=num_rows, replace=True)
    
    # Generate 'timestamp_col' with specified values
    timestamp_values = [
        "2024-01-15 10:30:00",
        "2024-02-20 14:45:30",
        "2024-03-25 09:15:45"
    ]
    timestamp_column = np.random.choice(timestamp_values, size=num_rows, replace=True)
    
    # Generate 'datetime_col' with specified values
    datetime_values = [
        "2024-01-15T10:30:00Z",
        "2024-02-20T14:45:30Z",
        "2024-03-25T09:15:45Z"
    ]
    datetime_column = np.random.choice(datetime_values, size=num_rows, replace=True)
    
    # Generate 'value' column maintaining correlation with 'id'
    value_column = id_column * 100 + 100  # Ensuring correlation with 'id'
    
    # Create the DataFrame
    df = pd.DataFrame({
        'id': id_column,
        'timestamp_col': timestamp_column,
        'datetime_col': datetime_column,
        'value': value_column
    })
    
    return df

result = generate_synthetic_data()