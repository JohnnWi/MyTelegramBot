import os
import telebot
import sqlite3
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import locale
from apscheduler.schedulers.background import BackgroundScheduler

# Caricamento delle variabili d'ambiente
load_dotenv()

locale.setlocale(locale.LC_ALL, '')

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CMC_API_KEY = os.getenv('CMC_API_KEY')
AUTHORIZED_USER_ID = int(os.getenv('AUTHORIZED_USER_ID'))

# Inizializzazione del bot
bot = telebot.TeleBot(TELEGRAM_TOKEN)

def is_authorized(message):
    return message.from_user.id == AUTHORIZED_USER_ID

def authorized_only(func):
    def wrapper(message):
        if is_authorized(message):
            return func(message)
        else:
            bot.reply_to(message, "Non sei autorizzato ad utilizzare questo bot.")
    return wrapper

# Funzioni di utilità per il database
def get_db_connection():
    conn = sqlite3.connect('crypto_tracker.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
     user_id INTEGER,
     crypto TEXT,
     quantity REAL,
     price REAL,
     date DATE)
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS price_alerts
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
     user_id INTEGER,
     crypto TEXT,
     target_price REAL,
     is_above BOOLEAN)
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS scheduled_reports
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
     user_id INTEGER,
     time TEXT,
     frequency TEXT)
    ''')
    conn.commit()
    conn.close()

# Inizializzazione del database
init_db()

# Funzioni di utilità
def get_current_price(crypto):
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
    parameters = {
        'symbol': crypto,
        'convert': 'USD'
    }
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': CMC_API_KEY,
    }
    
    try:
        response = requests.get(url, params=parameters, headers=headers)
        data = response.json()
        
        if response.status_code == 200:
            return data['data'][crypto]['quote']['USD']['price'], data['data'][crypto]['quote']['USD']['percent_change_24h']
        else:
            print(f"Errore nell'ottenere il prezzo per {crypto}: {data['status']['error_message']}")
            return None, None
    except Exception as e:
        print(f"Errore nella richiesta API per {crypto}: {e}")
        return None, None

# Handler dei comandi
@bot.message_handler(commands=['start', 'help'])
@authorized_only
def send_welcome(message):
    help_text = """
    Comandi disponibili:
    /add - Aggiungi una nuova transazione
    /addmultiple - Aggiungi multiple transazioni in una volta
    /balance - Mostra il saldo attuale e le performance
    /profit - Mostra il profitto/perdita totale
    /weekly - Mostra il confronto con 7 giorni fa
    /history <crypto> - Mostra lo storico delle transazioni per una criptovaluta
    /deleteedit - Elimina o modifica una transazione esistente
    /reset - Cancella tutti i dati salvati
    /debug - Mostra le ultime 20 transazioni nel database
    /setalert - Imposta un avviso di prezzo
    /setreport - Imposta un report periodico del portafoglio
    /deletereport - Cancella il report periodico programmato
    /showreport - Mostra il report periodico attualmente impostato
    """
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['add'])
@authorized_only
def add_transaction_start(message):
    msg = bot.reply_to(message, "Inserisci la transazione nel formato: SIMBOLO PREZZO QUANTITÀ DATA (es. BTC 30000 0.1 25-12-2023)")
    bot.register_next_step_handler(msg, process_add_transaction)

def process_add_transaction(message):
    try:
        crypto, price, quantity, date = message.text.split()
        price = float(price)
        quantity = float(quantity)
        date = datetime.strptime(date, "%d-%m-%Y").date()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO transactions (user_id, crypto, quantity, price, date) VALUES (?, ?, ?, ?, ?)",
                       (message.from_user.id, crypto.upper(), quantity, price, date))
        conn.commit()
        conn.close()
        
        bot.reply_to(message, f"Transazione aggiunta con successo: {quantity:.4f} {crypto.upper()} a ${price:.2f} il {date.strftime('%d-%m-%Y')}")
    except ValueError:
        bot.reply_to(message, "Formato non valido. Usa: SIMBOLO PREZZO QUANTITÀ DATA (es. BTC 30000 0.1 25-12-2023)")
    except Exception as e:
        bot.reply_to(message, f"Si è verificato un errore: {str(e)}")

@bot.message_handler(commands=['addmultiple'])
@authorized_only
def add_multiple_transactions_start(message):
    instructions = """
    Inserisci le transazioni multiple, una per riga, nel seguente formato:
    SIMBOLO PREZZO QUANTITÀ DATA

    Esempio:
    BTC 30000 0.1 25-12-2023
    ETH 2000 1.5 26-12-2023
    
    Invia 'FINE' su una nuova riga quando hai finito di inserire le transazioni.
    """
    msg = bot.reply_to(message, instructions)
    bot.register_next_step_handler(msg, process_add_multiple_transactions)

def process_add_multiple_transactions(message):
    if message.text.upper() == 'FINE':
        bot.reply_to(message, "Inserimento multiplo completato.")
        return

    transactions = message.text.split('\n')
    success_count = 0
    errors = []

    conn = get_db_connection()
    cursor = conn.cursor()

    for transaction in transactions:
        try:
            crypto, price, quantity, date = transaction.split()
            price = float(price)
            quantity = float(quantity)
            date = datetime.strptime(date, "%d-%m-%Y").date()
            
            cursor.execute("INSERT INTO transactions (user_id, crypto, quantity, price, date) VALUES (?, ?, ?, ?, ?)",
                           (message.from_user.id, crypto.upper(), quantity, price, date))
            success_count += 1
        except ValueError:
            errors.append(transaction)
        except Exception as e:
            errors.append(f"{transaction} - Errore: {str(e)}")

    conn.commit()
    conn.close()

    response = f"Transazioni aggiunte con successo: {success_count}"
    if errors:
        response += f"\nTransazioni non valide: {len(errors)}"
        for error in errors:
            response += f"\n- {error}"
    
    msg = bot.reply_to(message, response)
    bot.register_next_step_handler(msg, process_add_multiple_transactions)

@bot.message_handler(commands=['balance'])
@authorized_only
def show_balance(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT crypto, 
           SUM(quantity) as total_quantity, 
           SUM(quantity * price) as total_cost,
           MIN(date) as first_purchase_date
    FROM transactions 
    WHERE user_id = ?
    GROUP BY crypto
    """, (message.from_user.id,))
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        bot.reply_to(message, "📊 Non hai ancora aggiunto alcuna transazione.")
        return
    
    response = "📊 *Il tuo Portafoglio Crypto*\n\n"
    total_portfolio_value = 0
    total_portfolio_cost = 0
    
    for result in results:
        crypto = result['crypto']
        quantity = result['total_quantity']
        cost = result['total_cost']
        first_purchase_date = datetime.strptime(result['first_purchase_date'], '%Y-%m-%d').date()
        current_price, percent_change_24h = get_current_price(crypto)
        
        if current_price is not None:
            current_value = quantity * current_price
            total_portfolio_value += current_value
            total_portfolio_cost += cost
            profit_loss = current_value - cost
            profit_loss_percentage = (profit_loss / cost) * 100
            days_held = (datetime.now().date() - first_purchase_date).days
            
            response += f"*{crypto}*:\n"
            response += f"Quantità: {quantity:.4f}\n"
            response += f"Valore attuale: ${current_value:.2f}\n"
            response += f"Prezzo attuale: ${current_price:.2f}\n"
            response += f"Variazione 24h: {percent_change_24h:.2f}%\n"
            response += f"P/L: ${profit_loss:.2f} ({profit_loss_percentage:.2f}%)\n"
            response += f"Giorni di detenzione: {days_held}\n\n"
    
    total_profit_loss = total_portfolio_value - total_portfolio_cost
    total_profit_loss_percentage = (total_profit_loss / total_portfolio_cost) * 100
    
    response += f"*📈 Performance totale del portafoglio*:\n"
    response += f"*Valore totale: ${total_portfolio_value:.2f}*\n"
    response += f"Costo totale: ${total_portfolio_cost:.2f}\n"
    response += f"*P/L totale: ${total_profit_loss:.2f} ({total_profit_loss_percentage:.2f}%)*\n"
    
    bot.reply_to(message, response, parse_mode='Markdown')

@bot.message_handler(commands=['profit'])
@authorized_only
def show_profit(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT crypto, SUM(quantity) as total_quantity, SUM(quantity * price) as total_cost FROM transactions WHERE user_id = ? GROUP BY crypto", (message.from_user.id,))
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        bot.reply_to(message, "Non hai ancora aggiunto alcuna transazione.")
        return
    
    total_profit = 0
    response = "Profitto/Perdita:\n\n"
    for result in results:
        crypto = result['crypto']
        quantity = result['total_quantity']
        cost = result['total_cost']
        current_price, _ = get_current_price(crypto)
        if current_price is not None:
            current_value = quantity * current_price
            profit = current_value - cost
            profit_percentage = (profit / cost) * 100
            total_profit += profit
            response += f"{crypto}:\n"
            response += f"  Profitto/Perdita: ${profit:.2f}\n"
            response += f"  Percentuale: {profit_percentage:+.2f}%\n\n"
        else:
            response += f"{crypto}: Prezzo non disponibile\n\n"
    
    response += f"Profitto/Perdita totale: ${total_profit:.2f}"
    bot.reply_to(message, response)

@bot.message_handler(commands=['weekly'])
@authorized_only
def show_weekly_comparison(message):
    seven_days_ago = datetime.now().date() - timedelta(days=7)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT crypto, 
           SUM(CASE WHEN date <= ? THEN quantity ELSE 0 END) as quantity_7_days_ago,
           SUM(quantity) as current_quantity
    FROM transactions 
    WHERE user_id = ?
    GROUP BY crypto
    """, (seven_days_ago, message.from_user.id))
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        bot.reply_to(message, "Non hai transazioni sufficienti per un confronto settimanale.")
        return
    
    response = "Confronto con 7 giorni fa:\n\n"
    for result in results:
        crypto = result['crypto']
        quantity_7_days_ago = result['quantity_7_days_ago']
        current_quantity = result['current_quantity']
        current_price, _ = get_current_price(crypto)
        if current_price is not None:
            value_7_days_ago = quantity_7_days_ago * current_price
            current_value = current_quantity * current_price
            difference = current_value - value_7_days_ago
            difference_percentage = (difference / value_7_days_ago) * 100 if value_7_days_ago != 0 else 0
            
            response += f"{crypto}:\n"
            response += f"  7 giorni fa: {quantity_7_days_ago:.4f} (${value_7_days_ago:.2f})\n"
            response += f"  Oggi: {current_quantity:.4f} (${current_value:.2f})\n"
            response += f"  Differenza: ${difference:.2f} ({difference_percentage:+.2f}%)\n\n"
        else:
            response += f"{crypto}: Prezzo non disponibile\n\n"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=['history'])
@authorized_only
def show_history(message):
    try:
        _, crypto = message.text.split()
        crypto = crypto.upper()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT quantity, price, date FROM transactions WHERE user_id = ? AND crypto = ? ORDER BY date", (message.from_user.id, crypto))
        transactions = cursor.fetchall()
        conn.close()
        
        if not transactions:
            bot.reply_to(message, f"Non hai transazioni per {crypto}.")
            return
        
        response = f"Storico delle transazioni per {crypto}:\n\n"
        for transaction in transactions:
            response += f"Data: {transaction['date']}, Quantità: {transaction['quantity']:.4f}, Prezzo: ${transaction['price']:.2f}\n"
        
        current_price, _ = get_current_price(crypto)
        if current_price is not None:
            response += f"\nPrezzo attuale di {crypto}: ${current_price:.2f}"
        
        bot.reply_to(message, response)
    except ValueError:
        bot.reply_to(message, "Formato non valido. Usa: /history SIMBOLO (es. /history BTC)")

@bot.message_handler(commands=['reset'])
@authorized_only
def reset_data(message):
    msg = bot.reply_to(message, "Sei sicuro di voler cancellare tutti i dati? Questa azione non può essere annullata. Rispondi 'SI' per confermare.")
    bot.register_next_step_handler(msg, confirm_reset)

def confirm_reset(message):
    if message.text.upper() == 'SI':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM transactions WHERE user_id = ?", (message.from_user.id,))
        conn.commit()
        conn.close()
        bot.reply_to(message, "Tutti i tuoi dati sono stati cancellati.")
    else:
        bot.reply_to(message, "Operazione annullata. I tuoi dati sono al sicuro.")

@bot.message_handler(commands=['deleteedit'])
@authorized_only
def deleteedit_transaction_start(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, crypto, quantity, price, date FROM transactions WHERE user_id = ? ORDER BY date DESC LIMIT 10", (message.from_user.id,))
    transactions = cursor.fetchall()
    conn.close()
    
    if not transactions:
        bot.reply_to(message, "Non hai transazioni da modificare o eliminare.")
        return
    
    response = "Seleziona il numero della transazione che vuoi modificare o eliminare:\n\n"
    for i, trans in enumerate(transactions, 1):
        response += f"{i}. {trans['crypto']} - {trans['quantity']:.4f} @ ${trans['price']:.2f} on {trans['date']}\n"
    
    msg = bot.reply_to(message, response)
    bot.register_next_step_handler(msg, process_delete_selection, transactions)

def process_delete_selection(message, transactions):
    try:
        selection = int(message.text) - 1
        if 0 <= selection < len(transactions):
            selected_transaction = transactions[selection]
            msg = bot.reply_to(message, f"Hai selezionato: {selected_transaction['crypto']} - {selected_transaction['quantity']:.4f} @ ${selected_transaction['price']:.2f} on {selected_transaction['date']}\n"
                                        "Vuoi eliminare (E) o modificare (M) questa transazione?")
            bot.register_next_step_handler(msg, process_delete_action, selected_transaction)
        else:
            bot.reply_to(message, "Selezione non valida. Per favore, usa /deleteedit per ricominciare.")
    except ValueError:
        bot.reply_to(message, "Input non valido. Per favore, inserisci un numero. Usa /deleteedit per ricominciare.")

def process_delete_action(message, transaction):
    action = message.text.upper()
    if action == 'E':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM transactions WHERE id = ?", (transaction['id'],))
        conn.commit()
        conn.close()
        bot.reply_to(message, "Transazione eliminata con successo.")
    elif action == 'M':
        msg = bot.reply_to(message, "Inserisci i nuovi dettagli della transazione nel formato: SIMBOLO PREZZO QUANTITÀ DATA (es. BTC 30000 0.1 25-12-2023)")
        bot.register_next_step_handler(msg, process_modify_transaction, transaction['id'])
    else:
        bot.reply_to(message, "Azione non valida. Per favore, usa /deleteedit per ricominciare.")

def process_modify_transaction(message, transaction_id):
    try:
        crypto, price, quantity, date = message.text.split()
        price = float(price)
        quantity = float(quantity)
        date = datetime.strptime(date, "%d-%m-%Y").date()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE transactions SET crypto = ?, quantity = ?, price = ?, date = ? WHERE id = ?",
                       (crypto.upper(), quantity, price, date, transaction_id))
        conn.commit()
        conn.close()
        
        bot.reply_to(message, f"Transazione modificata con successo: {quantity:.4f} {crypto.upper()} a ${price:.2f} il {date.strftime('%d-%m-%Y')}")
    except ValueError:
        bot.reply_to(message, "Formato non valido. Usa: SIMBOLO PREZZO QUANTITÀ DATA (es. BTC 30000 0.1 25-12-2023)")
    except Exception as e:
        bot.reply_to(message, f"Si è verificato un errore: {str(e)}")

@bot.message_handler(commands=['debug'])
@authorized_only
def debug_transactions(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC LIMIT 20", (message.from_user.id,))
    transactions = cursor.fetchall()
    conn.close()
    
    if not transactions:
        bot.reply_to(message, "Non ci sono transazioni nel database per questo utente.")
        return
    
    response = "Ultime 20 transazioni nel database:\n\n"
    for trans in transactions:
        response += f"ID: {trans['id']}, Crypto: {trans['crypto']}, Quantità: {trans['quantity']:.4f}, Prezzo: ${trans['price']:.2f}, Data: {trans['date']}\n"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=['setalert'])
@authorized_only
def set_price_alert(message):
    msg = bot.reply_to(message, "Inserisci l'avviso di prezzo nel formato: SIMBOLO PREZZO SOPRA/SOTTO (es. BTC 30000 SOPRA)")
    bot.register_next_step_handler(msg, process_price_alert)

def process_price_alert(message):
    try:
        crypto, price, direction = message.text.split()
        price = float(price)
        is_above = direction.upper() == 'SOPRA'
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO price_alerts (user_id, crypto, target_price, is_above) VALUES (?, ?, ?, ?)",
                       (message.from_user.id, crypto.upper(), price, is_above))
        conn.commit()
        conn.close()
        
        direction_text = "sopra" if is_above else "sotto"
        bot.reply_to(message, f"Avviso impostato per {crypto.upper()} quando il prezzo sarà {direction_text} ${price:.2f}")
    except ValueError:
        bot.reply_to(message, "Formato non valido. Usa: SIMBOLO PREZZO SOPRA/SOTTO (es. BTC 30000 SOPRA)")

@bot.message_handler(commands=['setreport'])
@authorized_only
def set_report(message):
    msg = bot.reply_to(message, "Inserisci la frequenza del report nel formato: FREQUENZA ORARIO\n"
                                "Frequenze disponibili: daily, every_12_hours, every_3_days\n"
                                "Esempio: daily 09:00")
    bot.register_next_step_handler(msg, process_report_frequency)

def process_report_frequency(message):
    try:
        frequency, time_str = message.text.split()
        time = datetime.strptime(time_str, "%H:%M").time()
        
        if frequency not in ['daily', 'every_12_hours', 'every_3_days']:
            raise ValueError("Frequenza non valida")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO scheduled_reports (user_id, time, frequency) VALUES (?, ?, ?)",
                       (message.from_user.id, time.strftime("%H:%M"), frequency))
        conn.commit()
        conn.close()
        
        bot.reply_to(message, f"Report impostato con frequenza '{frequency}' alle {time.strftime('%H:%M')}")
        
        # Aggiorna lo scheduler
        update_report_scheduler()
    except ValueError as e:
        bot.reply_to(message, f"Formato non valido. {str(e)}")

@bot.message_handler(commands=['deletereport'])
@authorized_only
def delete_report(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scheduled_reports WHERE user_id = ?", (message.from_user.id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    if deleted:
        bot.reply_to(message, "Il tuo report programmato è stato cancellato.")
        update_report_scheduler()
    else:
        bot.reply_to(message, "Non hai report programmati da cancellare.")

@bot.message_handler(commands=['showreport'])
@authorized_only
def show_report(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT time, frequency FROM scheduled_reports WHERE user_id = ?", (message.from_user.id,))
    report = cursor.fetchone()
    conn.close()
    
    if report:
        time, frequency = report
        bot.reply_to(message, f"Hai un report programmato con frequenza '{frequency}' alle {time}")
    else:
        bot.reply_to(message, "Non hai report programmati al momento.")

def send_scheduled_report(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT crypto, SUM(quantity) as total_quantity
    FROM transactions 
    WHERE user_id = ?
    GROUP BY crypto
    """, (user_id,))
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        bot.send_message(user_id, "Non hai transazioni nel tuo portafoglio.")
        return
    
    response = "📊 *Resoconto del tuo Portafoglio*\n\n"
    total_portfolio_value = 0
    total_portfolio_value_24h_ago = 0
    
    for result in results:
        crypto = result['crypto']
        quantity = result['total_quantity']
        current_price, percent_change_24h = get_current_price(crypto)
        
        if current_price is not None:
            value = quantity * current_price
            value_24h_ago = value / (1 + percent_change_24h/100)
            change_value = value - value_24h_ago
            total_portfolio_value += value
            total_portfolio_value_24h_ago += value_24h_ago
            
            response += f"*{crypto}*: ${value:.2f} (${change_value:.2f}, {percent_change_24h:.2f}%)\n"
    
    change_24h = total_portfolio_value - total_portfolio_value_24h_ago
    change_24h_percent = (change_24h / total_portfolio_value_24h_ago) * 100
    
    response += f"\n*Totale: ${total_portfolio_value:.2f}*\n"
    response += f"Variazione 24h: ${change_24h:.2f} ({change_24h_percent:.2f}%)"
    
    bot.send_message(user_id, response, parse_mode='Markdown')

def update_report_scheduler():
    scheduler.remove_all_jobs()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scheduled_reports")
    reports = cursor.fetchall()
    conn.close()
    
    for report in reports:
        user_id = report['user_id']
        time = datetime.strptime(report['time'], "%H:%M").time()
        frequency = report['frequency']
        
        if frequency == 'daily':
            scheduler.add_job(send_scheduled_report, 'cron', hour=time.hour, minute=time.minute, args=[user_id])
        elif frequency == 'every_12_hours':
            scheduler.add_job(send_scheduled_report, 'cron', hour=f"{time.hour},{(time.hour+12)%24}", minute=time.minute, args=[user_id])
        elif frequency == 'every_3_days':
            scheduler.add_job(send_scheduled_report, 'cron', day='*/3', hour=time.hour, minute=time.minute, args=[user_id])


def check_price_alerts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM price_alerts")
    alerts = cursor.fetchall()
    conn.close()
    
    for alert in alerts:
        current_price, _ = get_current_price(alert['crypto'])
        if current_price is not None:
            if (alert['is_above'] and current_price > alert['target_price']) or \
               (not alert['is_above'] and current_price < alert['target_price']):
                user_id = alert['user_id']
                crypto = alert['crypto']
                target_price = alert['target_price']
                direction = "sopra" if alert['is_above'] else "sotto"
                message = f"⚠️ Avviso: il prezzo di {crypto} è ora ${current_price:.2f}, che è {direction} il tuo obiettivo di ${target_price:.2f}"
                bot.send_message(user_id, message)
                
                # Rimuovi l'avviso dopo l'invio
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM price_alerts WHERE id = ?", (alert['id'],))
                conn.commit()
                conn.close()

# Gestione dei messaggi non riconosciuti
@bot.message_handler(func=lambda message: True)
@authorized_only
def echo_all(message):
    bot.reply_to(message, "Comando non riconosciuto. Usa /help per vedere l'elenco dei comandi disponibili.")

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_price_alerts, 'interval', minutes=5)
    update_report_scheduler()
    scheduler.start()
    
    bot.infinity_polling()