import jwt
from datetime import datetime, timedelta, timezone, date
from functools import wraps
from flask import Flask, request, jsonify, g, send_from_directory
from flask_sqlalchemy import SQLAlchemy

# Initialize SQLAlchemy instance first
db = SQLAlchemy()

# Import models here, AFTER db is defined and BEFORE app is used by models implicitly or explicitly
from backend.models import Plant, User, Recipe, MealEntry, WeeklyProgress

# Point Constants
POINTS_PER_MEAL = 5
POINTS_PER_DISTINCT_PLANT_IN_MEAL = 2
POINTS_FOR_WEEKLY_GOAL = 50

# Adjust path relative to main.py (which is in backend/)
app = Flask(__name__, static_folder='../frontend/static', static_url_path='/static')
app.config['SECRET_KEY'] = 'your-super-secret-key-please-change-in-prod'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///plant_tracker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize db with app
db.init_app(app)


# --- Helper Functions ---
def find_plant_by_id(plant_id):
    """Helper function to find a plant by its ID using SQLAlchemy."""
    try:
        return Plant.query.get(int(plant_id))
    except ValueError:
        return None

def find_recipe_by_id(recipe_id):
    """Helper function to find a recipe by its ID using SQLAlchemy."""
    try:
        return Recipe.query.get(int(recipe_id))
    except ValueError:
        return None

def get_current_week_start_date(today_date_param: date) -> date:
    days_to_monday = today_date_param.isoweekday() - 1
    return today_date_param - timedelta(days=days_to_monday)

def update_weekly_progress(user_id: int):
    today = datetime.now(timezone.utc).date()
    current_week_start = get_current_week_start_date(today)
    start_of_week_dt = datetime.combine(current_week_start, datetime.min.time(), tzinfo=timezone.utc)
    start_of_next_week_dt = start_of_week_dt + timedelta(days=7)

    relevant_meal_entries = MealEntry.query.filter(
        MealEntry.user_id == user_id,
        MealEntry.entry_datetime >= start_of_week_dt,
        MealEntry.entry_datetime < start_of_next_week_dt
    ).all()

    distinct_plant_ids_this_week = {entry.plant_id for entry in relevant_meal_entries}
    current_weekly_score = 0.0
    for plant_id_in_set in distinct_plant_ids_this_week:
        plant = find_plant_by_id(plant_id_in_set)
        if plant:
            current_weekly_score += 0.25 if plant.type == 'spice_tea' else 1.0

    existing_progress_record = WeeklyProgress.query.filter_by(
        user_id=user_id,
        week_start_date=current_week_start
    ).first()

    if existing_progress_record:
        existing_progress_record.distinct_plant_count = current_weekly_score
        if current_weekly_score >= 30 and existing_progress_record.goal_achieved_date is None:
            existing_progress_record.goal_achieved_date = today
            # Award points for achieving the goal for the first time on an existing record
            user_to_award_points = User.query.get(user_id)
            if user_to_award_points:
                current_points = getattr(user_to_award_points, 'total_points', 0)
                user_to_award_points.total_points = (current_points or 0) + POINTS_FOR_WEEKLY_GOAL
            else:
                print(f"Error: User {user_id} not found for awarding weekly goal points (existing record).")
    else:
        goal_achieved_date_val = today if current_weekly_score >= 30 else None
        new_progress_record = WeeklyProgress(
            user_id=user_id,
            week_start_date=current_week_start,
            distinct_plant_count=current_weekly_score,
            goal_achieved_date=goal_achieved_date_val
        )
        if goal_achieved_date_val is not None:
            # Award points for achieving the goal on a new record
            user_to_award_points = User.query.get(user_id)
            if user_to_award_points:
                current_points = getattr(user_to_award_points, 'total_points', 0)
                user_to_award_points.total_points = (current_points or 0) + POINTS_FOR_WEEKLY_GOAL
            else:
                print(f"Error: User {user_id} not found for awarding weekly goal points (new record).")
        db.session.add(new_progress_record)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error updating weekly progress for user {user_id}: {str(e)}")

# --- Token Required Decorator ---
def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        if not token: return jsonify({'message': 'Token is missing!'}), 401
        try:
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            user_id_from_token = payload['user_id']
            current_user = User.query.get(user_id_from_token)
            if current_user is None:
                return jsonify({'message': 'Token is invalid, user not found!'}), 401
            g.current_user = current_user
        except jwt.ExpiredSignatureError: return jsonify({'message': 'Token has expired!'}), 401
        except jwt.InvalidTokenError: return jsonify({'message': 'Token is invalid!'}), 401
        return f(*args, **kwargs)
    return decorated_function

