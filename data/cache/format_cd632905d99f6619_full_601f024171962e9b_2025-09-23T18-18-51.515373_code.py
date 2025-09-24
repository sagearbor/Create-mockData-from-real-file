import pandas as pd
import numpy as np

def generate_synthetic_data():
    np.random.seed(42)
    
    # Generate metric_a with specified properties
    metric_a = np.random.randint(1, 11, size=10)  # Unique values from 1 to 10
    
    # Generate metric_b with a correlation to metric_a
    metric_b = metric_a * 2.5 + np.random.normal(0, 5, size=10)  # Linear relationship with some noise
    
    # Generate category with exact distribution
    category = np.random.choice(['A', 'B'], size=10, p=[0.5, 0.5])  # Equal distribution of A and B
    
    # Create DataFrame
    df = pd.DataFrame({
        'metric_a': metric_a,
        'metric_b': metric_b,
        'category': category
    })
    
    return df

result = generate_synthetic_data()