// frontend/static/js/api.js
const BASE_URL = ''; // Assuming backend is served from the same origin

async function apiFetch(endpoint, method = 'GET', body = null, requiresAuth = false) {
    const headers = {
        'Content-Type': 'application/json',
    };
    const config = {
        method: method,
        headers: headers,
    };

    if (requiresAuth) {
        const token = localStorage.getItem('authToken');
        if (!token) {
            console.warn('Authentication token not found, redirecting to login.');
            window.location.href = '/login'; // Or throw an error
            return Promise.reject('No auth token found'); // Stop further execution
        }
        headers['Authorization'] = `Bearer ${token}`;
    }

    if (body) {
        config.body = JSON.stringify(body);
    }

    try {
        const response = await fetch(BASE_URL + endpoint, config);

        if (response.status === 401 && requiresAuth) {
            // Unauthorized, possibly expired or invalid token
            localStorage.removeItem('authToken');
            console.warn('Unauthorized access, token removed, redirecting to login.');
            window.location.href = '/login';
            return Promise.reject('Unauthorized'); // Stop further execution
        }

        const data = await response.json(); // Try to parse JSON regardless of status for error messages

        if (!response.ok) {
            // Construct an error object with message and status
            const error = new Error(data.error || data.message || `API request failed with status ${response.status}`);
            error.status = response.status;
            error.data = data; // Attach full response data to error
            throw error;
        }
        return data;
    } catch (error) {
        console.error(`API fetch error for endpoint ${endpoint}:`, error);
        throw error; // Re-throw the error to be caught by the caller
    }
}

// Specific API helper functions
function apiLogin(username, password) {
    return apiFetch('/users/login', 'POST', { username, password });
}

function apiRegister(username, email, password) {
    return apiFetch('/users/register', 'POST', { username, email, password });
}

function apiGetCurrentUser() {
    return apiFetch('/users/me', 'GET', null, true);
}

function apiGetCurrentWeeklyProgress() {
    return apiFetch('/weekly_progress/current', 'GET', null, true);
}

function apiGetPlants() {
    // Assuming /plants is a public endpoint listing all available plants
    return apiFetch('/plants', 'GET', null, false);
}

function apiGetUserRecipes() {
    // /recipes endpoint requires authentication and returns user-specific recipes
    return apiFetch('/recipes', 'GET', null, true);
}

function apiLogMeal(itemsArray) {
    // /meal_entries endpoint requires authentication
    return apiFetch('/meal_entries', 'POST', { items: itemsArray }, true);
}

// Add more specific helpers here as needed, e.g., for plants, recipes, meals
