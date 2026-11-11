# SignalDesk 2.0.0-dev1 – Entwicklungsstand

Basis ist SignalDesk 1.19. Dieser Stand wird für die fachliche und technische Weiterarbeit bereitgestellt; die Freigabe als fertige Version 2.0 steht aus.

## Was du ausprobieren kannst
- **Firmen finden:** Fehlgeschlagene und unvollständige Website-Abrufe werden gesondert angezeigt und können erneut gestartet werden. Eine selbst gefundene Website lässt sich als Vorschlag eintragen und nach Prüfung bestätigen. Eine gleiche Registernummer ohne Vergleich des Registergerichts reicht nicht für eine automatische Bestätigung. Bei Widersprüchen wird keine Zuordnung vorgenommen.
- **Firmen-Berichte:** Mehr als drei belegte Textbefunde, zusätzliche Themen für Aktionen und Bildmaterial sowie ausgewogenere Seitenauswahl. Das Budget bleibt auf fünf Seiten beschränkt. Erfolgreiche Schritte bleiben bei Wiederholung erhalten; abhängige Empfehlungen werden neu berechnet. Berichte mit Fehlern werden als teilweise abgeschlossen gekennzeichnet.
- **Leistungsprofil:** Unter „Datenqualität & System“ Themen für die regelbasierte Inhaltsanalyse an- und ausschalten und wörtliche Suchbegriffe ergänzen. Nur neue regelbasierte Firmenberichte und URL-Recherchen nutzen dieses Profil; technische Bewertung, Stellenklassifikation und Ollama nutzen eigene Verfahren. Das Ergebnis enthält einen Schnappschuss des Profils.
- **Recruiting:** Abruffehler und teilweise Prüfung erscheinen nicht als vollständiges negatives Suchergebnis. Wiederkehrende Karriereaufträge berücksichtigen ihr gewähltes Intervall.
- **Website-Scoring:** Ein fehlender Portal-Link gilt als unbekannt. Die neue Logik verwendet eine neue Score-Version; historische Werte und Gewichte bleiben erhalten.

## Was noch offen ist
Die automatische Suche findet nicht zuverlässig abweichende Marken-Domains. Die Suche benötigt hierfür weitere Quellen sowie eine unabhängige Qualitätsmessung. Suchbegriffe und Seitenbudget sind begrenzt; ein Fund ist eine Beobachtung, keine Bestätigung von Verkaufsbedarf. Mehrere ältere Recherchemodule verwenden eigene Worker. Recruiting-Verläufe erkennen weder jede inhaltliche Änderung noch sicher geschlossene Anzeigen.

Der gewünschte Praxistest für Handwerk im Raum Stuttgart konnte hier nicht durchgeführt werden: Die Cloud-Netzwerkrichtlinie blockierte die vorgesehenen Quellen mit HTTP 403. Die automatisierten Tests verwenden fiktive Websites und belegen keine Trefferquote auf echten Betrieben. Windows-Installation, Update und Wiederherstellung wurden für diesen Entwicklungsstand nicht erneut auf einem Windows-Gerät geprüft.

Start und Voraussetzungen stehen in README.md. Vor Einsatz vorhandener Daten eine externe Sicherung anlegen und die Wiederherstellung prüfen. Eine genaue Arbeits- und Prüfliste steht in `docs/UEBERGABE_FABLE.md`; künftige Funktionen stehen separat in `docs/MASTERPLAN_SOLOSELBSTAENDIGE.md`.
