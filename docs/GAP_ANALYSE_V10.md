# Gap-Analyse: Was braucht ein Sales-/Akquise- und Buchhaltungstool? (Stand v1.0, November 2026)

Ausgangslage v0.9: starke Recherche-, CRM- und Angebotsfunktionen, aber **der Weg vom angenommenen Angebot zum Geld auf dem Konto fehlte komplett**: keine Rechnung, keine Zahlungen, keine Ausgaben, keine Steuer-Vorbereitung, keine Datensicherung. Für eine Agentur in Deutschland ist das der Teil, der rechtlich am stärksten reguliert ist.

Legende: ✅ in v1.0 umgesetzt · 🟡 teilweise / vereinfacht · ⬜ offen

> Keine Rechts- oder Steuerberatung. Die Regeln unten sind nach bestem Wissen zum Stand 11/2026 zusammengefasst. Vor dem Produktiveinsatz bitte mit der eigenen Steuerberatung abstimmen.

## 1. Definitiv nötig (Pflicht bzw. ohne geht es nicht)

| Bereich | Warum Pflicht | Status v1.0 |
|---|---|---|
| **Rechnungen mit Pflichtangaben** (§ 14 Abs. 4 UStG) | Name/Anschrift beider Parteien, Steuernummer oder USt-IdNr., Datum, fortlaufende Nummer, Leistung, Leistungszeitpunkt, Entgelt je Steuersatz, Steuerbetrag bzw. Befreiungshinweis | ✅ Pflichtfeldprüfung vor Festschreibung |
| **Fortlaufende, eindeutige Rechnungsnummern** | Lückenlosigkeit ist Prüfkriterium bei Betriebsprüfungen | ✅ Nummer erst bei Festschreibung, je Jahr lückenlos (`RE-2026-0001`), chronologisch geprüft |
| **Unveränderbarkeit (GoBD)** | Festgeschriebene Belege dürfen nicht nachträglich geändert/gelöscht werden | ✅ SQLite-Trigger sperren Rechnung, Positionen und Protokoll; Korrektur nur per Stornorechnung |
| **Änderungsprotokoll (GoBD)** | Nachvollziehbarkeit jeder buchhalterischen Aktion | ✅ unveränderbares `audit_log` |
| **E-Rechnung empfangen** | Seit 01.01.2025 Pflicht für alle inländischen Unternehmen | ✅ Import XRechnung (UBL/CII) und ZUGFeRD-XML, Original wird unverändert archiviert |
| **E-Rechnung ausstellen** | B2B-Pflicht ab 2027 (Vorjahresumsatz > 800.000 €), ab 2028 für alle; Kleinunternehmer ausgenommen | ✅ XRechnung 3.0 (UBL) Export · ⚠️ nicht mit KoSIT-Validator geprüft (Validator war in der Build-Umgebung nicht erreichbar) |
| **Kleinunternehmerregelung** (§ 19 UStG, seit 2025: 25.000 € Vorjahr / 100.000 € lfd. Jahr) | Hinweistext, keine USt, Grenzüberwachung | ✅ Modus + Hinweis + Grenzwarnung |
| **Reverse Charge** (EU-Kunden & eingekaufte EU-Leistungen wie Werbeplattformen/SaaS) | Typischer Agentur-Fallstrick: USt wird trotz ausländischer Rechnung geschuldet | ✅ Ausgang (Kz 21 + ZM-Hinweis) und Eingang (Kz 46/47/67), auch für Kleinunternehmer korrekt |
| **Offene Posten & Zahlungseingang** | Liquidität, Ist-Versteuerung, Mahnwesen | ✅ Teil-/Vollzahlung, Rücknahme mit Protokoll |
| **Ausgaben/Belege mit Vorsteuer** | EÜR und Vorsteuerabzug | ✅ mit SKR03-Kontenvorschlag, § 13b, GWG-Warnung |
| **USt-Voranmeldung vorbereiten** | monatlich/quartalsweise Pflicht (außer KU) | 🟡 Kennzahlen 81/86/21/46/47/66/67 + Zahllast; Übermittlung weiterhin über ELSTER |
| **EÜR-Überblick** | Jahresabschluss für Freiberufler/Gewerbe ohne Bilanzpflicht | 🟡 vereinfachte Netto-Sicht; AfA, Privatanteile, Anlage EÜR fehlen |
| **Aufbewahrung** (Rechnungen/Belege 8 Jahre seit 2025, Bücher 10 Jahre) | Lead-Löschung darf Rechnungsdaten nicht vernichten | ✅ Leads mit Rechnungen sind nicht löschbar; Verkäuferdaten werden je Rechnung eingefroren |
| **Datensicherung** | Lokale SQLite-Datei = Single Point of Failure | ✅ Konsistentes Backup per Knopfdruck (SQLite-Backup-API); externe Kopie bleibt Nutzeraufgabe |
| **Verfahrensdokumentation (GoBD)** | Pflichtdokument, das beschreibt wie Belege entstehen, verarbeitet und archiviert werden | ⬜ Vorlage fehlt (siehe Roadmap) |
| **Belegablage für Papier-/PDF-Belege** | Ohne Beleg keine Buchung | 🟡 Belegverweis (Nummer/Dateiname) Pflicht; Datei-Upload fehlt |

