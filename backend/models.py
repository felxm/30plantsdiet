from backend.main import db
from datetime import datetime, timezone, date # Ensure date is imported for WeeklyProgress
import json
from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    total_points = db.Column(db.Integer, default=0, nullable=False) # New field

    # Relationships
    recipes = db.relationship('Recipe', backref='creator', lazy=True)
    meal_entries = db.relationship('MealEntry', backref='user', lazy=True)
    weekly_progress_entries = db.relationship('WeeklyProgress', backref='user', lazy=True)

    def __init__(self, username, email, password, id=None): # id is optional, total_points handled by default
        if id is not None: # This was from before when IDs were manually managed for in-memory
            self.id = id    # For SQLAlchemy, id is auto-generated on commit if not provided
        self.username = username
        self.email = email
        self.set_password(password)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        # No need to check for self.password_hash is None, as it's nullable=False
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class Plant(db.Model):
    __tablename__ = 'plant'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    type = db.Column(db.String(50), nullable=False)  # e.g., 'normal', 'spice_tea'
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Defaulting to system/global plant if null

    # Relationship
    meal_entries = db.relationship('MealEntry', backref='plant_consumed', lazy=True)

    # No custom __init__ needed if all fields are passed as kwargs to SQLAlchemy, or simple one:
    def __init__(self, name, type, id=None, created_by_user_id=None):
        if id is not None:
            self.id = id
        self.name = name
        self.type = type
        self.created_by_user_id = created_by_user_id

    def __repr__(self):
        return f'<Plant {self.name}>'

class Recipe(db.Model):
    __tablename__ = 'recipe'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    _ingredients_json = db.Column(db.Text, nullable=False)  # Store ingredients as JSON string
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    @property
    def ingredients(self):
        return json.loads(self._ingredients_json)

    @ingredients.setter
    def ingredients(self, value):
        if not isinstance(value, list):
            raise ValueError("Ingredients must be a list of tuples or lists.")
        # Ensure inner elements are appropriate, e.g. list of [plant_id, quantity_description]
        # The model stored tuples (plant_id, quantity_str)
        # JSON stores them as lists of lists.
        for item in value:
            if not (isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], int) and isinstance(item[1], str)):
                raise ValueError("Each ingredient must be a tuple/list of [plant_id (int), quantity_description (str)].")
        self._ingredients_json = json.dumps(value)

    def __init__(self, name, ingredients, created_by_user_id, id=None):
        if id is not None:
            self.id = id
        self.name = name
        self.ingredients = ingredients # This will use the setter
        self.created_by_user_id = created_by_user_id

    def __repr__(self):
        return f'<Recipe {self.name}>'

class MealEntry(db.Model):
    __tablename__ = 'meal_entry'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    plant_id = db.Column(db.Integer, db.ForeignKey('plant.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=1.0)
    entry_datetime = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    is_recipe_component_of = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=True)

    # No custom __init__ needed if SQLAlchemy handles all kwargs, or simple one:
    def __init__(self, user_id, plant_id, quantity=1.0, entry_datetime=None, is_recipe_component_of=None, id=None):
        if id is not None:
            self.id = id
        self.user_id = user_id
        self.plant_id = plant_id
        self.quantity = quantity
        self.entry_datetime = entry_datetime if entry_datetime is not None else datetime.now(timezone.utc)
        self.is_recipe_component_of = is_recipe_component_of

    def __repr__(self):
        return f'<MealEntry {self.id} by User {self.user_id}>'

class WeeklyProgress(db.Model):
    __tablename__ = 'weekly_progress'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    week_start_date = db.Column(db.Date, nullable=False) # SQLAlchemy handles date objects directly
    distinct_plant_count = db.Column(db.Float, nullable=False, default=0.0)
    goal_achieved_date = db.Column(db.Date, nullable=True) # SQLAlchemy handles date objects

    __table_args__ = (db.UniqueConstraint('user_id', 'week_start_date', name='uq_user_week_start'),)

    # No custom __init__ needed if SQLAlchemy handles all kwargs, or simple one:
    def __init__(self, user_id, week_start_date, distinct_plant_count=0.0, goal_achieved_date=None, id=None):
        if id is not None:
            self.id = id
        self.user_id = user_id
        self.week_start_date = week_start_date # Should be a date object
        self.distinct_plant_count = distinct_plant_count
        self.goal_achieved_date = goal_achieved_date # Should be a date object or None

    def __repr__(self):
        return f'<WeeklyProgress User {self.user_id} Week {self.week_start_date}>'
