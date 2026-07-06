import os
from app.config import get_llm_provider, get_gemini_api_key
from app.ai import gemini_client

print('LLM_PROVIDER=', get_llm_provider())
print('GEMINI_API_KEY (env)=', os.getenv('GEMINI_API_KEY'))
print('GEMINI_API_KEY (loader)=', get_gemini_api_key())
try:
    c = gemini_client.configure_gemini()
    print('configure_gemini returned:', type(c))
except Exception as e:
    print('configure_gemini error:', repr(e))
