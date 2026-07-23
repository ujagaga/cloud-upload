from werkzeug.security import generate_password_hash, check_password_hash
import settings
import store


def verify_password(password: str) -> bool:
    """Master password always works. Otherwise check the stored hash, or fall
    back to the initial password until one has been set through the UI."""
    if not password:
        return False

    if password == settings.MASTER_PASSWORD:
        return True

    stored = store.get("password_hash")
    if stored:
        return check_password_hash(stored, password)

    return password == settings.INITIAL_PASSWORD


def set_password(new_password: str):
    """Persist a new password hash locally."""
    store.set("password_hash", generate_password_hash(new_password))
