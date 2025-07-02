#!/usr/bin/env python3
import sys
import os

# --- IMPORTANT: Add project root to Python's path ---
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
print(f"DEBUG main.py: Project root '{project_root}' added to sys.path.")
# --- End of path modification ---

from flask import Flask, render_template, jsonify, request, redirect, url_for
from src.models.models import db, Product, Category, UserFavorite # Assuming models.py is in src/models/
# Assuming nlp_utils.py is in src/ and src/__init__.py exists
from src.nlp_utils import (
    perform_hybrid_search,
    initialize_nltk_resources,
    OLLAMA_MODEL_NAME as NLP_OLLAMA_MODEL_NAME # Import the configured model name
)

import json
from datetime import datetime, timedelta

# APScheduler Imports
from apscheduler.schedulers.background import BackgroundScheduler
import atexit


# --- DEBUG PRINT: Confirm imported model name ---
print(f"DEBUG main.py: Imported NLP_OLLAMA_MODEL_NAME from nlp_utils is: {NLP_OLLAMA_MODEL_NAME}")

app = Flask(__name__,
            template_folder=".",  # Looks for templates in the same directory as main.py (i.e., src/)
            static_folder="static") # Looks for static files in src/static/

# --- Database Configuration ---
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///alibaba_explorer.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# --- Initialize NLP resources once on Flask app startup ---
with app.app_context():
    print("DEBUG main.py: Initializing NLTK resources via nlp_utils...")
    initialize_nltk_resources() # This also initializes Ollama client in nlp_utils

# --- App Configuration for Search Behavior ---
app.config["MIN_LLM_SCORE_TO_DISPLAY"] = 5
app.config["MAX_RESULTS_TO_DISPLAY_CAP"] = 500
app.config["FUZZY_SEARCH_CANDIDATES_COUNT"] = 500 # Number of candidates for LLM
app.config["MIN_FUZZY_SCORE_THRESHOLD"] = 40   # Min fuzzy score for stage 1

# --- Helper Functions ---
def archive_old_products():
    # This function now handles its own app_context for database operations
    print("Archiving old products...")
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    with app.app_context():
        try:
            old_products = Product.query.filter(Product.last_scraped_date < thirty_days_ago, Product.is_active == True).all()
            if old_products:
                for product in old_products:
                    product.is_active = False
                db.session.commit()
                print(f"Archived {len(old_products)} products.")
            else:
                print("No active products found older than 30 days to archive.")
        except Exception as e:
            db.session.rollback()
            print(f"Error archiving old products: {e}")

def load_scraped_data_to_db():
    # Note: This function's database operations (Product.query, db.session.add, db.session.commit)
    # need to be called within an active Flask application context.
    # Callers like scheduled_load_data_job, load_data_command, run_scraper_route,
    # and the initial startup logic are responsible for providing this context.
    print("Attempting to load scraped data into DB...")
    scraper_output_file = r"C:\Users\zdoes\Downloads\alibaba_explorer\scraped_alibaba_new_arrivals_enhanced.json"
    try:
        with open(scraper_output_file, "r", encoding="utf-8") as f:
            products_data = json.load(f)
        print(f"Loaded {len(products_data)} items from {scraper_output_file}")
    except FileNotFoundError:
        print(f"ERROR: Scraper output file '{scraper_output_file}' not found. Skipping DB load.")
        return
    except json.JSONDecodeError:
        print(f"ERROR: Could not decode JSON from '{scraper_output_file}'. Skipping DB load.")
        return
    except Exception as e:
        print(f"ERROR: Unexpected error loading '{scraper_output_file}': {e}")
        return

    added_count = 0
    updated_count = 0
    for prod_data in products_data:
        if not prod_data.get("product_url") or not prod_data.get("name"):
            print(f"Skipping product due to missing URL or name: {str(prod_data)[:100]}...")
            continue
        existing_product = Product.query.filter_by(product_url=prod_data.get("product_url")).first()
        if existing_product:
            existing_product.name = prod_data.get("name", existing_product.name)
            existing_product.price = prod_data.get("price", existing_product.price)
            existing_product.image_url = prod_data.get("image_url", existing_product.image_url)
            existing_product.alibaba_category = prod_data.get("alibaba_category", existing_product.alibaba_category)
            existing_product.last_scraped_date = datetime.utcnow()
            existing_product.is_active = True # Ensure re-scraped products are active
            updated_count += 1
        else:
            new_product = Product(
                name=prod_data.get("name"), product_url=prod_data.get("product_url"),
                image_url=prod_data.get("image_url"), price=prod_data.get("price"),
                alibaba_category=prod_data.get("alibaba_category"),
                arrival_date=datetime.utcnow(), last_scraped_date=datetime.utcnow(),
                is_active=True
            )
            db.session.add(new_product)
            added_count +=1
    try:
        db.session.commit()
        print(f"DB Load: {added_count} new products added, {updated_count} products updated.")
    except Exception as e:
        db.session.rollback()
        print(f"Error committing product data to database: {e}")
    
    archive_old_products() # This will run within the app_context provided by the caller

