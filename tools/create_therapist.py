"""Crea una cuenta de terapeuta o cambia su contraseña (se ejecuta en el servidor).

No hay registro desde la web a propósito: en una red compartida, cualquiera podría crearse
una cuenta. Uso:
  python tools/create_therapist.py                     # pregunta los datos
  python tools/create_therapist.py --username ana --name "Ana Pérez"
  python tools/create_therapist.py --username ana --reset-password
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth  # noqa: E402
from database import Database  # noqa: E402


def ask_password() -> str:
    while True:
        password = getpass.getpass(f"Contraseña (mínimo {auth.MIN_PASSWORD_LENGTH} caracteres): ")
        if len(password) < auth.MIN_PASSWORD_LENGTH:
            print("Demasiado corta.")
            continue
        if getpass.getpass("Repítela: ") != password:
            print("No coinciden.")
            continue
        return password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--username")
    parser.add_argument("--name")
    parser.add_argument("--reset-password", action="store_true", help="cambia la contraseña (y cierra sus sesiones)")
    args = parser.parse_args()

    db = Database()
    db.initialize()
    username = (args.username or input("Usuario: ")).strip().lower()
    if not username or not username.replace(".", "").replace("_", "").replace("-", "").isalnum():
        print("Usuario no válido (letras, números, punto, guion o guion bajo).")
        return 1

    existing = db.get_therapist_by_username(username)
    if args.reset_password:
        if not existing:
            print(f"No existe el usuario '{username}'.")
            return 1
        db.set_therapist_password(username, auth.hash_password(ask_password()))
        print(f"Contraseña de '{username}' cambiada. Sus sesiones abiertas se han cerrado.")
        return 0

    if existing:
        print(f"El usuario '{username}' ya existe. Para cambiar su contraseña usa --reset-password.")
        return 1
    name = (args.name or input("Nombre completo: ")).strip() or username
    db.create_therapist(username, name, auth.hash_password(ask_password()))
    print(f"Cuenta creada: {name} ({username}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
