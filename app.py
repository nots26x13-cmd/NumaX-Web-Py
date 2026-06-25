# ==========================================
# NUMAX OTP - PYTHON FLASK BACKEND
# No Firebase - Pure Python & SQLite
# ==========================================

import os
import json
import sqlite3
import datetime
import threading
import time
import requests
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# Render-এ Disk Mount করলে ডাটা পার্মানেন্ট থাকবে
DB_PATH = '/data/numax_app.db' if os.path.exists('/data') else 'numax_app.db'
ADMIN_UID = "8505710811"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS kv_store (
                        collection TEXT, 
                        doc_id TEXT, 
                        data JSON, 
                        PRIMARY KEY (collection, doc_id))''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS otps (
                        otp_id TEXT PRIMARY KEY, 
                        uid TEXT, 
                        number TEXT, 
                        code TEXT, 
                        message TEXT, 
                        panel TEXT, 
                        cost REAL, 
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()

init_db()

# ==========================================
# PURE PYTHON CORS HANDLING
# ==========================================
@app.before_request
def handle_options_preflight():
    if request.method == 'OPTIONS':
        response = app.make_response('')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, mauthapi'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        return response

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, mauthapi'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return response

# ==========================================
# TELEGRAM BOT ENGINE (ALWAYS RUNNING)
# ==========================================
def bot_polling_thread():
    last_update_id = 0
    while True:
        time.sleep(2) # Polling interval
        try:
            with get_db() as conn:
                c = conn.cursor()
                c.execute("SELECT data FROM kv_store WHERE collection='settings' AND doc_id='global'")
                row = c.fetchone()
                settings = json.loads(row['data']) if row else {}
                
                # Default Bot Settings
                token = settings.get('botToken', '8992145506:AAH9z6Mz9u76LIHBo8zgyn44OFKIDqaR1d0')
                welcome_msg = settings.get('welcomeMsg', 'Welcome to NumaX OTP! Premium SMS Verification.')
                bot_username = settings.get('botUsername', 'NumaX_bot')
                app_short = settings.get('appShortName', 'app')
                
            if not token: continue
            
            resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates?offset={last_update_id}&timeout=2")
            data = resp.json()
            
            if data.get('ok') and data.get('result'):
                for update in data['result']:
                    last_update_id = update['update_id'] + 1
                    msg = update.get('message', {})
                    text = msg.get('text', '')
                    chat_id = msg.get('chat', {}).get('id')
                    uid = str(msg.get('from', {}).get('id', ''))
                    
                    if not text or not chat_id: continue
                    
                    if text.startswith('/start'):
                        app_url = f"https://t.me/{bot_username}/{app_short}"
                        parts = text.split(' ')
                        if len(parts) > 1: app_url += f"?startapp={parts[1]}"
                        
                        # Send Welcome Message with WebApp Button
                        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                            "chat_id": chat_id,
                            "text": f"🎉 <b>{welcome_msg}</b>",
                            "parse_mode": "HTML",
                            "reply_markup": {"inline_keyboard": [[{"text": "🚀 OPEN APP", "url": app_url}]]}
                        })
                        
                        # Only show custom keyboard if user is Admin
                        if uid == ADMIN_UID:
                            reply_markup = {
                                "keyboard": [[{"text": "Broadcast"}, {"text": "Total User"}]],
                                "resize_keyboard": True,
                                "is_persistent": True
                            }
                            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                                "chat_id": chat_id,
                                "text": "🛠️ Admin Menu options:",
                                "reply_markup": reply_markup
                            })
                        else:
                            # For normal users, clear existing keyboards
                            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                                "chat_id": chat_id,
                                "text": "Welcome to our app! Use the button above to launch.",
                                "reply_markup": {"remove_keyboard": True}
                            })
                        
                    elif text == "Total User":
                        if uid == ADMIN_UID:
                            with get_db() as c2:
                                cur = c2.cursor()
                                cur.execute("SELECT COUNT(*) as cnt FROM kv_store WHERE collection='users'")
                                total = cur.fetchone()['cnt']
                            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                                "chat_id": chat_id, "text": f"👥 <b>Total Active Users:</b> {total}", "parse_mode": "HTML"
                            })
                        else:
                            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                                "chat_id": chat_id, "text": "❌ You are not an admin.",
                                "reply_markup": {"remove_keyboard": True}
                            })
                        
                    elif text == "Broadcast":
                        if uid == ADMIN_UID:
                            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                                "chat_id": chat_id, "text": "📝 To send a broadcast, reply with:\n`/bc Your message here`", "parse_mode": "Markdown"
                            })
                        else:
                            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                                "chat_id": chat_id, "text": "❌ You are not an admin.",
                                "reply_markup": {"remove_keyboard": True}
                            })
                            
                    elif text.startswith('/bc '):
                        if uid == ADMIN_UID:
                            bc_msg = text.replace('/bc ', '')
                            # Send to all users
                            with get_db() as c2:
                                cur = c2.cursor()
                                cur.execute("SELECT doc_id FROM kv_store WHERE collection='users'")
                                for user_row in cur.fetchall():
                                    try:
                                        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                                            "chat_id": user_row['doc_id'], "text": f"📢 <b>Announcement</b>\n\n{bc_msg}", "parse_mode": "HTML"
                                        })
                                    except: pass
                            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                                "chat_id": chat_id, "text": "✅ Broadcast sent successfully!"
                            })
                        else:
                            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                                "chat_id": chat_id, "text": "❌ You are not an admin."
                            })
                        
        except Exception as e:
            pass

# Background task শুরু করা হলো
threading.Thread(target=bot_polling_thread, daemon=True).start()

