"""
Development seed script for Reflex backend.
Creates default test users (Retailer, Dispatcher, Rider) in the SQLite database if not already present.
"""
from sqlalchemy import select
from database import Base, SessionLocal, engine
from models.rider import Rider
from models.user import User, UserRole


def seed_data():
    # Ensure database tables exist
    Base.metadata.create_all(bind=engine)

    # Create a SessionLocal database session
    db = SessionLocal()

    try:
        seed_users = [
            {
                "name": "Test Retailer",
                "phone": "0700000000",
                "password_hash": "development-retailer-password-hash",
                "role": UserRole.RETAILER,
            },
            {
                "name": "Test Dispatcher",
                "phone": "0700000001",
                "password_hash": "development-dispatcher-password-hash",
                "role": UserRole.DISPATCHER,
            },
            {
                "name": "Test Rider",
                "phone": "0700000002",
                "password_hash": "development-rider-password-hash",
                "role": UserRole.RIDER,
            },
        ]

        results = {}
        for user_info in seed_users:
            stmt = select(User).where(User.phone == user_info["phone"])
            existing_user = db.scalars(stmt).first()

            if existing_user:
                print(f"User already exists: ID={existing_user.id}, Name='{existing_user.name}', Role='{existing_user.role.value}', Phone='{existing_user.phone}'")
                results[existing_user.role.value] = existing_user.id
            else:
                new_user = User(
                    name=user_info["name"],
                    phone=user_info["phone"],
                    role=user_info["role"],
                    password_hash=user_info["password_hash"],
                )
                db.add(new_user)
                db.commit()
                db.refresh(new_user)
                if new_user.role == UserRole.RIDER:
                    db.add(Rider(
                        user_id=new_user.id,
                        availability_status="AVAILABLE",
                        vehicle_type="MOTORCYCLE",
                        plate_number="KMCA 123X",
                    ))
                    db.commit()
                print(f"Created user: ID={new_user.id}, Name='{new_user.name}', Role='{new_user.role.value}', Phone='{new_user.phone}'")
                results[new_user.role.value] = new_user.id

        print("\n" + "=" * 55)
        print(" SEEDED TEST USERS FOR SWAGGER TESTING")
        print("=" * 55)
        for role, uid in results.items():
            print(f" {role:<12}: ID = {uid}")
        print("=" * 55 + "\n")

        return results

    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
