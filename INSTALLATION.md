# Installing RAM Optimiser

## Install

1. Download `RAM-Optimiser-Setup.exe` from the release location you trust.
2. Run it and review the displayed install location. The default is `%LOCALAPPDATA%\Programs\RAM Optimiser`, for the current Windows account.
3. Keep the Start Menu shortcut selected. Select the optional desktop shortcut only if you want one.
4. Finish setup, then launch **RAM Optimiser** from the Start Menu.

The installer is configured for a per-user install and requests no administrator privileges. It does not add RAM Optimiser to Windows startup and does not automatically launch the app after setup.

## Uninstall

Open **Settings > Apps > Installed apps** (Windows 11) or **Apps & features** (Windows 10), select **RAM Optimiser**, and choose **Uninstall**. You can also use the **Uninstall RAM Optimiser** entry in the Start Menu. The uninstaller removes the installed application and its shortcuts. It intentionally leaves settings, history, and logs in `%LOCALAPPDATA%\RAM Optimiser` so your data is not silently deleted. Clear history in the app's Settings; remove that folder manually only after exiting the app if you also want to remove all local data.

## Safety and permissions

Monitoring works without administrator access. Individual process operations and machine-wide startup registry changes may be refused by Windows. RAM Optimiser does not elevate itself. Boost requests memory working-set trimming and never closes apps. Process close/force-terminate actions are separate, explicitly selected actions; force termination can discard unsaved work. Read [README.md](README.md), [PRIVACY.md](PRIVACY.md), and [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for details.

## Unsigned application

The current executable and installer are not digitally signed. Windows may show an unfamiliar-app prompt. Do not run files from a source you do not trust. No SmartScreen reputation is claimed.
