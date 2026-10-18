# Test and verification status

## Existing application checks

The source project's recorded results report 10 unit tests passed, along with compile, UI construction/resize, frozen startup, and dependency checks on the development Windows 11 host (build 26200; Python 3.12.14; PySide6 6.8.3; psutil 7.2.2). This release-preparation pass did not rerun the source unit suite.

The executable is the PyInstaller one-file x64 build. Its ProductName, ProductVersion, and FileDescription identify RAM Optimiser / 1.0.0. The staged EXE SHA256 matches the original release EXE. The app is unsigned; no SmartScreen reputation is claimed.

## Installer build and test (2026-10-18)

- Inno Setup 7.1.0 x64 was downloaded from the official distribution and its Authenticode signature verified to Pyrsys B.V. `ISCC.exe` compiled the staged script successfully. The setup has RAM Optimiser / 1.0.0 file metadata and is unsigned.
- A non-elevated per-user install returned exit code 0 on the Windows 11 development host. The installed executable hash matched the payload; version metadata read as 1.0.0. The Start Menu shortcut and current-user uninstall entry were created.
- The installed executable's offscreen startup smoke test returned exit code 0 with the app's smoke-test flag enabled and its `LOCALAPPDATA` redirected to staging. The app's existing user data directory was not used for this test.
- The uninstaller ran without elevation and returned exit code 0. The install directory, Start Menu shortcut, and uninstall registration were absent afterward. The pre-existing `%LOCALAPPDATA%\RAM Optimiser` data directory remained present.
- The optional desktop shortcut remained unchecked by default. It was not tested as selected because the account's registered Desktop folder is absent.

## Shell-folder diagnosis

Read-only checks found `User Shell Folders\Desktop` set to `%USERPROFILE%\Desktop`, whose target does not exist. `Local AppData` is set to `%USERPROFILE%\AppData\Local` and that directory exists. In the restricted workspace process, Windows returned `0x80070002` for `SHGetFolderPath`/`SHGetKnownFolderPath` calls with the respective CREATE flags, although the no-create LocalAppData lookup succeeds. The official compiler bootstrap succeeded when run outside the workspace sandbox in current-user mode. No folder settings were changed.

## Remaining release checks and limitations

- Test the optional desktop shortcut in an account with a valid Desktop shell folder.
- Clean Windows 10 and Windows 11 testing and additional hardware/driver coverage remain outstanding.
- Exercise process operations, startup backup/restore, tray actions, notifications, and sign-in behavior on clean accounts.
- Verify Qt licensing, notices, and relinking materials for the exact frozen Qt DLL/plugin set before public redistribution. See `THIRD_PARTY_NOTICES.md`; no legal review is claimed.
- The app and setup are unsigned.
