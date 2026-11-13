from xml.etree import ElementTree as ET

from paperflow.scheduler.autostart import NS, task_name, task_xml


def test_login_task_uses_current_user_windowless_unlimited_process(tmp_path):
    root = tmp_path / "Vault & space"
    pythonw = root / ".paperflow/.venv/Scripts/pythonw.exe"
    value = ET.fromstring(task_xml(root, pythonw, "S-1-5-21-test"))
    ns = {"t": NS}
    assert value.findtext("t:Principals/t:Principal/t:UserId", namespaces=ns) == "S-1-5-21-test"
    assert value.findtext("t:Principals/t:Principal/t:RunLevel", namespaces=ns) == "LeastPrivilege"
    assert value.findtext("t:Principals/t:Principal/t:LogonType", namespaces=ns) == "InteractiveToken"
    assert value.findtext("t:Actions/t:Exec/t:Command", namespaces=ns).endswith("pythonw.exe")
    arguments = value.findtext("t:Actions/t:Exec/t:Arguments", namespaces=ns)
    assert "service serve" in arguments and '"' in arguments and "--vault" in arguments
    assert value.findtext("t:Settings/t:ExecutionTimeLimit", namespaces=ns) == "PT0S"
    assert value.findtext("t:Settings/t:RestartOnFailure/t:Count", namespaces=ns) == "3"
    assert value.findtext("t:Settings/t:DisallowStartIfOnBatteries", namespaces=ns) == "false"
    assert task_name(root) == task_name(root / ".." / root.name)
