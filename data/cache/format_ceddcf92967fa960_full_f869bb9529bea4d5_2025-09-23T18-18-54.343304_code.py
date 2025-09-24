import pandas as pd
import numpy as np

def generate_synthetic_data():
    data = {
        'id': [1, 2, 3],
        'value': [10.5, 20.3, 30.7]
    }
    df = pd.DataFrame(data)
    return df

result = generate_synthetic_data()