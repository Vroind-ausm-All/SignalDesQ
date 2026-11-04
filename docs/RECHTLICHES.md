# Deutschland / DACH: Rechtliche Leitplanken für Akquise-Tools

**Wichtig: keine Rechtsberatung.** Stand 15.10.2026. Für konkrete Marketingkampagnen deutsche Rechtsberatung und Datenschutzprüfung einholen; Österreich und Schweiz haben eigene Regeln.

1. **Unerbetene Werbe-E-Mail in Deutschland**: grundsätzlich ausdrückliche vorherige Einwilligung, **auch B2B** (§ 7 Abs. 2 Nr. 2 UWG). Die Ausnahme bei Bestandskunden greift nur, wenn **alle** Voraussetzungen des § 7 Abs. 3 UWG vorliegen (im Verkaufszusammenhang erhaltene E-Mail, eigene ähnliche Leistungen, kein Widerspruch, entsprechende Hinweise bei Erhebung und jeder Verwendung). Quelle: https://www.gesetze-im-internet.de/uwg_2004/__7.html
2. **Telefonische B2B-Werbung:** Mindestens **mutmaßliche Einwilligung bezogen auf gerade diesen Telefonanruf** erforderlich (§ 7 Abs. 2 Nr. 1 UWG). Ein öffentlicher Ansprechpartner oder ein Website-Signal allein genügt nicht. IHK München warnt vor ungeprüfter Kaltakquise: https://www.ihk-muenchen.de/ratgeber/recht/werbung-fairer-wettbewerb/richtig-werben-a-z/ ; IHK Saarland https://www.saarland.ihk.de/aktuelles/telefonische-kaltakquise-nein
3. **LinkedIn-/Social-Direktnachrichten, WhatsApp, automatisierte DM-Sequenzen:** nicht als pauschal rechtsfrei behandeln. Einzelfall nach Kanal und Werbecharakter prüfen; keine Auto-Versand-Funktion in diesem MVP.
4. **DSGVO**: Personenbezogene berufliche Kontaktdaten bleiben personenbezogen. Vor der Speicherung einen Zweck und eine tragfähige Rechtsgrundlage prüfen (Art. 6), Transparenz und ggf. Informationspflichten (Art. 13/14), Datenminimierung und Aufbewahrungsfrist festlegen, Widerspruch gegen Direktwerbung (Art. 21) respektieren. Offizielle Verordnung: https://eur-lex.europa.eu/eli/reg/2016/679/oj?locale=de
5. **Blockliste statt Umgehung:** Status `nicht_kontaktieren` setzt den Prioritätsscore auf 0 und sperrt die Pipeline. Dies ersetzt keine durchgängige rechtliche/organisatorische Blocklistenlogik außerhalb der App.
6. **Technische Sicherheit:** Aktuelle Version: lokal, nur Loopback, ein Nutzer, SQLite. Kein Passwort/Login, keine TLS-Terminierung, kein AVV, keine Rollen und kein prüfbares Lösch-/Backup-Konzept. **Nicht öffentlich deployen oder sensiblen Daten anderer Mitarbeiter Zugriff gewähren.** Datenbank ist unverschlüsselt auf dem lokalen Dateisystem; OS-Verschlüsselung/Backups nach eigenen Schutzbedarfen.
7. **Datenquellen:** keine Profile scrapen, Website-Nutzungsbedingungen, Urheber- und Datenbankrechte sowie robots.txt beachten. Nur überprüfbare geschäftsbezogene Signale mit URL erfassen; keine besonderen Kategorien persönlicher Daten.
8. **KI-Nutzung:** Wenn später ein LLM angeschlossen wird, keine personenbezogenen Leads ohne geprüfte Rechtsgrundlage, Anbieter-/Datentransferprüfung und geeignete Vereinbarung an Drittanbieter übertragen. Halluzinierte Signale dürfen nicht als überprüfte Fakten verwendet werden.

## Einwilligung in diesem MVP

`opt_in` bedeutet **nur**, dass ein Anwender im CRM eine Einwilligung markiert hat – die Software kann deren Qualität, Zeitpunkt und Umfang nicht prüfen. `bestandskunde_pruefen` und `telefon_einzelfall` markieren ausdrücklich eine **ausstehende Einzelfallprüfung**, keine automatische Freigabe. Das Tool hat absichtlich **keinen Send-Endpunkt**.

## Praktisch risikoärmere Akquisepfade

Fachlicher Inbound-Content, gezielte Suchmaschinen-/ggf. Ads-Landingpages mit freiwilligem Kontaktformular, persönliche Empfehlungen mit Einverständnis, Netzwerkgespräche auf Veranstaltungen, Angebote auf konkret angefragte Leistungen und seriöses Bestandskundenmanagement nach Prüfung der Voraussetzungen.

## Entscheider-Recherche / Lusha-Erweiterung (v0.5)

Geschäftliche Kontaktdaten natürlicher Personen sind personenbezogene Daten. Eine API-Lizenz oder öffentlich zugängliche Durchwahl stellt keine Werbeeinwilligung dar. Für jede Verarbeitung sind DSGVO-Rechtsgrundlage, Zweckbindung, Datenminimierung, Informationspflichten (insbesondere bei indirekter Datenerhebung, Art. 14 DSGVO), Lösch- und Widerspruchsmöglichkeiten sowie gegebenenfalls internationale Datentransfers zu prüfen. Relevante Quellen und rechtmäßige Gründe für die Kontaktaufnahme dokumentieren.

Telefonakquise im B2B-Bereich erfordert nach § 7 UWG mindestens eine anhand konkreter Umstände tragfähige mutmaßliche Einwilligung; allgemeine Relevanz der angebotenen Leistung genügt nicht. Werbliche E-Mails benötigen grundsätzlich ein vorheriges Opt-in bzw. müssen die eng gefasste Bestandskunden-Ausnahme erfüllen. Eine Do-Not-Call-Sperre und persönliche Widersprüche sind zu beachten. SignalDesk versendet keine Nachrichten und tätigt keine Anrufe.


## v0.6 Eigene Recherche statt kommerzieller Kontaktdatenanbieter

Personenbezogene Kontaktdaten sind auch dann nicht automatisch frei verwendbar, wenn sie auf der Unternehmenswebsite stehen. Recherche nur aus Quellen mit zulässigem Abruf, keine social-network Scraper oder Nummern-Enumeration; nach Datenschutzrecht Rechtsgrundlage, Art.-14-Informationspflichten, Zweckbindung und Widerspruchs-/Löschprozesse prüfen. § 7 UWG bleibt unabhängig davon für Werbung maßgeblich. Das Programm sieht keine automatische Kontaktaufnahme vor. Siehe `docs/EIGENE_ENTSCHEIDER_RECHERCHE_V06.md`.
