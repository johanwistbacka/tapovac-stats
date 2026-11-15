# TapoVac Stats

En kompletterande Home Assistant-integration för statistik från
[TapoVac-ADV](https://github.com/jan-tdy/TapoVac-ADV).

TapoVac Stats ska läsa data från den installerade TapoVac-ADV-integrationen.
Originalintegrationen kan fortsätta uppdateras som vanligt; ingen egen fork behövs.

## Status

Detta är en projektgrund, inte en fungerande statistik-integration ännu.
Installation och konfiguration kommer när dataläsning och sensorer är implementerade.
`hacs.json` och katalogstrukturen är förberedda för distribution som ett eget
HACS-repository; projektet är ännu inte publicerat eller godkänt i HACS.

## Planerad funktion

- En sensor per rum med senaste registrerade städtid.
- Antal registrerade städningar per rum idag, enligt Home Assistants tidszon.
- Antal registrerade städningar per rum under de senaste 168 timmarna.
- Ett dashboardkort som sorterar rummen efter senaste städning, nyast först.
- Identifiering av rum med både integrationspost, kart-ID och rums-ID.
- Tydlig hantering när TapoVac-ADV saknas eller datan inte är tillgänglig.

## Datakälla och begränsningar

Den granskade TapoVac-ADV-koden lagrar `rooms_last_cleaned` och
`rooms_clean_log` i sin coordinator. Loggen sparas i åtta dagar och överlever
omstarter. Loggen exponeras för närvarande inte som vanliga entitetsattribut.
TapoVac Stats behöver därför en avgränsad adapter till integrationens interna
data. Ändringar i TapoVac-ADV kan kräva att adaptern uppdateras.

Granskad upstream-revision:
`3677024c358eeb3d3281e5be9ca5af6729d11520`.

Upstream räknar ett rum som städat från 20 procent karttäckning. Tidsstämpeln
kommer från körningens historik, inte från exakt sluttid i varje rum.
Historik kan vara ofullständig under inläsning eller om robotens äldre
poster inte längre är tillgängliga. Saknad historik ska inte visas som ett
bekräftat antal noll.

## Nästa utvecklingssteg

Det konkreta upplägget för sensorer, dataflöde, uppdateringar och kort finns i
[DESIGN.md](DESIGN.md).

1. Kontrollera datastrukturen mot användarens installerade TapoVac-ADV-version.
2. Implementera adapter och val av TapoVac-ADV-enhet via konfigurationsflöde.
3. Implementera rumssensorer med uppdatering även vid midnatt och när äldre
   städningar lämnar sjudagarsintervallet.
4. Testa tidszoner, omstarter, flera kartor och otillgänglig datakälla.
5. Lägg till installationsguide och kortets YAML.

## Projektstruktur

```text
custom_components/tapovac_stats/  Integrationsgrund
hacs.json                       Metadata för HACS
```
