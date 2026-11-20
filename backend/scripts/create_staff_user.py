"""Create a reviewer or administrator account (FR-068: staff use e-mail + password;
public registration only creates candidates).

Usage (from the backend folder):
    python -m scripts.create_staff_user --role reviewer --name "Rania" --email rania@example.com
The password is asked for and never shown or stored in plain text.
"""

import argparse
import getpass
import sys

from app.core.exceptions import EmailAlreadyExistsError
from app.core.security import hash_password
from app.domain.entities.user import User
from app.domain.enums.user_role import UserRole
from app.infrastructure.persistence.db.session import SessionLocal
from app.infrastructure.persistence.repositories.user_repository import UserRepository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=["reviewer", "administrator"], required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", help="omit to be asked (recommended)")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Password (min 8 characters): ")
    if len(password) < 8:
        print("Password must be at least 8 characters")
        return 1

    with SessionLocal() as db:
        try:
            user = UserRepository(db).create(User(
                user_id=None, name=args.name, email=args.email.lower(),
                password_hash=hash_password(password), role=UserRole(args.role)))
        except EmailAlreadyExistsError:
            print(f"{args.email} is already registered")
            return 1
    print(f"Created {args.role} {user.email} (user_id {user.user_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
