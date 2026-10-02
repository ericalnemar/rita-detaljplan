# Säkerhet

Pluginet hanterar planer, databasanslutningar och (vid leverans till NGP) inloggningsuppgifter. Nyckel och hemlighet till
Lantmäteriets API lagras **inte av pluginet** utan i QGIS autentiseringsdatabas.

En genomgång av vad pluginet gör, vilka data som rör sig vart och kända fynd finns i
[docs/sakerhet.md](docs/sakerhet.md).

## Rapportera en säkerhetsbrist

Beskriv inte säkerhetsbrister i ett öppet ärende. Använd i stället GitHubs
[privata rapportering](https://github.com/ericalnemar/rita-detaljplan/security/advisories/new) (fliken *Security* →
*Report a vulnerability*). Du får svar så snart det går; pluginet underhålls av en enskild person på fritiden.

## Stödda versioner

Bara den senaste utgivna versionen får rättningar.
