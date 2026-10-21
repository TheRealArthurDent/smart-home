"""The mosquitto_passwd filter keeps a password file entry while the password still matches it (#7).

The vectors come from mosquitto_passwd in the eclipse-mosquitto images, for the password `s3cr3t/&x`:
1.6 writes SHA512 ($6$, what setup.sh created), 2.x writes PBKDF2-SHA512 ($7$).
"""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "ansible" / "roles" / "smart_home" / "filter_plugins" / "mosquitto.py"

PASSWORD = "s3cr3t/&x"
FROM_1_6 = (
    "mosquitto:$6$+PC9WYmQcXY1fUOF$Y+Vw8P6bsFHZKBQUkPJUEqEcSeERu9IQcGuxcXKfz9e/dghy3+PasfQYY9xmgnDa9IqipduYTZwyC+Q3"
    "NWRhfA=="
)
FROM_2_0 = (
    "mosquitto:$7$101$eCt95EFAw2xWl8Bl$6vodyvLJu8ctww5pFPyJ9O7+D+dAUc5TGZh8rTJajvuuKec4gU4+hL097LNyAZxSR7CLqXHv0qO4U5"
    "eNQG6rvg=="
)


def load_filters():
    spec = importlib.util.spec_from_file_location("mosquitto_filter", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FilterModule().filters()


@pytest.fixture(name="passwd")
def fixture_passwd():
    return load_filters()["mosquitto_passwd"]


@pytest.mark.parametrize("existing", [FROM_1_6, FROM_2_0], ids=["sha512", "pbkdf2"])
def test_keeps_a_matching_entry(passwd, existing):
    assert passwd(PASSWORD, "mosquitto", existing + "\n") == existing


def test_keeps_a_matching_entry_among_other_users(passwd):
    assert passwd(PASSWORD, "mosquitto", "other:$7$101$abc$def\n" + FROM_2_0 + "\n") == FROM_2_0


@pytest.mark.parametrize("existing", ["", None, FROM_2_0.replace("mosquitto:", "other:")], ids=["empty", "none", "other user"])
def test_creates_a_pbkdf2_entry_without_one(passwd, existing):
    line = passwd(PASSWORD, "mosquitto", existing)
    assert re.fullmatch(r"mosquitto:\$7\$101\$[A-Za-z0-9+/]{16}\$[A-Za-z0-9+/]{86}==", line)
    # The new entry is kept on the next run, so a second run reports no change.
    assert passwd(PASSWORD, "mosquitto", line) == line


@pytest.mark.parametrize("existing", [FROM_1_6, FROM_2_0], ids=["sha512", "pbkdf2"])
def test_replaces_the_entry_of_a_changed_password(passwd, existing):
    line = passwd("changed", "mosquitto", existing)
    assert line != existing
    assert passwd("changed", "mosquitto", line) == line
    assert passwd(PASSWORD, "mosquitto", line) != line


def test_new_entries_get_their_own_salt(passwd):
    assert passwd(PASSWORD, "mosquitto") != passwd(PASSWORD, "mosquitto")


def test_replaces_a_garbled_entry(passwd):
    line = passwd(PASSWORD, "mosquitto", "mosquitto:not-a-hash\n")
    assert line.startswith("mosquitto:$7$")
