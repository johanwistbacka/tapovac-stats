# TapoVac Stats

En kompletterande Home Assistant-integration för rumsstatistik från
[TapoVac-ADV](https://github.com/jan-tdy/TapoVac-ADV).
Originalintegrationen kan fortsätta uppdateras som vanligt; ingen fork behövs.

## Funktioner

- Tre sensorer per rum: senaste registrerade städtid, antal idag och antal
  de senaste 168 timmarna.
- En översiktssensor med rummen sorterade efter senaste städtillfälle,
  senast städade överst.
- Ett vanligt Markdown-kort med kolumnerna Rum, Senast, Idag och 7 dagar.
- Uppdateringar när TapoVac-ADV ändras och varje minut för tidsgränser.
- Val av installerad TapoVac-ADV via Enheter och tjänster. Inga extra lösenord.

## Status

Version 0.1.0 är en första testversion. Statistiktester använder syntetiska data.
Alla 16 tester passerar, inklusive livscykel och kortmall mot Home Assistant
2025.1.4 på Python 3.12, med en simulerad TapoVac-datakälla.
Kopplingen till en verklig robot och användarens installerade TapoVac-ADV
måste verifieras innan normal användning. Interna upstream-ändringar kan
kräva uppdatering av TapoVac Stats.

## Installation

TapoVac-ADV måste redan vara installerat och konfigurerat.

### Via HACS

1. Lägg till `https://github.com/johanwistbacka/tapovac-stats` under HACS →
   Anpassade förråd, kategori **Integration**.
2. Hämta TapoVac Stats och starta om Home Assistant.
3. Öppna Inställningar → Enheter och tjänster → Lägg till integration.
4. Välj **TapoVac Stats** och därefter din TapoVac-ADV-installation.

Projektet är ett anpassat HACS-repository, inte en del av HACS standardlista.

### Manuellt

Kopiera katalogen `custom_components/tapovac_stats` till
`/config/custom_components/tapovac_stats`, starta om Home Assistant och lägg
sedan till integrationen enligt steg 3–4 ovan.

## Kortet

Öppna integrationens enhet och hitta sensorn **Rumsöversikt**. Kopiera
[examples/room_statistics_card.yaml](examples/room_statistics_card.yaml) till
ett manuellt dashboardkort och ersätt `sensor.byt_till_din_rumsoversikt` med
dess entitets-ID. Inga andra korttillägg behövs.

Kortet visar bara den aktiva kartans rum. Rum utan känd städtid hamnar sist.
Rum från andra kartor blir otillgängliga när kartan byts, och återkommer när
kartan är aktiv igen. Rumsnamn kan ändras utan att unika entitets-ID:n ändras.

## Vad räknas?

Idag betyder sedan midnatt i Home Assistants tidszon. Sju dagar betyder
168 timmar bakåt, även när sommartiden ändras. Räknarna visar registrerade
körningar per rum; dubbletter av samma körningstidsstämpel räknas bara en gång.

Den granskade TapoVac-ADV-versionen räknar ett rum som städat från 20 procent
karttäckning. Tidsstämpeln kommer från körningens historik, inte från exakt
sluttid i varje rum. Rum i samma körning kan ha samma tidsstämpel.

TapoVac-ADV sparar rumsloggen i åtta dagar och läser in äldre robotposter
successivt. Historiken kan därför vara ofullständig, särskilt efter installation
eller uppgradering. Noll betyder inga registrerade städningar i den tillgängliga
loggen. Om loggen saknas blir antal okänt. Vid otillgänglig datakälla visar
kortet ett meddelande i stället för gamla antal.

## Kompatibilitet

Datakällan läses via en avgränsad adapter till TapoVac-ADV:s interna coordinator:
`rooms_named()`, `map_id`, `rooms_last_cleaned`, `rooms_clean_log`,
`_freshness_loaded` och `last_update_success`. Integrationen skriver inte i
originalets data och anropar inte roboten direkt.

Granskad upstream-revision: `3677024c358eeb3d3281e5be9ca5af6729d11520`.
Äldre versioner utan dessa strukturer kan ge otillgängliga sensorer.

## Utveckling och tester

Kör `python -m unittest discover -s tests -v` från repots rot.
Beräkningstesterna kräver bara Python. Med Home Assistant installerat körs
även tester för konfiguration, uppdateringar, återhämtning, kartbyte och kortmall.
En reproducerbar testmiljö kan skapas med Python 3.12 och
`pip install -r requirements-test.txt` i en separat virtuell miljö.
Se [DESIGN.md](DESIGN.md) för arkitektur och ursprungliga designval.
