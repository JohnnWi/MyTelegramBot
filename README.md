# Procedura

1. Vai su Telegram e cerca `@BotFather` e crea un nuovo bot (salvati il Telegram Token).
2. Vai su Telegram e cerca `@userinfobot`, fai start e salvati il tuo ID (in questo modo solo tu potrai avviare e utilizzare il bot).
3. Vai su [CoinMarketCap API](https://coinmarketcap.com/api/pricing/), registrati per un account gratis e salvati l'API Key che ti forniscono.
4. Apri la directory del tuo progetto, apri il file `.env` e inserisci i vari dati dopo il segno `=`.
5. Apri la directory e installa `pip` e `python` (per Linux): (se necessario usa un comando alla volta)

    ```sh
    sudo apt update
    sudo apt install python3 python3-pip
    python3 --version
    pip3 --version
    ```

6. Installa i pacchetti richiesti con `pip`:

    ```sh
    pip install python-telegram-bot pyTelegramBotAPI requests python-dotenv APScheduler
    pip install pandas
    pip install openpyxl
    ```

7. Avvia lo script (se non ricevi nessun messaggio allora sta funzionando):

    ```sh
    python crypto2.py
    ```

    oppure

    ```sh
    python3 crypto2.py
    ```

8. Vai su Telegram, cerca il tuo bot e invia il comando `/start`.
9. Ricordati che quando aggiungi le transazioni NON devi inserire il nome della crypto ma il simbolo. Per esempio invece di scrivere Bitcoin, scrivi `BTC`.

RICORDATI CHE SE BLOCCHI IL CODICE, IL BOT NON FUNZIONERà PIù. DEVE ESSERE SEMPRE OPERATIVO

N.B. SE HAI ERRORI, FORNISCI IL CODICE A CHATGPT E INSIEME L'ERRORE E TI AIUTERà