# --- Plant API Endpoints ---
@app.route('/plants', methods=['GET'])
def get_plants():
    all_plants_query_result = Plant.query.all()
    return jsonify([{'id':p.id, 'name':p.name, 'type':p.type, 'created_by_user_id':p.created_by_user_id} for p in all_plants_query_result])

@app.route('/plants', methods=['POST'])
def create_plant():
    data = request.get_json()
    if not data or 'name' not in data or 'type' not in data:
        return jsonify({"error": "Missing name or type in request body"}), 400
    new_plant = Plant(name=data['name'], type=data['type'], created_by_user_id=None)
    db.session.add(new_plant)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create plant', 'details': str(e)}), 500
    return jsonify({'id':new_plant.id, 'name':new_plant.name, 'type':new_plant.type, 'created_by_user_id':new_plant.created_by_user_id}), 201

# --- User API Endpoints ---
@app.route('/users/register', methods=['POST'])
def register_user():
    data = request.get_json()
    if not data or 'username' not in data or 'email' not in data or 'password' not in data:
        return jsonify({"error": "Missing username, email, or password in request body"}), 400
    if User.query.filter((User.username == data['username']) | (User.email == data['email'])).first():
        return jsonify({"error": "Username or email already exists"}), 409
    new_user = User(username=data['username'], email=data['email'], password=data['password'])
    db.session.add(new_user)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to register user', 'details': str(e)}), 500
    return jsonify({"id": new_user.id, "username": new_user.username, "email": new_user.email}), 201

@app.route('/users/login', methods=['POST'])
def login_user():
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "Missing username or password in request body"}), 400
    user_to_login = User.query.filter_by(username=data['username']).first()
    if not user_to_login or not user_to_login.check_password(data['password']):
        return jsonify({"error": "Invalid username or password"}), 401
    payload = {'user_id': user_to_login.id, 'exp': datetime.now(timezone.utc) + timedelta(hours=1)}
    token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')
    return jsonify({"message": "Login successful", "token": token, "user": {"id": user_to_login.id, "username": user_to_login.username, "email": user_to_login.email}}), 200

@app.route('/users/me', methods=['GET'])
@token_required
def get_current_user_profile():
    if not g.current_user:
        return jsonify({"error": "User not found or token invalid"}), 401
    user_data = {
        "id": g.current_user.id,
        "username": g.current_user.username,
        "email": g.current_user.email,
        "total_points": g.current_user.total_points # Added total_points
    }
    return jsonify(user_data), 200

@app.route('/weekly_progress/current', methods=['GET'])
@token_required
def get_current_weekly_progress():
    user_id = g.current_user.id
    today = datetime.now(timezone.utc).date()
    current_week_start = get_current_week_start_date(today)
    progress_record = WeeklyProgress.query.filter_by(user_id=user_id, week_start_date=current_week_start).first()
    if progress_record:
        goal_achieved_date_str = progress_record.goal_achieved_date.isoformat() if progress_record.goal_achieved_date else None
        week_start_date_str = progress_record.week_start_date.isoformat()
        progress_data = {"id": progress_record.id, "user_id": progress_record.user_id, "week_start_date": week_start_date_str, "distinct_plant_count": progress_record.distinct_plant_count, "goal_achieved_date": goal_achieved_date_str}
    else:
        progress_data = {"user_id": user_id, "week_start_date": current_week_start.isoformat(), "distinct_plant_count": 0.0, "goal_achieved_date": None}
    return jsonify(progress_data), 200

# --- Recipe API Endpoints ---
@app.route('/recipes', methods=['POST'])
@token_required
def create_recipe():
    data = request.get_json()
    if not data or 'name' not in data or 'ingredients' not in data:
        return jsonify({"error": "Missing name or ingredients in request body"}), 400
    if not isinstance(data['name'], str) or not isinstance(data['ingredients'], list):
        return jsonify({"error": "Invalid data type for name or ingredients"}), 400
    ingredients_for_model = []
    for ing_data in data['ingredients']:
        if not (isinstance(ing_data, dict) and 'plant_id' in ing_data and 'quantity_description' in ing_data and isinstance(ing_data['plant_id'], int) and isinstance(ing_data['quantity_description'], str)):
            return jsonify({"error": "Invalid ingredient format"}), 400
        if not find_plant_by_id(ing_data['plant_id']):
            return jsonify({'error': f'Plant with id {ing_data["plant_id"]} not found.'}), 400
        ingredients_for_model.append([ing_data['plant_id'], ing_data['quantity_description']])
    new_recipe = Recipe(name=data['name'], ingredients=ingredients_for_model, created_by_user_id=g.current_user.id)
    db.session.add(new_recipe)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create recipe', 'details': str(e)}), 500
    return jsonify({'id': new_recipe.id, 'name': new_recipe.name, 'ingredients': new_recipe.ingredients, 'created_by_user_id': new_recipe.created_by_user_id}), 201

