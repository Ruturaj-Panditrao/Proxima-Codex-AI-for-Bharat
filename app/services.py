import boto3
import json
import os
import re
from dotenv import load_dotenv

load_dotenv()

# Initialize the Bedrock client
bedrock = boto3.client('bedrock-runtime', region_name=os.getenv("AWS_DEFAULT_REGION", "ap-south-1"))

def get_query_embedding(text: str):
    """Converts the user's spoken question into a 1024-dimension vector using Titan V2."""
    try:
        body = json.dumps({
            "inputText": text,
            "dimensions": 1024,
            "normalize": True
        })
        response = bedrock.invoke_model(
            body=body,
            modelId='amazon.titan-embed-text-v2:0',  # <-- Upgraded to V2
            accept='application/json',
            contentType='application/json'
        )
        return json.loads(response.get('body').read())['embedding']
    except Exception as e:
        print(f"Error getting query embedding: {e}")
        return None

def generate_agent_response(user_query: str, retrieved_schemes: list):
    """Acts as the AI Agent, reading the DB results and answering the user."""
    
    # 1. Format the database results into readable context for Claude
    context_text = ""
    for idx, scheme in enumerate(retrieved_schemes):
        context_text += f"\n--- Scheme {idx+1}: {scheme.schemeName} ---\n"
        context_text += f"Description: {scheme.briefDescription}\n"
        
        # Safely extract eligibility if it exists in deep_details
        deep = scheme.deep_details or {}
        details_en = deep.get("details", {}).get("en", {})
        eligibility_md = details_en.get("eligibilityCriteria", {}).get("eligibilityDescription_md", "")
        if eligibility_md:
            context_text += f"Eligibility: {eligibility_md}\n"

    # 2. Build the System Prompt (This tells the AI how to behave)
    system_prompt = """You are a helpful and empathetic AI assistant for Indian citizens, built for the AI for Bharat Hackathon. 
    Using ONLY the scheme information provided in the Context, answer the user's question simply and directly. 
    If the context does not contain the answer, politely say you don't know. Do not invent or hallucinate information."""

    prompt = f"Context:\n{context_text}\n\nUser Query: {user_query}"

    # # 3. Call Claude 3 Haiku
    # try:
    #     body = json.dumps({
    #         "anthropic_version": "bedrock-2023-05-31",
    #         "max_tokens": 500,
    #         "system": system_prompt,
    #         "messages": [{"role": "user", "content": prompt}]
    #     })

    #     # response = bedrock.invoke_model(
    #     #     modelId='anthropic.claude-3-haiku-20240307-v1:0', 
    #     #     body=body
    #     # )
        
    #     response = bedrock.invoke_model(
    #         modelId='amazon.titan-text-express-v1', 
    #         accept='application/json',
    #         contentType='application/json',
    #         body=body
    #     )
        
    #     result = json.loads(response.get('body').read())
    #     return result['content'][0]['text']
    
    
    # 3. Call Amazon Nova Lite using the modern Converse API
    try:
        response = bedrock.converse(
            # CHANGE THIS LINE: Add 'us.' to the front of the model ID
            modelId='apac.amazon.nova-lite-v1:0', 
            messages=[{
                "role": "user",
                "content": [{"text": prompt}]
            }],
            system=[{"text": system_prompt}],
            inferenceConfig={
                "maxTokens": 500,
                "temperature": 0.2
            }
        )
        
        return response['output']['message']['content'][0]['text']
    
    except Exception as e:
        print(f"Error generating agent response: {e}")
        return "I'm sorry, I am having trouble connecting to the AI brain right now."


def analyze_turn_for_followup(user_text: str, history_turns: list, detected_language_code: str | None = None):
    """
    LLM decides if follow-up is needed and produces retrieval hints.
    Returns a normalized dict:
    {
      should_follow_up: bool,
      follow_up_question: str,
      search_query: str,
      state_filter: str | None,
      slots: dict
    }
    """
    fallback = {
        "should_follow_up": False,
        "follow_up_question": "",
        "search_query": user_text,
        "state_filter": None,
        "slots": {},
    }

    compact_history = []
    for t in history_turns[-8:]:
        role = t.get("role", "unknown")
        text = t.get("message_text", "")
        compact_history.append({"role": role, "text": text})

    system_prompt = (
        "You are a conversation manager for an Indian welfare-schemes voice assistant.\n"
        "You must decide if a follow-up question is required before searching schemes.\n"
        "Rules:\n"
        "1) Ask follow-up only when truly necessary to improve recommendation quality.\n"
        "2) Ask at most one concise question.\n"
        "3) If enough info exists, do not ask follow-up.\n"
        "4) Return strict JSON only (no markdown).\n"
        "JSON schema:\n"
        "{\n"
        "  \"should_follow_up\": boolean,\n"
        "  \"follow_up_question\": string,\n"
        "  \"search_query\": string,\n"
        "  \"state_filter\": string|null,\n"
        "  \"slots\": {\"state\": string|null, \"occupation\": string|null, \"age\": number|null, \"gender\": string|null, \"income_monthly\": number|null}\n"
        "}\n"
    )

    user_payload = {
        "detected_language_code": detected_language_code,
        "history": compact_history,
        "latest_user_text": user_text,
    }

    try:
        response = bedrock.converse(
            modelId="apac.amazon.nova-lite-v1:0",
            messages=[{
                "role": "user",
                "content": [{"text": json.dumps(user_payload, ensure_ascii=False)}]
            }],
            system=[{"text": system_prompt}],
            inferenceConfig={
                "maxTokens": 500,
                "temperature": 0.1
            }
        )

        raw_text = response["output"]["message"]["content"][0]["text"]

        match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if not match:
            return fallback

        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            return fallback

        return {
            "should_follow_up": bool(parsed.get("should_follow_up", False)),
            "follow_up_question": str(parsed.get("follow_up_question", "") or ""),
            "search_query": str(parsed.get("search_query", "") or user_text),
            "state_filter": parsed.get("state_filter"),
            "slots": parsed.get("slots") if isinstance(parsed.get("slots"), dict) else {},
        }
    except Exception as e:
        print(f"Error in analyze_turn_for_followup: {e}")
        return fallback
