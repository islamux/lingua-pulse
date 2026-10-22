from linguapulse import notify


class FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


BUS_ENV = {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus", "PATH": "/usr/bin:/bin"}


def test_session_bus_address_prefers_the_dbus_variable():
    assert notify.session_bus_address(BUS_ENV) == "unix:path=/run/user/1000/bus"


def test_session_bus_address_falls_back_to_the_runtime_directory():
    env = {"XDG_RUNTIME_DIR": "/run/user/1000", "PATH": "/usr/bin:/bin"}
    assert notify.session_bus_address(env) == "unix:path=/run/user/1000/bus"


def test_session_bus_address_is_none_without_any_hint():
    assert notify.session_bus_address({"PATH": "/usr/bin:/bin"}) is None


def test_child_environment_always_carries_a_bus_address():
    env = {"XDG_RUNTIME_DIR": "/run/user/1000", "PATH": "/usr/bin:/bin"}
    assert notify.child_environment(env)["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/run/user/1000/bus"


def test_notify_send_path_is_none_when_it_is_not_installed():
    assert notify.notify_send_path({"PATH": "/nonexistent"}) is None


def test_send_without_notify_send_reports_an_actionable_error():
    result = notify.send("title", "body", env={"PATH": "/nonexistent", "XDG_RUNTIME_DIR": "/run/user/1000"})
    assert result.ok is False
    assert result.code == 127
    assert "notify-send" in result.message


def test_send_without_a_session_bus_explains_the_problem(monkeypatch):
    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/notify-send")
    result = notify.send("title", "body", env={"PATH": "/usr/bin:/bin"})
    assert result.ok is False
    assert "session bus" in result.message


def test_send_reports_the_error_of_a_failing_notify_send(monkeypatch):
    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/notify-send")
    monkeypatch.setattr(
        notify.subprocess,
        "run",
        lambda *args, **kwargs: FakeCompleted(1, "", "Could not connect: No such file or directory"),
    )
    result = notify.send("title", "body", env=BUS_ENV)
    assert result.ok is False
    assert result.code == 1
    assert "Could not connect" in result.message


def test_send_reports_success(monkeypatch):
    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/notify-send")
    monkeypatch.setattr(notify.subprocess, "run", lambda *args, **kwargs: FakeCompleted(0))
    result = notify.send("title", "body", env=BUS_ENV)
    assert result.ok is True
    assert result.code == 0


def test_send_reports_a_timeout_as_a_failure(monkeypatch):
    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/notify-send")

    def fake_run(args, **kwargs):
        raise notify.subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    result = notify.send("title", "body", env=BUS_ENV)
    assert result.ok is False
    assert result.code == 124
    assert "timed out" in result.message


def test_the_bus_address_is_passed_to_the_child_process(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["env"] = kwargs.get("env")
        return FakeCompleted(0)

    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/notify-send")
    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    notify.send("title", "body", env={"XDG_RUNTIME_DIR": "/run/user/1000", "PATH": "/usr/bin:/bin"})
    assert captured["env"]["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/run/user/1000/bus"


def test_the_notification_daemon_is_read_from_the_bus(monkeypatch):
    listing = (
        "NAME                           PID PROCESS  USER  CONNECTION  UNIT\n"
        "org.freedesktop.Notifications  3576 dunst    user  :1.20       app-org.freedesktop.Notifications.service\n"
    )
    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/busctl")
    monkeypatch.setattr(notify.subprocess, "run", lambda *args, **kwargs: FakeCompleted(0, listing))
    assert notify.notification_daemon(BUS_ENV) == "dunst"


def test_no_notification_daemon_is_reported_as_none(monkeypatch):
    monkeypatch.setattr(notify.shutil, "which", lambda name, path=None: "/usr/bin/busctl")
    monkeypatch.setattr(notify.subprocess, "run", lambda *args, **kwargs: FakeCompleted(0, "NAME PID PROCESS\n"))
    assert notify.notification_daemon(BUS_ENV) is None