@app.route('/recipes', methods=['GET'])
@token_required
def get_user_recipes():
    user_recipes_query = Recipe.query.filter_by(created_by_user_id=g.current_user.id).all()
    return jsonify([{'id':r.id, 'name':r.name, 'ingredients':r.ingredients, 'created_by_user_id':r.created_by_user_id} for r in user_recipes_query]), 200

# --- Meal Entry API Endpoint ---
@app.route('/meal_entries', methods=['POST'])
@token_required
def create_meal_entries():
    data = request.get_json()
    if not data or not isinstance(data.get('items'), list):
        return jsonify({"error": "Request body must be an 'items' list."}), 400
    user_id = g.current_user.id
    current_time = datetime.now(timezone.utc)
    meal_entry_objects_to_add = []
    for item_data in data['items']:
        if not isinstance(item_data, dict): return jsonify({"error": "Each item must be an object."}), 400
        if 'plant_id' in item_data:
            if not isinstance(item_data.get('plant_id'), int): return jsonify({"error": "plant_id must be an integer."}), 400
            try: quantity = float(item_data.get('quantity', 1.0))
            except (ValueError, TypeError): return jsonify({"error": "quantity must be a number."}), 400
            if not find_plant_by_id(item_data['plant_id']): return jsonify({'error': f'Plant with id {item_data["plant_id"]} not found.'}), 400
            meal_entry_objects_to_add.append(MealEntry(user_id=user_id, plant_id=item_data['plant_id'], quantity=quantity, entry_datetime=current_time))
        elif 'recipe_id' in item_data:
            if not isinstance(item_data.get('recipe_id'), int): return jsonify({"error": "recipe_id must be an integer."}), 400
            recipe = find_recipe_by_id(item_data['recipe_id'])
            if not recipe: return jsonify({'error': f'Recipe with id {item_data["recipe_id"]} not found.'}), 400
            if recipe.created_by_user_id != user_id: return jsonify({'error': 'Cannot log a recipe not created by you.'}), 403
            for ing_plant_id, _ in recipe.ingredients:
                if not find_plant_by_id(ing_plant_id): return jsonify({'error': f'Plant with id {ing_plant_id} in recipe {item_data["recipe_id"]} not found.'}), 500
                meal_entry_objects_to_add.append(MealEntry(user_id=user_id, plant_id=ing_plant_id, quantity=1.0, entry_datetime=current_time, is_recipe_component_of=recipe.id))
        else: return jsonify({'error': 'Invalid item. Must contain plant_id or recipe_id.'}), 400

    if not meal_entry_objects_to_add: return jsonify({'error': 'No valid meal entry items provided.'}), 400

    db.session.add_all(meal_entry_objects_to_add)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to log meal entries', 'details': str(e)}), 500

    # Award points
    user_to_update = User.query.get(user_id)
    if not user_to_update:
        print(f"Error: User {user_id} not found for awarding points after meal logging.")
    else:
        user_to_update.total_points = (user_to_update.total_points or 0) + POINTS_PER_MEAL

        distinct_plant_ids_in_this_meal = set()
        for entry in meal_entry_objects_to_add: # These are the newly created MealEntry objects
            distinct_plant_ids_in_this_meal.add(entry.plant_id)

        user_to_update.total_points += len(distinct_plant_ids_in_this_meal) * POINTS_PER_DISTINCT_PLANT_IN_MEAL

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error saving points for user {user_to_update.id}: {str(e)}")

    created_entries_response = [{'id':e.id, 'user_id':e.user_id, 'plant_id':e.plant_id, 'quantity':e.quantity, 'entry_datetime':e.entry_datetime.isoformat(), 'is_recipe_component_of':e.is_recipe_component_of} for e in meal_entry_objects_to_add]

    update_weekly_progress(user_id)

    return jsonify(created_entries_response), 201

# --- Sample Protected Route ---
@app.route('/protected_area', methods=['GET'])
@token_required
def protected_area():
    return jsonify({'message': f'Welcome to the protected area, {g.current_user.username}!', 'user_id': g.current_user.id}), 200

# --- HTML Serving Routes ---
@app.route('/')
def serve_index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/login')
def serve_login_page():
    return send_from_directory('../frontend', 'login.html')

@app.route('/register')
def serve_register_page():
    return send_from_directory('../frontend', 'register.html')

@app.route('/dashboard')
def serve_dashboard_page():
    return send_from_directory('../frontend', 'dashboard.html')

@app.route('/<path:filename>.html')
def serve_html_page(filename):
    return send_from_directory('../frontend', f"{filename}.html")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
