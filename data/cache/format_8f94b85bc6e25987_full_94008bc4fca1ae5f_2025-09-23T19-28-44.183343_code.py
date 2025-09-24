import pandas as pd
import numpy as np

def generate_synthetic_data():
    data = {
        'id': [1, 2],
        'random_col_1758670113': ['value1', 'value2'],
        'another_col': ['data1', 'data2']
    }
    return pd.DataFrame(data)

result = generate_synthetic_data()