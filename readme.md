# Bez Filtra
Bez Filtra je moderná webová aplikácia postavená na frameworku Flask, ktorá slúži na inteligentnú agregáciu a sumarizáciu správ z rôznych RSS zdrojov. Cieľom projektu je poskytnúť používateľovi čistý prehľad o najdôležitejších udalostiach dňa bez duplicitného obsahu a balastu.
# Hlavne funkcie
RSS Agregácia: Automatický zber dát z viacerých zdrojov pomocou knižnice feedparser.
Čistenie obsahu: Odstránenie HTML tagov a irelevantných prvkov pomocou BeautifulSoup.
Inteligentné zoskupovanie: Články o rovnakých témach sú identifikované a zoskupené pomocou Jaccardovho koeficientu, čo eliminuje duplicitu správ.
AI Sumarizácia: Využitie Gemini API na generovanie stručných, výstižných a prehľadných bodov z každej skupiny článkov.
# Technologie
Backend: Flask (Python)
Parsing: Feedparser & BeautifulSoup4
Spracovanie dát: Jaccard Similarity Coefficient
LLM: Google Gemini API

# Spustenie
Pre spustenie aplikácie na vašom lokálnom stroji postupujte podľa týchto krokov:

Klonovanie repozitára:
Bash
git clone https://github.com/vas-profil/bez-filtra.git
cd bez-filtra
Vytvorenie virtuálneho prostredia:

Bash
python -m venv venv
# Aktivácia na Windows
venv\Scripts\activate
# Aktivácia na macOS/Linux:
source venv/bin/activate
Inštalácia závislostí:

Bash
pip install -r requirements.txt
Nastavenie API kľúča:
Vytvorte súbor .env a vložte doň svoj kľúč pre Gemini API:

Útržok kódu
GEMINI_API_KEY=vas_tajny_kluc
Spustenie aplikácie:

Bash
python app.py
Aplikácia bude dostupná na http://127.0.0.1:5000.

Licencia a podmienky použitia
Tento projekt je Open Source. Môžete ho voľne používať, upravovať a šíriť.

Podmienka použitia: Pri akomkoľvek využití tohto kódu alebo jeho častí v iných projektoch je potrebné uviesť pôvodného autora (credit).
