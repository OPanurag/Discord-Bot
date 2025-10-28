"""
A lightweight Discord engagement automation bot powered by Google Gemini (Free API).

Features:
- Monitors target channel for product/support questions.
- Uses Gemini models to draft helpful, on-brand responses (auto-selects available model).
- Redacts PII before sending text to the LLM.
- Injects a local brand_info.txt as the authoritative context (RAG-lite).
- Posts suggestions in a moderator channel for approval (optional auto-post).
- Logs all interactions in JSONL for analytics and computes simple stats.
- Moderator commands: !stats, !refresh

Author: Anurag Mishra (adapted)
"""

import os
import re
import json
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import discord
import google.generativeai as genai

# -----------------------
# Logging
# -----------------------
os.makedirs("logs", exist_ok=True)
# remove existing handlers to avoid duplicate messages when reloading
for h in logging.root.handlers[:]:
    logging.root.removeHandler(h)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log", mode="a"),
        logging.StreamHandler()
    ]
)

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

if not GEMINI_API_KEY:
    logging.warning("GEMINI_API_KEY not set. Gemini calls will fail until you set it in .env")
else:
    genai.configure(api_key=GEMINI_API_KEY)

# =======================
# Discord Setup
# =======================
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# =======================
# Globals / Config
# =======================
QUESTION_KEYWORDS = [
    "how", "what", "why", "when", "where", "issue",
    "bug", "error", "help", "support", "price", "fees",
]

# Preferred model order — we will pick the first available for this API key
PREFERRED_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5"
]

SELECTED_MODEL = "gemini-2.5-flash"
BRAND_INFO = ""


# -----------------------
# Utility functions
# -----------------------
def is_product_question(text: str) -> bool:
    """Quick heuristic classifier to detect product-related questions."""
    if not text:
        return False
    text_l = text.lower()
    if len(text_l) < 5:
        return False
    if "?" in text_l:
        return True
    if any(kw in text_l for kw in QUESTION_KEYWORDS):
        return True
    if any(x in text_l for x in ["lol", "haha", "thanks", "gg"]):
        return False
    return True


def redact_pii(text: str) -> str:
    """Simple regex-based redaction of PII (emails, numbers)."""
    if not text:
        return text
    text = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w{2,}\b", "[REDACTED_EMAIL]", text)
    text = re.sub(r"\b\d{6,}\b", "[REDACTED_NUMBER]", text)
    return text


def load_brand_info(path: str = "data/brand_info.txt") -> str:
    """
    Load a local brand info file to use as contextual data.
    Returns a short string; on missing file returns a helpful default.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
            # keep it reasonably short for token budget; truncate if huge
            max_chars = 18000  # pragmatic guard
            if len(raw) > max_chars:
                logging.info("Brand info file too long; truncating to %d chars", max_chars)
                return raw[:max_chars] + "\n\n[TRUNCATED]"
            return raw
    except FileNotFoundError:
        logging.warning("brand_info.txt not found at %s", path)
        return "No detailed brand info available. Use brief, factual tone."


def make_prompt(user_message: str) -> str:
    """
    Compose a prompt that includes brand context (RAG-lite).
    Most relevant brand facts are included so the model answers accurately.
    """
    user_msg_trim = (user_message or "").strip()
    if len(user_msg_trim) > 2000:
        user_msg_trim = user_msg_trim[:2000] + " ...[truncated]"

    prompt = f"""
You are a customer success assistant for {BRAND_NAME}.
Tone: {BRAND_TONE}.

Brand context (do not invent facts; use only what's below; if info is missing, ask a clarifying question):
{BRAND_INFO}

User message:
\"\"\"{user_msg_trim}\"\"\"

Instructions:
1) Answer concisely and accurately using ONLY the Brand context above when available.
2) If the exact answer is not in the Brand context, say you don't know and ask for clarifying info (e.g., tx hash, network).
3) Do NOT request private keys or sensitive data.
4) End with a suggested next step (e.g., "Please share your tx hash" or "Escalate to ops").

