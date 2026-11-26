---
name: dependency-security
description: Prüfliste für jede neue oder geänderte Abhängigkeit von SignalDesk (Python-Paket, JS-Bibliothek, Modellgewicht, CI-Action, Werkzeug-Download) und jede Änderung an requirements*.txt, Lockdateien, make_lock.py, make_sbom.py oder der CI. Verwenden bei „Paket hinzufügen“, „Version anheben“, „Lockdatei neu erzeugen“, „neues Werkzeug in der CI“.
---

# Abhängigkeiten sicher aufnehmen

Zweck: Jede fremde Komponente ist geprüft, fest gepinnt, mit Prüfsumme installiert und dokumentiert – bevor sie läuft.
Durchgesetzt wird das in der CI (Job „audit“: pip-audit, Gitleaks, Ruff; Job „release“: SBOM aktuell) und in
`tests/test_ci_gates.py`, `tests/test_sprintS6_release.py`. Dieser Skill prüft, ob eine Änderung diese Wege benutzt.

## Eingaben
- Der Diff (Anforderungsdatei, Lockdatei, Workflow, gebündelte Datei).
- Name, Version und Original-Repository der Komponente.

## Prüfliste

1. **Bedarf belegt:** Gibt es einen Plan-Eintrag (Technologieregister in `docs/plan/open_intelligence.json`) und einen messbaren
   Zusatznutzen gegenüber dem Bestand? Ohne Messung kein Einbau (Plan: „Kandidaten sind keine Installationsliste“).
2. **Drei Rechte getrennt:** Softwarelizenz, Lizenz der Modellgewichte (falls vorhanden) und Rechte an den verarbeiteten Daten –
   jeweils mit Quelle notiert. Unklare Lizenz = nicht aufnehmen.
3. **Fest gepinnt mit Prüfsumme:**
   - Python-Pakete nur über `tools/make_lock.py` (Wartezeit 14 Tage, `--require-hashes`); Programmvarianten in
     `requirements-lock-<variante>.txt`, Prüfwerkzeuge in `tools/requirements-lock-dev.txt` (nicht im Release, nicht in der SBOM).
   - JS-Bibliotheken lokal gebündelt mit SHA-256 im Repository, kein CDN zur Laufzeit.
   - CI-Actions per 40-stelligem Commit, Werkzeug-Downloads mit fester Version und SHA-256 (`sha256sum -c` vor dem Entpacken).
4. **Schwachstellen:** `pip-audit --require-hashes --disable-pip -r <lockdatei>` ohne Fund. Bei Fund: auf behobene Version gehen;
   ist die zu jung für die Wartezeit, ausdrücklich pinnen und begründen – nie den Fund unterdrücken.
5. **Plattformen:** Windows x64 und Linux x64, Python 3.10–3.13 für Programmvarianten (Prüfwerkzeuge 3.12–3.13). Keine Komponente,
   die eine Variante „basis“ (nur Standardbibliothek) bricht.
6. **Laufzeitrechte:** Kein Netz-, Shell- oder Schreibzugriff außerhalb des vorgesehenen Wegs; Parser und Modelle nur mit lokalen,
   begrenzten Daten (Plan, Vertrauensgrenzen). Keine Installation oder Downloads beim Programmstart.
7. **Dokumentiert:** `python tools/make_sbom.py` neu erzeugt (`sbom/signaldesk.cdx.json`, `docs/BESTANDTEILE.md`), Eintrag im
   CHANGELOG, bei externen Skills/Plugins zusätzlich `docs/SKILLS_REGISTRY.md`.
8. **Rückbau:** Wie wird die Komponente wieder entfernt, und was fällt dann weg? Ein Satz im CHANGELOG oder in BESTANDTEILE.

## Ausgabe
Je Punkt `eingehalten / verletzt / nicht betroffen` mit Datei und Zeile. Bei „verletzt“: konkrete Korrektur.

## Sicherheitsregeln
- Keine Wartezeit, Prüfsumme oder Advisory-Prüfung umgehen, um einen Lauf grün zu bekommen.
- Keine Pakete aus unbekannten Indizes, keine `curl | sh`-Installationen, keine ungepinnten `@main`-Actions.
- Funde nicht per Ausnahme-Liste ausblenden, ohne Begründung, Ablaufdatum und Plan-Eintrag.

## Beispiel
Änderung: „pip-audit in die CI aufnehmen.“
Ergebnis: Punkt 3 eingehalten (`tools/requirements-lock-dev.txt` mit Hashes, nicht in `release_files()`), Punkt 4 zunächst verletzt
(filelock 4.1.0 mit bekannten Schwachstellen, erzwungen durch Python 3.10) → Korrektur: Prüfwerkzeuge nur für Python 3.12–3.13
auflösen, danach filelock ≥ 4.2.1 und kein Fund; Punkt 7 eingehalten (CHANGELOG, Skills-Register).
