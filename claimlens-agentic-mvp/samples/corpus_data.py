"""
Value pools used by generate_corpus.py.

Health-claim line items use REAL ICD-10-CM diagnosis codes and REAL
CPT/HCPCS procedure codes (these are public coding standards, not
proprietary data) so the generated documents at least look and code
like genuine medical claims, even though the patients/amounts are
fabricated. This is the cheap, free way to ground synthetic documents
in something real without needing PHI-restricted data.
"""

import random

FIRST_NAMES = [
    "Priya", "Arjun", "Sanya", "Rohan", "Ananya", "Vikram", "Meera", "Karan",
    "Divya", "Aditya", "Neha", "Rahul", "Ishita", "Siddharth", "Pooja",
    "Manish", "Kavya", "Aman", "Riya", "Nikhil",
]
LAST_NAMES = [
    "Nair", "Mehta", "Kapoor", "Sharma", "Reddy", "Iyer", "Gupta", "Joshi",
    "Verma", "Pillai", "Rao", "Singh", "Bose", "Menon", "Chatterjee",
]
CITIES = ["Bengaluru", "Pune", "Mumbai", "Hyderabad", "Chennai", "Delhi", "Kolkata", "Ahmedabad"]
STREETS = ["MG Road", "Lakeview Apartments", "Park Street", "Brigade Road", "Koramangala 5th Block",
           "Whitefield Main Road", "Anna Salai", "FC Road"]

VEHICLE_MAKES_MODELS = [
    ("Honda", "City"), ("Maruti Suzuki", "Swift"), ("Hyundai", "Creta"),
    ("Toyota", "Innova"), ("Tata", "Nexon"), ("Mahindra", "XUV700"),
    ("Kia", "Seltos"), ("Volkswagen", "Virtus"),
]

CAUSES_OF_LOSS_PROPERTY = [
    "Water damage from burst pipe", "Fire damage in kitchen", "Storm damage to roof",
    "Theft and forced entry", "Falling tree on structure", "Electrical fire in wiring",
]

ROOMS = ["Kitchen", "Living Room", "Master Bedroom", "Hallway", "Garage", "Bathroom", "Study Room"]

CONTENTS_ITEMS = [
    ("Sofa set", 35000), ("Refrigerator", 28000), ("Television", 42000),
    ("Dining table", 18000), ("Wardrobe", 22000), ("Washing machine", 26000),
    ("Microwave oven", 8000), ("Bed frame", 15000), ("Mattress", 12000),
    ("Bookshelf", 6000), ("Office chair", 7000), ("Curtains (set)", 4000),
    ("Carpet", 9000), ("Air conditioner", 32000), ("Water heater", 11000),
    ("Kitchen cabinets", 24000), ("Dinnerware set", 3500), ("Lamp", 2200),
    ("Coffee table", 5000), ("Bicycle", 9500),
]

AUTO_PARTS_LABOR = [
    ("Front bumper replacement", 8500), ("Headlight assembly (RH)", 4200),
    ("Rear quarter panel repair", 11000), ("Windshield replacement", 6500),
    ("Door panel respray", 5200), ("Radiator replacement", 7800),
    ("Wheel alignment", 1200), ("Suspension strut (front)", 9000),
    ("Bonnet (hood) repair", 6000), ("Bumper sensor recalibration", 3000),
    ("Paint and clear coat (panel)", 4500), ("Labor - body shop (per hr)", 1500),
    ("Airbag module replacement", 18000), ("Side mirror assembly", 2800),
    ("Tail light assembly", 3200),
]

# Real ICD-10-CM diagnosis codes (public coding standard)
ICD10_CODES = [
    ("K35.80", "Unspecified acute appendicitis"),
    ("S72.001A", "Fracture of neck of right femur, initial encounter"),
    ("J18.9", "Pneumonia, unspecified organism"),
    ("I21.9", "Acute myocardial infarction, unspecified"),
    ("N39.0", "Urinary tract infection, site not specified"),
    ("E11.9", "Type 2 diabetes mellitus without complications"),
    ("S52.501A", "Fracture of lower end of right radius, initial encounter"),
    ("M54.50", "Low back pain, unspecified"),
]

# Real CPT/HCPCS procedure codes (public coding standard)
CPT_CODES = [
    ("99284", "Emergency dept visit, high severity", 4500),
    ("47562", "Laparoscopic cholecystectomy", 65000),
    ("71046", "Chest X-ray, 2 views", 1200),
    ("80053", "Comprehensive metabolic panel", 950),
    ("85025", "Complete blood count (CBC) with differential", 600),
    ("36415", "Collection of venous blood by venipuncture", 150),
    ("99291", "Critical care, first 30-74 minutes", 8500),
    ("73610", "X-ray, ankle, complete", 1100),
    ("99213", "Office/outpatient visit, established patient", 800),
    ("J7050", "Infusion, normal saline solution, 250cc", 350),
]

HOSPITALS = ["Fortis Hospital", "Apollo Hospitals", "Manipal Hospital", "Max Healthcare",
             "Narayana Health", "Columbia Asia Hospital"]

CONTRACTORS = ["R. Kulkarni & Associates", "Shree Constructions", "Reliable Restoration Co.",
               "Metro Builders", "Skyline Renovation Services"]

INSPECTORS = ["R. Kulkarni", "A. Deshmukh", "S. Iyengar", "P. Bhatt", "M. Rao"]
OFFICERS = ["Inspector K. Patil", "Sub-Inspector R. Nambiar", "Constable V. Shetty"]
ADJUSTERS = ["Adjuster S. Krishnan", "Adjuster N. Fernandes", "Adjuster T. Sengupta"]


def random_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def random_address(rng: random.Random) -> str:
    return f"{rng.randint(1, 99)} {rng.choice(STREETS)}, {rng.choice(CITIES)}"


def random_policy_number(rng: random.Random, prefix: str) -> str:
    return f"{prefix}-2026-{rng.randint(10000, 99999)}"


def random_vin(rng: random.Random) -> str:
    chars = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    return "".join(rng.choice(chars) for _ in range(17))


def random_date(rng: random.Random, year=2026, month_range=(1, 6)) -> str:
    month = rng.randint(*month_range)
    day = rng.randint(1, 28)
    return f"{year}-{month:02d}-{day:02d}"
