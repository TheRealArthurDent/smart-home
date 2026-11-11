"""The dotenv_value filter reads a value from the secrets file exactly as Docker Compose does.

The role hashes MOSQUITTO_PASSWD for Mosquitto's password file, and Compose hands the same key to Telegraf. If the
two read the value differently, Telegraf can't log in. infrastructure's secrets role writes every value double-quoted
(its dotenv_quote filter: \\ -> \\\\, " -> \\", $ -> $$); hosts it hasn't reached yet still have unquoted values.
"""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "ansible" / "roles" / "smart_home" / "filter_plugins" / "dotenv.py"

# Classic ways to break a password: Compose interpolation, Jinja, quotes and backslashes, a # that may be taken for a
# comment, blanks at the ends, YAML-ish values and non-ASCII.
AWKWARD = [
    "tes$abc$bla{xyz}blub",
    "${HOME}$$x$",
    "$",
    "{{ 7 * 6 }}",
    "{% raw %}x{% endraw %}{# c #}",
    "a\"b'c`d",
    "back\\slash\\",
    "\\n\\t\\$x\\\"",
    " lead and trail ",
    "a #not-a-comment",
    "#start",
    "a=b=c",
    "$(id) `id`; rm -rf / && echo |",
    "äöü€ß",
    "0123",
    "true",
    "%s %(x)s %%",
    '"',
    "'",
    "\\",
    "'quoted'",
    '"quoted"',
]


def dotenv_quote(value):
    """What infrastructure's secrets role writes (roles/secrets/filter_plugins/dotenv.py there)."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "$$") + '"'


def load_filter():
    spec = importlib.util.spec_from_file_location("dotenv_filter", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FilterModule().filters()["dotenv_value"]


def compose_available():
    return bool(shutil.which("docker")) and subprocess.run(
        ["docker", "compose", "version"], capture_output=True, check=False).returncode == 0


def compose_reads(env_file, key, workdir):
    """MOSQUITTO_PASSWD as Compose gives it to Telegraf (docker-compose.yaml: MOSQUITTO_PASSWD=${MOSQUITTO_PASSWD})."""
    (workdir / "compose.yaml").write_text(json.dumps(
        {"services": {"telegraf": {"image": "alpine", "environment": [f"{key}=${{{key}}}"]}}}))
    result = subprocess.run(["docker", "compose", "--env-file", str(env_file), "config", "--format", "json"],
                            cwd=workdir, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)["services"]["telegraf"]["environment"][key].replace("$$", "$")


def env_content(value, other="OTHER=1"):
    return f"# secrets\n{other}\n\nMOSQUITTO_PASSWD={value}\nGRAFANA_PASSWORD=\"x\"\n"


@pytest.mark.parametrize("password", AWKWARD)
def test_reads_a_quoted_value_back(password):
    assert load_filter()(env_content(dotenv_quote(password)), "MOSQUITTO_PASSWD") == password


@pytest.mark.skipif(not compose_available(), reason="needs the docker compose CLI (no daemon)")
@pytest.mark.parametrize("password", AWKWARD)
def test_reads_what_compose_reads(tmp_path, password):
    env_file = tmp_path / ".env"
    env_file.write_text(env_content(dotenv_quote(password)))
    assert compose_reads(env_file, "MOSQUITTO_PASSWD", tmp_path) == password
    assert load_filter()(env_file.read_text(), "MOSQUITTO_PASSWD") == password


@pytest.mark.skipif(not compose_available(), reason="needs the docker compose CLI (no daemon)")
@pytest.mark.parametrize("line", ["plain-secret", "s3cr3t/&x", "  blanks  ", "'single $x quoted'", "a #comment"])
def test_reads_unquoted_and_single_quoted_values_like_compose(tmp_path, line):
    """Unquoted: the format before infrastructure's dotenv_quote, still on hosts it hasn't reached."""
    env_file = tmp_path / ".env"
    env_file.write_text(env_content(line))
    assert load_filter()(env_file.read_text(), "MOSQUITTO_PASSWD") == compose_reads(env_file, "MOSQUITTO_PASSWD",
                                                                                     tmp_path)


def test_refuses_an_unquoted_value_compose_would_interpolate():
    """Compose expands $abc there, so no hash the role computes would match what Telegraf gets."""
    with pytest.raises(Exception, match="MOSQUITTO_PASSWD.*\\$") as err:
        load_filter()(env_content("tes$abc$bla{xyz}blub"), "MOSQUITTO_PASSWD")
    assert "abc" not in str(err.value)


def test_missing_key_is_empty():
    assert load_filter()("OTHER=1\n", "MOSQUITTO_PASSWD") == ""


def test_does_not_take_a_key_that_only_ends_the_same():
    assert load_filter()('X_MOSQUITTO_PASSWD="no"\nMOSQUITTO_PASSWD="yes"\n', "MOSQUITTO_PASSWD") == "yes"


def test_windows_line_endings():
    assert load_filter()('MOSQUITTO_PASSWD="a b"\r\nOTHER=1\r\n', "MOSQUITTO_PASSWD") == "a b"


def test_refuses_an_unterminated_quote_without_showing_the_value():
    with pytest.raises(Exception, match="MOSQUITTO_PASSWD") as err:
        load_filter()('MOSQUITTO_PASSWD="SECRET-VALUE\n', "MOSQUITTO_PASSWD")
    assert "SECRET-VALUE" not in str(err.value)
