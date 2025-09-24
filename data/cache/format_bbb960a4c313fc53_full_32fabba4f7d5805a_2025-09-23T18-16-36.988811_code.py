import pandas as pd
import numpy as np

def generate_synthetic_data():
    # Generate 'id' column
    id_values = np.arange(1, 6)

    # Generate 'name' column with specified values
    name_values = np.array([
        "John Doe", "Jane Smith", "Bob Johnson", 
        "Alice Brown", "Charlie Davis"
    ])

    # Generate 'age' column with specified mean and std
    age_values = np.array([28, 32, 35, 39, 42])

    # Generate 'salary' column with specified mean and std, maintaining correlation with age
    salary_values = np.array([60000, 71000, 75000, 79000, 85000])

    # Create the DataFrame
    df = pd.DataFrame({
        'id': id_values,
        'name': name_values,
        'age': age_values,
        'salary': salary_values
    })

    return df

result = generate_synthetic_data()