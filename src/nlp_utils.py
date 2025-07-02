import openai
import re
import time
from thefuzz import fuzz
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
import os # For OLLAMA_MODEL_NAME environment variable

# --- Configuration ---
# Try to get model name from environment variable, otherwise use a default
OLLAMA_MODEL_NAME = os.environ.get("OLLAMA_MODEL_NAME", "gemma3:1b")
print(f"***** NLP_UTILS.PY: OLLAMA_MODEL_NAME is set to: {OLLAMA_MODEL_NAME} *****")
OLLAMA_BASE_URL = "http://localhost:11434/v1"

# --- NLTK Setup ---
_nltk_data_downloaded = False
lemmatizer = WordNetLemmatizer()
stop_words = None

def download_nltk_data_once():
    global _nltk_data_downloaded
    if _nltk_data_downloaded:
        return
    nltk_dependencies = ["wordnet", "stopwords", "punkt"]
    print("Checking NLTK data dependencies for nlp_utils...")
    for dep in nltk_dependencies:
        try:
            if dep == "punkt": nltk.data.find(f"tokenizers/{dep}")
            else: nltk.data.find(f"corpora/{dep}")
            print(f"  NLTK data '{dep}' found.")
        except LookupError:
            print(f"  Downloading NLTK data: {dep}...")
            nltk.download(dep, quiet=True)
    _nltk_data_downloaded = True
    print("NLTK data check complete for nlp_utils.")

def initialize_nltk_resources():
    global stop_words
    if stop_words is None:
        download_nltk_data_once()
        stop_words = set(stopwords.words("english"))
        print("NLTK stop_words initialized in nlp_utils.")

def preprocess_text_for_fuzzy(text):
    if stop_words is None:
        initialize_nltk_resources()
    if not text or not isinstance(text, str):
        return ""
    text = re.sub(r"\W", " ", text).lower()
    text = re.sub(r"\s+", " ", text)
    tokens = nltk.word_tokenize(text)
    tokens = [lemmatizer.lemmatize(word) for word in tokens if word not in stop_words and len(word) > 1]
    return " ".join(tokens)

# --- Ollama Client Initialization ---
ollama_client = None
try:
    ollama_client = openai.OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
    print(f"Ollama client initialized in nlp_utils, pointing to {OLLAMA_BASE_URL}.")
    # You could add a quick ping or model list here to confirm connection on startup
    # ollama_client.models.list()
except Exception as e:
    print(f"Error initializing Ollama client in nlp_utils: {e}")
    ollama_client = None

def query_local_llm(prompt_text, model_name_override=None, system_message="You are a helpful relevance scoring assistant."):
    if not ollama_client:
        print("Ollama client not initialized in nlp_utils.")
        return None
    
    current_model_name = model_name_override if model_name_override else OLLAMA_MODEL_NAME

    try:
        completion = ollama_client.chat.completions.create(
            model=current_model_name,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt_text}
            ],
            temperature=0.2,
            max_tokens=60,
        )
        return completion.choices[0].message.content.strip()
    except openai.APIConnectionError as e:
        print(f"Ollama Connection Error (model: {current_model_name}): Is Ollama running and model available? {e}")
    except Exception as e:
        print(f"Error calling local LLM API for model '{current_model_name}': {e}")
    return None

def parse_llm_score(llm_response_text):
    if not llm_response_text: return 0
    match = re.search(r"(?:Score is|Score:\s*|Relevance:\s*|Rating:\s*)?(\b(?:10|[0-9])\b)(?:/10)?", llm_response_text, re.IGNORECASE)
    if match:
        try:
            score = int(match.group(1))
            if 0 <= score <= 10: return score
        except ValueError: pass
    numbers = re.findall(r'\b(10|[0-9])\b', llm_response_text)
    if numbers:
        try:
            score = int(numbers[-1])
            if 0 <= score <= 10: return score
        except ValueError: pass
    return 0

