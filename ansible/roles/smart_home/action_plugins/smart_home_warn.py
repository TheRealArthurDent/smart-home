"""smart_home_warn: show a message as an Ansible [WARNING] and change nothing.

ansible.builtin.debug only prints its message in the task output, where it's easy to miss in a long run; a warning
also stands out in the play recap's neighbourhood and in CI logs.
"""

from ansible.plugins.action import ActionBase
from ansible.utils.display import Display

display = Display()


class ActionModule(ActionBase):
    _requires_connection = False
    _supports_check_mode = True
    _VALID_ARGS = frozenset(("msg",))

    def run(self, tmp=None, task_vars=None):
        result = super().run(tmp, task_vars)
        display.warning(str(self._task.args["msg"]))
        result.update(changed=False, msg=self._task.args["msg"])
        return result
