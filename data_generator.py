"""
Generates deterministic fake data records for API pagination simulation.
Uses a seed-based approach so data is consistent across requests/pages.
"""
import hashlib
import random
from datetime import datetime, timedelta

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Christopher", "Karen", "Charles", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Dorothy", "Paul", "Kimberly", "Andrew", "Emily", "Joshua", "Donna",
    "Kenneth", "Michelle", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa",
    "Timothy", "Deborah"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts"
]

DEPARTMENTS = [
    "Engineering", "Marketing", "Sales", "Finance", "Human Resources",
    "Operations", "Legal", "Product", "Design", "Data Science",
    "Customer Support", "IT", "Research", "Quality Assurance", "Security"
]

CITIES = [
    "New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
    "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose",
    "Austin", "Jacksonville", "Fort Worth", "Columbus", "Charlotte",
    "Indianapolis", "San Francisco", "Seattle", "Denver", "Nashville"
]


def _seeded_random(record_id: int, seed: int = 42) -> random.Random:
    """Create a deterministic Random instance for a given record ID."""
    hash_input = f"{seed}-{record_id}".encode()
    hash_val = int(hashlib.md5(hash_input).hexdigest(), 16)
    rng = random.Random(hash_val)
    return rng


def generate_record(record_id: int, seed: int = 42) -> dict:
    """Generate a single deterministic fake record."""
    rng = _seeded_random(record_id, seed)

    first_name = rng.choice(FIRST_NAMES)
    last_name = rng.choice(LAST_NAMES)
    department = rng.choice(DEPARTMENTS)
    city = rng.choice(CITIES)

    base_date = datetime(2015, 1, 1)
    hire_date = base_date + timedelta(days=rng.randint(0, 3650))

    return {
        "id": record_id,
        "firstName": first_name,
        "lastName": last_name,
        "email": f"{first_name.lower()}.{last_name.lower()}@contoso.com",
        "department": department,
        "city": city,
        "salary": round(rng.uniform(45000, 185000), 2),
        "hireDate": hire_date.strftime("%Y-%m-%d"),
        "isActive": rng.random() > 0.15
    }


def generate_records(start: int, count: int, total: int, seed: int = 42) -> list[dict]:
    """
    Generate a slice of records.

    Args:
        start: Starting record index (0-based).
        count: Number of records to generate.
        total: Total number of records in the dataset.
        seed: Random seed for deterministic generation.

    Returns:
        List of record dicts.
    """
    end = min(start + count, total)
    return [generate_record(i + 1, seed) for i in range(start, end)]
