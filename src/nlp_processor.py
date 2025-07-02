import json
import openai  # For interacting with Ollama's OpenAI-compatible API
import re
import os
import sys
import time
from thefuzz import fuzz  # For initial fast filtering
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

# --- Configuration ---
# Path to your scraped product data
PRODUCT_DATA_FILE = r"C:\Users\zdoes\Downloads\alibaba_explorer\scraped_alibaba_new_arrivals_enhanced.json"
# The model name you have pulled and are running in Ollama
OLLAMA_MODEL_NAME = "llama3:8b"  # <<< TRY A SMALL, FAST MODEL FIRST (e.g., gemma3:1b or llama3.2)
# Ollama API endpoint
OLLAMA_BASE_URL = "http://localhost:11434/v1"

# --- Stage 1: Fuzzy Search Configuration ---
# Number of top results from fuzzy search to pass to LLM for re-ranking
FUZZY_SEARCH_CANDIDATES_COUNT = 30
# Minimum fuzzy search score to be considered a candidate (0-100)
MIN_FUZZY_SCORE_THRESHOLD = 40

# --- Stage 2 & Display Configuration ---
# Minimum LLM-assigned score (0-10) for a product to be considered "reasonably related" and displayed
MIN_LLM_SCORE_TO_DISPLAY = 5  # <<< ADJUST THIS THRESHOLD AS NEEDED (e.g., 5, 6, or 7)
# Maximum number of results to display, even if many meet the MIN_LLM_SCORE_TO_DISPLAY
MAX_RESULTS_TO_DISPLAY_CAP = 20 # <<< ADJUST THIS CAP AS NEEDED

# --- NLTK Setup ---
_nltk_data_downloaded = False
def download_nltk_data_once():
    global _nltk_data_downloaded
    if _nltk_data_downloaded: return
    nltk_dependencies = ["wordnet", "stopwords", "punkt"]
    print("Checking NLTK data dependencies...")
    for dep in nltk_dependencies:
        try:
            nltk.data.find(f"corpora/{dep}" if dep != "punkt" else f"tokenizers/{dep}")
            print(f"  NLTK data '{dep}' found.")
        except LookupError:
            print(f"  Downloading NLTK data: {dep}...")
            nltk.download(dep, quiet=True)
    _nltk_data_downloaded = True
    print("NLTK data check complete.")

lemmatizer = WordNetLemmatizer()
stop_words = None

def initialize_nltk_resources():
    global stop_words
    download_nltk_data_once()
    stop_words = set(stopwords.words("english"))

def preprocess_text_for_fuzzy(text):
    if stop_words is None: initialize_nltk_resources()
    if not text or not isinstance(text, str): return ""
    text = re.sub(r"\W", " ", text).lower()
    text = re.sub(r"\s+", " ", text)
    tokens = nltk.word_tokenize(text)
    tokens = [lemmatizer.lemmatize(word) for word in tokens if word not in stop_words and len(word) > 1]
    return " ".join(tokens)

# --- Initialize OpenAI Client for Ollama ---
client = None
try:
    client = openai.OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
    print(f"OpenAI client initialized for Ollama at {OLLAMA_BASE_URL}")
except Exception as e:
    print(f"Error initializing OpenAI client for Ollama: {e}")

def query_local_llm(prompt_text, model_name, system_message="You are a helpful relevance scoring assistant."):
    if not client: return None
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt_text}
            ],
            temperature=0.2, max_tokens=60,
        )
        return completion.choices[0].message.content.strip()
    except openai.APIConnectionError as e:
        print(f"Ollama Connection Error (model: {model_name}): Is Ollama running and model available? {e}")
    except Exception as e:
        print(f"Error calling local LLM API for model '{model_name}': {e}")
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
    # print(f"Warning: Could not parse score (0-10) from LLM response: '{llm_response_text}'. Defaulting to 0.")
    return 0