Format: Plain text reply, one paragraph. Keep it under 150 words.
"""
    return prompt


def persist_interaction(entry: dict):
    """Append conversation data to JSONL log."""
    os.makedirs("data", exist_ok=True)
    with open("data/interactions.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# -----------------------
# Gemini helpers (model selection + robust call)
# -----------------------
def list_models_available():
    """
    Return a list of model names accessible by the current key.
    Uses genai.list_models() if available.
    """
    try:
        models = genai.list_models()
        names = []
        for m in models:
            if isinstance(m, dict):
                nm = m.get("name") or m.get("model") or str(m)
            else:
                nm = getattr(m, "name", str(m))
            names.append(nm)
        return names
    except Exception as e:
        logging.warning("Failed to list models: %s", e)
        return []


def pick_model():
    """
    Pick a model from PREFERRED_MODELS that exists in the available models list.
    If nothing matches, fallback to the first preferred model (best-effort).
    """
    global SELECTED_MODEL
    try:
        available = list_models_available()
        # logging.info("Available models: %s", available)
        for pref in PREFERRED_MODELS:
            if any(pref in a for a in available):
                SELECTED_MODEL = pref
                logging.info("Selected model: %s", SELECTED_MODEL)
                return SELECTED_MODEL
        # fallback: choose first preferred (may fail but we'll handle errors)
        SELECTED_MODEL = PREFERRED_MODELS[0]
        logging.info("No preferred match found; falling back to: %s", SELECTED_MODEL)
        return SELECTED_MODEL
    except Exception as e:
        logging.exception("Error picking model: %s", e)
        SELECTED_MODEL = PREFERRED_MODELS[0]
        return SELECTED_MODEL


async def call_gemini(prompt: str) -> str:
    """
    Robust Gemini caller (async):
    - Uses a synchronous worker wrapped by asyncio.to_thread to avoid accidentally returning coroutines.
    - Tries several SDK call patterns and always returns a plain string.
    """
    model_name = SELECTED_MODEL or pick_model()
    if not GEMINI_API_KEY:
        return "Error: GEMINI_API_KEY not configured."

    def _call_sync():
        """Synchronous worker trying multiple SDK patterns; returns text."""
        # Pattern 1: new-style client.models.generate_content if present
        try:
            Client = getattr(genai, "Client", None)
            if Client:
                c = Client()
                try:
                    resp = c.models.generate_content(model=model_name, contents=prompt)
                    if hasattr(resp, "text") and resp.text:
                        return resp.text.strip()
                    if isinstance(resp, dict) and "candidates" in resp:
                        return resp["candidates"][0].get("content", "").strip()
                    return str(resp)
                except Exception as e:
                    logging.info("client.models.generate_content failed: %s", e)
        except Exception as e:
            logging.info("Client pattern not available or failed: %s", e)

        # Pattern 2: GenerativeModel wrapper (older)
        try:
            gm = genai.GenerativeModel(model_name)
            resp = gm.generate_content(prompt)
            if hasattr(resp, "text") and resp.text:
                return resp.text.strip()
            if isinstance(resp, dict) and "candidates" in resp:
                return resp["candidates"][0].get("content", "").strip()
            return str(resp)
        except Exception as e:
            logging.info("GenerativeModel.generate_content failed: %s", e)

        # Pattern 3: top-level helper (generate_text / generate) if present
        try:
            if hasattr(genai, "generate_text"):
                out = genai.generate_text(model=model_name, input=prompt)
                if hasattr(out, "text"):
                    return out.text.strip()
                if isinstance(out, dict) and "candidates" in out:
                    return out["candidates"][0].get("content", "").strip()
                return str(out)
        except Exception as e:
            logging.info("genai.generate_text failed: %s", e)

        return "Error: could not generate reply (see logs)."

    try:
        # Run the blocking worker in a thread and await the string result
        text = await asyncio.to_thread(_call_sync)
        if text is None:
            return "Error: empty response from model."
        return str(text)
    except Exception as e:
        logging.exception("Unexpected error calling Gemini: %s", e)
        return f"Error generating reply: {e}"


# -----------------------
# Discord event handlers
# -----------------------
@client.event
async def on_ready():
    logging.info("Logged in as %s | Ready to serve!", client.user)
    # pick model at startup
    pick_model()
    # load brand info
    global BRAND_INFO
    BRAND_INFO = load_brand_info()
    client.target_channel = discord.utils.get(client.get_all_channels(), name=TARGET_CHANNEL_NAME)
    client.moderator_channel = discord.utils.get(client.get_all_channels(), name=MODERATOR_CHANNEL_NAME)
    if not client.target_channel:
        logging.warning("Target channel '%s' not found. Monitoring all channels.", TARGET_CHANNEL_NAME)
    if not client.moderator_channel:
        logging.warning("Moderator channel '%s' not found. Suggestions will print to console.", MODERATOR_CHANNEL_NAME)


@client.event
async def on_message(message):
    # Ignore messages from self
    if message.author == client.user:
        return

    # Moderator commands (only respond in moderator channel)
    content_stripped = (message.content or "").strip()
    if message.channel and message.channel.name == MODERATOR_CHANNEL_NAME:
        if content_stripped.lower() == "!stats":
            # compute interaction count and avg latency from interactions.jsonl
            total = 0
            latencies = []
            path = "data/interactions.jsonl"
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                            total += 1
                            sent = obj.get("sent_at")
                            received = obj.get("received_at")
                            if sent and received:
                                try:
                                    s = datetime.fromisoformat(sent)
                                    r = datetime.fromisoformat(received)
                                    latencies.append((r - s).total_seconds())
                                except Exception:
                                    pass
                        except Exception:
                            pass
            avg_latency = (sum(latencies) / len(latencies)) if latencies else 0
            await message.channel.send(f"Interactions logged: {total}\nAverage AI latency: {avg_latency:.2f}s (based on timestamps)")
            return

        if content_stripped.lower() == "!refresh":
            global BRAND_INFO
            BRAND_INFO = load_brand_info()
            await message.channel.send("Brand info reloaded.")
            return

    # If target channel specified, ignore other channels
    if client.target_channel and message.channel != client.target_channel:
        return

    # detect if the message is a product question
    if not is_product_question(content_stripped):
        return

    # Redact PII
    redacted = redact_pii(content_stripped)
    logging.info("📨 New question from %s: %s", message.author, redacted)

    # Compose prompt and call Gemini
    prompt = make_prompt(redacted)

    sent_time = datetime.utcnow().isoformat()
    reply = await call_gemini(prompt)

    # Defensive coercion: ensure reply is a plain string
    if not isinstance(reply, str):
        try:
            reply = str(reply)
        except Exception:
            reply = "Error: non-text reply received from model."

    received_time = datetime.utcnow().isoformat()

    # Save metadata
    interaction = {
        "timestamp": datetime.utcnow().isoformat(),
        "sent_at": sent_time,
        "received_at": received_time,
        "user": str(message.author),
        "content": redacted,
        "reply": reply,
        "channel": message.channel.name,
        "model": SELECTED_MODEL
    }
    persist_interaction(interaction)

    # Send to moderator channel or console
    moderator_output = (
        f"**Suggested Reply (model: {SELECTED_MODEL})**\n> {reply}\n\n"
        f"👤 From: {message.author}\n"
        f"💬 Message: {redacted}\n"
        f"📎 Link: {message.jump_url if hasattr(message, 'jump_url') else 'n/a'}"
    )

    if client.moderator_channel:
        try:
            await client.moderator_channel.send(moderator_output)
        except Exception as e:
            logging.exception("Failed to send to moderator channel: %s", e)
            await message.channel.send("Error delivering suggestion to moderator channel; see logs.")
    else:
        logging.info("Moderator Output:\n%s", moderator_output)
        # fallback: post suggestion to the original channel only if AUTO_POST is true
        if AUTO_POST:
            await message.channel.send(reply)

    # Auto-post to user channel if requested (be careful in prod)
    if AUTO_POST:
        try:
            await message.channel.send(reply)
        except Exception as e:
            logging.exception("Auto-post failed: %s", e)


# -----------------------
# Entrypoint
# -----------------------
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logging.error("DISCORD_TOKEN missing. Check .env file.")
        print("❌ Missing DISCORD_TOKEN in .env")
    elif not GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY missing. Check .env file.")
        print("❌ Missing GEMINI_API_KEY in .env")
    else:
        try:
            client.run(DISCORD_TOKEN)
        except Exception as e:
            logging.exception("Failed to run Discord client: %s", e)
            print("Failed to run bot. See logs/app.log for details.")
