"""Local, narrowly scoped Android device discovery and mirroring."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
import os
from pathlib import Path
import shutil
import subprocess
from threading import Lock
from typing import Callable, Sequence


logger = logging.getLogger("creator-os-android-device")


class AndroidDeviceState(str, Enum):
    CONNECTED = "CONNECTED"
    UNAUTHORIZED = "UNAUTHORIZED"
    OFFLINE = "OFFLINE"
    MULTIPLE_DEVICES = "MULTIPLE_DEVICES"
    NOT_CONNECTED = "NOT_CONNECTED"
    ADB_NOT_AVAILABLE = "ADB_NOT_AVAILABLE"
    ADB_TIMEOUT = "ADB_TIMEOUT"
    ADB_ERROR = "ADB_ERROR"


@dataclass(frozen=True)
class AndroidDeviceStatus:
    state: AndroidDeviceState
    adb_available: bool
    scrcpy_available: bool
    mirror_available: bool
    mirror_running: bool = False
    serial: str | None = None
    model: str | None = None
    manufacturer: str | None = None
    message: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "available": self.state == AndroidDeviceState.CONNECTED,
            "state": self.state.value,
            "serial": self.serial,
            "model": self.model,
            "manufacturer": self.manufacturer,
            "adb_available": self.adb_available,
            "scrcpy_available": self.scrcpy_available,
            "mirror_available": self.mirror_available,
            "mirror_running": self.mirror_running,
            "message": self.message,
        }


@dataclass(frozen=True)
class MirrorLaunchResult:
    result: str
    serial: str

    def to_payload(self) -> dict[str, str]:
        return {"result": self.result, "serial": self.serial}


@dataclass(frozen=True)
class SleepResult:
    result: str
    serial: str
    mirror_closed: bool

    def to_payload(self) -> dict[str, object]:
        return {"result": self.result, "serial": self.serial, "mirror_closed": self.mirror_closed}


@dataclass(frozen=True)
class InstagramHandoffDeviceResult:
    serial: str
    android_path: str
    mirror_result: str


class AndroidDeviceError(RuntimeError):
    def __init__(self, state: AndroidDeviceState, message: str):
        super().__init__(message)
        self.state = state


class AndroidDeviceService:
    """Owns safe ADB discovery and the scrcpy processes launched by Creator-OS."""

    ADB_TIMEOUT_SECONDS = 5
    PROPERTY_TIMEOUT_SECONDS = 3
    PROCESS_STOP_TIMEOUT_SECONDS = 5
    FILE_TRANSFER_TIMEOUT_SECONDS = 60
    INSTAGRAM_PACKAGE = "com.instagram.android"
    INSTAGRAM_HANDOFF_DIR = "/sdcard/Pictures/Creator-OS"

    def __init__(
        self,
        *,
        executable_finder: Callable[[str], str | None] | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        process_launcher: Callable[..., subprocess.Popen] = subprocess.Popen,
    ) -> None:
        self._find_executable = executable_finder or self._discover_executable
        self._run_command = command_runner
        self._launch_process = process_launcher
        self._mirror_processes: dict[str, subprocess.Popen] = {}
        self._process_lock = Lock()

    def status(self) -> AndroidDeviceStatus:
        adb_path = self._find_executable("adb")
        scrcpy_path = self._find_executable("scrcpy")
        if not adb_path:
            logger.warning("event=android_adb_unavailable")
            return self._status(AndroidDeviceState.ADB_NOT_AVAILABLE, None, scrcpy_path, mirror_running=self._any_mirror_running(), message="ADB unavailable")

        logger.debug("event=android_adb_detected path=%s", adb_path)
        if scrcpy_path:
            logger.debug("event=android_scrcpy_detected path=%s", scrcpy_path)
        else:
            logger.warning("event=android_scrcpy_unavailable")

        try:
            result = self._run(
                [adb_path, "devices", "-l"], timeout=self.ADB_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired:
            logger.warning("event=android_adb_timeout")
            return self._status(AndroidDeviceState.ADB_TIMEOUT, adb_path, scrcpy_path, mirror_running=self._any_mirror_running(), message="ADB device check timed out")
        except (OSError, subprocess.SubprocessError) as error:
            logger.warning("event=android_adb_failed error=%s", error)
            return self._status(AndroidDeviceState.ADB_ERROR, adb_path, scrcpy_path, mirror_running=self._any_mirror_running(), message="ADB device check failed")

        if result.returncode != 0:
            logger.warning("event=android_adb_failed returncode=%s", result.returncode)
            return self._status(AndroidDeviceState.ADB_ERROR, adb_path, scrcpy_path, mirror_running=self._any_mirror_running(), message="ADB device check failed")

        try:
            entries = self._parse_devices(result.stdout)
        except ValueError:
            logger.warning("event=android_adb_malformed_output")
            return self._status(AndroidDeviceState.ADB_ERROR, adb_path, scrcpy_path, mirror_running=self._any_mirror_running(), message="ADB returned unexpected device output")

        authorized = [entry for entry in entries if entry[1] == "device"]
        if len(authorized) > 1:
            logger.info("event=android_multiple_devices count=%s", len(authorized))
            return self._status(AndroidDeviceState.MULTIPLE_DEVICES, adb_path, scrcpy_path, mirror_running=self._any_mirror_running(), message="Multiple authorized Android devices connected")
        if len(authorized) == 1:
            serial = authorized[0][0]
            manufacturer = self._property(adb_path, serial, "ro.product.manufacturer")
            model = self._property(adb_path, serial, "ro.product.model") or authorized[0][2].get("model")
            logger.info(
                "event=android_device_connected serial=%s manufacturer=%s model=%s",
                serial, manufacturer or "unknown", model or "unknown",
            )
            return self._status(
                AndroidDeviceState.CONNECTED,
                adb_path,
                scrcpy_path,
                serial=serial,
                manufacturer=manufacturer,
                model=model,
                mirror_running=self._mirror_running(serial),
                message=None if scrcpy_path else "scrcpy unavailable",
            )

        unauthorized = [entry for entry in entries if entry[1] == "unauthorized"]
        if unauthorized:
            return self._status(AndroidDeviceState.UNAUTHORIZED, adb_path, scrcpy_path, serial=unauthorized[0][0], mirror_running=self._any_mirror_running(), message="Phone authorization required")
        offline = [entry for entry in entries if entry[1] == "offline"]
        if offline:
            return self._status(AndroidDeviceState.OFFLINE, adb_path, scrcpy_path, serial=offline[0][0], mirror_running=self._any_mirror_running(), message="Android device is offline")
        return self._status(AndroidDeviceState.NOT_CONNECTED, adb_path, scrcpy_path, mirror_running=self._any_mirror_running(), message="Phone not connected")

    def launch_mirror(self) -> MirrorLaunchResult:
        current = self.status()
        if current.state != AndroidDeviceState.CONNECTED or not current.serial:
            raise AndroidDeviceError(current.state, current.message or "No authorized Android device is available")
        scrcpy_path = self._find_executable("scrcpy")
        if not scrcpy_path:
            raise AndroidDeviceError(AndroidDeviceState.CONNECTED, "scrcpy unavailable")

        with self._process_lock:
            existing = self._mirror_processes.get(current.serial)
            if existing is not None and existing.poll() is None:
                logger.info("event=android_mirror_already_running serial=%s", current.serial)
                return MirrorLaunchResult(result="ALREADY_OPEN", serial=current.serial)
            if existing is not None:
                self._mirror_processes.pop(current.serial, None)
            self._wake_display_if_needed(adb_path=self._find_executable("adb"), serial=current.serial)
            command = [scrcpy_path, "--serial", current.serial]
            try:
                process = self._launch_process(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
                )
            except OSError as error:
                logger.exception("event=android_mirror_launch_failed serial=%s", current.serial)
                raise AndroidDeviceError(AndroidDeviceState.CONNECTED, f"Unable to start scrcpy: {error}") from error
            self._mirror_processes[current.serial] = process
            logger.info("event=android_mirror_started serial=%s pid=%s", current.serial, getattr(process, "pid", None))
            return MirrorLaunchResult(result="STARTED", serial=current.serial)

    def sleep(self) -> SleepResult:
        current = self.status()
        if current.state != AndroidDeviceState.CONNECTED or not current.serial:
            raise AndroidDeviceError(current.state, current.message or "No authorized Android device is available")
        adb_path = self._find_executable("adb")
        if not adb_path:
            raise AndroidDeviceError(AndroidDeviceState.ADB_NOT_AVAILABLE, "ADB unavailable")
        self._run_adb_action(
            [adb_path, "-s", current.serial, "shell", "input", "keyevent", "KEYCODE_SLEEP"],
            "Unable to put the Android display to sleep",
        )
        mirror_closed = self._stop_tracked_mirror(current.serial)
        logger.info("event=android_device_slept serial=%s mirror_closed=%s", current.serial, mirror_closed)
        return SleepResult(result="SLEPT", serial=current.serial, mirror_closed=mirror_closed)

    def handoff_instagram_image(
        self, local_path: str | Path, *, remote_filename: str
    ) -> InstagramHandoffDeviceResult:
        """Transfer one prepared image and open Instagram on the selected device."""
        current = self.status()
        if current.state != AndroidDeviceState.CONNECTED or not current.serial:
            raise AndroidDeviceError(current.state, current.message or "No authorized Android device is available")
        adb_path = self._find_executable("adb")
        if not adb_path:
            raise AndroidDeviceError(AndroidDeviceState.ADB_NOT_AVAILABLE, "ADB unavailable")
        source = Path(local_path)
        if not source.is_file():
            raise AndroidDeviceError(AndroidDeviceState.CONNECTED, "Prepared Instagram image is unavailable")
        safe_name = Path(remote_filename).name
        if safe_name != remote_filename or not safe_name.lower().endswith(".png"):
            raise ValueError("Instagram handoff filename must be a safe PNG filename")
        serial = current.serial
        package_check = self._run_adb_stage(
            [adb_path, "-s", serial, "shell", "pm", "path", self.INSTAGRAM_PACKAGE],
            "Instagram installed check failed",
        )
        if not package_check.stdout.strip().startswith("package:"):
            raise AndroidDeviceError(AndroidDeviceState.CONNECTED, "Instagram is not installed on the connected Android device")
        self._run_adb_stage(
            [adb_path, "-s", serial, "shell", "mkdir", "-p", self.INSTAGRAM_HANDOFF_DIR],
            "Unable to create the Creator-OS image directory on Android",
        )
        android_path = f"{self.INSTAGRAM_HANDOFF_DIR}/{safe_name}"
        self._run_adb_stage(
            [adb_path, "-s", serial, "push", str(source), android_path],
            "Unable to push the Instagram image to Android",
            timeout=self.FILE_TRANSFER_TIMEOUT_SECONDS,
        )
        self._run_adb_stage(
            [adb_path, "-s", serial, "shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{android_path}"],
            "Unable to scan the Instagram image into Android media",
        )
        mirror = self.launch_mirror()
        self._run_adb_stage(
            [adb_path, "-s", serial, "shell", "monkey", "-p", self.INSTAGRAM_PACKAGE, "-c", "android.intent.category.LAUNCHER", "1"],
            "Unable to open Instagram on Android",
        )
        return InstagramHandoffDeviceResult(serial=serial, android_path=android_path, mirror_result=mirror.result)

    def _run(self, command: Sequence[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        return self._run_command(
            list(command), capture_output=True, text=True, timeout=timeout,
            check=False, shell=False,
        )

    @staticmethod
    def _discover_executable(name: str) -> str | None:
        discovered = shutil.which(name)
        if discovered or os.name != "nt":
            return discovered
        local_app_data = os.getenv("LOCALAPPDATA")
        if not local_app_data:
            return None
        root = Path(local_app_data)
        direct_candidates = (
            root / "Microsoft" / "WindowsApps" / f"{name}.exe",
            root / "Microsoft" / "WinGet" / "Links" / f"{name}.exe",
        )
        for candidate in direct_candidates:
            if candidate.is_file():
                return str(candidate)
        if name.lower() == "scrcpy":
            packages = root / "Microsoft" / "WinGet" / "Packages"
            matches = sorted(packages.glob("Genymobile.scrcpy_*/*/scrcpy.exe"), reverse=True)
            if matches:
                return str(matches[0])
        return None

    def _property(self, adb_path: str, serial: str, name: str) -> str | None:
        try:
            result = self._run(
                [adb_path, "-s", serial, "shell", "getprop", name],
                timeout=self.PROPERTY_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        value = result.stdout.strip() if result.returncode == 0 else ""
        return value or None

    def _wake_display_if_needed(self, *, adb_path: str | None, serial: str) -> None:
        if not adb_path:
            raise AndroidDeviceError(AndroidDeviceState.ADB_NOT_AVAILABLE, "ADB unavailable")
        try:
            result = self._run(
                [adb_path, "-s", serial, "shell", "dumpsys", "power"],
                timeout=self.PROPERTY_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise AndroidDeviceError(AndroidDeviceState.ADB_TIMEOUT, "Android display-state check timed out") from error
        except (OSError, subprocess.SubprocessError) as error:
            raise AndroidDeviceError(AndroidDeviceState.ADB_ERROR, "Unable to determine Android display state") from error
        if result.returncode != 0:
            raise AndroidDeviceError(AndroidDeviceState.ADB_ERROR, "Unable to determine Android display state")
        awake = self._parse_display_awake(result.stdout)
        if awake is None:
            raise AndroidDeviceError(AndroidDeviceState.ADB_ERROR, "ADB returned an unrecognized Android display state")
        if awake:
            logger.debug("event=android_display_already_awake serial=%s", serial)
            return
        self._run_adb_action(
            [adb_path, "-s", serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP"],
            "Unable to wake the Android display",
        )
        logger.info("event=android_display_woken serial=%s", serial)

    def _run_adb_action(self, command: Sequence[str], failure_message: str) -> None:
        try:
            result = self._run(command, timeout=self.PROPERTY_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as error:
            raise AndroidDeviceError(AndroidDeviceState.ADB_TIMEOUT, f"{failure_message}: command timed out") from error
        except (OSError, subprocess.SubprocessError) as error:
            raise AndroidDeviceError(AndroidDeviceState.ADB_ERROR, failure_message) from error
        if result.returncode != 0:
            raise AndroidDeviceError(AndroidDeviceState.ADB_ERROR, failure_message)

    def _run_adb_stage(
        self, command: Sequence[str], failure_message: str, *, timeout: int | None = None
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = self._run(command, timeout=timeout or self.PROPERTY_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as error:
            raise AndroidDeviceError(AndroidDeviceState.ADB_TIMEOUT, f"{failure_message}: command timed out") from error
        except (OSError, subprocess.SubprocessError) as error:
            raise AndroidDeviceError(AndroidDeviceState.ADB_ERROR, failure_message) from error
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise AndroidDeviceError(AndroidDeviceState.ADB_ERROR, f"{failure_message}: {detail}" if detail else failure_message)
        return result

    @staticmethod
    def _parse_display_awake(output: str) -> bool | None:
        normalized = output.lower()
        if "display power: state=on" in normalized or "mwakefulness=awake" in normalized or "minteractive=true" in normalized:
            return True
        if (
            "display power: state=off" in normalized
            or "mwakefulness=asleep" in normalized
            or "mwakefulness=dozing" in normalized
            or "minteractive=false" in normalized
        ):
            return False
        return None

    def _mirror_running(self, serial: str) -> bool:
        with self._process_lock:
            process = self._mirror_processes.get(serial)
            if process is None:
                return False
            if process.poll() is None:
                return True
            self._mirror_processes.pop(serial, None)
            logger.info("event=android_mirror_exited serial=%s", serial)
            return False

    def _any_mirror_running(self) -> bool:
        with self._process_lock:
            running = False
            for serial, process in tuple(self._mirror_processes.items()):
                if process.poll() is None:
                    running = True
                else:
                    self._mirror_processes.pop(serial, None)
                    logger.info("event=android_mirror_exited serial=%s", serial)
            return running

    def _stop_tracked_mirror(self, serial: str) -> bool:
        with self._process_lock:
            process = self._mirror_processes.get(serial)
            if process is None or process.poll() is not None:
                self._mirror_processes.pop(serial, None)
                return False
            try:
                process.terminate()
                process.wait(timeout=self.PROCESS_STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=self.PROCESS_STOP_TIMEOUT_SECONDS)
                except (OSError, subprocess.SubprocessError) as error:
                    raise AndroidDeviceError(AndroidDeviceState.CONNECTED, "Unable to close the Creator-OS phone mirror") from error
            except OSError as error:
                raise AndroidDeviceError(AndroidDeviceState.CONNECTED, "Unable to close the Creator-OS phone mirror") from error
            finally:
                if process.poll() is not None:
                    self._mirror_processes.pop(serial, None)
            return True

    @staticmethod
    def _parse_devices(output: str) -> list[tuple[str, str, dict[str, str]]]:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not lines or lines[0] != "List of devices attached":
            raise ValueError("Unexpected adb devices header")
        entries: list[tuple[str, str, dict[str, str]]] = []
        for line in lines[1:]:
            fields = line.split()
            if len(fields) < 2 or fields[1] not in {"device", "unauthorized", "offline"}:
                raise ValueError("Unexpected adb device row")
            metadata = dict(field.split(":", 1) for field in fields[2:] if ":" in field)
            entries.append((fields[0], fields[1], metadata))
        return entries

    @staticmethod
    def _status(
        state: AndroidDeviceState,
        adb_path: str | None,
        scrcpy_path: str | None,
        *,
        serial: str | None = None,
        model: str | None = None,
        manufacturer: str | None = None,
        mirror_running: bool = False,
        message: str | None = None,
    ) -> AndroidDeviceStatus:
        return AndroidDeviceStatus(
            state=state,
            adb_available=bool(adb_path),
            scrcpy_available=bool(scrcpy_path),
            mirror_available=state == AndroidDeviceState.CONNECTED and bool(scrcpy_path),
            mirror_running=mirror_running,
            serial=serial,
            model=model,
            manufacturer=manufacturer,
            message=message,
        )
