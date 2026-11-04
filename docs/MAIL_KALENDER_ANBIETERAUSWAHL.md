# Geschäfts-Mail und Termine: Anbieterwahl für Windows

SignalDesk v0.9 läuft **ohne** externen Provider. Mailentwürfe und Termine sind lokale Dateien/Datensätze. Später muss eine autorisierte Integration separat entwickelt werden.

## Auswahlliste (Deutschland, Oktober 2026)

- **Microsoft 365 Business Basic:** Outlook-/Exchange-E-Mail mit eigener Domain, Kalender und Microsoft Bookings. Deutsche Microsoft-Preisseite nennt 6,07 €/Nutzer/Monat bei jährlicher Abrechnung, zzgl. MwSt. Preise/Tarife vor Abschluss prüfen: https://www.microsoft.com/de-de/microsoft-365/business/microsoft-365-plans-and-pricing
- **Google Workspace Business Starter:** Gmail mit eigener Domain, Google Kalender und Meet. Deutsche Google-Seite nennt 6,80 €/Nutzer/Monat bei Jahresbindung bzw. 8,10 € flexibel; aktuell gültige Preise prüfen: https://workspace.google.com/intl/de/

**Für Windows** wäre Microsoft 365 Business Basic eine sinnvolle Standardwahl, wenn du noch keinen Anbieter hast. Beide Optionen sind geeignet; du musst noch keine wählen, um v0.9 zu nutzen.

## Sinnvolle Einrichtungsreihenfolge

1. Deine Domain registrieren und Eigentümerschaft klären.
2. Business-Postfach bei Anbieter deiner Wahl anlegen.
3. DNS für E-Mail-Zustellung korrekt einrichten (MX, SPF, DKIM und DMARC), zunächst mit vorsichtiger DMARC-Policy.
4. Geschäftliche Signatur, Datenschutz und erforderliche geschäftliche Angaben prüfen.
5. Buchungsseite/Terminlinks einrichten; zeitliche Verfügbarkeit mit deiner echten Delivery-Zeit abstimmen.
6. Später SignalDesk per OAuth/Graph bzw. Google APIs mit **minimal notwendigen Berechtigungen** verbinden. Tokens sicher verschlüsselt speichern; keine Passwörter oder Schlüssel ins Git-Repository.
7. E-Mail-Entwürfe erst nach menschlicher Freigabe versenden. Keine automatisierte unerbetene B2B-Werbung.

## Rechtsgrenze

B2B-Werbe-E-Mails sind auch an veröffentlichte geschäftliche Adressen grundsätzlich einwilligungspflichtig (Ausnahme nach § 7 Abs. 3 UWG nur eng bei Bestandskunden). Bei B2B-Werbeanrufen ist eine konkrete, dokumentierte mutmaßliche Einwilligung im Einzelfall nötig. Öffentlich gefundene Manager, Telefonnummern oder Websiteprobleme ersetzen diese Grundlage nicht.
