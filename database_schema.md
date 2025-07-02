# Database Schema: Alibaba New Arrivals Product Explorer

This document outlines the database schema for the Alibaba New Arrivals Product Explorer. The schema is designed to support the core functionalities including product storage, user favorites/tracking, and keyword/niche management.

## Tables

### 1. `products`

Stores information about products scraped from Alibaba.

| Column Name         | Data Type     | Constraints              | Description                                                                 |
|---------------------|---------------|--------------------------|-----------------------------------------------------------------------------|
| `id`                | INTEGER       | PRIMARY KEY, AUTOINCREMENT | Unique identifier for the product.                                          |
| `alibaba_product_id`| VARCHAR(255)  | UNIQUE, NOT NULL         | Product ID from Alibaba (if available and unique).                          |
| `name`              | TEXT          | NOT NULL                 | Product name.                                                               |
| `description`       | TEXT          | NULLABLE                 | Product description.                                                        |
| `product_url`       | TEXT          | NOT NULL, UNIQUE         | Direct URL to the product page on Alibaba.                                  |
| `image_url`         | TEXT          | NULLABLE                 | URL of the product image.                                                   |
| `price`             | VARCHAR(100)  | NULLABLE                 | Product price (stored as string to accommodate various formats/currencies). |
| `alibaba_category`  | TEXT          | NULLABLE                 | Category as listed on Alibaba.                                              |
| `smart_category_id` | INTEGER       | FOREIGN KEY (`categories.id`) | Foreign key referencing the `categories` table for smart categorization.    |
| `arrival_date`      | TIMESTAMP     | NOT NULL                 | Date and time when the product was first scraped.                           |
| `last_scraped_date` | TIMESTAMP     | NOT NULL                 | Date and time when the product was last updated/verified by the scraper.    |
| `is_active`         | BOOLEAN       | NOT NULL, DEFAULT TRUE   | Flag to indicate if the product is within the 30-day active window.         |

**Indexes:**
*   `idx_products_arrival_date` on `arrival_date` (for 30-day archive management)
*   `idx_products_name` on `name` (for searching/filtering)
*   `idx_products_smart_category_id` on `smart_category_id`

### 2. `categories` (Smart Categories/Niches)

Stores the smart categories or niches identified by the NLP module or defined by users.

| Column Name    | Data Type    | Constraints              | Description                                         |
|----------------|--------------|--------------------------|-----------------------------------------------------|
| `id`           | INTEGER      | PRIMARY KEY, AUTOINCREMENT | Unique identifier for the category/niche.           |
| `name`         | VARCHAR(255) | UNIQUE, NOT NULL         | Name of the category or niche (e.g., "Home Decor"). |
| `description`  | TEXT         | NULLABLE                 | Optional description of the category/niche.         |
| `cluster_id`   | INTEGER      | NULLABLE, FOREIGN KEY (`keyword_clusters.id`) | Foreign key referencing a keyword cluster.          |

**Indexes:**
*   `idx_categories_name` on `name` (for searching/filtering)

### 3. `keywords`

Stores keywords extracted from products or entered by users.

| Column Name | Data Type    | Constraints              | Description                               |
|-------------|--------------|--------------------------|-------------------------------------------|
| `id`        | INTEGER      | PRIMARY KEY, AUTOINCREMENT | Unique identifier for the keyword.        |
| `term`      | VARCHAR(255) | UNIQUE, NOT NULL         | The keyword itself (e.g., "wireless charger"). |

**Indexes:**
*   `idx_keywords_term` on `term`

### 4. `product_keywords` (Many-to-Many relationship between `products` and `keywords`)

Links products to relevant keywords.

| Column Name | Data Type | Constraints                                           | Description                                      |
|-------------|-----------|-------------------------------------------------------|--------------------------------------------------|
| `product_id`| INTEGER   | PRIMARY KEY, FOREIGN KEY (`products.id`) ON DELETE CASCADE | Foreign key referencing the `products` table.    |
| `keyword_id`| INTEGER   | PRIMARY KEY, FOREIGN KEY (`keywords.id`) ON DELETE CASCADE | Foreign key referencing the `keywords` table.    |

### 5. `keyword_clusters`

Stores clusters of similar keywords.

| Column Name   | Data Type    | Constraints              | Description                                       |
|---------------|--------------|--------------------------|---------------------------------------------------|
| `id`          | INTEGER      | PRIMARY KEY, AUTOINCREMENT | Unique identifier for the keyword cluster.        |
| `cluster_name`| VARCHAR(255) | UNIQUE, NOT NULL         | A representative name for the cluster.            |
| `description` | TEXT         | NULLABLE                 | Optional description of the keyword cluster.      |

### 6. `cluster_keywords` (Many-to-Many relationship between `keyword_clusters` and `keywords`)

Links keywords to their respective clusters.

| Column Name      | Data Type | Constraints                                                      | Description                                            |
|------------------|-----------|------------------------------------------------------------------|--------------------------------------------------------|
| `cluster_id`     | INTEGER   | PRIMARY KEY, FOREIGN KEY (`keyword_clusters.id`) ON DELETE CASCADE | Foreign key referencing the `keyword_clusters` table.  |
| `keyword_id`     | INTEGER   | PRIMARY KEY, FOREIGN KEY (`keywords.id`) ON DELETE CASCADE         | Foreign key referencing the `keywords` table.          |

### 7. `user_favorites`

Stores products favorited or tracked by users. (Assumes a `users` table will be added if authentication is implemented. For now, it can be simplified or made device/session-based if full user accounts are out of scope for the initial version).

| Column Name  | Data Type | Constraints                                           | Description                                      |
|--------------|-----------|-------------------------------------------------------|--------------------------------------------------|
| `id`         | INTEGER   | PRIMARY KEY, AUTOINCREMENT                            | Unique identifier for the favorite entry.        |
| `user_id`    | INTEGER   | NOT NULL (FOREIGN KEY (`users.id`) if `users` table exists) | Identifier for the user.                         |
| `product_id` | INTEGER   | NOT NULL, FOREIGN KEY (`products.id`) ON DELETE CASCADE | Foreign key referencing the `products` table.    |
| `notes`      | TEXT      | NULLABLE                                              | User-added notes for the tracked product.        |
| `added_date` | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP                   | Date and time when the product was favorited.    |

**Indexes:**
*   `idx_user_favorites_user_product` on (`user_id`, `product_id`) (UNIQUE constraint if a user can favorite a product only once)

## Relationships:

*   One `product` can belong to one `smart_category` (from `categories` table).
*   One `product` can have many `keywords` (via `product_keywords` table).
*   One `keyword` can belong to many `products` (via `product_keywords` table).
*   One `keyword` can belong to many `keyword_clusters` (via `cluster_keywords` table).
*   One `keyword_cluster` can contain many `keywords` (via `cluster_keywords` table).
*   One `category` (niche) can optionally be associated with one `keyword_cluster`.
*   One `user` can have many `user_favorites`.
*   One `product` can be favorited by many `users` (via `user_favorites` table).

## Considerations for Future Enhancements:

*   **`users` table:** For full user authentication and management.
    *   `id` (PK), `username`, `email`, `password_hash`, `created_at`.
*   **Scraping Logs:** A table to log the status, duration, and any errors from each scraping session.
*   **Price History:** If tracking price changes over time is a requirement, a separate table for price history linked to products.

This schema provides a foundation for the Alibaba New Arrivals Product Explorer. It will be implemented using SQLAlchemy models within the Flask application structure.
