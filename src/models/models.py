#!/usr/bin/env python3
import os
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# This db object will be initialized in main.py
db = SQLAlchemy()

class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    alibaba_product_id = db.Column(db.String(255), unique=True, nullable=True) # Allow null if not always available
    name = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=True)
    product_url = db.Column(db.Text, nullable=False, unique=True)
    image_url = db.Column(db.Text, nullable=True)
    price = db.Column(db.String(100), nullable=True)
    alibaba_category = db.Column(db.Text, nullable=True)
    smart_category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    cluster_id = db.Column(db.Integer, nullable=True) # Added from NLP output
    arrival_date = db.Column(db.TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_scraped_date = db.Column(db.TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Relationships
    category = db.relationship("Category", back_populates="products")
    keywords = db.relationship("Keyword", secondary="product_keywords", back_populates="products")
    favorited_by = db.relationship("UserFavorite", back_populates="product")

    def __repr__(self):
        return f"<Product {self.id}: {self.name[:50]}>"

class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    # cluster_id = db.Column(db.Integer, db.ForeignKey("keyword_clusters.id"), nullable=True) # Link to keyword_clusters if needed

    products = db.relationship("Product", back_populates="category")
    # keyword_cluster = db.relationship("KeywordCluster", back_populates="categories")

    def __repr__(self):
        return f"<Category {self.id}: {self.name}>"

class Keyword(db.Model):
    __tablename__ = "keywords"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    term = db.Column(db.String(255), unique=True, nullable=False)

    products = db.relationship("Product", secondary="product_keywords", back_populates="keywords")
    # clusters = db.relationship("KeywordCluster", secondary="cluster_keywords", back_populates="keywords")

    def __repr__(self):
        return f"<Keyword {self.id}: {self.term}>"

# Association table for Product and Keyword (Many-to-Many)
product_keywords = db.Table("product_keywords",
    db.Column("product_id", db.Integer, db.ForeignKey("products.id"), primary_key=True),
    db.Column("keyword_id", db.Integer, db.ForeignKey("keywords.id"), primary_key=True)
)

# Keyword Clusters (Simplified for now, can be expanded)
# class KeywordCluster(db.Model):
#     __tablename__ = "keyword_clusters"
#     id = db.Column(db.Integer, primary_key=True, autoincrement=True)
#     cluster_name = db.Column(db.String(255), unique=True, nullable=False)
#     description = db.Column(db.Text, nullable=True)

#     categories = db.relationship("Category", back_populates="keyword_cluster")
#     keywords = db.relationship("Keyword", secondary="cluster_keywords", back_populates="clusters")

# cluster_keywords = db.Table("cluster_keywords",
#     db.Column("cluster_id", db.Integer, db.ForeignKey("keyword_clusters.id"), primary_key=True),
#     db.Column("keyword_id", db.Integer, db.ForeignKey("keywords.id"), primary_key=True)
# )

class UserFavorite(db.Model):
    __tablename__ = "user_favorites"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False) # Assuming a users table
    user_id = db.Column(db.Integer, nullable=False, default=1) # Simplified: default to user 1 for now
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    added_date = db.Column(db.TIMESTAMP, nullable=False, default=datetime.utcnow)

    product = db.relationship("Product", back_populates="favorited_by")
    # user = db.relationship("User", back_populates="favorites")

    __table_args__ = (db.UniqueConstraint("user_id", "product_id", name="uq_user_product_favorite"),)

    def __repr__(self):
        return f"<UserFavorite user_id={self.user_id} product_id={self.product_id}>"

# If you add a User model later:
# class User(db.Model):
#     __tablename__ = "users"
#     id = db.Column(db.Integer, primary_key=True, autoincrement=True)
#     username = db.Column(db.String(80), unique=True, nullable=False)
#     email = db.Column(db.String(120), unique=True, nullable=False)
#     # ... other fields like password hash, etc.
#     favorites = db.relationship("UserFavorite", back_populates="user")

