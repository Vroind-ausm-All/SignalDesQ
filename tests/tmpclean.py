"""Gemeinsames Aufräumen für Tests mit temporärer Datenbank.

Recherche-Worker fragen ihre Datenbank noch einige Sekunden nach dem letzten Auftrag ab. Unter Windows lässt sich eine
geöffnete Datei nicht löschen – der Test scheitert dann beim Aufräumen, je nach Zeitpunkt mal hier, mal dort.
Deshalb: erst alle Worker beenden, dann löschen; eine eben geschlossene Datei gibt Windows manchmal erst kurz darauf frei.

Unter Linux zeigt sich derselbe Wettlauf anders: Ein Anfrage- oder Hintergrund-Thread öffnet die Datenbank noch einmal,
während gelöscht wird, und legt dabei die SQLite-Begleitdateien (-wal/-shm) neu an – das Löschen endet dann mit
„Directory not empty“ (gesehen im CI-Lauf von 2.0.0-dev20). Auch das wird kurz abgewartet und wiederholt.
"""
import errno
import time

RETRY_ERRNOS = {errno.ENOTEMPTY, errno.EEXIST}


def cleanup_tmp(tmp, attempts=40, pause=0.25):
    from sales_tool.research import jobs
    jobs.stop_all_workers()
    for attempt in range(attempts):
        try:
            tmp.cleanup()
            return
        except OSError as exc:  # PermissionError (Windows) oder ENOTEMPTY (Linux/macOS)
            if not isinstance(exc, PermissionError) and exc.errno not in RETRY_ERRNOS:
                raise
            if attempt == attempts - 1:
                raise
            time.sleep(pause)