# --- Routes ---
@app.route("/")
def index():
    page = request.args.get("page", 1, type=int)
    per_page_db_query = 20
    user_query = request.args.get("query", "", type=str).strip()

    products_to_display = []
    pagination_obj = None
    search_method_used = "Latest Products (No Query)"
    total_results_count = 0

    print(f"DEBUG main.py index route: Received query: '{user_query}'")

    if user_query:
        print(f"DEBUG main.py index route: Using LLM model '{NLP_OLLAMA_MODEL_NAME}' for hybrid search (imported from nlp_utils).")
        search_method_used = f"Hybrid LLM Search for '{user_query}' using {NLP_OLLAMA_MODEL_NAME}"
        
        all_active_db_products_dicts = [
            {
                "id": p.id, "name": p.name, "product_url": p.product_url,
                "image_url": p.image_url, "price": p.price,
                "alibaba_category": p.alibaba_category
            }
            for p in Product.query.filter(Product.is_active == True).all()
        ]

        if not all_active_db_products_dicts:
            print("No active products in DB to search for web request.")
        else:
            llm_search_results = perform_hybrid_search(
                user_query, 
                all_active_db_products_dicts,
                fuzzy_candidates_count=app.config["FUZZY_SEARCH_CANDIDATES_COUNT"],
                min_fuzzy_score_threshold=app.config["MIN_FUZZY_SCORE_THRESHOLD"],
                llm_model_to_use=NLP_OLLAMA_MODEL_NAME
            )
            
            min_score_display = app.config["MIN_LLM_SCORE_TO_DISPLAY"]
            max_cap_display = app.config["MAX_RESULTS_TO_DISPLAY_CAP"]
            
            for res_dict in llm_search_results:
                if res_dict.get("similarity_score", 0) >= min_score_display:
                    if len(products_to_display) < max_cap_display:
                        products_to_display.append(res_dict)
                    else: break 
                else: break 
            total_results_count = len(products_to_display)
            print(f"Displaying {total_results_count} products after LLM scoring and filtering.")
            
    else: # No search query
        products_query_obj = Product.query.filter(Product.is_active == True)
        pagination_obj = products_query_obj.order_by(Product.last_scraped_date.desc()).paginate(page=page, per_page=per_page_db_query, error_out=False)
        products_to_display = pagination_obj.items
        total_results_count = pagination_obj.total
    
    clusters = [] 

    return render_template("index.html", 
                           products=products_to_display, 
                           pagination=pagination_obj,
                           query=user_query, 
                           search_method=search_method_used,
                           total_results=total_results_count,
                           clusters=clusters,
                           selected_cluster=None)

@app.route("/favorites")
def favorites():
    favs = UserFavorite.query.filter_by(user_id=1).join(Product).order_by(UserFavorite.added_date.desc()).all()
    return render_template("favorites.html", favorites=favs)