# ==========================================
# FLASK REST API
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/kv/<collection>', methods=['GET'])
def get_all_docs(collection):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT doc_id, data FROM kv_store WHERE collection=?", (collection,))
        return jsonify({row['doc_id']: json.loads(row['data']) for row in c.fetchall()})

@app.route('/api/kv/<collection>/<doc_id>', methods=['GET'])
def get_doc(collection, doc_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT data FROM kv_store WHERE collection=? AND doc_id=?", (collection, doc_id))
        row = c.fetchone()
        return jsonify(json.loads(row['data'])) if row else jsonify(None)

@app.route('/api/kv/<collection>/<doc_id>', methods=['POST'])
def set_doc(collection, doc_id):
    data = request.json
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT data FROM kv_store WHERE collection=? AND doc_id=?", (collection, doc_id))
        row = c.fetchone()
        
        # Merge dictionary so old settings don't reset
        if row:
            existing = json.loads(row['data'])
            existing.update(data)
            data_to_save = existing
        else:
            data_to_save = data
            
        c.execute("REPLACE INTO kv_store (collection, doc_id, data) VALUES (?, ?, ?)", 
                  (collection, doc_id, json.dumps(data_to_save)))
        conn.commit()
    return jsonify({"status": "success", "data": data_to_save})

@app.route('/api/kv/<collection>/<doc_id>', methods=['DELETE'])
def del_doc(collection, doc_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM kv_store WHERE collection=? AND doc_id=?", (collection, doc_id))
        conn.commit()
    return jsonify({"status": "success"})

# --- OTP & REFERRAL LOGIC ---
@app.route('/api/otp/save', methods=['POST'])
def save_otp():
    data = request.json
    otp_id = data.get('otp_id')
    uid = data.get('uid')
    cost = float(data.get('cost', 0.15))
    panel = data.get('panel', 'stex')
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT otp_id FROM otps WHERE otp_id=?", (otp_id,))
        if c.fetchone(): return jsonify({"status": "exists"})
            
        # 1. Save OTP
        c.execute("""INSERT INTO otps (otp_id, uid, number, code, message, panel, cost) 
                     VALUES (?, ?, ?, ?, ?, ?, ?)""", 
                  (otp_id, uid, data.get('number'), data.get('code'), data.get('message'), panel, cost))
        
        # 2. Update User Balance & Check Referral
        c.execute("SELECT data FROM kv_store WHERE collection='users' AND doc_id=?", (uid,))
        u_row = c.fetchone()
        if u_row:
            u_data = json.loads(u_row['data'])
            u_data['balance'] = float(u_data.get('balance', 0)) + cost
            
            # Check Referral Commission
            referer = u_data.get('referredBy')
            
            c.execute("SELECT data FROM kv_store WHERE collection='settings' AND doc_id='global'")
            s_row = c.fetchone()
            settings = json.loads(s_row['data']) if s_row else {}
            
            ref_onetime_enabled = settings.get('referEnableOneTime', False)
            ref_lifetime_enabled = settings.get('referEnableLifetime', True)
            ref_onetime_amt = float(settings.get('referOneTimeAmt', 5.0))
            ref_comm = float(settings.get('refComm', 0.05))
            
            ref_earn = 0
            if referer:
                # Onetime bonus
                if ref_onetime_enabled and not u_data.get('hasDoneFirstOtp'):
                    ref_earn += ref_onetime_amt
                # Lifetime comm
                if ref_lifetime_enabled:
                    ref_earn += ref_comm
            
            u_data['hasDoneFirstOtp'] = True
            c.execute("UPDATE kv_store SET data=? WHERE collection='users' AND doc_id=?", (json.dumps(u_data), uid))
            
            # Apply commission to Referrer
            if referer and ref_earn > 0:
                c.execute("SELECT data FROM kv_store WHERE collection='users' AND doc_id=?", (referer,))
                ref_row = c.fetchone()
                if ref_row:
                    ref_data = json.loads(ref_row['data'])
                    ref_data['balance'] = float(ref_data.get('balance', 0)) + ref_earn
                    ref_data['referralEarnings'] = float(ref_data.get('referralEarnings', 0)) + ref_earn
                    c.execute("UPDATE kv_store SET data=? WHERE collection='users' AND doc_id=?", (json.dumps(ref_data), referer))
                    
        conn.commit()
    return jsonify({"status": "success"})

# --- ADMIN STATS ---
@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    with get_db() as conn:
        c = conn.cursor()
        
        # Lifetime Stats
        c.execute("SELECT panel, COUNT(*) as cnt FROM otps GROUP BY panel")
        lifetime = {'stex': 0, 'voltx': 0, 'total': 0}
        for r in c.fetchall():
            lifetime[r['panel']] = r['cnt']
            lifetime['total'] += r['cnt']
            
        # Today's Stats (Auto reset at 12 AM using SQLite date)
        c.execute("SELECT panel, COUNT(*) as cnt FROM otps WHERE date(created_at, 'localtime') = date('now', 'localtime') GROUP BY panel")
        today = {'stex': 0, 'voltx': 0, 'total': 0}
        for r in c.fetchall():
            today[r['panel']] = r['cnt']
            today['total'] += r['cnt']
            
        # Total Users
        c.execute("SELECT COUNT(*) as cnt FROM kv_store WHERE collection='users'")
        total_users = c.fetchone()['cnt']
            
        return jsonify({"lifetime": lifetime, "today": today, "total_users": total_users})

if __name__ == '__main__':
    app.run(port=5000, host='0.0.0.0', debug=True)
