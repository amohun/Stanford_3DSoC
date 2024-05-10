import tomli
import os.path as path

def load_settings(settings):
    if settings is None:
        raise ValueError("settings is required to specify instrument sessions")
    elif isinstance(settings, str):
        with open(settings, "rb") as settings_file:
            settings = tomli.load(settings_file)
            if isinstance(settings, dict):
                return settings
            else:
                raise ValueError("settings must be a toml file or dictionary")
    elif isinstance(settings, dict):
        return settings
    else:
        raise ValueError("settings must be a toml file or dictionary")
    

if __name__ == "__main__":
    load_settings("settings\default.toml")