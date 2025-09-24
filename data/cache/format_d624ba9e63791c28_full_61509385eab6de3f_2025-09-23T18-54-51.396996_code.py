import pandas as pd
import numpy as np

def generate_synthetic_data():
    # Generate customer_id
    customer_id = np.array([1, 2, 3, 4, 5])
    
    # Generate purchase_amount with specified mean and std
    purchase_amount = np.random.normal(loc=195.3, scale=79.81, size=5).clip(100.5, 300.0)
    
    # Generate product_category with specified distribution
    product_category = np.random.choice(
        ['Electronics', 'Clothing', 'Books'], 
        size=5, 
        p=[0.4, 0.4, 0.2]  # Distribution based on most_common_values
    )
    
    # Create DataFrame
    df = pd.DataFrame({
        'customer_id': customer_id,
        'purchase_amount': purchase_amount,
        'product_category': product_category
    })
    
    return df

result = generate_synthetic_data()