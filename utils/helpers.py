import openai
import os
def get_embedding(text, model="text-embedding-ada-002"):
    openai.api_key = os.getenv("OPENAI_API_KEY")
    res = openai.Embedding.create(input=text, model=model)
    return res['data'][0]['embedding']
