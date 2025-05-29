from flask import Flask, request, jsonify
from backend.models import Plant

app = Flask(__name__)

# In-memory storage for plants
plants_db = []
next_plant_id = 1

@app.route('/plants', methods=['GET'])
def get_plants():
    """Returns a list of all plants."""
    return jsonify([plant.__dict__ for plant in plants_db])

@app.route('/plants', methods=['POST'])
def create_plant():
    """Creates a new plant."""
    global next_plant_id
    data = request.get_json()

    if not data or 'name' not in data or 'type' not in data:
        return jsonify({"error": "Missing name or type in request body"}), 400

    name = data['name']
    plant_type = data['type']
    created_by_user_id = 0  # Hardcoded as per requirement

    new_plant = Plant(id=next_plant_id, name=name, type=plant_type, created_by_user_id=created_by_user_id)
    next_plant_id += 1
    
    plants_db.append(new_plant)
    
    return jsonify(new_plant.__dict__), 201

if __name__ == '__main__':
    app.run(debug=True)
