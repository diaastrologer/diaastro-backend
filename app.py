#!/usr/bin/env python3
"""
DiaAstro Flask Backend
======================
Exposes the DiaAstroAgent over HTTP so the React website can call it.

Endpoints:
  POST /ask           - AI astrology guidance
  POST /palm-reading  - Palm image analysis
  POST /save-lead     - Save visitor lead (name + phone) — emails Ruchi instantly
  GET  /leads         - View in-memory leads for current session
  GET  /health        - Health check
"""

import os
import re
import sys
import base64
import logging
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)

ALLOWED_ORIGINS = os.getenv(
    'ALLOWED_ORIGINS',
    'http://localhost:3000,http://localhost:3001,https://diaastro.in,https://www.diaastro.in'
).split(',')

CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

# ── In-memory lead store (survives within a session, cleared on restart) ──────
_leads_store = []

# ── Email helper ──────────────────────────────────────────────────────────────
def send_lead_email(name, phone, feature, timestamp, dob='', tob='', pob=''):
    """Send lead details to Ruchi's email via Gmail SMTP. Runs in background thread."""
    smtp_user     = os.getenv('SMTP_USER', '')
    smtp_password = os.getenv('SMTP_PASSWORD', '')
    notify_email  = os.getenv('NOTIFY_EMAIL', smtp_user)

    if not smtp_user or not smtp_password:
        logger.warning("Email not configured — SMTP_USER or SMTP_PASSWORD missing.")
        return

    feature_label = 'AI Palm Reading' if feature == 'palm' else 'AI Astrology Guidance'

    subject = f"🌟 New DiaAstro Lead — {name}"
    body = f"""
New lead from diaastro.in

Name            : {name}
Phone           : {phone}
Feature         : {feature_label}
Year of Birth   : {dob if dob else 'Not provided'}
Time of Birth   : {tob if tob else 'Not provided'}
Place of Birth  : {pob if pob else 'Not provided'}
Time            : {timestamp}

Reply to this email or WhatsApp them at:
https://wa.me/91{phone}
""".strip()

    try:
        msg = MIMEMultipart()
        msg['From']    = smtp_user
        msg['To']      = notify_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Always also send to dia.astrologer@gmail.com
        recipients = list({notify_email, 'dia.astrologer@gmail.com'})

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, recipients, msg.as_string())

        logger.info(f"Lead email sent for {name} to {recipients}")
    except Exception as e:
        logger.error(f"Failed to send lead email: {e}")


# ── Load Agent ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

agent = None
try:
    from main import DiaAstroAgent
    agent = DiaAstroAgent()
    logger.info(f"Agent ready | Business: {agent.config.get('BUSINESS_NAME', 'DiaAstro')}")
except Exception as e:
    logger.error(f"Agent initialization failed: {e}")
    agent = None


# ── Helper ─────────────────────────────────────────────────────────────────────
def agent_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not agent:
            return jsonify({'success': False,
                            'error': 'Astrology service is temporarily unavailable. Please try again later.'}), 503
        return fn(*args, **kwargs)
    return wrapper


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy' if agent else 'degraded',
        'agent_available': agent is not None,
        'business': agent.config.get('BUSINESS_NAME', 'DiaAstro') if agent else 'Unknown',
        'email_configured': bool(os.getenv('SMTP_USER') and os.getenv('SMTP_PASSWORD')),
        'leads_this_session': len(_leads_store),
        'timestamp': datetime.now().isoformat(),
    })


@app.route('/ask', methods=['POST'])
@agent_required
def ask():
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()

    if not question:
        return jsonify({'success': False, 'error': 'Please provide a question.'}), 400
    if len(question) > 1000:
        return jsonify({'success': False, 'error': 'Question too long (max 1000 chars).'}), 400

    logger.info(f"/ask | question: {question[:80]}...")
    response = agent.generate_astrology_insight(question)

    if not response:
        return jsonify({'success': False, 'error': 'Unable to generate guidance right now. Please try again in a moment.'}), 500

    return jsonify({'success': True, 'response': response, 'timestamp': datetime.now().isoformat()})


@app.route('/palm-reading', methods=['POST'])
@agent_required
def palm_reading():
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'No image provided.'}), 400

    image_file = request.files['image']
    reading_style = request.form.get('style', 'mystic')

    if image_file.filename == '':
        return jsonify({'success': False, 'error': 'No image selected.'}), 400

    image_data = image_file.read()
    if len(image_data) > 5 * 1024 * 1024:
        return jsonify({'success': False, 'error': 'Image too large. Please use an image under 5 MB.'}), 400

    image_b64 = base64.b64encode(image_data).decode('utf-8')
    mime_type  = image_file.content_type or 'image/jpeg'

    logger.info(f"/palm-reading | style={reading_style} | size={len(image_data)} bytes")
    reading = agent.generate_palm_reading(image_b64, mime_type, reading_style)

    if not reading:
        return jsonify({'success': False, 'error': 'Unable to read the palm. Please try a clearer image.'}), 500

    return jsonify({'success': True, 'reading': reading, 'style': reading_style, 'timestamp': datetime.now().isoformat()})


@app.route('/save-lead', methods=['POST'])
def save_lead():
    """
    Save a visitor lead.
    1. Validates name + phone.
    2. Stores in in-memory list (visible via /leads this session).
    3. Emails instantly in a background thread (no delay to caller).
    """
    data    = request.get_json(silent=True) or {}
    name    = (data.get('name') or '').strip()
    phone   = re.sub(r'\D', '', data.get('phone') or '')
    feature = data.get('feature', 'unknown')
    dob     = (data.get('dob') or '').strip()
    tob     = (data.get('tob') or '').strip()
    pob     = (data.get('pob') or '').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Name is required.'}), 400
    if len(phone) != 10:
        return jsonify({'success': False, 'error': 'Please enter a valid 10-digit mobile number.'}), 400

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Store in memory
    _leads_store.append({
        'name': name, 'phone': phone, 'feature': feature,
        'dob': dob, 'tob': tob, 'pob': pob,
        'timestamp': timestamp
    })

    # Email in background — caller gets instant response
    thread = threading.Thread(
        target=send_lead_email,
        args=(name, phone, feature, timestamp, dob, tob, pob),
        daemon=True
    )
    thread.start()

    logger.info(f"/save-lead | {name} | {phone} | feature={feature} | dob={dob} | tob={tob} | pob={pob}")
    return jsonify({'success': True, 'message': 'Lead saved successfully.'})


@app.route('/leads', methods=['GET'])
def view_leads():
    """
    View leads captured since last restart.
    Protected by LEADS_TOKEN env var.
    Access: /leads?token=your_secret_token
    """
    token = os.getenv('LEADS_TOKEN', '')
    if token and request.args.get('token') != token:
        return jsonify({'error': 'Unauthorized'}), 401

    return jsonify({
        'leads': _leads_store,
        'total': len(_leads_store),
        'note': 'In-memory only — leads are also emailed to Ruchi instantly. This list resets on server restart.'
    })


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n{'='*45}")
    print("  DiaAstro AI Backend")
    print(f"{'='*45}")
    print(f"  Agent status    : {'READY' if agent else 'NOT READY - check .env'}")
    print(f"  Email alerts    : {'CONFIGURED' if os.getenv('SMTP_USER') else 'NOT SET - add SMTP_USER & SMTP_PASSWORD'}")
    print(f"  Server          : http://localhost:{port}")
    print(f"  Health check    : http://localhost:{port}/health")
    print(f"  CORS origins    : {ALLOWED_ORIGINS}")
    print(f"{'='*45}\n")

    app.run(host='0.0.0.0', port=port, debug=False)
