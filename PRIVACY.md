# RAM Optimiser privacy

RAM Optimiser has no account, advertising, analytics, crash upload, or required network service. It does not transmit system measurements.

Settings are stored in `%LOCALAPPDATA%\RAM Optimiser\settings.json`; performance samples, Boost results, and game sessions are stored in `%LOCALAPPDATA%\RAM Optimiser\history.sqlite3`. A diagnostic log may be written to the same directory if an application operation fails. History is trimmed to the configured retention period. Users can clear history from Settings or remove the local data directory after exiting the application.

Live metrics are read from Windows and psutil. Optional GPU readings use NVIDIA NVML locally when installed. The optional sign-in preference writes one per-user Windows Run-key value. Startup-app disable moves the selected Run-key value to a reversible backup key under `Software\RAM Optimiser\Disabled Startup` in the same registry hive.

No data is sent to the project maintainers. If a user chooses to report a problem, they should review any log or screenshot before sharing it because it may contain device or process names.
