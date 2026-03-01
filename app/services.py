import boto3
import json
import os
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

    # 3. Call Claude 3 Haiku
    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}]
        })

        # response = bedrock.invoke_model(
        #     modelId='anthropic.claude-3-haiku-20240307-v1:0', 
        #     body=body
        # )
        
        response = bedrock.invoke_model(
            modelId='amazon.titan-text-express-v1', 
            accept='application/json',
            contentType='application/json',
            body=body
        )
        
        result = json.loads(response.get('body').read())
        return result['content'][0]['text']
    except Exception as e:
        print(f"Error generating agent response: {e}")
        return "I'm sorry, I am having trouble connecting to the AI brain right now."