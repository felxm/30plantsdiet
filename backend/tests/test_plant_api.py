import unittest
import json
from backend.main import app, plants_db, next_plant_id
from backend.models import Plant

class TestPlantAPI(unittest.TestCase):

    def setUp(self):
        """Set up test client and reset database before each test."""
        self.app = app.test_client()
        # Configure app for testing
        app.config['TESTING'] = True 
        
        # Reset in-memory database state directly
        plants_db.clear()
        import backend.main # Import the main module to modify its variable
        backend.main.next_plant_id = 1


    def tearDown(self):
        """Clean up after tests if necessary."""
        # Reset in-memory database state directly again to be sure
        plants_db.clear()
        import backend.main # Import the main module to modify its variable
        backend.main.next_plant_id = 1

    def test_create_plant_success(self):
        """Test successful plant creation."""
        payload = {"name": "Apple", "type": "normal"}
        response = self.app.post('/plants', 
                                 data=json.dumps(payload), 
                                 content_type='application/json')
        self.assertEqual(response.status_code, 201)
        response_data = json.loads(response.data)
        self.assertEqual(response_data['name'], "Apple")
        self.assertEqual(response_data['id'], 1)
        self.assertEqual(response_data['type'], "normal")
        self.assertEqual(response_data['created_by_user_id'], 0) # As it's hardcoded

        # Verify in-memory db state
        self.assertEqual(len(plants_db), 1)
        self.assertIsInstance(plants_db[0], Plant)
        self.assertEqual(plants_db[0].name, "Apple")
        self.assertEqual(plants_db[0].id, 1)


    def test_get_plants_empty(self):
        """Test getting plants when none exist."""
        response = self.app.get('/plants')
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.data)
        self.assertEqual(response_data, [])

    def test_get_plants_after_creation(self):
        """Test getting plants after one has been created."""
        # First, create a plant
        plant_payload = {"name": "Banana", "type": "normal"}
        self.app.post('/plants', 
                      data=json.dumps(plant_payload), 
                      content_type='application/json')

        # Then, get plants
        response = self.app.get('/plants')
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.data)
        self.assertEqual(len(response_data), 1)
        self.assertEqual(response_data[0]['name'], "Banana")
        self.assertEqual(response_data[0]['id'], 1)
        self.assertEqual(response_data[0]['type'], "normal")


    def test_create_plant_missing_name(self):
        """Test plant creation with missing name."""
        payload = {"type": "spice_tea"}
        response = self.app.post('/plants', 
                                 data=json.dumps(payload), 
                                 content_type='application/json')
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.data)
        self.assertIn("error", response_data)
        self.assertEqual(response_data["error"], "Missing name or type in request body")


    def test_create_plant_missing_type(self):
        """Test plant creation with missing type."""
        payload = {"name": "Ginger"}
        response = self.app.post('/plants', 
                                 data=json.dumps(payload), 
                                 content_type='application/json')
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.data)
        self.assertIn("error", response_data)
        self.assertEqual(response_data["error"], "Missing name or type in request body")

if __name__ == "__main__":
    unittest.main()
