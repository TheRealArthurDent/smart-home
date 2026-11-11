"""dotenv_value: a value from the secrets file, read as Docker Compose reads it.

The role hashes MOSQUITTO_PASSWD into Mosquitto's password file, and Compose hands the same key to Telegraf, so both
must see the same password. infrastructure's secrets role writes every value double-quoted, escaping \\, " and $ (its
dotenv_quote filter), because Compose expands $VAR in unquoted values: tes$abc$bla{xyz}blub reached Telegraf as
tes{xyz}blub. Hosts it hasn't reached yet still have unquoted values.

Read like Compose:
- "double-quoted": \\\\ -> \\, \\" -> ", $$ -> $. Any other $ would be interpolated and any other escape changes the
  value, which dotenv_quote never writes, so they are refused.
- 'single-quoted': literal.
- unquoted: up to a blank followed by #, without the blanks around it. A $ in it would be interpolated: refused.

Errors name the key, never the value.
"""

import re

from ansible.errors import AnsibleFilterError


def _double_quoted(body, key):
    value, index = [], 0
    while index < len(body):
        char = body[index]
        pair = body[index:index + 2]
        if pair in ("\\\\", '\\"', "$$"):
            value.append(pair[1])
            index += 2
        elif char in ('\\', '$', '"'):
            raise AnsibleFilterError(
                f"dotenv_value: {key} has an unescaped {char!r}; infrastructure's secrets role (dotenv_quote) "
                "never writes that")
        else:
            value.append(char)
            index += 1
    return "".join(value)


def dotenv_value(content, key):
    """Return key's value from .env content, or '' when the key is missing."""
    for line in str(content).splitlines():
        line = line.rstrip("\r")
        if not line.startswith(f"{key}="):
            continue
        raw = line[len(key) + 1:]
        if raw[:1] in ('"', "'"):
            quote = raw[0]
            end = raw.rfind(quote)
            if end == 0 or raw[end + 1:].strip():
                raise AnsibleFilterError(f"dotenv_value: the quoted value of {key} isn't terminated")
            body = raw[1:end]
            return _double_quoted(body, key) if quote == '"' else body
        value = re.split(r"\s#", raw, maxsplit=1)[0].strip()
        if "$" in value:
            raise AnsibleFilterError(
                f"dotenv_value: {key} is unquoted and holds a $, which Compose would expand. Run infrastructure's "
                "bootstrap.yaml (secrets role) on this host, it quotes the values.")
        return value
    return ""


class FilterModule:  # pylint: disable=too-few-public-methods
    def filters(self):
        return {"dotenv_value": dotenv_value}
