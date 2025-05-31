import unittest
import json
import jwt
from datetime import datetime, timedelta, timezone
import backend.main # To access app and potentially config
from backend.main import db # Import db instance
from backend.models import User # For assertions

class TestUserAPI(unittest.TestCase):

    def setUp(self):
        """Set up test client, in-memory DB, and app context."""
        self.flask_app = backend.main.app
        self.flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.flask_app.config['TESTING'] = True
        self.flask_app.config['SECRET_KEY'] = backend.main.app.config.get('SECRET_KEY', 'test-secret-key-user-api')

        self.app = self.flask_app.test_client()

        self.app_context = self.flask_app.app_context()
        self.app_context.push() # Push context

        db.create_all() # Create tables

    def tearDown(self):
        """Clean up database session and drop tables."""
        db.session.remove()
        db.drop_all()
        self.app_context.pop() # Pop context

    def _register_user(self, username, email, password):
        """Helper method to register a user via API."""
        payload = {}
        if username is not None: payload['username'] = username
        if email is not None: payload['email'] = email
        if password is not None: payload['password'] = password

        return self.app.post('/users/register',
                             data=json.dumps(payload),
                             content_type='application/json')

    # --- Registration Test Cases ---
    def test_register_user_success(self):
        response = self._register_user("testuser", "test@example.com", "password123")
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertEqual(data['username'], "testuser")
        self.assertEqual(data['email'], "test@example.com")
        self.assertNotIn('password_hash', data)
        self.assertNotIn('password', data)

        # DB Verification
        self.assertEqual(User.query.count(), 1)
        db_user = User.query.filter_by(username="testuser").first()
        self.assertIsNotNone(db_user)
        self.assertEqual(db_user.email, "test@example.com")
        self.assertEqual(db_user.id, data['id']) # Ensure response ID matches DB ID
        self.assertTrue(len(db_user.password_hash) > 0)

    def test_register_user_missing_username(self):
        response = self._register_user(None, "test@example.com", "password123")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.query.count(), 0)

    def test_register_user_missing_email(self):
        response = self._register_user("testuser", None, "password123")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.query.count(), 0)

    def test_register_user_missing_password(self):
        response = self._register_user("testuser", "test@example.com", None)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.query.count(), 0)

    def test_register_user_duplicate_username(self):
        self._register_user("testuser", "test1@example.com", "password123")
        response = self._register_user("testuser", "test2@example.com", "password456")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(User.query.count(), 1) # Only the first user should be in DB

    def test_register_user_duplicate_email(self):
        self._register_user("testuser1", "test@example.com", "password123")
        response = self._register_user("testuser2", "test@example.com", "password456")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(User.query.count(), 1)

    # --- Login Test Cases ---
    def test_login_user_success(self):
        reg_response = self._register_user("testuser", "test@example.com", "password123")
        self.assertEqual(reg_response.status_code, 201) # Prerequisite for login

        response = self.app.post('/users/login',
                                 data=json.dumps({"username": "testuser", "password": "password123"}),
                                 content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['message'], "Login successful")
        self.assertIn('user', data)
        self.assertEqual(data['user']['username'], "testuser")
        self.assertEqual(data['user']['email'], "test@example.com")

        db_user = User.query.filter_by(username="testuser").first()
        self.assertIsNotNone(db_user)
        self.assertEqual(data['user']['id'], db_user.id) # Ensure response ID matches DB ID
        self.assertIn('token', data)
        self.assertTrue(data['token'])

    def test_login_user_not_found(self):
        response = self.app.post('/users/login',
                                 data=json.dumps({"username": "nonexistent", "password": "password123"}),
                                 content_type='application/json')
        self.assertEqual(response.status_code, 401)

    def test_login_user_wrong_password(self):
        self._register_user("testuser", "test@example.com", "password123")
        response = self.app.post('/users/login',
                                 data=json.dumps({"username": "testuser", "password": "wrongpassword"}),
                                 content_type='application/json')
        self.assertEqual(response.status_code, 401)

    def test_login_user_missing_username(self):
        response = self.app.post('/users/login',
                                 data=json.dumps({"password": "password123"}),
                                 content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_login_user_missing_password(self):
        response = self.app.post('/users/login',
                                 data=json.dumps({"username": "testuser"}),
                                 content_type='application/json')
        self.assertEqual(response.status_code, 400)

    # --- Protected Route Test Cases ---
    def test_protected_route_no_token(self):
        response = self.app.get('/protected_area')
        self.assertEqual(response.status_code, 401)

    def test_protected_route_malformed_header(self):
        response = self.app.get('/protected_area', headers={'Authorization': 'InvalidTokenFormat'})
        self.assertEqual(response.status_code, 401)

    def test_protected_route_invalid_signature_token(self):
        # A user needs to exist for the token's user_id to potentially be valid,
        # even if the signature is wrong.
        reg_resp = self._register_user("testuser_for_invalid_sig", "invsig@example.com", "password")
        user_id = json.loads(reg_resp.data)['id']

        payload = {'user_id': user_id, 'exp': datetime.now(timezone.utc) + timedelta(hours=1)}
        invalid_token = jwt.encode(payload, 'wrong-secret-key', algorithm='HS256')
        response = self.app.get('/protected_area', headers={'Authorization': f'Bearer {invalid_token}'})
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'Token is invalid!')

    def test_protected_route_expired_token(self):
        reg_response = self._register_user("expiredtokenuser", "expired@example.com", "password123")
        user_id = json.loads(reg_response.data)['id']

        payload = {'user_id': user_id, 'exp': datetime.now(timezone.utc) - timedelta(hours=1)}
        expired_token = jwt.encode(payload, self.flask_app.config['SECRET_KEY'], algorithm='HS256')
        response = self.app.get('/protected_area', headers={'Authorization': f'Bearer {expired_token}'})
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data['message'], 'Token has expired!')

    def test_protected_route_valid_token(self):
        reg_response = self._register_user("authtest", "auth@example.com", "password123")
        self.assertEqual(reg_response.status_code, 201)

        login_response = self.app.post('/users/login',
                                       data=json.dumps({"username": "authtest", "password": "password123"}),
                                       content_type='application/json')
        self.assertEqual(login_response.status_code, 200)
        login_data = json.loads(login_response.data)
        valid_token = login_data['token']
        user_id_from_login = login_data['user']['id']

        response = self.app.get('/protected_area', headers={'Authorization': f'Bearer {valid_token}'})
        self.assertEqual(response.status_code, 200)
        protected_data = json.loads(response.data)
        self.assertIn(f'Welcome to the protected area, authtest!', protected_data['message'])
        self.assertEqual(protected_data['user_id'], user_id_from_login)

    def test_get_me_endpoint(self):
        """Test the /users/me endpoint for a newly registered user."""
        # Register a new user
        reg_response = self._register_user("mepointstest", "mepoints@example.com", "password123")
        self.assertEqual(reg_response.status_code, 201, "User registration failed")

        # Log in the user to get a token
        login_response = self.app.post('/users/login',
                                        data=json.dumps({"username": "mepointstest", "password": "password123"}),
                                        content_type='application/json')
        self.assertEqual(login_response.status_code, 200, "User login failed")
        login_data = json.loads(login_response.data)
        self.assertIn('token', login_data, "Token not found in login response")
        token = login_data['token']

        # Call /users/me
        me_response = self.app.get('/users/me', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(me_response.status_code, 200, "/users/me endpoint failed")
        me_data = json.loads(me_response.data)

        # Assertions for /users/me response
        self.assertIn('id', me_data)
        self.assertEqual(me_data['username'], "mepointstest")
        self.assertEqual(me_data['email'], "mepoints@example.com")
        self.assertIn('total_points', me_data, "total_points not in /users/me response")
        self.assertEqual(me_data['total_points'], 0, "Newly registered user should have 0 total_points")

if __name__ == "__main__":
    unittest.main()
