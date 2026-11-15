# Upplägg för TapoVac Stats

## Första versionen

Användaren lägger till TapoVac Stats via Enheter och tjänster och väljer en
installerad TapoVac-ADV-instans. Inga ytterligare inloggningsuppgifter behövs.
TapoVac Stats läser bara integrationens redan hämtade data och skickar inga
kommandon till roboten.

## Dataflöde

```text
TapoVac-ADV coordinator
        ↓
upstream.py: kontrollera och kopiera data
        ↓
statistics.py: beräkna rumstatistik
        ↓
sensor.py: publicera Home Assistant-entiteter
        ↓
Markdown-kort: sortera och visa rummen
```

All åtkomst till TapoVac-ADV:s interna datastruktur samlas i `upstream.py`.
Det gör att ändringar i originalintegrationen kan hanteras på ett ställe.
Adaptern ska aldrig ändra originalets listor, lagring eller coordinator.

## Entiteter

Varje rum får tre sensorer:

| Sensor | Värde |
| --- | --- |
| Senast städat | Tidsstämpel från senaste registrerade körningen |
| Städningar idag | Antal distinkta körningstidsstämplar sedan lokal midnatt |
| Städningar senaste 7 dagarna | Antal distinkta körningstidsstämplar under senaste 168 timmarna |

Varje sensor får attribut för `map_id`, `room_id` och datakällans integrationspost.
Senast städat får även `coverage` när detta finns. Unika ID:n baseras på
datakällans integrationspost, kart-ID, rums-ID och mätvärde; namnbyten ska inte
skapa nya entiteter. Rumsnamnet används bara som visningsnamn.

Vi börjar med rum på den aktiva kartan, eftersom upstream räknar täckning mot
den aktiva kartan. Historik för andra kartor får inte beskrivas som komplett.
Entiteter från tidigare kartor behålls vid kartbyte men markeras otillgängliga
tills deras karta åter är aktiv. Beständig identifiering och kartbyte måste
verifieras mot installerad upstream-version innan implementationen låses.

## Uppdateringar och tillgänglighet

- Prenumerera på datakällans coordinator och räkna om när den uppdateras.
- Räkna också om varje minut, så att midnatt och rullande sjudagarsgränser
  slår igenom utan en ny städning.
- Använd Home Assistants lokala tidszon för idag, inklusive sommar- och vintertid.
- Vid borttagen eller otillgänglig datakälla blir sensorerna otillgängliga.
- Vid saknad eller inkompatibel logg ska antal vara okänt, inte noll.
- En tom tillgänglig logg betyder inga registrerade körningar; den bevisar
  inte att rummet aldrig har städats. Visa detta i dokumentationen.
- Vänta på att datakällan har läst in sin lagring efter start.
- Ta bort prenumerationer och timer när integrationen laddas ur.

## Kortet

Första versionen använder Home Assistants vanliga Markdown-kort, utan en egen
JavaScript-resurs. YAML-exemplet ska hitta integrationens rumssensorer via
integrationspost och stabila metadata, inte anta användarens entitetsnamn.

| Rum | Senast städat | Idag | 7 dagar |
| --- | --- | ---: | ---: |
| Kök | Idag 14:32 | 2 | 9 |
| Hall | Idag 14:20 | 1 | 7 |

Rummen sorteras med nyast tidsstämpel först. Rum utan känd tidsstämpel hamnar
sist och visas som okända. Samma tidsstämpel sorteras efter rumsnamn; vi kan
inte avgöra besöksordningen inom samma körning. Otillgängliga värden visas
som streck, aldrig som noll.

## Filer att implementera

```text
custom_components/tapovac_stats/
  __init__.py       Setup, unload och koppling till datakälla
  manifest.json     Beroenden och integrationsmetadata
  const.py          Domän och gemensamma nycklar
  config_flow.py    Val av TapoVac-ADV-instans och dubblettkontroll
  upstream.py       Avgränsad adapter till TapoVac-ADV
  coordinator.py    Uppdateringar, timer och tillgänglighet
  statistics.py    Fristående beräkningar utan Home Assistant-beroende
  sensor.py        Tre sensorer per rum
  strings.json     Texter för inställningar
  translations/
    sv.json
    en.json
examples/
  room_statistics_card.yaml
tests/
  test_statistics.py
  test_upstream.py
  test_lifecycle.py
```

## Verifiering innan första release

Beräkningarna behöver tester för lokal midnatt, tidsomställning, exakt
168-timmarsgräns, dubbletter, saknade data och flera rum med samma namn.
Livscykeln behöver verifieras med återstart, kartbyte, borttagen datakälla
och ändrad upstream-struktur. Testerna ska använda syntetiska fixtures;
inga privata robotdata eller autentiseringsuppgifter ska finnas i repot.

Första releasen kräver verifiering mot användarens installerade TapoVac-ADV
och Home Assistant. Statisk läsning av senaste upstream räcker inte för att
lova kompatibilitet med en annan installerad version.
