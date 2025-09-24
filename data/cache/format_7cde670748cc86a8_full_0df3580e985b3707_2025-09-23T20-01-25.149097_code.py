import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

def generate_synthetic_data():
    num_rows = 100

    # Generate patient_id
    patient_ids = [f'P00{str(i).zfill(1)}' for i in range(1, 6)]
    patient_id = np.random.choice(patient_ids, size=num_rows)

    # Generate age
    age = np.random.randint(29, 63, size=num_rows)

    # Generate gender
    gender = np.random.choice(['M', 'F'], size=num_rows, p=[0.6, 0.4])

    # Generate diagnosis
    diagnosis = np.random.choice(['Hypertension', 'Diabetes Type 2', 'Anxiety', 'Depression'], 
                                  size=num_rows, p=[0.4, 0.2, 0.2, 0.2])

    # Generate treatment_date
    treatment_dates = pd.date_range(start='2024-01-10', periods=5, freq='D')
    treatment_date = np.random.choice(treatment_dates, size=num_rows)

    # Generate doctor_id
    doctor_ids = ['D101', 'D102', 'D103']
    doctor_id = np.random.choice(doctor_ids, size=num_rows, p=[0.4, 0.3, 0.3])

    # Generate medication
    medications = ['Lisinopril', 'Metformin', 'Sertraline', 'Amlodipine', 'Fluoxetine']
    medication = np.random.choice(medications, size=num_rows)

    # Generate dosage_mg
    dosage_mg = np.random.choice([5, 10, 20, 50, 500], size=num_rows)

    # Generate test3
    test3 = np.random.choice([0, 1], size=num_rows)

    # Create DataFrame
    data = {
        'patient_id': patient_id,
        'age': age,
        'gender': gender,
        'diagnosis': diagnosis,
        'treatment_date': treatment_date,
        'doctor_id': doctor_id,
        'medication': medication,
        'dosage_mg': dosage_mg,
        'test3': test3
    }

    return pd.DataFrame(data)

result = generate_synthetic_data()