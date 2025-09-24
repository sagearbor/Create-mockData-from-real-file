"""Clinical reference data library for generating meaningful mock medical data."""

import pandas as pd
from typing import Dict, List, Any, Optional
import random
from pathlib import Path
import json

class ClinicalReferenceLibrary:
    """Provides clinical reference data for realistic synthetic data generation."""

    def __init__(self):
        """Initialize with common clinical and general reference data."""
        self.medications = self._load_medications()
        self.lab_tests = self._load_lab_tests()
        self.units = self._load_units()
        self.diagnoses = self._load_diagnoses()
        self.procedures = self._load_procedures()
        self.body_sites = self._load_body_sites()
        self.clinical_terms = self._load_clinical_terms()
        # Add general categorical reference data
        self.gender_values = self._load_gender_values()
        self.ethnicity_values = self._load_ethnicity_values()
        self.states = self._load_states()
        self.countries = self._load_countries()
        self.marital_status = self._load_marital_status()
        self.employment_status = self._load_employment_status()
        self.education_levels = self._load_education_levels()
        self.blood_types = self._load_blood_types()
        self.cities = self._load_cities()
        self.first_names = self._load_first_names()
        self.last_names = self._load_last_names()

    def _load_medications(self) -> List[str]:
        """Load common medication names."""
        return [
            # Pain relievers
            "Acetaminophen", "Ibuprofen", "Aspirin", "Naproxen", "Morphine",
            "Oxycodone", "Tramadol", "Codeine", "Gabapentin", "Pregabalin",

            # Antibiotics
            "Amoxicillin", "Azithromycin", "Ciprofloxacin", "Doxycycline",
            "Cephalexin", "Metronidazole", "Clindamycin", "Levofloxacin",
            "Penicillin", "Vancomycin",

            # Cardiovascular
            "Metoprolol", "Lisinopril", "Amlodipine", "Atorvastatin",
            "Simvastatin", "Losartan", "Hydrochlorothiazide", "Furosemide",
            "Warfarin", "Clopidogrel", "Aspirin", "Digoxin",

            # Diabetes
            "Metformin", "Insulin glargine", "Insulin lispro", "Glipizide",
            "Glyburide", "Sitagliptin", "Empagliflozin", "Liraglutide",

            # Mental health
            "Sertraline", "Escitalopram", "Fluoxetine", "Duloxetine",
            "Venlafaxine", "Bupropion", "Trazodone", "Alprazolam",
            "Lorazepam", "Clonazepam", "Diazepam", "Risperidone",

            # Gastrointestinal
            "Omeprazole", "Pantoprazole", "Ranitidine", "Famotidine",
            "Ondansetron", "Metoclopramide", "Loperamide", "Docusate",

            # Respiratory
            "Albuterol", "Budesonide", "Fluticasone", "Montelukast",
            "Prednisone", "Methylprednisolone", "Dexamethasone",

            # Other common
            "Levothyroxine", "Vitamin D", "Folic acid", "Iron sulfate",
            "Potassium chloride", "Calcium carbonate", "Magnesium oxide"
        ]

    def _load_lab_tests(self) -> List[str]:
        """Load common laboratory test names."""
        return [
            # Blood counts
            "WBC", "RBC", "Hemoglobin", "Hematocrit", "Platelet count",
            "Neutrophils", "Lymphocytes", "Monocytes", "Eosinophils", "Basophils",

            # Chemistry panel
            "Glucose", "BUN", "Creatinine", "eGFR", "Sodium", "Potassium",
            "Chloride", "CO2", "Calcium", "Total protein", "Albumin",
            "Total bilirubin", "ALT", "AST", "Alkaline phosphatase",

            # Lipid panel
            "Total cholesterol", "LDL cholesterol", "HDL cholesterol", "Triglycerides",

            # Cardiac markers
            "Troponin", "BNP", "CK-MB", "Myoglobin", "D-dimer",

            # Thyroid
            "TSH", "Free T4", "Free T3", "Total T4", "Total T3",

            # Diabetes
            "HbA1c", "Fasting glucose", "Random glucose", "C-peptide",

            # Inflammation
            "CRP", "ESR", "Ferritin", "Procalcitonin",

            # Vitamins and minerals
            "Vitamin B12", "Vitamin D", "Folate", "Iron", "TIBC",

            # Urinalysis
            "Urine protein", "Urine glucose", "Urine specific gravity",
            "Urine pH", "Urine ketones", "Urine blood",

            # Coagulation
            "PT", "PTT", "INR", "Fibrinogen"
        ]

    def _load_units(self) -> Dict[str, List[str]]:
        """Load common medical units grouped by category."""
        return {
            "weight": ["mg", "g", "kg", "mcg", "lb", "oz"],
            "volume": ["mL", "L", "dL", "mcL", "cc"],
            "concentration": ["mg/dL", "g/dL", "mmol/L", "mEq/L", "ng/mL", "pg/mL", "mcg/mL", "IU/mL"],
            "rate": ["mg/hr", "mL/hr", "mcg/min", "units/hr", "gtt/min"],
            "count": ["cells/mcL", "x10^9/L", "x10^6/mcL", "/hpf", "/lpf"],
            "percentage": ["%", "percent"],
            "time": ["seconds", "minutes", "hours", "days", "weeks", "months", "years"],
            "temperature": ["°C", "°F", "Celsius", "Fahrenheit"],
            "pressure": ["mmHg", "cmH2O", "kPa"],
            "dosage": ["tablet", "capsule", "mL", "mg", "mcg", "units", "puffs", "drops"],
            "frequency": ["daily", "BID", "TID", "QID", "q4h", "q6h", "q8h", "q12h", "PRN", "weekly", "monthly"]
        }

    def _load_diagnoses(self) -> List[str]:
        """Load common diagnosis codes and descriptions."""
        return [
            # Cardiovascular
            "Hypertension", "Hyperlipidemia", "Coronary artery disease",
            "Atrial fibrillation", "Heart failure", "Myocardial infarction",

            # Respiratory
            "Asthma", "COPD", "Pneumonia", "Bronchitis", "Upper respiratory infection",
            "COVID-19", "Influenza", "Sleep apnea",

            # Endocrine
            "Type 2 diabetes mellitus", "Type 1 diabetes mellitus",
            "Hypothyroidism", "Hyperthyroidism", "Obesity",

            # Gastrointestinal
            "GERD", "Peptic ulcer disease", "Irritable bowel syndrome",
            "Crohn's disease", "Ulcerative colitis", "Gastroenteritis",

            # Neurological
            "Migraine", "Seizure disorder", "Stroke", "Parkinson's disease",
            "Alzheimer's disease", "Multiple sclerosis",

            # Psychiatric
            "Major depressive disorder", "Anxiety disorder", "Bipolar disorder",
            "PTSD", "ADHD", "Schizophrenia",

            # Musculoskeletal
            "Osteoarthritis", "Rheumatoid arthritis", "Osteoporosis",
            "Lower back pain", "Fibromyalgia",

            # Renal
            "Chronic kidney disease", "Acute kidney injury", "UTI",

            # Other
            "Anemia", "Cancer", "Pregnancy", "Allergic rhinitis"
        ]

    def _load_procedures(self) -> List[str]:
        """Load common medical procedures."""
        return [
            "Physical examination", "Blood draw", "IV insertion",
            "ECG", "Chest X-ray", "CT scan", "MRI", "Ultrasound",
            "Colonoscopy", "Endoscopy", "Bronchoscopy", "Biopsy",
            "Cardiac catheterization", "Angioplasty", "CABG",
            "Appendectomy", "Cholecystectomy", "Hernia repair",
            "Joint replacement", "Fracture repair", "Wound care",
            "Dialysis", "Chemotherapy", "Radiation therapy",
            "Vaccination", "Injection", "Infusion", "Transfusion"
        ]

    def _load_body_sites(self) -> List[str]:
        """Load common body sites/anatomical locations."""
        return [
            "Head", "Neck", "Chest", "Abdomen", "Back", "Pelvis",
            "Right arm", "Left arm", "Right leg", "Left leg",
            "Right hand", "Left hand", "Right foot", "Left foot",
            "Heart", "Lungs", "Liver", "Kidneys", "Brain", "Spine",
            "Stomach", "Intestines", "Bladder", "Skin"
        ]

    def _load_clinical_terms(self) -> Dict[str, List[str]]:
        """Load various clinical terminology."""
        return {
            "severity": ["Mild", "Moderate", "Severe", "Critical"],
            "status": ["Active", "Resolved", "Chronic", "Acute", "Stable", "Unstable"],
            "admission_type": ["Emergency", "Elective", "Urgent", "Routine"],
            "discharge_disposition": ["Home", "SNF", "Rehab", "AMA", "Expired", "Transfer"],
            "gender": ["Male", "Female", "Other", "Unknown"],
            "blood_type": ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"],
            "allergy_severity": ["Mild", "Moderate", "Severe", "Life-threatening"],
            "pain_scale": ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
            "glasgow_coma": ["3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"]
        }

    def _load_gender_values(self) -> List[Dict[str, List[str]]]:
        """Load common gender value variations."""
        return [
            {"short": ["M", "F"], "long": ["Male", "Female"]},
            {"short": ["M", "F", "O"], "long": ["Male", "Female", "Other"]},
            {"numeric": ["0", "1"], "meaning": ["Female", "Male"]}  # Common in some systems
        ]

    def _load_ethnicity_values(self) -> List[str]:
        """Load common ethnicity categories."""
        return [
            "White", "Black or African American", "Asian",
            "Hispanic or Latino", "Native American", "Pacific Islander",
            "Middle Eastern", "Mixed/Multiple", "Other", "Prefer not to say"
        ]

    def _load_states(self) -> Dict[str, str]:
        """Load US state codes and names."""
        return {
            "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
            "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
            "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
            "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
            "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
            "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
            "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
            "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
            "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
            "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
            "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
            "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
            "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia"
        }

    def _load_countries(self) -> List[str]:
        """Load common country names and codes."""
        return [
            "USA", "United States", "Canada", "Mexico", "United Kingdom", "UK",
            "Germany", "France", "Spain", "Italy", "Japan", "China", "India",
            "Australia", "Brazil", "Russia", "South Korea", "Netherlands",
            "Switzerland", "Sweden", "Norway", "Denmark", "Finland", "Belgium"
        ]

    def _load_marital_status(self) -> List[str]:
        """Load marital status options."""
        return [
            "Single", "Married", "Divorced", "Widowed", "Separated",
            "Domestic Partnership", "Civil Union"
        ]

    def _load_employment_status(self) -> List[str]:
        """Load employment status options."""
        return [
            "Employed Full-time", "Employed Part-time", "Self-employed",
            "Unemployed", "Retired", "Student", "Disabled", "Homemaker"
        ]

    def _load_education_levels(self) -> List[str]:
        """Load education level options."""
        return [
            "No formal education", "Elementary", "Middle School", "High School",
            "Some College", "Associate Degree", "Bachelor's Degree",
            "Master's Degree", "Doctorate", "Professional Degree"
        ]

    def _load_blood_types(self) -> List[str]:
        """Load blood type options."""
        return ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

    def _load_cities(self) -> List[str]:
        """Load common US city names."""
        return [
            "New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
            "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose",
            "Austin", "Jacksonville", "Fort Worth", "Columbus", "Indianapolis",
            "Charlotte", "San Francisco", "Seattle", "Denver", "Washington",
            "Boston", "El Paso", "Nashville", "Detroit", "Oklahoma City",
            "Portland", "Las Vegas", "Memphis", "Louisville", "Baltimore",
            "Milwaukee", "Albuquerque", "Tucson", "Fresno", "Mesa",
            "Sacramento", "Atlanta", "Kansas City", "Colorado Springs", "Miami",
            "Raleigh", "Omaha", "Long Beach", "Virginia Beach", "Oakland",
            "Minneapolis", "Tulsa", "Arlington", "Tampa", "New Orleans"
        ]

    def _load_first_names(self) -> Dict[str, List[str]]:
        """Load common first names."""
        return {
            "male": [
                "James", "John", "Robert", "Michael", "William", "David", "Richard",
                "Joseph", "Thomas", "Christopher", "Charles", "Daniel", "Matthew",
                "Anthony", "Mark", "Donald", "Steven", "Kenneth", "Paul", "Joshua",
                "Kevin", "Brian", "George", "Edward", "Ronald", "Timothy", "Jason",
                "Jeffrey", "Ryan", "Jacob", "Gary", "Nicholas", "Eric", "Jonathan"
            ],
            "female": [
                "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara",
                "Susan", "Jessica", "Sarah", "Karen", "Nancy", "Lisa", "Betty",
                "Margaret", "Sandra", "Ashley", "Kimberly", "Emily", "Donna",
                "Michelle", "Carol", "Amanda", "Dorothy", "Melissa", "Deborah",
                "Stephanie", "Rebecca", "Laura", "Sharon", "Cynthia", "Amy", "Angela"
            ],
            "neutral": [
                "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie",
                "Avery", "Cameron", "Quinn", "Blake", "Hayden", "Parker", "Sage"
            ]
        }

    def _load_last_names(self) -> List[str]:
        """Load common last names."""
        return [
            "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
            "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
            "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
            "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
            "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
            "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
            "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell"
        ]

    def get_random_medications(self, n: int = 1) -> List[str]:
        """Get random medication names."""
        return random.sample(self.medications, min(n, len(self.medications)))

    def get_random_lab_tests(self, n: int = 1) -> List[str]:
        """Get random lab test names."""
        return random.sample(self.lab_tests, min(n, len(self.lab_tests)))

    def get_random_diagnoses(self, n: int = 1) -> List[str]:
        """Get random diagnosis names."""
        return random.sample(self.diagnoses, min(n, len(self.diagnoses)))

    def get_units_for_category(self, category: str) -> List[str]:
        """Get units for a specific category."""
        return self.units.get(category, [])

    def get_random_units(self, category: Optional[str] = None) -> str:
        """Get a random unit, optionally from a specific category."""
        if category and category in self.units:
            return random.choice(self.units[category])
        all_units = [unit for units in self.units.values() for unit in units]
        return random.choice(all_units)

    def detect_clinical_column_type(self, column_name: str) -> Optional[Dict[str, Any]]:
        """
        Detect if a column name represents clinical or categorical data and suggest appropriate values.

        Args:
            column_name: Name of the column

        Returns:
            Dictionary with detected type and suggested values, or None if not detected
        """
        col_lower = column_name.lower()

        # Gender-related
        gender_keywords = ['gender', 'sex', 'male_female', 'm_f']
        if any(keyword in col_lower for keyword in gender_keywords):
            return {
                "type": "gender",
                "suggested_values": ["M", "F"],
                "alternate_values": ["Male", "Female"],
                "category": "demographic"
            }

        # Ethnicity-related
        ethnicity_keywords = ['ethnicity', 'race', 'ethnic']
        if any(keyword in col_lower for keyword in ethnicity_keywords):
            return {
                "type": "ethnicity",
                "suggested_values": self.ethnicity_values[:10],
                "category": "demographic"
            }

        # State-related
        state_keywords = ['state', 'province', 'region']
        if any(keyword in col_lower for keyword in state_keywords):
            return {
                "type": "state",
                "suggested_values": list(self.states.keys())[:20],  # State codes
                "alternate_values": list(self.states.values())[:20],  # State names
                "category": "geographic"
            }

        # Country-related
        country_keywords = ['country', 'nation', 'nationality']
        if any(keyword in col_lower for keyword in country_keywords):
            return {
                "type": "country",
                "suggested_values": self.countries[:10],
                "category": "geographic"
            }

        # Marital status-related
        marital_keywords = ['marital', 'marriage', 'married']
        if any(keyword in col_lower for keyword in marital_keywords):
            return {
                "type": "marital_status",
                "suggested_values": self.marital_status,
                "category": "demographic"
            }

        # Employment-related
        employment_keywords = ['employment', 'employed', 'job_status', 'work_status']
        if any(keyword in col_lower for keyword in employment_keywords):
            return {
                "type": "employment_status",
                "suggested_values": self.employment_status,
                "category": "demographic"
            }

        # Education-related
        education_keywords = ['education', 'degree', 'schooling', 'qualification']
        if any(keyword in col_lower for keyword in education_keywords):
            return {
                "type": "education_level",
                "suggested_values": self.education_levels,
                "category": "demographic"
            }

        # City-related
        city_keywords = ['city', 'town', 'location', 'place', 'municipality']
        if any(keyword in col_lower for keyword in city_keywords):
            return {
                "type": "city",
                "suggested_values": self.cities[:20],
                "category": "geographic"
            }

        # Name-related
        name_keywords = ['name', 'firstname', 'first_name', 'lastname', 'last_name', 'full_name']
        if any(keyword in col_lower for keyword in name_keywords):
            # Determine if it's first, last, or full name
            if 'first' in col_lower:
                return {
                    "type": "first_name",
                    "suggested_values": (
                        self.first_names.get("male", [])[:10] +
                        self.first_names.get("female", [])[:10]
                    ),
                    "category": "personal"
                }
            elif 'last' in col_lower:
                return {
                    "type": "last_name",
                    "suggested_values": self.last_names[:20],
                    "category": "personal"
                }
            else:
                # Full name - combine first and last
                full_names = []
                for _ in range(20):
                    first = random.choice(
                        self.first_names.get("male", []) +
                        self.first_names.get("female", []) +
                        self.first_names.get("neutral", [])
                    )
                    last = random.choice(self.last_names)
                    full_names.append(f"{first} {last}")
                return {
                    "type": "full_name",
                    "suggested_values": full_names,
                    "category": "personal"
                }

        # Medication-related
        medication_keywords = ['medication', 'drug', 'medicine', 'rx', 'prescription', 'med']
        if any(keyword in col_lower for keyword in medication_keywords):
            return {
                "type": "medication",
                "suggested_values": self.get_random_medications(20),
                "category": "clinical"
            }

        # Lab test-related
        lab_keywords = ['lab', 'test', 'wbc', 'rbc', 'glucose', 'creatinine', 'hemoglobin']
        if any(keyword in col_lower for keyword in lab_keywords):
            return {
                "type": "lab_test",
                "suggested_values": self.get_random_lab_tests(20),
                "category": "clinical"
            }

        # Unit-related
        unit_keywords = ['unit', 'dose', 'dosage', 'amount', 'concentration']
        if any(keyword in col_lower for keyword in unit_keywords):
            return {
                "type": "unit",
                "suggested_values": self.get_random_units(),
                "category": "clinical"
            }

        # Diagnosis-related
        diagnosis_keywords = ['diagnosis', 'disease', 'condition', 'disorder', 'icd']
        if any(keyword in col_lower for keyword in diagnosis_keywords):
            return {
                "type": "diagnosis",
                "suggested_values": self.get_random_diagnoses(20),
                "category": "clinical"
            }

        # Procedure-related
        procedure_keywords = ['procedure', 'surgery', 'operation', 'treatment']
        if any(keyword in col_lower for keyword in procedure_keywords):
            return {
                "type": "procedure",
                "suggested_values": random.sample(self.procedures, min(20, len(self.procedures))),
                "category": "clinical"
            }

        # Body site-related
        site_keywords = ['site', 'location', 'anatomy', 'body_part']
        if any(keyword in col_lower for keyword in site_keywords):
            return {
                "type": "body_site",
                "suggested_values": random.sample(self.body_sites, min(10, len(self.body_sites))),
                "category": "clinical"
            }

        # Check specific clinical terms
        for term_type, values in self.clinical_terms.items():
            if term_type in col_lower:
                return {
                    "type": term_type,
                    "suggested_values": values,
                    "category": "clinical"
                }

        return None

    def enhance_metadata_with_clinical_context(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance metadata with clinical context for better synthetic data generation.

        Args:
            metadata: Original metadata dictionary

        Returns:
            Enhanced metadata with clinical suggestions
        """
        if "statistics" in metadata:
            for column_name, column_stats in metadata["statistics"].items():
                clinical_context = self.detect_clinical_column_type(column_name)
                if clinical_context:
                    column_stats["clinical_context"] = clinical_context
                    # Add to metadata for LLM to use
                    if column_stats.get("type") == "string" and clinical_context.get("suggested_values"):
                        column_stats["suggested_values"] = clinical_context["suggested_values"][:10]
                        column_stats["is_clinical"] = True

        return metadata

    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert reference library to a DataFrame for analysis.

        Returns:
            DataFrame with all reference data
        """
        data = {
            "medications": pd.DataFrame({"value": self.medications, "type": "medication"}),
            "lab_tests": pd.DataFrame({"value": self.lab_tests, "type": "lab_test"}),
            "diagnoses": pd.DataFrame({"value": self.diagnoses, "type": "diagnosis"}),
            "procedures": pd.DataFrame({"value": self.procedures, "type": "procedure"}),
            "body_sites": pd.DataFrame({"value": self.body_sites, "type": "body_site"})
        }

        # Combine all DataFrames
        combined_df = pd.concat(data.values(), ignore_index=True)
        return combined_df

    def save_to_json(self, file_path: Path):
        """Save reference library to JSON file."""
        data = {
            "medications": self.medications,
            "lab_tests": self.lab_tests,
            "units": self.units,
            "diagnoses": self.diagnoses,
            "procedures": self.procedures,
            "body_sites": self.body_sites,
            "clinical_terms": self.clinical_terms
        }
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

    def load_from_json(self, file_path: Path):
        """Load reference library from JSON file."""
        with open(file_path, 'r') as f:
            data = json.load(f)
        self.medications = data.get("medications", [])
        self.lab_tests = data.get("lab_tests", [])
        self.units = data.get("units", {})
        self.diagnoses = data.get("diagnoses", [])
        self.procedures = data.get("procedures", [])
        self.body_sites = data.get("body_sites", [])
        self.clinical_terms = data.get("clinical_terms", {})