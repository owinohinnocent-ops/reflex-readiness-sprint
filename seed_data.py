"""
One-off script to seed reflex_db with mock users, rider profiles, and a
starter delivery so you can actually log in and test the real API.

Run this AFTER:
  1. database/session.py points at PostgreSQL (see session.py in this folder)
  2. uvicorn has started at least once (so Base.metadata.create_all()
     has created the tables in reflex_db)

Usage (from the project root, with your venv active):
    .venv\\Scripts\\python.exe seed_data.py
"""
from auth.passwords import hash_password
from database.session import SessionLocal
from models.delivery import Delivery, DeliveryStatus
from models.delivery_status_history import DeliveryStatusHistory
from models.rider import Rider
from models.user import User, UserRole

db = SessionLocal()


def get_or_create_user(name, phone, password, role):
    existing = db.query(User).filter(User.phone == phone).first()
    if existing:
        print(f"Skipping existing user {phone}")
        return existing
    user = User(
        name=name,
        phone=phone,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    db.flush()
    print(f"Created {role.value} '{name}' ({phone}) / password: {password}")
    return user


def get_or_create_rider(user, vehicle_type="motorbike", location=None):
    existing = db.query(Rider).filter(Rider.user_id == user.id).first()
    if existing:
        if location and not existing.location:
            existing.location = location
            db.flush()
        return existing
    rider = Rider(
        user_id=user.id,
        availability_status="AVAILABLE",
        vehicle_type=vehicle_type,
        location=location,
    )
    db.add(rider)
    db.flush()
    print(f"  -> rider profile #{rider.id} for {user.name}")
    return rider





# Retailer
mary = get_or_create_user("Mary Wanjiru", "0712000001", "retailer123", UserRole.RETAILER)

# Dispatcher
john = get_or_create_user("John Kimani", "0722000002", "dispatch123", UserRole.DISPATCHER)

# Riders (each needs a User row AND a linked Rider profile row)
brian_user = get_or_create_user("Brian Otieno", "0733000003", "rider123", UserRole.RIDER)
peter_user = get_or_create_user("Peter Mwangi", "0733000004", "rider123", UserRole.RIDER)
db.flush()

brian_rider = get_or_create_rider(brian_user, location="Kilimani")
peter_rider = get_or_create_rider(peter_user, location="CBD-Moi Avenue")

# A sample OPEN delivery so the dispatcher has something to assign immediately
existing_sample = (
    db.query(Delivery).filter(Delivery.customer_phone == "+254712345678").first()
)
if not existing_sample:
    sample = Delivery(
        item_description="5kg Maize Flour and Cooking Oil",
        pickup_address="Biashara Street, Stall 12, Meru",
        customer_name="Jane Wanjiku",
        customer_phone="+254712345678",
        delivery_address="Kileleshwa, App 4B, Meru",
        retailer_id=mary.id,
        status=DeliveryStatus.OPEN,
    )
    db.add(sample)
    db.flush()
    db.add(DeliveryStatusHistory(delivery_id=sample.id, status=DeliveryStatus.OPEN))
    print("Created a sample OPEN delivery for Mary")

db.commit()

print("\nSeed complete. Sign in at http://localhost:5173 with:")
print(f"  Retailer:   {mary.phone} / retailer123")
print(f"  Dispatcher: {john.phone} / dispatch123")
print(f"  Rider:      {brian_user.phone} / rider123  (rider profile #{brian_rider.id})")
print(f"  Rider:      {peter_user.phone} / rider123  (rider profile #{peter_rider.id})")
print(
    "\nWhen you log in as the dispatcher and assign the sample delivery, "
    f"use rider profile ID {brian_rider.id} or {peter_rider.id}."
)

db.close()
