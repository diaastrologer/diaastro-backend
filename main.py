#!/usr/bin/env python3
"""
DiaAstro AI Agent - Main Orchestrator
Generates Vedic astrology insights using Google Gemini AI
"""

# Fix Unicode display on Windows console
import os
import sys
if sys.platform == 'win32':
    try:
        os.system('chcp 65001 > nul 2>&1')
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/agent.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class DiaAstroAgent:
    """Main AI Agent - DiaAstro Astrology Engine"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing DiaAstro AI Agent...")
        self.config = {}
        self.load_config()
        self.verify_gemini_key()
        self.logger.info("Agent initialized successfully!")

    def load_config(self):
        """Load configuration from .env file"""
        try:
            load_dotenv()
            self.config = {
                'GEMINI_API_KEY': os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_AI_API_KEY'),
                'BUSINESS_NAME': os.getenv('BUSINESS_NAME', 'DiaAstro'),
                'INSTAGRAM':     os.getenv('INSTAGRAM', '@dia.astrologer'),
                'PHONE':         os.getenv('PHONE', '8625815099'),
                'EMAIL':         os.getenv('EMAIL', 'ruchi.bhardwaj@diaastro.in'),
            }

            key_present = bool(self.config.get('GEMINI_API_KEY'))
            self.logger.info(f"Config loaded | Gemini API key present: {key_present}")

            if key_present:
                k = self.config['GEMINI_API_KEY']
                self.logger.info(f"API key: {k[:8]}...{k[-4:]}")

        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            self.config = {}

    def verify_gemini_key(self):
        """Verify that the Gemini API key is present"""
        if not self.config.get('GEMINI_API_KEY'):
            raise ValueError(
                "GEMINI_API_KEY (or GOOGLE_AI_API_KEY) is missing from your .env file. "
                "Please add it and restart the server."
            )
        self.logger.info("Gemini API key verified.")

    # ------------------------------------------------------------------
    # Core AI methods
    # ------------------------------------------------------------------

    def _get_genai_model(self):
        """Return an initialized Gemini model, trying latest models first."""
        import google.generativeai as genai

        api_key = self.config.get('GEMINI_API_KEY')
        genai.configure(api_key=api_key)

        models_to_try = [
            'gemini-2.5-flash',
            'gemini-2.0-flash',
            'gemini-1.5-flash',
        ]

        last_err = None
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                # Lightweight probe
                model.generate_content("ping")
                self.logger.info(f"Using model: {model_name}")
                return model
            except Exception as e:
                self.logger.warning(f"Model {model_name} unavailable: {str(e)[:60]}")
                last_err = e

        raise RuntimeError(f"All Gemini models failed. Last error: {last_err}")

    def generate_astrology_insight(self, question: str) -> str | None:
        """Generate a Vedic astrology response for the given question."""
        try:
            import google.generativeai as genai

            api_key = self.config.get('GEMINI_API_KEY')
            if not api_key:
                self.logger.error("No Gemini API key in config")
                return None

            genai.configure(api_key=api_key)

            full_prompt = f"""You are a knowledgeable and compassionate Vedic astrologer representing \
{self.config.get('BUSINESS_NAME', 'DiaAstro')}, guided by Astrologer Ruchi Bhardwaj.

Guidelines:
- Give warm, personalized responses based on Vedic astrology principles
- Cover relevant topics: birth chart, planetary positions, doshas, remedies, muhurat
- Keep responses clear, practical, and uplifting (200-350 words)
- End by gently suggesting a full personal consultation
- Contact: Instagram: {self.config.get('INSTAGRAM')}, Phone: {self.config.get('PHONE')}

User Question: {question}

Astrology Guidance:"""

            models_to_try = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']

            for model_name in models_to_try:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(full_prompt)
                    self.logger.info(f"Insight generated via {model_name}")
                    return response.text
                except Exception as e:
                    self.logger.warning(f"Model {model_name} failed: {str(e)[:80]}")
                    continue

            self.logger.error("All Gemini models failed to generate insight")
            return None

        except Exception as e:
            self.logger.error(f"generate_astrology_insight error: {e}")
            return None

    def generate_palm_reading(self, image_b64: str, mime_type: str, style: str = 'mystic') -> str | None:
        """Generate a palm reading from a base64-encoded image."""
        try:
            import google.generativeai as genai

            api_key = self.config.get('GEMINI_API_KEY')
            if not api_key:
                return None

            genai.configure(api_key=api_key)

            style_prompts = {
                'mystic': (
                    "You are an ancient mystic and Vedic palmist with deep spiritual wisdom. "
                    "Read this palm with rich, poetic language, referencing cosmic forces, karma, and spiritual destiny."
                ),
                'modern': (
                    "You are a modern palmistry expert combining ancient knowledge with contemporary psychology. "
                    "Read this palm in a clear, practical way connecting to everyday life, relationships, and career."
                ),
                'vedic': (
                    "You are a traditional Indian Vedic palmist (Hast Rekha Shastra expert). "
                    "Read this palm using authentic Vedic principles — Jeevan Rekha, Hridaya Rekha, "
                    "Mastishk Rekha, Bhagya Rekha, and mounts."
                ),
            }

            system_prompt = style_prompts.get(style, style_prompts['mystic'])

            full_prompt = f"""{system_prompt}

Analyze the palm and provide a reading covering:
1. Life Line - vitality, major life changes
2. Heart Line - love, emotions, relationships
3. Head Line - intellect, decision-making
4. Fate Line - career, destiny (if visible)
5. Key Mounts - notable strengths
6. Overall Message - unified insight and guidance

Keep your reading warm, insightful, 300-400 words. End with an encouraging note and suggest a full consultation.
Contact: Instagram @dia.astrologer | Phone: +91 {self.config.get('PHONE', '8625815099')}"""

            vision_models = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']

            for model_name in vision_models:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content([
                        full_prompt,
                        {'mime_type': mime_type, 'data': image_b64}
                    ])
                    self.logger.info(f"Palm reading generated via {model_name}")
                    return response.text
                except Exception as e:
                    self.logger.warning(f"Palm model {model_name} failed: {str(e)[:80]}")
                    continue

            return None

        except Exception as e:
            self.logger.error(f"generate_palm_reading error: {e}")
            return None

    def test_connection(self) -> bool:
        """Quick smoke-test for the Gemini connection."""
        try:
            result = self.generate_astrology_insight("Hello! Confirm you are ready.")
            return bool(result)
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False


# -----------------------------------------------------------------------
# Standalone entry point (python main.py)
# -----------------------------------------------------------------------
if __name__ == "__main__":
    agent = DiaAstroAgent()
    ok = agent.test_connection()
    print("Connection test:", "PASSED" if ok else "FAILED")
