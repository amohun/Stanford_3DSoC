"""
Settings Utility Module
Author: Andrew Bechdolt
Date: 2024-08-18
Documentation Assistance: ChatGPT

This module provides a `SettingsUtil` class for managing application settings
from a TOML file or a dictionary. It includes methods for loading, retrieving,
updating, and saving settings, as well as handling nested settings with dot-separated
keys or lists of keys. The utility also offers error handling through a custom
`SettingsException`.

Key Features:
- Load settings from a TOML file or dictionary.
- Retrieve settings using dot-separated strings or a list of keys.
- Ensure required settings are present, raising an exception if they are missing.
- Update settings and save them back to a TOML file.
- Reload settings from the original file if needed.
- Customizable default values for non-required settings.

Example Usage:
```python
from SourceScripts.settings_util import SettingsUtil

# Load settings from a TOML file
settings_util = SettingsUtil("settings/default.toml")

# Retrieve a setting with a default value if it doesn't exist
some_value = settings_util.get_setting("some_key", default="default_value")

# Retrieve a nested setting, raising an error if it doesn't exist
all_wls = settings_util.get_setting("device.all_WLS", required=True)

# Update a setting and save it to the original TOML file
settings_util.update_setting("new_key", "new_value")
settings_util.save_settings()

# Reload settings from the original file
settings_util.reload_settings()
"""

class SettingsUtil:
    """
    A utility class for managing settings from a TOML file or a dictionary.

    This class provides methods to load, update, and save settings, as well as
    retrieve specific values from the settings.
    """
    class SettingsException(Exception):
        """Exception produced by the SettingsUtil class."""
        def __init__(self, msg):
            super().__init__(f"SettingsUtil: {msg}")

    def __init__(self, settings):
        """
        Initializes the SettingsUtil object with settings from a dictionary or TOML file.

        Args:
            settings (Union[dict, str]): The settings data as a dictionary or the path to a TOML file.
        """
        from tomli import load

        import os.path as path

        self.load = load
        self.path = path
        self.update_settings(settings)

    def update_settings(self, settings):
        """
        Updates the current settings with a new dictionary or loads settings from a TOML file.

        Args:
            settings (Union[dict, str]): The settings data as a dictionary or the path to a TOML file or another SettingsUtil class.

        Raises:
            self.SettingsException: If the settings are not provided as a dictionary or valid TOML file path.
        """
        if isinstance(settings, dict):
            self.settings = settings
            self.settings_path = "Imported"  # No file path associated with these settings
        
        elif isinstance(settings, str):
            self.settings = self._load_settings(settings)
            self.settings_path = settings
        
        elif isinstance(settings,SettingsUtil):
            self.settings = settings.settings
            self.settings_path = settings.settings_path
        
        else:
            raise self.SettingsException("Settings must be provided as a dictionary or a valid TOML file path.")

    def _load_settings(self, file_path: str) -> dict:
        """
        Loads settings from a TOML file.

        Args:
            file_path (str): The path to the TOML settings file.

        Returns:
            dict: The loaded settings as a dictionary.

        Raises:
            self.SettingsException: If the file does not exist or is not a valid TOML file.
        """
        if not self.path.exists(file_path):
            raise self.SettingsException(f"Settings file path '{file_path}' does not exist.")
        
        with open(file_path, "rb") as settings_file:
            settings = self.load(settings_file)
            if not isinstance(settings, dict):
                raise self.SettingsException("Loaded settings must be a dictionary.")
            return settings

    def get_setting(self, key, default=None, required=False):
        """
        Retrieves a specific setting value by key.

        Args:
            key (str): The key of the setting to retrieve.
            default (Any, optional): The default value to return if the key is not found. Default is None.

        Returns:
            Any: The value of the setting or the default value if the key is not found.
        """
        
        
        if isinstance(key, str):
            key = key.split(".")
        elif not isinstance(key, list):
            raise self.SettingsException("Key must be a string or a list of strings.")
        

        value = self.settings
        for k in key:
            try:
                value = value[k]
            except (KeyError, TypeError):
                if required:
                    raise self.SettingsException(f"Setting '{'.'.join(key)}' not found.")
                else:
                    print(f"Setting '{'.'.join(key)}' not found. Using default value: {default}")
                    return default

        return value


    def update_setting(self, key, value):
        """
        Updates a specific setting in the settings dictionary.

        Args:
            key (str): The key of the setting to update.
            value (Any): The new value for the setting.
        """
        self.settings[key] = value

    def reload_settings(self):
        """
        Reloads settings from the original TOML file if a file path is available.

        Raises:
            self.SettingsException: If no file path is available to reload the settings.
        """
        if not self.settings_path:
            raise self.SettingsException("No file path available to reload settings.")
        
        self.settings = self._load_settings(self.settings_path)

if __name__ == "__main__":
    # Example usage
    settings_util = SettingsUtil("settings/default.toml")
    print(settings_util.get_setting("some_key", "default_value"))
    settings_util.update_setting("new_key", "new_value")
    settings_util.save_settings()
