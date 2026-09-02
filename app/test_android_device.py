import subprocess

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import android_device as api
from app.services.android_device_service import (
    AndroidDeviceError,
    AndroidDeviceService,
    AndroidDeviceState,
    AndroidDeviceStatus,
    MirrorLaunchResult,
    SleepResult,
)
from pathlib import Path


ADB = r"C:\platform-tools\adb.exe"
SCRCPY = r"C:\scrcpy\scrcpy.exe"


def completed(stdout="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout, "")


def service_for(output, *, adb=ADB, scrcpy=SCRCPY, launcher=None, display_awake=True):
    commands = []

    def finder(name):
        return adb if name == "adb" else scrcpy

    def runner(command, **_kwargs):
        commands.append(command)
        if command[-3:] == ["shell", "getprop", "ro.product.manufacturer"]:
            return completed("samsung\n")
        if command[-3:] == ["shell", "getprop", "ro.product.model"]:
            return completed("SM-G781U1\n")
        if command[-3:] == ["shell", "dumpsys", "power"]:
            return completed("mWakefulness=Awake\n" if display_awake else "mWakefulness=Asleep\n")
        if "keyevent" in command:
            return completed()
        if "pm" in command and "path" in command:
            return completed("package:/data/app/com.instagram.android/base.apk\n")
        return completed(output)

    service = AndroidDeviceService(
        executable_finder=finder,
        command_runner=runner,
        process_launcher=launcher or (lambda *_args, **_kwargs: FakeProcess()),
    )
    service.commands = commands
    return service


class FakeProcess:
    pid = 123

    def __init__(self):
        self.returncode = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("scrcpy", timeout)
        return self.returncode


def test_adb_missing():
    status = AndroidDeviceService(executable_finder=lambda _name: None).status()
    assert status.state == AndroidDeviceState.ADB_NOT_AVAILABLE
    assert status.adb_available is False


def test_scrcpy_discovery_falls_back_to_official_winget_package(monkeypatch, tmp_path):
    executable = tmp_path / "Microsoft" / "WinGet" / "Packages" / "Genymobile.scrcpy_Microsoft.Winget.Source_x" / "scrcpy-win64-v4.1" / "scrcpy.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("app.services.android_device_service.shutil.which", lambda _name: None)
    assert AndroidDeviceService._discover_executable("scrcpy") == str(executable)


def test_adb_available_but_malformed_output():
    status = service_for("unexpected output").status()
    assert status.state == AndroidDeviceState.ADB_ERROR


@pytest.mark.parametrize(
    ("output", "state"),
    [
        ("List of devices attached\n", AndroidDeviceState.NOT_CONNECTED),
        ("List of devices attached\nSERIAL unauthorized\n", AndroidDeviceState.UNAUTHORIZED),
        ("List of devices attached\nSERIAL offline\n", AndroidDeviceState.OFFLINE),
        ("List of devices attached\nONE device\nTWO device\n", AndroidDeviceState.MULTIPLE_DEVICES),
    ],
)
def test_device_states(output, state):
    assert service_for(output).status().state == state


def test_one_authorized_device_is_selected_with_metadata_and_ignores_unauthorized_entries():
    status = service_for(
        "List of devices attached\nRFCN90JL1LP device product:r8quex model:SM_G781U1\nOTHER unauthorized\n"
    ).status()
    assert status.state == AndroidDeviceState.CONNECTED
    assert status.serial == "RFCN90JL1LP"
    assert status.manufacturer == "samsung"
    assert status.model == "SM-G781U1"
    assert status.mirror_available is True


def test_scrcpy_missing_does_not_change_connected_device_state():
    status = service_for("List of devices attached\nSERIAL device\n", scrcpy=None).status()
    assert status.state == AndroidDeviceState.CONNECTED
    assert status.scrcpy_available is False
    assert status.mirror_available is False
    assert status.message == "scrcpy unavailable"


def test_successful_mirror_uses_argument_array_and_prevents_duplicate_then_reopens():
    launches = []

    def launcher(command, **kwargs):
        process = FakeProcess()
        launches.append((command, kwargs, process))
        return process

    service = service_for("List of devices attached\nSERIAL device\n", launcher=launcher)
    assert service.launch_mirror().result == "STARTED"
    assert service.status().mirror_running is True
    assert launches[0][0] == [SCRCPY, "--serial", "SERIAL"]
    assert launches[0][1]["shell"] is False
    assert service.launch_mirror().result == "ALREADY_OPEN"
    assert len(launches) == 1
    launches[0][2].returncode = 0
    assert service.status().mirror_running is False
    assert service.launch_mirror().result == "STARTED"
    assert len(launches) == 2


def test_sleeping_display_is_woken_before_mirror_launch():
    service = service_for("List of devices attached\nSERIAL device\n", display_awake=False)
    service.launch_mirror()
    dumpsys_index = next(index for index, command in enumerate(service.commands) if command[-3:] == ["shell", "dumpsys", "power"])
    wake_index = next(index for index, command in enumerate(service.commands) if command[-2:] == ["keyevent", "KEYCODE_WAKEUP"])
    assert dumpsys_index < wake_index


def test_dozing_samsung_display_is_treated_as_asleep():
    service = service_for("List of devices attached\nSERIAL device\n")
    assert service._parse_display_awake("mWakefulness=Dozing\n") is False


def test_awake_display_is_not_power_toggled_before_mirror_launch():
    service = service_for("List of devices attached\nSERIAL device\n", display_awake=True)
    service.launch_mirror()
    assert not any(command[-2:] == ["keyevent", "KEYCODE_WAKEUP"] for command in service.commands)


def test_sleep_turns_display_off_and_terminates_only_tracked_mirror():
    processes = []
    unrelated = FakeProcess()

    def launcher(*_args, **_kwargs):
        process = FakeProcess(); processes.append(process); return process

    service = service_for("List of devices attached\nSERIAL device\n", launcher=launcher)
    service.launch_mirror()
    result = service.sleep()
    assert result == SleepResult(result="SLEPT", serial="SERIAL", mirror_closed=True)
    assert any(command[-2:] == ["keyevent", "KEYCODE_SLEEP"] for command in service.commands)
    assert processes[0].terminated is True
    assert unrelated.terminated is False
    assert service.status().state == AndroidDeviceState.CONNECTED
    assert service.status().mirror_running is False


def test_sleep_succeeds_when_tracked_mirror_already_exited():
    process = FakeProcess()
    service = service_for("List of devices attached\nSERIAL device\n", launcher=lambda *_args, **_kwargs: process)
    service.launch_mirror(); process.returncode = 0
    result = service.sleep()
    assert result.mirror_closed is False
    assert any(command[-2:] == ["keyevent", "KEYCODE_SLEEP"] for command in service.commands)


def test_failed_mirror_launch_is_reported():
    def fail(*_args, **_kwargs):
        raise OSError("launch failed")

    service = service_for("List of devices attached\nSERIAL device\n", launcher=fail)
    with pytest.raises(AndroidDeviceError, match="Unable to start scrcpy"):
        service.launch_mirror()


def test_instagram_handoff_pushes_scans_exact_file_reuses_mirror_and_opens_app(tmp_path):
    image = tmp_path / "prepared.png"
    image.write_bytes(b"png")
    service = service_for("List of devices attached\nSERIAL device\n")

    first = service.handoff_instagram_image(image, remote_filename="handoff.png")
    second = service.handoff_instagram_image(image, remote_filename="handoff.png")

    remote = "/sdcard/Pictures/Creator-OS/handoff.png"
    assert first.android_path == remote
    assert first.mirror_result == "STARTED"
    assert second.mirror_result == "ALREADY_OPEN"
    assert [ADB, "-s", "SERIAL", "push", str(image), remote] in service.commands
    assert [ADB, "-s", "SERIAL", "shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{remote}"] in service.commands
    assert [ADB, "-s", "SERIAL", "shell", "monkey", "-p", "com.instagram.android", "-c", "android.intent.category.LAUNCHER", "1"] in service.commands


def test_instagram_handoff_requires_installed_package(tmp_path):
    image = tmp_path / "prepared.png"
    image.write_bytes(b"png")
    service = service_for("List of devices attached\nSERIAL device\n")
    original_runner = service._run_command

    def missing_package(command, **kwargs):
        if "pm" in command and "path" in command:
            return completed("")
        return original_runner(command, **kwargs)

    service._run_command = missing_package
    with pytest.raises(AndroidDeviceError, match="Instagram is not installed"):
        service.handoff_instagram_image(image, remote_filename="handoff.png")


class FakeApiService:
    def __init__(self, status, mirror=None, sleep=None):
        self.current_status = status
        self.mirror = mirror
        self.sleep_result = sleep

    def status(self):
        return self.current_status

    def launch_mirror(self):
        if isinstance(self.mirror, Exception):
            raise self.mirror
        return self.mirror

    def sleep(self):
        if isinstance(self.sleep_result, Exception):
            raise self.sleep_result
        return self.sleep_result


def client(monkeypatch, service):
    monkeypatch.setattr(api, "android_device_service", service)
    application = FastAPI()
    application.include_router(api.router)
    return TestClient(application)


def connected_status():
    return AndroidDeviceStatus(
        state=AndroidDeviceState.CONNECTED, adb_available=True,
        scrcpy_available=True, mirror_available=True, serial="SERIAL",
        model="Model", manufacturer="Maker",
    )


def test_status_endpoint_returns_structured_state(monkeypatch):
    response = client(monkeypatch, FakeApiService(connected_status())).get("/api/v1/device/android/status")
    assert response.status_code == 200
    assert response.json() == {
        "available": True, "state": "CONNECTED", "serial": "SERIAL",
        "model": "Model", "manufacturer": "Maker", "adb_available": True,
        "scrcpy_available": True, "mirror_available": True, "message": None,
        "mirror_running": False,
    }


def test_mirror_endpoint_rejects_invalid_state(monkeypatch):
    error = AndroidDeviceError(AndroidDeviceState.NOT_CONNECTED, "Phone not connected")
    response = client(monkeypatch, FakeApiService(connected_status(), error)).post("/api/v1/device/android/mirror")
    assert response.status_code == 409
    assert response.json()["detail"] == "Phone not connected"


def test_mirror_endpoint_accepts_connected_device(monkeypatch):
    mirror = MirrorLaunchResult(result="STARTED", serial="SERIAL")
    response = client(monkeypatch, FakeApiService(connected_status(), mirror)).post("/api/v1/device/android/mirror")
    assert response.status_code == 202
    assert response.json() == {"result": "STARTED", "serial": "SERIAL"}


def test_sleep_endpoint_turns_off_phone_and_closes_mirror(monkeypatch):
    result = SleepResult(result="SLEPT", serial="SERIAL", mirror_closed=True)
    response = client(monkeypatch, FakeApiService(connected_status(), sleep=result)).post("/api/v1/device/android/sleep")
    assert response.status_code == 200
    assert response.json() == {"result": "SLEPT", "serial": "SERIAL", "mirror_closed": True}
