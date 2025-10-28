import re

def redact_pii(text):
    text = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w{2,}\b", "[REDACTED_EMAIL]", text)
    text = re.sub(r"\b\d{6,}\b", "[REDACTED_NUMBER]", text)
    return text
