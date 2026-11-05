import os
import subprocess

from PySide6.QtCore import QSettings

ORGANIZATION = "YouTubeDownloader"
APPLICATION = "YouTubeDownloader"
REGISTRY_EXPORT_NAME = "registry_settings.reg"


def app_settings():
    return QSettings(QSettings.IniFormat, QSettings.UserScope, ORGANIZATION, APPLICATION)


def migrate_registry_settings():
    settings = app_settings()
    if os.path.exists(settings.fileName()):
        return
    export = os.path.join(os.path.dirname(settings.fileName()), REGISTRY_EXPORT_NAME)
    if os.path.exists(export):
        subprocess.run(["reg", "import", export], capture_output=True)
    registry = QSettings(ORGANIZATION, APPLICATION)
    for key in registry.allKeys():
        settings.setValue(key, registry.value(key))
    settings.sync()
    if os.path.exists(export) and os.path.exists(settings.fileName()):
        os.remove(export)
