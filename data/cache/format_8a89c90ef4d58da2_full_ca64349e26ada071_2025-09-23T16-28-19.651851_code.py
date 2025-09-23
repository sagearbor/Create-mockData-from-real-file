import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

def generate_synthetic_data():
    # Define the number of rows
    num_rows = 5

    # Generate patient_id
    patient_ids = [f'P00{i+1}' for i in range(num_rows)]

    # Generate age with specified mean and std deviation
    ages = [random.randint(29, 62) for _ in range(num_rows)]

    # Generate gender with specified distribution
    genders = random.choices(['M', 'F'], weights=[3, 2], k=num_rows)

    # Generate diagnosis with specified distribution
    diagnoses = random.choices(['Hypertension', 'Diabetes Type 2', 'Anxiety', 'Depression'], weights=[2, 1, 1, 1], k=num_rows)

    # Generate treatment_date
    treatment_dates = pd.date_range(start='2024-01-10', periods=num_rows, freq='D').strftime('%Y-%m-%d').tolist()

    # Generate doctor_id with specified distribution
    doctor_ids = random.choices(['D101', 'D102', 'D103'], weights=[2, 1, 2], k=num_rows)

    # Generate medication with specified distribution
    medications = random.choices(['Lisinopril', 'Metformin', 'Sertraline', 'Amlodipine', 'Fluoxetine'], k=num_rows)

    # Generate dosage_mg with specified range
    dosages = [random.randint(5, 500) for _ in range(num_rows)]

    # Generate LDL_mg with specified range
    LDLS = [random.randint(23, 88) for _ in range(num_rows)]

    # Create the DataFrame
    data = {
        'patient_id': patient_ids,
        'age': ages,
        'gender': genders,
        'diagnosis': diagnoses,
        'treatment_date': treatment_dates,
        'doctor_id': doctor_ids,
        'medication': medications,
        'dosage_mg': dosages,
        'LDL_mg': LDLS
    }
    
    df = pd.DataFrame(data)
    return df

result = generate_synthetic_data()