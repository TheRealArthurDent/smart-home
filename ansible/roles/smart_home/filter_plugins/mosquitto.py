"""mosquitto_passwd: a Mosquitto password file entry for a user, idempotent across runs (#7).

mosquitto_passwd salts every hash randomly, so writing a fresh entry on each run would always report a change.
The filter keeps the existing entry while it still matches the password and only hashes anew when the password
changed (or there is no entry yet). It reads both formats Mosquitto 2 accepts: $6$ (SHA512 of password and salt,
what mosquitto_passwd 1.6 wrote) and $7$ (PBKDF2-SHA512, mosquitto_passwd 2.x). New entries are $7$.
"""

import base64
import hashlib
import hmac
import os

PBKDF2_ITERATIONS = 101  # mosquitto_passwd's default
SALT_BYTES = 12


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def _matches(entry, password):
    parts = entry.split("$")
    try:
        if len(parts) == 4 and parts[1] == "6":
            salt, expected = base64.b64decode(parts[2]), base64.b64decode(parts[3])
            actual = hashlib.sha512(password.encode() + salt).digest()
        elif len(parts) == 5 and parts[1] == "7":
            iterations, salt, expected = int(parts[2]), base64.b64decode(parts[3]), base64.b64decode(parts[4])
            actual = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, iterations)
        else:
            return False
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


def mosquitto_passwd(password, username, existing=None):
    """Return the line `username:hash` for the password file, given its current content (or None)."""
    for line in (existing or "").splitlines():
        user, _, entry = line.strip().partition(":")
        if user == username and _matches(entry, str(password)):
            return line.strip()
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha512", str(password).encode(), salt, PBKDF2_ITERATIONS)
    return f"{username}:$7${PBKDF2_ITERATIONS}${_b64(salt)}${_b64(digest)}"


class FilterModule:  # pylint: disable=too-few-public-methods
    def filters(self):
        return {"mosquitto_passwd": mosquitto_passwd}
