Du skal bygge en app for meg som kjører i streamlit
den kan ha tilgang til supabase database. 

Vi skal ha ett dashboard der jeg kan endre og legge til watchlister på aksjer. 
I listene skal livekurs, og kursutvikliing siden åpning vises(evnt siste dag)
Når jeg legger til en aksje, skal jeg og kunen legge til en kommentar. 
Jeg skal og ha en journal/dagbok, der jeg velger ticker, og kan skrive en kommentar som lagres med dato og tid. @
Jeg ksal kunne scrolle i dagboken, samt søke. Når jeg senere velger meg inn på en ticker, skal og kommentarene på tickeren være synlig. 
JEg skal kunne legge inn kjøp og salg på aksjer. Det skal vises åpne og lukkede posisjoner, og jeg skal kunne skrive inn kommentar. Jeg skal da få resulat på trade, samt en time value score (holdetid/resultat)


Softwaren skal ha en funskjon som henter kurs fra Oslo børs, SAP500 og Stockholm børs, (vi kan starte med oslo)
Kanskje flere i fremtiden. 
Historisk kurs skal lagres for å raskt kunne hentes. Som en parquet fil?
Appen skal screene valgt børs, den skal da lage tabell basert på hvilke
aksjer som tilfredstiller minervinis trend template.
Den skal og automatisk kunne detektere pivots. Og fange aksjer som nylig har brutt med volum, og aksjer som har brudd uten volum, de som har 7/7 kriterier, og de som er i ferd med å bryte. Det skal lages en logisk tabell med nødvendig informasjon. Blant annet Relativt volum mot volum sma50. Tabellen skal være fint bygget opp med ui og logiske farger. 

Jeg skal og ha en screeningfunskjon som søker alle tickere og lager en komplett liste. Samt utvikling siste 3-6mnd og 1 år.HEr har vi all data vi bruker i appen. JEg skal så kunne bruke avansert database filtrering, da kan jeg filtrere ut aksjer som eks er innenfor 5% av 52w high og har ett relativt volum over volum sma50 som eksempel. 

DEt skal og være en screeningfunskjon som kun henter askjer med for lite data til å gå inn i minervini (nye ipoer)

Du skal bygge det på en fin måte ift datahenting, catching og effetkvitet. Dlik at softawaren flyter fint og elegant. 

Jeg skal kunne velge alle tickere da skal jeg kunne få opp candle chart fra aksjene. 
Det skal være gratis, det er virkig at jeg skal kunne tegne enkle linjer og gjøre en teknisk analyse i chart som lagres. 
KAn highcharts brukes?
i minervini scanneren lages det brudd mot pivots. Historiske brudd samt pågående pivots skal kunne vises i chart. Samt datoer der 7/7 kriterier i minervnini tmeplate fullføres og når det ikke er 7/7 lengre. 
Datahenting av kurser, kan gjøres automatisk etter børsslutt, eks kl 17 på oslo, 19 for stockholm og 23 for USA?

Du skal tenke UI og brukervennlighet hele veien.