## 2. Sehr nützlich für Sales/Akquise

| Funktion | Nutzen | Status v1.0 |
|---|---|---|
| Angebotsnummer und Bindefrist | Professionelles Angebot, Nachfassen bei Ablauf | ✅ `AN-2026-0001`, gültig 30 Tage, Ablaufmarkierung |
| Angebot angenommen → Lead „gewonnen“ + Aktivität | Pipeline bleibt ohne Doppelpflege aktuell | ✅ |
| Angebot → Rechnung (voll / 40 % Abschlag / Schlussrechnung mit Abzug der Abschläge) | Kein Abtippen, keine Rechenfehler | ✅ |
| Wiederkehrende Rechnungen (Growth Care) | Monatliche Retainer | 🟡 „Als neuen Entwurf kopieren“; keine automatische Serie |
| „Angenommen, aber nicht berechnet“-Liste | Verhindert vergessene Umsätze | ✅ |
| Mahnwesen (Zahlungserinnerung → 1. Mahnung → letzte Mahnung, § 288 BGB Zinsen + 40 € Pauschale) | Cashflow | ✅ als Entwurf + Wiedervorlage, kein Versand |
| Vertriebskennzahlen (Annahmequote, Ø Auftragswert, Umsatz je Kontaktweg) | Lernen, welche Kanäle wirklich zahlen | ✅ Basis |
| Automatische Suche nach neuen Firmen und Ausschreibungen aus offenen Quellen | Pipeline füllen ohne Datenhändler | ✅ v1.1 Lead-Finder (siehe LEADQUELLEN_V11.md) |
| Win/Loss-Gründe als Pflichtfeld bei „verloren“ | Bessere Angebote | ⬜ |
| Nachkalkulation (Ist-Stunden vs. kalkulierte Stunden je Festpreisprojekt) | Für Festpreisgeschäft entscheidend: Lohnen sich die Pakete? | ⬜ **nächster großer Hebel** |
| Projekt-/Delivery-Tracking nach Auftrag (Meilensteine, Abnahme) | Abnahme ist Voraussetzung für Schlussrechnung | ⬜ |
| E-Mail-/Kalender-Anbindung (M365/Google) | Weniger Copy & Paste | ⬜ bewusst nicht ohne Rechts-/Sicherheitsprüfung |
| Vertragsvorlagen (AGB, AV-Vertrag nach Art. 28 DSGVO, Nutzungsrechte) | Agenturen verarbeiten oft Kundendaten (Tracking, Formulare) | ⬜ |

## 3. Nützlich für die Buchhaltung (nächste Ausbaustufen)

| Funktion | Nutzen | Aufwand |
|---|---|---|
| Bankumsatz-Import (CSV / CAMT.053) und Abgleich mit offenen Posten | Größte Zeitersparnis im Alltag | mittel |
| PDF-Erzeugung mit eingebetteter XML (ZUGFeRD/Factur-X) | Eine Datei für Mensch und Maschine | hoch (PDF/A-3 ohne Bibliothek aufwendig) |
| GiroCode (EPC-QR) auf der Rechnung | Schnellere Zahlung | gering–mittel |
| DATEV-Export (EXTF-Buchungsstapel) | Direkte Übergabe an Steuerberatung | mittel, nur mit Testimport beim Steuerbüro |
| Belegupload (PDF/JPG) mit Hash und unveränderbarer Ablage | GoBD-konforme Belegablage im Tool | mittel |
| AfA-/Anlagenverzeichnis | Hardware > 800 € netto | mittel |
| Verschlüsselte Datenbank + Passwortschutz | Schutz bei Laptop-Verlust | mittel |
| Multi-User mit Rollen | Sobald Mitarbeitende/Freelancer mitarbeiten | hoch (eigenes Produkt, siehe ROADMAP) |

## 4. Bewusst nicht im Tool

- **ELSTER-Übermittlung**: erfordert Zertifikat und ERiC-Bibliothek; Fehlerrisiko und Haftung zu hoch für ein lokales Hilfstool. Werte werden vorbereitet, übermittelt wird über „Mein ELSTER“ oder die Steuerberatung.
- **Automatischer Versand von Rechnungen/Mahnungen**: wie bisher keine Sendefunktion. Rechnungen werden heruntergeladen und manuell versendet.
- **Doppelte Buchführung/Bilanz**: SignalDesk bleibt EÜR-orientiert. Für GmbH/UG mit Bilanzpflicht gehört die Buchhaltung zur Steuerberatung bzw. in eine Finanzbuchhaltung.

## Empfohlene Reihenfolge

1. Stammdaten pflegen, erste echte Rechnung als Entwurf → Vorschau → Festschreibung.
2. **Eine** erzeugte XRechnung mit dem [KoSIT-Validator](https://github.com/itplr-kosit/validator) oder einem Online-Validator prüfen, bevor sie an Kunden geht.
3. Mit der Steuerberatung abstimmen: Kontenrahmen, Ist/Soll, Export-Format, Verfahrensdokumentation.
4. Danach entwickeln: Bankimport + Abgleich → Nachkalkulation → Belegupload → DATEV-Export.