def perform_hybrid_search(user_query, all_db_products, 
                          fuzzy_candidates_count=30, 
                          min_fuzzy_score_threshold=40,
                          llm_model_to_use=None):
    """
    Performs a two-stage search on a list of product data.
    Args:
        user_query (str): The user's search query.
        all_db_products (list): A list of product dictionaries from the database.
                                Each dict should at least have 'id', 'name'.
        fuzzy_candidates_count (int): How many candidates from fuzzy search to re-rank.
        min_fuzzy_score_threshold (int): Min fuzzy score to be considered.
        llm_model_to_use (str, optional): Specific Ollama model name for this search. Defaults to OLLAMA_MODEL_NAME.
    Returns:
        list: A list of product dictionaries, sorted by LLM score, with scores included.
    """
    if not all_db_products: return []
    
    actual_llm_model = llm_model_to_use if llm_model_to_use else OLLAMA_MODEL_NAME
    print(f"Performing hybrid search with LLM: {actual_llm_model}")

    # --- Stage 1: Fast Fuzzy Candidate Filtering ---
    processed_query_for_fuzzy = preprocess_text_for_fuzzy(user_query)
    if not processed_query_for_fuzzy:
        print("Query empty after preprocessing for fuzzy search.")
        return []

    fuzzy_candidates = []
    for product_dict in all_db_products: # Expecting a list of dicts
        product_name = product_dict.get("name")
        if not product_name: continue
        processed_name = preprocess_text_for_fuzzy(product_name)
        if not processed_name: continue
        
        fuzzy_score = fuzz.token_set_ratio(processed_query_for_fuzzy, processed_name)
        if fuzzy_score >= min_fuzzy_score_threshold:
            # Add the original product dictionary and its fuzzy score
            fuzzy_candidates.append({"product_data": product_dict, "fuzzy_score": fuzzy_score})

    fuzzy_candidates.sort(key=lambda x: x["fuzzy_score"], reverse=True)
    top_fuzzy_candidates = fuzzy_candidates[:fuzzy_candidates_count]

    if not top_fuzzy_candidates:
        print(f"No candidates found after fuzzy matching (threshold: {min_fuzzy_score_threshold}).")
        return []
    print(f"Found {len(top_fuzzy_candidates)} candidates from fuzzy matching to pass to LLM.")

    # --- Stage 2: LLM Re-ranking of Candidates ---
    llm_scored_products = []
    for i, candidate in enumerate(top_fuzzy_candidates):
        product_dict_data = candidate["product_data"] # This is the original product dict
        product_name_for_llm = product_dict_data.get("name")
        
        prompt = (
            f"User query: '{user_query}'\n"
            f"Product name: '{product_name_for_llm}'\n\n"
            f"On a scale of 0 to 10 (10 is extremely relevant, 0 is not relevant), "
            f"how relevant is this product to the user query based ONLY on the product name and query?\n"
            f"Respond with only the numerical score (e.g., 'Score: 7' or just '7')."
        )
        # print(f"  LLM processing candidate {i+1}/{len(top_fuzzy_candidates)}: {product_name_for_llm[:60]}...")
        llm_response = query_local_llm(prompt, model_name_override=actual_llm_model)
        llm_score = 0
        if llm_response:
            llm_score = parse_llm_score(llm_response)
        
        # Create a new dictionary for the result, copying original product data
        # and adding scoring information.
        result_product = product_dict_data.copy() 
        result_product["llm_raw_response"] = llm_response or "Error/No Response"
        result_product["similarity_score"] = llm_score # LLM's score
        result_product["original_fuzzy_score"] = candidate["fuzzy_score"]
        llm_scored_products.append(result_product)

    llm_scored_products.sort(key=lambda x: x["similarity_score"], reverse=True)
    return llm_scored_products

# Call initialization once when the module is imported
initialize_nltk_resources()

if __name__ == '__main__':
    # This part is for testing nlp_utils.py directly
    print("Testing nlp_utils.py directly...")
    if not ollama_client:
        print("Ollama client not available. Cannot run tests.")
        sys.exit(1)
        
    # Create some dummy product data similar to what the Flask app would provide
    dummy_products_from_db = [
        {"id": 1, "name": "High Quality Custom Logo Printed Recycled Brown Kraft Paper Bag for Shopping", "price": "$0.50", "alibaba_category": "Packaging"},
        {"id": 2, "name": "Eco Friendly Reusable Shopping Tote Bag with Custom Print", "price": "$1.20", "alibaba_category": "Bags"},
        {"id": 3, "name": "Luxury Velvet Pouch for Jewelry with Ribbon", "price": "$0.80", "alibaba_category": "Jewelry Accessories"},
        {"id": 4, "name": "Recycled Kraft Paper Box for Gifts", "price": "$0.30", "alibaba_category": "Packaging"},
        {"id": 5, "name": "Plain Cotton Canvas Tote Bag Bulk", "price": "$0.90", "alibaba_category": "Bags"}
    ]
    test_query = "custom recycled paper bag with logo"
    print(f"\nTest Query: '{test_query}'")
    
    # Test with a specific model available in your Ollama
    test_llm_model = "gemma3:1b" # or "gemma3:1b" if you pulled that
    # Ensure the test_llm_model is pulled in Ollama: `ollama pull llama3:8b`

    results = perform_hybrid_search(test_query, dummy_products_from_db, llm_model_to_use=test_llm_model)

    print(f"\n--- Test Search Results for '{test_query}' (Ranked by LLM) ---")
    if results:
        for i, res_product in enumerate(results):
            print(f"\n{i+1}. Name: {res_product.get('name')}")
            print(f"   LLM Score: {res_product.get('similarity_score')}")
            print(f"   (Original Fuzzy Score: {res_product.get('original_fuzzy_score')})")
            print(f"   LLM Raw Output: \"{res_product.get('llm_raw_response')}\"")
    else:
        print("No relevant products found in test.")
