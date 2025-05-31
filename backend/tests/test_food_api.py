import unittest
import json
from datetime import datetime, date, timedelta, timezone
import backend.main # To access app
from backend.main import db # Import db instance
from backend.models import User, Plant, Recipe, MealEntry, WeeklyProgress # Models
# Helper functions from main are not directly imported for testing API,
# but get_current_week_start_date might be useful for crafting expected dates.
from backend.main import get_current_week_start_date, POINTS_PER_MEAL, POINTS_PER_DISTINCT_PLANT_IN_MEAL, POINTS_FOR_WEEKLY_GOAL
# User model is already imported via from backend.models import ... User ...


class TestFoodAPI(unittest.TestCase):

    def setUp(self):
        """Set up test client, in-memory DB, and app context."""
        self.flask_app = backend.main.app
        self.flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.flask_app.config['TESTING'] = True
        # Ensure SECRET_KEY is consistent for JWT
        self.flask_app.config['SECRET_KEY'] = backend.main.app.config.get('SECRET_KEY', 'test-secret-key-food-api')

        self.app = self.flask_app.test_client()

        self.app_context = self.flask_app.app_context()
        self.app_context.push()

        db.create_all()

        # Seed initial data
        self._seed_plants()
        self._setup_test_user()

    def _seed_plants(self):
        # Pre-populate plants
        # Note: created_by_user_id is None for these global plants
        self.plant1 = Plant(name="Apple", type="normal", created_by_user_id=None)
        self.plant2_spice = Plant(name="Cinnamon", type="spice_tea", created_by_user_id=None)
        db.session.add_all([self.plant1, self.plant2_spice])
        db.session.commit()
        # Refresh instances to get IDs assigned by DB
        self.plant1 = Plant.query.get(self.plant1.id)
        self.plant2_spice = Plant.query.get(self.plant2_spice.id)


    def _setup_test_user(self):
        self.test_user_username = "foodtestuser"
        self.test_user_email = "food@example.com"
        self.test_user_password = "password123"

        reg_response = self._register_user_api(self.test_user_username, self.test_user_email, self.test_user_password)
        if reg_response.status_code != 201:
            # If registration fails, try to fetch user in case it's from a previous failed test run
            existing_user = User.query.filter_by(username=self.test_user_username).first()
            if existing_user:
                self.test_user_id = existing_user.id
            else: # If still no user, fail setup
                raise Exception(f"User registration failed in setUp: {reg_response.get_json()}")
        else:
             self.test_user_id = reg_response.get_json()['id']

        login_response = self._login_user_api(self.test_user_username, self.test_user_password)
        if login_response.status_code != 200:
            raise Exception(f"User login failed in setUp: {login_response.get_json()}")
        self.test_user_token = login_response.get_json()['token']


    def tearDown(self):
        """Clean up database session and drop tables."""
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # --- API Helper Methods ---
    def _register_user_api(self, username, email, password):
        return self.app.post('/users/register',
                             data=json.dumps({"username": username, "email": email, "password": password}),
                             content_type='application/json')

    def _login_user_api(self, username, password):
        return self.app.post('/users/login',
                             data=json.dumps({"username": username, "password": password}),
                             content_type='application/json')

    def _get_auth_headers(self):
        return {'Authorization': f'Bearer {self.test_user_token}'}

    def _create_plant_api(self, name, type_): # type is a reserved keyword
        return self.app.post('/plants',
                             data=json.dumps({'name': name, 'type': type_}),
                             content_type='application/json',
                             headers=self._get_auth_headers()) # Assuming /plants POST might be protected or need user context eventually

    def _create_recipe_api(self, name, ingredients_list_of_dicts):
         payload = {"name": name, "ingredients": ingredients_list_of_dicts}
         return self.app.post('/recipes', headers=self._get_auth_headers(), data=json.dumps(payload), content_type='application/json')

    def _log_meal_api(self, items_list_of_dicts):
        """ Helper to log meals via API. items_list_of_dicts is the 'items' field for the request. """
        return self.app.post('/meal_entries', headers=self._get_auth_headers(), data=json.dumps({"items": items_list_of_dicts}), content_type='application/json')

    # --- Recipe API Test Cases (/recipes) ---
    def test_create_recipe_success(self):
        ingredients_data = [
            {"plant_id": self.plant1.id, "quantity_description": "1 whole"},
            {"plant_id": self.plant2_spice.id, "quantity_description": "1 tsp"}
        ]
        response = self._create_recipe_api("Apple Cinnamon Delight", ingredients_data)

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data['name'], "Apple Cinnamon Delight")
        self.assertEqual(data['created_by_user_id'], self.test_user_id)
        self.assertEqual(len(data['ingredients']), 2)
        # The Recipe model's ingredients property returns list of lists/tuples
        self.assertIn([self.plant1.id, "1 whole"], data['ingredients'])
        self.assertIn([self.plant2_spice.id, "1 tsp"], data['ingredients'])

        self.assertEqual(Recipe.query.count(), 1)
        db_recipe = Recipe.query.get(data['id'])
        self.assertIsNotNone(db_recipe)
        self.assertEqual(db_recipe.name, "Apple Cinnamon Delight")

    def test_create_recipe_no_token(self):
        payload = {"name": "Secret Recipe", "ingredients": [{"plant_id": self.plant1.id, "quantity_description": "Some"}]}
        response = self.app.post('/recipes', data=json.dumps(payload), content_type='application/json') # No headers
        self.assertEqual(response.status_code, 401)

    def test_create_recipe_invalid_plant_id(self):
        response = self._create_recipe_api("Ghost Recipe", [{"plant_id": 999, "quantity_description": "1 ghost pepper"}])
        self.assertEqual(response.status_code, 400)
        self.assertIn("Plant with id 999 not found", response.get_json()['error'])

    def test_create_recipe_missing_fields(self):
        payload = {"ingredients": [{"plant_id": self.plant1.id, "quantity_description": "Some"}]} # Missing name
        response = self.app.post('/recipes', headers=self._get_auth_headers(), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_get_user_recipes_success(self):
        # Create recipe1 for self.test_user
        self._create_recipe_api("My Recipe", [{"plant_id": self.plant1.id, "quantity_description": "1"}])

        # Create another user and their recipe (not to be returned)
        other_user_reg = self._register_user_api("otheruser", "other@example.com", "password")
        self.assertEqual(other_user_reg.status_code, 201)
        other_user_login = self._login_user_api("otheruser", "password")
        self.assertEqual(other_user_login.status_code, 200)
        other_user_token = other_user_login.get_json()['token']

        self.app.post('/recipes', headers={'Authorization': f'Bearer {other_user_token}'},
                        data=json.dumps({"name": "Other User Recipe", "ingredients": [{"plant_id": self.plant2_spice.id, "quantity_description": "2g"}]}),
                        content_type='application/json')

        response = self.app.get('/recipes', headers=self._get_auth_headers()) # Get recipes for self.test_user
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], "My Recipe")

    def test_get_recipes_no_token(self):
        response = self.app.get('/recipes') # No headers
        self.assertEqual(response.status_code, 401)

    # --- Meal Entry API Test Cases (/meal_entries) ---
    def test_log_meal_individual_plants_success(self):
        response = self._log_meal_api([{'plant_id': self.plant1.id, 'quantity': 2.0}])
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['plant_id'], self.plant1.id)
        self.assertEqual(data[0]['quantity'], 2.0)
        self.assertEqual(data[0]['user_id'], self.test_user_id)
        self.assertIsNone(data[0]['is_recipe_component_of'])
        self.assertEqual(MealEntry.query.count(), 1)

    def test_log_meal_with_recipe_success(self):
        recipe_resp = self._create_recipe_api("Test Salad", [
            {"plant_id": self.plant1.id, "quantity_description": "1 apple"},
            {"plant_id": self.plant2_spice.id, "quantity_description": "pinch"}
        ])
        self.assertEqual(recipe_resp.status_code, 201)
        test_recipe_id = recipe_resp.get_json()['id']

        meal_response = self._log_meal_api([{'recipe_id': test_recipe_id}])
        self.assertEqual(meal_response.status_code, 201)
        data = meal_response.get_json()
        self.assertEqual(len(data), 2) # Two ingredients in the recipe

        self.assertEqual(MealEntry.query.count(), 2)
        meal_entries_for_recipe = MealEntry.query.filter_by(is_recipe_component_of=test_recipe_id).all()
        self.assertEqual(len(meal_entries_for_recipe), 2)
        entry_plant_ids = {entry.plant_id for entry in meal_entries_for_recipe}
        self.assertIn(self.plant1.id, entry_plant_ids)
        self.assertIn(self.plant2_spice.id, entry_plant_ids)

    def test_log_meal_no_token(self):
        response = self.app.post('/meal_entries', data=json.dumps({"items": [{'plant_id': self.plant1.id}]}), content_type='application/json')
        self.assertEqual(response.status_code, 401)

    def test_log_meal_invalid_plant_id(self):
        response = self._log_meal_api([{'plant_id': 999, 'quantity': 1.0}])
        self.assertEqual(response.status_code, 400)

    def test_log_meal_invalid_recipe_id(self):
        response = self._log_meal_api([{'recipe_id': 999}])
        self.assertEqual(response.status_code, 400)

    def test_log_meal_recipe_not_owned(self):
        # Create recipe for another user
        other_user_reg = self._register_user_api("otheruser2", "other2@example.com", "password")
        self.assertEqual(other_user_reg.status_code, 201)
        other_user_login = self._login_user_api("otheruser2", "password")
        self.assertEqual(other_user_login.status_code, 200)
        other_user_token = other_user_login.get_json()['token']

        recipe_resp_other_user = self.app.post('/recipes',
            headers={'Authorization': f'Bearer {other_user_token}'},
            data=json.dumps({"name": "Not My Recipe", "ingredients": [{"plant_id": self.plant1.id, "quantity_description": "1"}]}),
            content_type='application/json')
        self.assertEqual(recipe_resp_other_user.status_code, 201)
        other_recipe_id = recipe_resp_other_user.get_json()['id']

        # Try to log meal with self.test_user_token
        response = self._log_meal_api([{'recipe_id': other_recipe_id}])
        self.assertEqual(response.status_code, 403)

    def test_log_meal_malformed_item(self):
        response = self._log_meal_api([{'bad_key': 1}])
        self.assertEqual(response.status_code, 400)

    # --- Test Cases for get_current_week_start_date (direct call, no API) ---
    def test_get_week_start_monday(self):
        monday = date(2023, 10, 23)
        self.assertEqual(get_current_week_start_date(monday), monday)

    def test_get_week_start_sunday(self):
        sunday = date(2023, 10, 29)
        expected_monday = date(2023, 10, 23)
        self.assertEqual(get_current_week_start_date(sunday), expected_monday)

    def test_get_week_start_mid_week(self):
        wednesday = date(2023, 10, 25)
        expected_monday = date(2023, 10, 23)
        self.assertEqual(get_current_week_start_date(wednesday), expected_monday)

    # --- Test Cases for update_weekly_progress (tested via meal logging API) ---
    def test_progress_no_meals_this_week(self):
        # Ensure no meals are logged for self.test_user_id in the current week
        # update_weekly_progress is called after meal logging. If no meals, it might not be called.
        # Let's explicitly call it to ensure a record for the user exists if no meals are logged.
        # However, the current design calls update_weekly_progress from create_meal_entries.
        # So, if no meals are created via API, update_weekly_progress isn't called for that user.
        # This test should verify that if a user has NO meal entries, their progress is 0 or non-existent.
        # If we want a record to exist even with 0, update_weekly_progress would need to be callable separately.
        # For now, let's assume it's okay if no record exists for a user with no meals this week.
        # Or, we can create a dummy meal entry to trigger the update.

        # To test the "no meals this week" scenario for update_weekly_progress,
        # we need to ensure it's called. We can log a meal for a *different* user
        # or directly call it if we modify its context dependency (not ideal for API testing).
        # Let's just check that for our test_user, if they log no meals, no progress record is made
        # OR if it is made (e.g. by another user's activity triggering a global check - not current design)
        # its score is 0.
        # Current design: update_weekly_progress is called by create_meal_entries for the current user.
        # So if test_user logs no meals, their progress won't be updated.

        # This test will ensure that if we call it manually (as if by a cron job or similar)
        # a record is created with 0 if no relevant meals.
        with self.app_context: # Ensure DB operations can happen
             backend.main.update_weekly_progress(self.test_user_id) # Direct call

        progress_record = WeeklyProgress.query.filter_by(user_id=self.test_user_id, week_start_date=get_current_week_start_date(date.today())).first()
        self.assertIsNotNone(progress_record)
        self.assertEqual(progress_record.distinct_plant_count, 0)
        self.assertIsNone(progress_record.goal_achieved_date)


    def test_progress_one_normal_plant_via_api(self):
        self._log_meal_api([{'plant_id': self.plant1.id, 'quantity': 1.0}])
        progress_record = WeeklyProgress.query.filter_by(user_id=self.test_user_id).first()
        self.assertIsNotNone(progress_record)
        self.assertEqual(progress_record.distinct_plant_count, 1.0)

    def test_progress_one_spice_plant_via_api(self):
        self._log_meal_api([{'plant_id': self.plant2_spice.id, 'quantity': 1.0}])
        progress_record = WeeklyProgress.query.filter_by(user_id=self.test_user_id).first()
        self.assertIsNotNone(progress_record)
        self.assertEqual(progress_record.distinct_plant_count, 0.25)

    def test_progress_mixed_distinct_plants_via_api(self):
        self._log_meal_api([
            {'plant_id': self.plant1.id, 'quantity': 1.0},
            {'plant_id': self.plant2_spice.id, 'quantity': 1.0}
        ])
        progress_record = WeeklyProgress.query.filter_by(user_id=self.test_user_id).first()
        self.assertIsNotNone(progress_record)
        self.assertEqual(progress_record.distinct_plant_count, 1.25)

    def test_progress_duplicate_plants_in_meal_via_api(self):
        self._log_meal_api([
            {'plant_id': self.plant1.id, 'quantity': 1.0},
            {'plant_id': self.plant1.id, 'quantity': 0.5} # Same plant, different entry in same log
        ])
        # The API will create two MealEntry objects.
        # update_weekly_progress should count plant1 only once for the score.
        progress_record = WeeklyProgress.query.filter_by(user_id=self.test_user_id).first()
        self.assertIsNotNone(progress_record)
        self.assertEqual(progress_record.distinct_plant_count, 1.0)

    def test_progress_multiple_meals_same_week_distinct_plants_via_api(self):
        self._log_meal_api([{'plant_id': self.plant1.id, 'quantity': 1.0}]) # First meal, score 1.0
        self._log_meal_api([{'plant_id': self.plant2_spice.id, 'quantity': 1.0}]) # Second meal, score adds 0.25

        self.assertEqual(WeeklyProgress.query.filter_by(user_id=self.test_user_id).count(), 1)
        progress_record = WeeklyProgress.query.filter_by(user_id=self.test_user_id).first()
        self.assertIsNotNone(progress_record)
        self.assertEqual(progress_record.distinct_plant_count, 1.25)

    def test_progress_goal_met_via_api(self):
        # Create 29 additional distinct normal plants
        temp_plants_created_ids = []
        for i in range(29):
            plant_name = f"Temp Normal Plant {i}"
            # Use API to create plants to ensure they are in DB for find_plant_by_id
            # Assuming create_plant does not require auth or uses a system/test auth
            # For this test, let's add them directly to DB session within test context
            temp_plant = Plant(name=plant_name, type="normal", created_by_user_id=None)
            db.session.add(temp_plant)
        db.session.commit() # Commit all temp plants

        # Fetch them back to get their IDs
        all_temp_plants = Plant.query.filter(Plant.name.like("Temp Normal Plant %")).all()
        self.assertEqual(len(all_temp_plants), 29)
        temp_plants_created_ids = [p.id for p in all_temp_plants]

        meal_items = [{'plant_id': self.plant1.id, 'quantity': 1.0}] # self.plant1 is normal (score 1)
        for plant_id in temp_plants_created_ids:
            meal_items.append({'plant_id': plant_id, 'quantity': 1.0})

        self.assertEqual(len(meal_items), 30) # 1 (plant1) + 29 temp plants

        self._log_meal_api(meal_items)

        progress_record = WeeklyProgress.query.filter_by(user_id=self.test_user_id).first()
        self.assertIsNotNone(progress_record)
        self.assertEqual(progress_record.distinct_plant_count, 30.0)
        self.assertIsNotNone(progress_record.goal_achieved_date)
        self.assertEqual(progress_record.goal_achieved_date, date.today())

    def test_progress_goal_already_met_score_changes_via_api(self):
        # 1. Achieve goal (similar to test_progress_goal_met)
        temp_plants_for_goal_ids = []
        for i in range(29):
            temp_plant = Plant(name=f"Goal Plant {i}", type="normal")
            db.session.add(temp_plant)
        db.session.commit()
        all_goal_plants = Plant.query.filter(Plant.name.like("Goal Plant %")).all()
        temp_plants_for_goal_ids = [p.id for p in all_goal_plants]

        meal_items_goal = [{'plant_id': self.plant1.id, 'quantity': 1.0}]
        for plant_id in temp_plants_for_goal_ids:
            meal_items_goal.append({'plant_id': plant_id, 'quantity': 1.0})

        self._log_meal_api(meal_items_goal)

        progress_record = WeeklyProgress.query.filter_by(user_id=self.test_user_id).first()
        self.assertIsNotNone(progress_record)
        self.assertEqual(progress_record.distinct_plant_count, 30.0)
        first_goal_date = progress_record.goal_achieved_date
        self.assertIsNotNone(first_goal_date)

        # 2. Log another distinct plant (spice for variety)
        self._log_meal_api([{'plant_id': self.plant2_spice.id, 'quantity': 1.0}]) # plant2_spice adds 0.25

        updated_progress_record = WeeklyProgress.query.filter_by(user_id=self.test_user_id).first() # Should be the same record
        self.assertIsNotNone(updated_progress_record)
        self.assertEqual(updated_progress_record.id, progress_record.id) # Same record
        self.assertEqual(updated_progress_record.distinct_plant_count, 30.25) # Score increased
        self.assertEqual(updated_progress_record.goal_achieved_date, first_goal_date) # Date should not change

    def test_progress_meals_last_week_vs_this_week_via_api(self):
        # This test is tricky because update_weekly_progress always uses datetime.now().
        # To truly test different weeks' records, we'd need to mock datetime.now()
        # or have update_weekly_progress accept a date parameter.
        # Given current implementation, it will always update current week's record.
        # Logging a meal for "last week" via API will still result in update_weekly_progress
        # calculating score for *this* week, but that meal entry won't be included.

        # Log meal for "last week" - API will store it with a past date
        # For this, we need to directly create a MealEntry with a past date,
        # because the API endpoint uses current_time.
        with self.app_context: # To allow db operations
            past_meal_entry = MealEntry(
                user_id=self.test_user_id,
                plant_id=self.plant1.id, # Score 1.0
                quantity=1.0,
                entry_datetime=datetime.now(timezone.utc) - timedelta(days=7)
            )
            db.session.add(past_meal_entry)
            db.session.commit()
            # Manually call update_weekly_progress, simulating it ran last week
            # This requires modifying update_weekly_progress to take a 'today_date'
            # OR we accept its current limitation.
            # For now, let's test current behavior: update_weekly_progress is for *actual* current week.

        # Call update_weekly_progress for the user. It should create a record for *this* week,
        # and ignore the meal entry from last week.
        with self.app_context:
            backend.main.update_weekly_progress(self.test_user_id)

        progress_this_week_initial = WeeklyProgress.query.filter_by(
            user_id=self.test_user_id,
            week_start_date=get_current_week_start_date(date.today())
        ).first()
        self.assertIsNotNone(progress_this_week_initial, "Progress for this week should exist after update.")
        self.assertEqual(progress_this_week_initial.distinct_plant_count, 0, "Score should be 0 as last week's meal is ignored for this week's record.")

        # Now, log a meal for *this* week via API
        self._log_meal_api([{'plant_id': self.plant2_spice.id, 'quantity': 1.0}]) # Score 0.25

        progress_this_week_updated = WeeklyProgress.query.filter_by(
            user_id=self.test_user_id,
            week_start_date=get_current_week_start_date(date.today())
        ).first()
        self.assertIsNotNone(progress_this_week_updated)
        self.assertEqual(progress_this_week_updated.distinct_plant_count, 0.25) # Only this week's spice plant

        # There should only be one weekly progress record for this user (for the current week)
        self.assertEqual(WeeklyProgress.query.filter_by(user_id=self.test_user_id).count(), 1)

    # --- Test Cases for GET /weekly_progress/current ---

    def test_get_current_progress_no_token(self):
        response = self.app.get('/weekly_progress/current')
        self.assertEqual(response.status_code, 401)

    def test_get_current_progress_no_existing_record(self):
        response = self.app.get('/weekly_progress/current', headers=self._get_auth_headers())
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        self.assertEqual(data['user_id'], self.test_user_id)
        self.assertEqual(data['distinct_plant_count'], 0.0)
        self.assertIsNone(data['goal_achieved_date'])

        today = datetime.now(timezone.utc).date()
        expected_week_start = get_current_week_start_date(today).isoformat()
        self.assertEqual(data['week_start_date'], expected_week_start)
        self.assertNotIn('id', data) # Or self.assertIsNone(data.get('id'))

    def test_get_current_progress_with_existing_record(self):
        # Log one normal plant using the API to trigger WeeklyProgress record creation
        meal_data = {'items': [{'plant_id': self.plant1.id, 'quantity': 1.0}]}
        log_response = self.app.post('/meal_entries', json=meal_data, headers=self._get_auth_headers())
        self.assertEqual(log_response.status_code, 201, "Prerequisite: Failed to log meal")

        response = self.app.get('/weekly_progress/current', headers=self._get_auth_headers())
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        self.assertEqual(data['user_id'], self.test_user_id)
        self.assertEqual(data['distinct_plant_count'], 1.0) # plant1 is normal type
        self.assertIsNone(data['goal_achieved_date'])

        today = datetime.now(timezone.utc).date()
        expected_week_start = get_current_week_start_date(today).isoformat()
        self.assertEqual(data['week_start_date'], expected_week_start)
        self.assertIsNotNone(data.get('id')) # Record should exist and have an ID

    def test_get_current_progress_goal_achieved(self):
        # Create and log 30 distinct normal plants
        temp_plants_for_goal = []
        for i in range(30):
            plant = Plant(name=f"TempGoalPlant{i}", type="normal")
            temp_plants_for_goal.append(plant)
        db.session.add_all(temp_plants_for_goal)
        db.session.commit()

        # Fetch their IDs
        logged_plant_ids = [p.id for p in Plant.query.filter(Plant.name.like('TempGoalPlant%')).all()]
        self.assertEqual(len(logged_plant_ids), 30, "Failed to create 30 temp plants for goal test")

        meal_items = [{'plant_id': pid, 'quantity': 1.0} for pid in logged_plant_ids]
        log_response = self.app.post('/meal_entries', json={'items': meal_items}, headers=self._get_auth_headers())
        self.assertEqual(log_response.status_code, 201, "Failed to log meals for goal achievement test")

        response = self.app.get('/weekly_progress/current', headers=self._get_auth_headers())
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        self.assertEqual(data['user_id'], self.test_user_id)
        self.assertGreaterEqual(data['distinct_plant_count'], 30.0)
        self.assertIsNotNone(data['goal_achieved_date'])
        self.assertEqual(data['goal_achieved_date'], datetime.now(timezone.utc).date().isoformat())
        self.assertIsNotNone(data.get('id'))

    # --- Test Cases for Points Awarding ---

    def test_points_awarded_for_meal_logging(self):
        # Get initial points (should be 0 for a fresh user in test after setup)
        user = User.query.get(self.test_user_id)
        self.assertIsNotNone(user, "Test user not found in DB at start of points test")
        initial_points = user.total_points
        self.assertEqual(initial_points, 0, "Initial points for test user should be 0")

        # Log a meal with 1 distinct normal plant (self.plant1)
        meal1_data = {'items': [{'plant_id': self.plant1.id, 'quantity': 1.0}]}
        response = self.app.post('/meal_entries', json=meal1_data, headers=self._get_auth_headers())
        self.assertEqual(response.status_code, 201, f"Meal1 logging failed: {response.data.decode()}")

        user = User.query.get(self.test_user_id) # Re-fetch user
        expected_points_after_meal1 = initial_points + POINTS_PER_MEAL + (1 * POINTS_PER_DISTINCT_PLANT_IN_MEAL)
        self.assertEqual(user.total_points, expected_points_after_meal1)

        # Log another meal with 2 distinct plants (self.plant1, self.plant2_spice)
        # Note: self.plant1 has been logged before, but it's distinct *for this meal*
        meal2_data = {'items': [
            {'plant_id': self.plant1.id, 'quantity': 1.0},
            {'plant_id': self.plant2_spice.id, 'quantity': 1.0}
        ]}
        response = self.app.post('/meal_entries', json=meal2_data, headers=self._get_auth_headers())
        self.assertEqual(response.status_code, 201, f"Meal2 logging failed: {response.data.decode()}")

        user = User.query.get(self.test_user_id) # Re-fetch user
        expected_points_after_meal2 = expected_points_after_meal1 + POINTS_PER_MEAL + (2 * POINTS_PER_DISTINCT_PLANT_IN_MEAL)
        self.assertEqual(user.total_points, expected_points_after_meal2)

    def test_points_awarded_for_weekly_goal(self):
        user = User.query.get(self.test_user_id)
        self.assertIsNotNone(user, "Test user not found in DB at start of weekly goal points test")
        initial_points = user.total_points
        self.assertEqual(initial_points, 0, "Initial points for test user should be 0 for weekly goal test")

        # Setup: Create 30 distinct normal plants for reliable goal achievement
        temp_plants = []
        for i in range(30):
            # Ensure unique names if there's a unique constraint on plant names in tests
            plant = Plant(name=f"GoalTestPlant_WPG_{i}", type="normal")
            temp_plants.append(plant)
        db.session.add_all(temp_plants)
        db.session.commit()

        # Fetch their IDs after commit
        goal_plant_ids = [p.id for p in Plant.query.filter(Plant.name.like('GoalTestPlant_WPG_%')).all()]
        self.assertEqual(len(goal_plant_ids), 30, "Failed to create 30 plants for goal test")

        # Log these 30 distinct plants in one meal
        meal_items = [{'plant_id': pid, 'quantity': 1.0} for pid in goal_plant_ids]
        log_response = self.app.post('/meal_entries', json={'items': meal_items}, headers=self._get_auth_headers())
        self.assertEqual(log_response.status_code, 201, f"Meal logging failed for goal achievement: {log_response.data.decode()}")

        user = User.query.get(self.test_user_id) # Re-fetch user
        points_from_meal_logging = POINTS_PER_MEAL + (30 * POINTS_PER_DISTINCT_PLANT_IN_MEAL)
        expected_points_after_goal = initial_points + points_from_meal_logging + POINTS_FOR_WEEKLY_GOAL
        self.assertEqual(user.total_points, expected_points_after_goal)

        # Log another meal in the same week (goal already met)
        # Use self.plant1 which was not part of the 30 temp plants
        another_meal_data = {'items': [{'plant_id': self.plant1.id, 'quantity': 1.0}]}
        log_response2 = self.app.post('/meal_entries', json=another_meal_data, headers=self._get_auth_headers())
        self.assertEqual(log_response2.status_code, 201, f"Logging another meal failed: {log_response2.data.decode()}")

        user = User.query.get(self.test_user_id)
        points_from_another_meal = POINTS_PER_MEAL + (1 * POINTS_PER_DISTINCT_PLANT_IN_MEAL)
        # Goal points should NOT be awarded again for the same week
        expected_points_final = expected_points_after_goal + points_from_another_meal
        self.assertEqual(user.total_points, expected_points_final)

        # Cleanup temp plants
        # This requires the User object associated with plants to be handled if cascade delete is on,
        # or ensure created_by_user_id is None for these temp plants if that's allowed.
        # For now, assuming simple delete works or tearDown handles full DB clear.
        # Plant.query.filter(Plant.name.like('GoalTestPlant_WPG_%')).delete(synchronize_session='fetch')
        # db.session.commit()
        # Let tearDown handle cleanup to avoid issues with session state if tests fail mid-way.

if __name__ == "__main__":
    unittest.main()
