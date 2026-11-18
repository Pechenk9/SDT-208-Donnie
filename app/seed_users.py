from getpass import getpass

from sqlalchemy import func, select

from app.config import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


INITIAL_ROLES = (
    UserRole.OWNER,
    UserRole.CUSTOMER,
    UserRole.CUSTOMER,
)


def seed_initial_users() -> None:
    with SessionLocal() as session:
        results = []
        seen_emails = set()

        try:
            for role in INITIAL_ROLES:
                label = role.value.title()
                email = input(f"{label} email: ").strip().lower()
                if not email:
                    raise ValueError(f"{label} email cannot be empty")
                if email in seen_emails:
                    raise ValueError("Each initial account needs a unique email")
                seen_emails.add(email)

                user = session.scalar(
                    select(User).where(func.lower(User.email) == email)
                )
                if user is not None:
                    user.role = role
                    results.append((email, "already existed"))
                    continue

                first_name = input(f"{label} first name: ").strip()
                last_name = input(f"{label} last name: ").strip()
                if not first_name or not last_name:
                    raise ValueError("First and last names cannot be empty")

                password = getpass(f"{label} password: ")
                confirmation = getpass(f"Confirm {label.lower()} password: ")
                if not password or password != confirmation:
                    raise ValueError("Passwords must be non-empty and match")

                session.add(
                    User(
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        password_hash=hash_password(password),
                        role=role,
                    )
                )
                session.flush()
                results.append((email, "created"))

            session.commit()
        except Exception:
            session.rollback()
            raise

    for email, status in results:
        print(f"{email}: {status}")


if __name__ == "__main__":
    seed_initial_users()