def hybrid_product_search(user_query, products_data, llm_model_name):
    if not products_data: return []
    print(f"\nStarting Hybrid Search for query: '{user_query}'")
    print("-" * 40)
    start_time_total = time.time()

    print("Stage 1: Fuzzy matching for initial candidates...")
    processed_query_for_fuzzy = preprocess_text_for_fuzzy(user_query)
    if not processed_query_for_fuzzy:
        print("Query empty after preprocessing for fuzzy search. No results."); return []
    print(f"  NLTK-Processed query for fuzzy matching: '{processed_query_for_fuzzy}'")

    fuzzy_candidates = []
    for product in products_data:
        product_name = product.get("name")
        if not product_name: continue
        processed_name = preprocess_text_for_fuzzy(product_name)
        if not processed_name: continue
        fuzzy_score = fuzz.token_set_ratio(processed_query_for_fuzzy, processed_name)
        if fuzzy_score >= MIN_FUZZY_SCORE_THRESHOLD:
            fuzzy_candidates.append({"product_data": product, "fuzzy_score": fuzzy_score})

    fuzzy_candidates.sort(key=lambda x: x["fuzzy_score"], reverse=True)
    top_fuzzy_candidates = fuzzy_candidates[:FUZZY_SEARCH_CANDIDATES_COUNT]

    if not top_fuzzy_candidates:
        print(f"No candidates found after fuzzy matching (threshold: {MIN_FUZZY_SCORE_THRESHOLD})."); return []
    print(f"Found {len(top_fuzzy_candidates)} candidates from fuzzy matching to pass to LLM.")
    print("-" * 40)

    print(f"Stage 2: LLM re-ranking of {len(top_fuzzy_candidates)} candidates using model '{llm_model_name}'...")
    llm_scored_products = []
    for i, candidate in enumerate(top_fuzzy_candidates):
        product = candidate["product_data"]
        product_name = product.get("name")
        prompt = (
            f"User query: '{user_query}'\n"
            f"Product name: '{product_name}'\n\n"
            f"On a scale of 0 to 10 (10 is extremely relevant, 0 is not relevant), "
            f"how relevant is this product to the user query based ONLY on the product name and query?\n"
            f"Respond with only the numerical score (e.g., 'Score: 7' or just '7')."
        )
        print(f"  LLM processing candidate {i+1}/{len(top_fuzzy_candidates)}: {product_name[:60]}... (Fuzzy: {candidate['fuzzy_score']})")
        start_llm_call = time.time()
        llm_response = query_local_llm(prompt, llm_model_name)
        llm_call_duration = time.time() - start_llm_call
        llm_score = 0
        if llm_response:
            llm_score = parse_llm_score(llm_response)
            print(f"    LLM raw: '{llm_response}', Parsed LLM score: {llm_score}, Time: {llm_call_duration:.2f}s")
        else:
            print(f"    Failed to get LLM response. LLM score: 0. Time: {llm_call_duration:.2f}s")
        
        llm_scored_products.append({
            "name": product_name, "product_url": product.get("product_url"),
            "image_url": product.get("image_url"), "price": product.get("price"),
            "alibaba_category": product.get("alibaba_category"),
            "llm_raw_response": llm_response or "Error/No Response",
            "similarity_score": llm_score, # LLM's score
            "original_fuzzy_score": candidate["fuzzy_score"]
        })

    total_processing_time = time.time() - start_time_total
    print("-" * 40)
    print(f"Finished LLM re-ranking. Total hybrid search time: {total_processing_time:.2f} seconds.")
    llm_scored_products.sort(key=lambda x: x["similarity_score"], reverse=True)
    return llm_scored_products

