#!/usr/bin/env python3
"""
DiaAstro Flask Backend
======================
Exposes the DiaAstroAgent over HTTP so the React website can call it.

Endpoints:
  POST /ask           - AI astrology guidance
  POST /palm-reading  - Palm image analysis
  POST /save-lead     - Save visitor lead (name + phone)
  GET  /leads         - View captured leads (protect in production!)
  GET  /health        - Health check
"""

import os
import re
import sys
import json
import base64
import logging
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('logs/diaastro_web.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)

# Allow React dev server (port 3000) and your production domain
ALLOWED_ORIGINS = os.getenv(
    'ALLOWED_ORIGINS',
    'http://localhost:3000,http://localhost:3001,https://diaastro.in,https://www.diaastro.in'
).split(',')

CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

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
    """Decorator: return 503 if agent is not available."""
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
        'timestamp': datetime.now().isoformat(),
    })


@app.route('/ask', methods=['POST'])
@agent_required
def ask():
    """Generate AI astrology guidance for a question."""
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()

    if not question:
        return jsonify({'success': False, 'error': 'Please provide a question.'}), 400
    if len(question) > 1000:
        return jsonify({'success': False, 'error': 'Question too long (max 1000 chars).'}), 400

    logger.info(f"/ask | question: {question[:80]}...")

    response = agent.generate_astrology_insight(question)

    if not response:
        return jsonify({
            'success': False,
            'error': 'Unable to generate guidance right now. Please try again in a moment.'
        }), 500

    return jsonify({
        'success': True,
        'response': response,
        'timestamp': datetime.now().isoformat(),
    })


@app.route('/palm-reading', methods=['POST'])
@agent_required
def palm_reading():
    """Analyse a palm image and return a reading."""
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
    mime_type = image_file.content_type or 'image/jpeg'

    logger.info(f"/palm-reading | style={reading_style} | size={len(image_data)} bytes")

    reading = agent.generate_palm_reading(image_b64, mime_type, reading_style)

    if not reading:
        return jsonify({'success': False, 'error': 'Unable to read the palm. Please try a clearer image.'}), 500

    return jsonify({
        'success': True,
        'reading': reading,
        'style': reading_style,
        'timestamp': datetime.now().isoformat(),
    })


@app.route('/save-lead', methods=['POST'])
def save_lead():
    """Save a visitor lead (name + phone) before unlocking AI features."""
    data = request.get_json(silent=True) or {}
    name    = (data.get('name') or '').strip()
    phone   = re.sub(r'\D', '', data.get('phone') or '')
    feature = data.get('feature', 'unknown')

    if not name:
        return jsonify({'success': False, 'error': 'Name is required.'}), 400
    if len(phone) < 10:
        return jsonify({'success': False, 'error': 'Please enter a valid 10-digit mobile number.'}), 400

    lead = {
        'name': name,
        'phone': phone,
        'feature': feature,
        'timestamp': datetime.now().isoformat(),
        'source': 'website',
    }

    leads_file = 'leads.json'
    leads = []
    if os.path.exists(leads_file):
        try:
            with open(leads_file, 'r', encoding='utf-8') as f:
                leads = json.load(f)
        except Exception:
            leads = []

    leads.append(lead)
    with open(leads_file, 'w', encoding='utf-8') as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)

    logger.info(f"/save-lead | {name} | {phone} | feature={feature}")
    return jsonify({'success': True, 'message': 'Lead saved successfully.'})


@app.route('/leads', methods=['GET'])
def view_leads():
    """
    View all captured leads.
    ⚠️  Protect this endpoint with a password or IP restriction in production!
    """
    # Basic token check — set LEADS_TOKEN in your .env
    token = os.getenv('LEADS_TOKEN', '')
    if token and request.args.get('token') != token:
        return jsonify({'error': 'Unauthorized'}), 401

    if not os.path.exists('leads.json'):
        return jsonify({'leads': [], 'total': 0})
    with open('leads.json', 'r', encoding='utf-8') as f:
        leads = json.load(f)
    return jsonify({'leads': leads, 'total': len(leads)})


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n{'='*45}")
    print("  DiaAstro AI Backend")
    print(f"{'='*45}")
    print(f"  Agent status : {'READY' if agent else 'NOT READY - check .env'}")
    if agent:
        print(f"  Business     : {agent.config.get('BUSINESS_NAME')}")
        print(f"  Instagram    : {agent.config.get('INSTAGRAM')}")
    print(f"  Server       : http://localhost:{port}")
    print(f"  Health check : http://localhost:{port}/health")
    print(f"  CORS origins : {ALLOWED_ORIGINS}")
    print(f"{'='*45}\n")

    app.run(host='0.0.0.0', port=port, debug=False)
