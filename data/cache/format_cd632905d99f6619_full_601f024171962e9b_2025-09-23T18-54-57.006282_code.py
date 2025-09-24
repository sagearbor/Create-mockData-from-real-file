import pandas as pd
import numpy as np

def generate_synthetic_data():
    np.random.seed(0)  # For reproducibility
    num_rows = 10

    # Generate metric_a with specified properties
    metric_a = np.random.randint(1, 11, size=num_rows)  # Unique values from 1 to 10

    # Generate metric_b with a strong correlation to metric_a
    metric_b = metric_a * 2.5 + np.random.normal(0, 2, num_rows)  # Linear relationship with some noise

    # Generate category with exact values and distribution
    category = np.random.choice(['A', 'B'], size=num_rows, p=[0.5, 0.5])  # 5 A's and 5 B's

    # Create DataFrame
    df = pd.DataFrame({
        'metric_a': metric_a,
        'metric_b': metric_b,
        'category': category
    })

    return df

result = generate_synthetic_data()