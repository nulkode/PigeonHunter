import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

class Translator:

    def __init__(self, api_key):
        logger.debug("Initializing Translator.")
        self.client = OpenAI(api_key=api_key)

    def translate_email(self, subject, body, target_lang, non_translate_langs):
        
        lang_list = ", ".join(non_translate_langs)
        logger.debug("Translating email for target_lang '%s' (non-translate: %s)", target_lang, lang_list)
        
        system_prompt = f"""
You are a translation assistant. You must respond ONLY with a valid JSON object.
Analyze the language of the provided email.
If the email's language IS one of the following: [{lang_list}], respond with:
{{"status": "skip"}}

If the email contains multiple versions of languages, and at least one of them is in the list [{lang_list}], respond with:
{{"status": "skip"}}

If the email's language IS NOT one of those languages, translate its subject and body to '{target_lang}' and respond with:
{{"status": "translated", "subject": "TRANSLATED_SUBJECT_HERE", "body": "TRANSLATED_BODY_HERE"}}

Do not include any text outside the JSON object.
"""

        user_prompt = f"""
Email to analyze:
Subject: {subject}
Body:
{body}
"""
        logger.debug("Sending translation request to OpenAI...")
        try:
            response = self.client.chat.completions.create(
                model="gpt-5-nano",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            json_response = json.loads(response.choices[0].message.content)
            logger.debug("Received OpenAI response: %s", json_response.get('status'))
            return json_response

        except Exception as e:
            logger.error("Error during OpenAI API call: %s", e, exc_info=True)
            return {"status": "error", "message": str(e)}

    def translate_text(self, text, target_lang):
        logger.debug("Translating notification text to %s.", target_lang)
        try:
            system_prompt = f"Translate the following text to {target_lang}. Respond only with the translated text."
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ]
            )
            translated_text = response.choices[0].message.content.strip()
            logger.debug("Notification text translated.")
            return translated_text
        except Exception as e:
            logger.error("Error translating text: %s", e, exc_info=True)
            return text