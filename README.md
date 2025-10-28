# Discord AI Support Bot with Google Gemini

A sophisticated Discord bot that automates customer support and product inquiries using Google's Gemini AI models. The bot monitors specific channels, intelligently responds to questions, and maintains brand consistency while protecting user privacy.

## Features

- 🤖 **AI-Powered Responses**: Uses Google Gemini models to generate contextually relevant, on-brand responses
- 🔒 **Privacy First**: Automatically redacts PII (Personally Identifiable Information) before processing
- 📚 **RAG Implementation**: Injects brand information and product context for accurate responses
- 👥 **Moderation Workflow**: Posts responses to a moderator channel for review (optional auto-posting)
- 📊 **Analytics**: Logs all interactions in JSONL format for tracking and statistics
- ⚙️ **Flexible Configuration**: Easy environment variable setup for customization
- 🔄 **Auto-Model Selection**: Automatically selects the best available Gemini model

## Project Structure

```
├── discord_gemini_bot.py    # Main bot implementation
├── env.template             # Environment variable template
├── gemini-api-model.py      # Utility to list available Gemini models
├── start.sh                 # Startup script with error handling
├── requirements.txt         # Python dependencies
├── data/
│   ├── brand_info.txt      # Brand context and guidelines
│   └── interactions.jsonl   # Interaction logs
├── logs/
│   └── app.log             # Application logs
└── utils/
    └── helper.py           # Utility functions (PII redaction, etc.)
```

## Setup and Installation

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `env.template` to `.env` and configure:
   ```bash
   cp env.template .env
   ```
5. Update `.env` with your credentials:
   ```
   DISCORD_TOKEN=<YOUR-DISCORD-TOKEN>
   GEMINI_API_KEY=<YOUR-GEMINI-API-KEY>
   TARGET_CHANNEL_NAME=product-questions
   MODERATOR_CHANNEL_NAME=moderator
   AUTO_POST=true
   BRAND_NAME=Your Brand
   BRAND_TONE=concise, helpful, friendly, slightly witty
   ```

## Key Components

### Main Bot (`discord_gemini_bot.py`)
- Core bot implementation with Discord event handling
- Question detection and response generation
- Integration with Gemini AI models
- Logging and analytics

### Gemini Model Utility (`gemini-api-model.py`)
- Lists available Gemini models for your API key
- Helps in debugging API access issues

### Helper Utilities (`utils/helper.py`)
- PII redaction functionality
- Protects user privacy by removing sensitive information

### Brand Information (`data/brand_info.txt`)
- Contains company information and guidelines
- Product details and common Q&A
- Support procedures and escalation paths

### Start Script (`start.sh`)
- Reliable bot startup with error handling
- Automatic restart capability
- Clean log management

## Running the Bot

1. Make the start script executable:
   ```bash
   chmod +x start.sh
   ```

2. Start the bot:
   ```bash
   ./start.sh
   ```

   To run without auto-restart:
   ```bash
   ./start.sh --no-restart
   ```

## Moderator Commands

- `!stats`: View interaction statistics
- `!refresh`: Reload brand information

## Dependencies

- discord.py (2.6.4)
- google-generativeai
- python-dotenv (1.2.1)
- protobuf

## Logging

- Application logs are stored in `logs/app.log`
- Interaction data is stored in `data/interactions.jsonl`

## Security Notes

- The bot automatically redacts sensitive information like emails and long numbers
- Brand information is stored locally and used as context for AI responses
- No user private keys or sensitive data are stored

## License

See the [LICENSE](LICENSE) file for details.

## Author

Created by Anurag Mishra

---

For more information or support, please open an issue in the repository.