@app.route("/add_favorite/<int:product_id>", methods=["POST"])
def add_favorite(product_id):
    existing_fav = UserFavorite.query.filter_by(user_id=1, product_id=product_id).first()
    if not existing_fav:
        product_to_fav = Product.query.filter_by(id=product_id, is_active=True).first()
        if product_to_fav:
            fav = UserFavorite(user_id=1, product_id=product_id)
            db.session.add(fav)
            db.session.commit()
            print(f"Added product ID {product_id} to favorites.")
        else:
            print(f"Could not add favorite: Product ID {product_id} not found or inactive.")
    return redirect(request.referrer or url_for("index"))

@app.route("/remove_favorite/<int:product_id>", methods=["POST"])
def remove_favorite(product_id):
    fav = UserFavorite.query.filter_by(user_id=1, product_id=product_id).first()
    if fav:
        db.session.delete(fav)
        db.session.commit()
        print(f"Removed product ID {product_id} from favorites.")
    return redirect(request.referrer or url_for("favorites"))

@app.route("/run_scraper", methods=["POST"])
def run_scraper_route():
    print("Received request to /run_scraper. Triggering data load...")
    with app.app_context(): # Ensure context for the call
        load_scraped_data_to_db()
    print("Data loading triggered after simulated scraper run.")
    return redirect(url_for("index"))

# --- CLI Commands for DB setup ---
@app.cli.command("init-db")
def init_db_command():
    with app.app_context():
        db.create_all()
        print("Initialized the database and created tables.")

@app.cli.command("load-data")
def load_data_command():
    with app.app_context():
        print("CLI: Attempting to load data...")
        load_scraped_data_to_db()
        print("CLI: Data loading and archival process finished.")

@app.cli.command("archive-data")
def archive_data_command():
    # archive_old_products now handles its own context
    archive_old_products() 
    print("CLI: Manual archival process finished.")

@app.cli.command("clear-products")
def clear_products_command():
    with app.app_context():
        try:
            num_favs = UserFavorite.query.delete()
            num_prods = Product.query.delete()
            db.session.commit()
            print(f"Cleared {num_prods} products and {num_favs} favorites from the database.")
        except Exception as e:
            db.session.rollback()
            print(f"Error clearing database: {e}")

# APScheduler Job Function
def scheduled_load_data_job():
    """
    This function will be called by APScheduler.
    It creates an app_context to ensure database operations work correctly.
    """
    with app.app_context():
        print(f"[{datetime.now()}] APScheduler: Running scheduled data load...")
        load_scraped_data_to_db()
        print(f"[{datetime.now()}] APScheduler: Scheduled data load finished.")


if __name__ == "__main__":
    instance_path = os.path.join(app.instance_path)
    if not os.path.exists(instance_path):
        try: os.makedirs(instance_path)
        except OSError as e: print(f"Could not create instance folder at {instance_path}: {e}")

    with app.app_context():
        print("Creating database tables if they don't exist (on app startup)...")
        db.create_all()
        # Initial load if DB is empty
        if not Product.query.first(): 
            print("No products found in DB on startup, attempting to load from JSON...")
            load_scraped_data_to_db() # Runs within the existing app_context here
            
    # Setup and Start APScheduler
    scheduler = BackgroundScheduler(daemon=True)
    # Run the job every 5 minutes. Adjust 'minutes' or use 'seconds' as needed.
    # For frequent scraping, you might use a shorter interval, e.g., minutes=1 or seconds=30
    scheduler.add_job(scheduled_load_data_job, 'interval', minutes=60) 
    scheduler.start()
    print(f"APScheduler started. Will run 'load_scraped_data_to_db' every 5 minutes.")

    # Ensure the scheduler shuts down when the app exits
    atexit.register(lambda: scheduler.shutdown())
            
    print(f"Starting Flask app. Will use NLP model: {NLP_OLLAMA_MODEL_NAME} (from nlp_utils) for searches.")
    # IMPORTANT: When using APScheduler with Flask's dev server,
    # set use_reloader=False to prevent the scheduler from being initialized multiple times.
    app.run(debug=True, host="0.0.0.0", port=5001, use_reloader=False)