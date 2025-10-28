"""
discord_gemini_bot.py
---------------------------------
A lightweight Discord engagement automation bot powered by Google Gemini (Free API).

Features:
- Monitors target channel for product/support questions.
- Uses Gemini 1.5 Flash to draft helpful, on-brand responses.
- Redacts PII before sending text to the LLM.
- Posts suggestions in a moderator channel for approval (optional auto-post).
- Logs all interactions in JSONL for analytics.

Author: Anurag Mishra
"""

import os
import re
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import discord
import google.generativeai as genai

import logging
logging.basicConfig(filename='logs/app.log', level=logging.INFO)

# =======================
# Environment setup
# =======================
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TARGET_CHANNEL_NAME = os.getenv("TARGET_CHANNEL_NAME", "product-questions")
MODERATOR_CHANNEL_NAME = os.getenv("MODERATOR_CHANNEL_NAME", "moderator")

AUTO_POST = os.getenv("AUTO_POST", "false").lower() == "true"
BRAND_NAME = os.getenv("BRAND_NAME", "Acme DeFi")
BRAND_TONE = os.getenv("BRAND_TONE", "concise, helpful, friendly, slightly witty")

genai.configure(api_key=GEMINI_API_KEY)

# =======================
# Discord Setup
# =======================
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# =======================
# Utility Functions
# =======================

QUESTION_KEYWORDS = [
    "how", "what", "why", "when", "where", "issue",
    "bug", "error", "help", "support", "price", "fees",
]

def is_product_question(text: str) -> bool:
    """Quick heuristic classifier to detect product-related questions."""
    text = text.lower()
    if len(text) < 5:
        return False
    if "?" in text:
        return True
    if any(kw in text for kw in QUESTION_KEYWORDS):
        return True
    if any(x in text for x in ["lol", "haha", "thanks"]):
        return False
    return False


def redact_pii(text: str) -> str:
    """Simple regex-based redaction of PII (emails, numbers)."""
    text = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w{2,}\b", "[REDACTED_EMAIL]", text)
    text = re.sub(r"\b\d{6,}\b", "[REDACTED_NUMBER]", text)
    return text


def make_prompt(user_message: str) -> str:
    """Compose LLM prompt for Gemini."""
    return f"""
You are a customer success assistant for {BRAND_NAME}.
Tone: {BRAND_TONE}.

User message:
\"\"\"{user_message}\"\"\"

Your task:
- Provide a concise, professional response in {BRAND_NAME}'s tone.
- If unsure, politely ask for clarification.
- Avoid speculation or false claims.
- End with a helpful call-to-action if relevant.

Reply in plain text only.
"""


async def call_gemini(prompt: str) -> str:
    """Query Gemini model for response."""
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print("❌ Gemini API Error:", e)
        return f"Error generating reply: {str(e)}"


def persist_interaction(entry: dict):
    """Append conversation data to JSONL log."""
    os.makedirs("data", exist_ok=True)
    with open("data/interactions.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# =======================
# Discord Events
# =======================

@client.event
async def on_ready():
    """Bot startup initialization."""
    print(f"🤖 Logged in as {client.user} | Ready to serve!")
    client.target_channel = discord.utils.get(client.get_all_channels(), name=TARGET_CHANNEL_NAME)
    client.moderator_channel = discord.utils.get(client.get_all_channels(), name=MODERATOR_CHANNEL_NAME)

    if not client.target_channel:
        print(f"⚠️  Target channel '{TARGET_CHANNEL_NAME}' not found. Monitoring all channels instead.")
    if not client.moderator_channel:
        print(f"⚠️  Moderator channel '{MODERATOR_CHANNEL_NAME}' not found. Suggestions will print to console.")


@client.event
async def on_message(message):
    """Handles new messages."""
    # Ignore self messages
    if message.author == client.user:
        return

    # Filter for target channel if defined
    if client.target_channel and message.channel != client.target_channel:
        return

    content = message.content.strip()
    if not is_product_question(content):
        return

    # Redact and log
    redacted = redact_pii(content)
    print(f"[{datetime.utcnow().isoformat()}] 📨 New question from {message.author}: {redacted}")

    # Compose prompt and get AI-generated draft
    prompt = make_prompt(redacted)
    reply = await call_gemini(prompt)

    # Save metadata
    interaction = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": str(message.author),
        "content": redacted,
        "reply": reply,
        "channel": message.channel.name,
    }
    persist_interaction(interaction)

    # Send to moderator or post automatically
    moderator_output = (
        f"**Suggested Reply:**\n> {reply}\n\n"
        f"👤 From: {message.author}\n"
        f"💬 Message: {redacted}\n"
        f"📎 Link: {message.jump_url if hasattr(message, 'jump_url') else 'n/a'}"
    )

    if client.moderator_channel:
        await client.moderator_channel.send(moderator_output)
    else:
        print("\nModerator Output:\n", moderator_output)

    if AUTO_POST:
        await message.channel.send(reply)


# =======================
# Main
# =======================

if __name__ == "__main__":
    if not DISCORD_TOKEN or not GEMINI_API_KEY:
        print("❌ Missing API key or Discord token. Check your .env file.")
    else:
        client.run(DISCORD_TOKEN)
