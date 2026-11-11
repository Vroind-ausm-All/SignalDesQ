"""Gemeinsames Aufräumen für Tests mit temporärer Datenbank.

Recherche-Worker fragen ihre Datenbank noch einige Sekunden nach dem letzten Auftrag ab. Unter Windows lässt sich eine
geöffnete Datei nicht löschen – der Test scheitert dann beim Aufräumen, je nach Zeitpunkt mal hier, mal dort.
Deshalb: erst alle Worker beenden, dann löschen; eine eben geschlossene Datei gibt Windows manchmal erst kurz darauf frei.
"""
import time


def cleanup_tmp(tmp, attempts=40, pause=0.25):
    from sales_tool.research import jobs
    jobs.stop_all_workers()
    for attempt in range(attempts):
        try:
            tmp.cleanup()
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(pause)
