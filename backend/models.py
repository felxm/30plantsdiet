from datetime import datetime, date

class User:
    def __init__(self, id: int, username: str, password_hash: str, email: str):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.email = email

class Plant:
    def __init__(self, id: int, name: str, type: str, created_by_user_id: int):
        self.id = id
        self.name = name
        self.type = type  # e.g., 'normal', 'spice_tea'
        self.created_by_user_id = created_by_user_id

class Recipe:
    def __init__(self, id: int, name: str, ingredients: list[tuple[int, str]], created_by_user_id: int):
        self.id = id
        self.name = name
        self.ingredients = ingredients  # List of tuples, e.g., [('plant_id', 'quantity_description')]
        self.created_by_user_id = created_by_user_id

class MealEntry:
    def __init__(self, id: int, user_id: int, plant_id: int, quantity: float, entry_datetime: datetime, is_recipe_component_of: int | None = None):
        self.id = id
        self.user_id = user_id
        self.plant_id = plant_id
        self.quantity = quantity
        self.entry_datetime = entry_datetime
        self.is_recipe_component_of = is_recipe_component_of  # Optional foreign key to Recipe

class WeeklyProgress:
    def __init__(self, id: int, user_id: int, week_start_date: date, distinct_plant_count: float, goal_achieved_date: date | None = None):
        self.id = id
        self.user_id = user_id
        self.week_start_date = week_start_date
        self.distinct_plant_count = distinct_plant_count
        self.goal_achieved_date = goal_achieved_date  # Optional
