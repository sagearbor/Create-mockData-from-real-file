import pandas as pd
import numpy as np

def generate_synthetic_data():
    # Create the id column with unique values 1, 2, 3
    ids = np.array([1, 2, 3])
    
    # Create the value column with a strong correlation to id
    values = np.array([10.5, 20.3, 30.7])
    
    # Create a DataFrame
    df = pd.DataFrame({
        'id': ids,
        'value': values
    })
    
    return df

result = generate_synthetic_data()