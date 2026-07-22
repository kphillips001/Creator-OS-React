# Creator_OS Windows Launcher

`Creator_OS.exe` is the native Windows entry point. It invokes `tools\launcher\launch_creator_os.ps1`, which remains the single source of truth for starting the FastAPI backend and React Vite development server, waiting for both services, and opening Creator_OS in the default browser.

The launcher cleanly restarts Creator_OS services on every run. It stops only services on ports 8001 and 5174 that pass Creator_OS-specific validation, waits for them to exit, then starts and health-checks the backend before starting and health-checking React. A generic HTTP response is not accepted: the backend must return the Creator_OS Content Studio context shape, and the frontend must contain the Creator_OS application markers. If an occupied port does not identify itself as Creator_OS, the launcher stops with a clear error and does not terminate that process.

On every run, the launcher also checks the current user's Desktop for `Creator_OS.lnk`. It creates the shortcut on first run and reuses it afterward. Existing shortcuts are never overwritten.

## Desktop shortcut

Run `Creator_OS.exe` once. The launcher automatically creates a **Creator_OS** shortcut on the current user's Desktop. The shortcut targets the project-root `Creator_OS.exe` and uses the project root as its working directory.

You can also create or verify it without starting Creator_OS by running:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools\launcher\create_desktop_shortcut.ps1
```

If `assets\icons\Creator_OS.ico` exists, the helper assigns it automatically. Otherwise Windows keeps the default shortcut icon.

## Pin to the Windows taskbar

Windows may not offer taskbar pinning directly for a `.bat` shortcut. Create a second shortcut as follows:

1. Right-click the desktop and select **New → Shortcut**.
2. Use this target, replacing the project path if Creator_OS is installed elsewhere:

   ```text
   C:\Windows\System32\cmd.exe /c "C:\Creator-OS-React\tools\launcher\launch_creator_os.bat"
   ```

3. Name it **Creator_OS**.
4. Right-click the new shortcut and select **Show more options → Pin to taskbar**.

## Assign or replace the Creator_OS icon

Windows shortcuts use `.ico` files. In the shortcut's **Properties**:

1. Select **Shortcut → Change Icon**.
2. Select **Browse**.
3. Choose your Creator_OS `.ico` file.
4. Select **OK**, then **Apply**.

For automatic assignment, store the approved icon at `assets\icons\Creator_OS.ico` before running the shortcut helper. The helper does not overwrite an existing shortcut, so delete the existing `Creator_OS.lnk` first if you intentionally want it recreated with a newly added icon.

## Expected startup behavior

The launcher displays concise progress:

```text
Starting Creator_OS...
✓ Backend running
✓ React running
Opening browser...
Done.
```

- Backend identity and health are checked on port 8001.
- The React Vite development server identity and health are checked on port 5174.
- Already-running Creator_OS services are stopped and restarted.
- Newly started services continue running after the launcher exits.
- Process output is written to the project's `logs` directory.
- On failure, the native launcher shows the failing step and exception. Full commands and diagnostics are recorded in `logs\runtime\launcher.log`.

The launcher requires the same prerequisites as manual startup: Python with the project's backend dependencies, Node.js, npm, and installed frontend packages.

The supervised runtimes include the standalone Image orchestrator and NudeNet, Vision, Grok, and Content Intelligence workers, the Photoshoot Analysis worker, and the durable Photoshoot Auto Run worker. Both Photoshoot workers use the same PID validation, heartbeat, lease recovery, restart, and process-tree shutdown protections as the existing workers. Photoshoot Auto Run owns full-plan generation after the UI issues start, pause, resume, stop, or retry commands.

Canonical reference hosting is configured through `HOSTED_REFERENCE_VERIFY_TTL_SECONDS`, `HOSTED_REFERENCE_RETRY_COUNT`, `HOSTED_REFERENCE_RETRY_BACKOFF_SECONDS`, `HOSTED_REFERENCE_VERIFY_TIMEOUT_SECONDS`, and `WAVESPEED_TRANSPORT_TIMEOUT_SECONDS`. These settings are consumed by the generation runtime; the launcher does not override them.