if __name__ == "__main__":
    initialize_nltk_resources()
    if not client:
        print("Exiting: Ollama client not initialized. Please check if Ollama is running."); sys.exit(1)

    try:
        with open(PRODUCT_DATA_FILE, "r", encoding="utf-8") as f:
            all_products = json.load(f)
        print(f"Successfully loaded {len(all_products)} products from {PRODUCT_DATA_FILE}")
    except Exception as e:
        print(f"Error loading product data from {PRODUCT_DATA_FILE}: {e}"); all_products = []

    if not all_products: print("No products loaded. Exiting."); sys.exit(1)

    print("\n" + "="*70)
    print("Hybrid Product Search Engine (Fuzzy Filter + LLM Re-ranking)")
    print(f"Will use fuzzy matching to find top {FUZZY_SEARCH_CANDIDATES_COUNT} candidates (min score: {MIN_FUZZY_SCORE_THRESHOLD}),")
    print(f"then use LLM model '{OLLAMA_MODEL_NAME}' to re-rank them.")
    print(f"Results with LLM score >= {MIN_LLM_SCORE_TO_DISPLAY} will be shown, up to {MAX_RESULTS_TO_DISPLAY_CAP} items.")
    print("="*70 + "\n")

    try:
        user_search_query = input("Enter your search query (e.g., 'eco friendly shopping bag with logo'): ").strip()
        if not user_search_query:
            print("No search query entered. Exiting.")
        else:
            results = hybrid_product_search(user_search_query, all_products, OLLAMA_MODEL_NAME)

            print(f"\n--- Search Results for '{user_search_query}' (Showing reasonably related items) ---")
            if not results:
                print("No products found matching your criteria after LLM re-ranking.")
            else:
                displayed_count = 0
                for i, res_product in enumerate(results):
                    if res_product.get("similarity_score", 0) >= MIN_LLM_SCORE_TO_DISPLAY:
                        if displayed_count < MAX_RESULTS_TO_DISPLAY_CAP:
                            print(f"\n{displayed_count+1}. Name: {res_product.get('name')}")
                            print(f"   LLM Score: {res_product.get('similarity_score')}")
                            print(f"   (Original Fuzzy Score: {res_product.get('original_fuzzy_score')})")
                            # print(f"   LLM Raw Output for score: \"{res_product.get('llm_raw_response')}\"") # Uncomment for debugging LLM score parsing
                            print(f"   Category: {res_product.get('alibaba_category')}")
                            print(f"   Price: {res_product.get('price')}")
                            print(f"   URL: {res_product.get('product_url')}")
                            displayed_count += 1
                        else:
                            print(f"\nReached maximum display cap of {MAX_RESULTS_TO_DISPLAY_CAP} relevant items.")
                            break 
                    else:
                        # Since results are sorted by LLM score, once we hit one below threshold,
                        # all subsequent ones will also be below (or equal if scores are tied).
                        if displayed_count == 0:
                             print(f"No products met the minimum LLM relevance score of {MIN_LLM_SCORE_TO_DISPLAY}.")
                        else:
                             print(f"\n--- End of reasonably related items (score fell below {MIN_LLM_SCORE_TO_DISPLAY}) ---")
                        break
                
                if displayed_count == 0 and results and results[0].get("similarity_score", 0) < MIN_LLM_SCORE_TO_DISPLAY :
                    # This case is for when there were results, but none met the threshold.
                    # The inner loop's "No products met..." message would have already printed.
                    pass
                elif displayed_count > 0 and displayed_count < len(results) and results[displayed_count-1].get("similarity_score",0) >= MIN_LLM_SCORE_TO_DISPLAY and (displayed_count == MAX_RESULTS_TO_DISPLAY_CAP or results[displayed_count].get("similarity_score",0) < MIN_LLM_SCORE_TO_DISPLAY):
                    # This means we either hit the cap or the next item was below threshold.
                    pass
                elif displayed_count == 0 and not results: # Should be caught by outer 'if not results'
                     print("No products found by the search logic at all.")


    except KeyboardInterrupt:
        print("\nSearch interrupted by user.")
    except Exception as e:
        print(f"An unexpected error occurred during the search process: {e}")

