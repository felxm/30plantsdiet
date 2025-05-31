document.addEventListener('DOMContentLoaded', function () {

    // Variables for meal logging
    let availablePlants = [];
    let userRecipes = [];
    const mealItemsContainer = document.getElementById('mealItemsContainer');
    const addMealItemButton = document.getElementById('addMealItemButton');
    const logMealForm = document.getElementById('logMealForm');
    const logMealMessage = document.getElementById('logMealMessage');

    async function displayWeeklyProgress() {
        const plantProgressDiv = document.getElementById('plantProgress');
        if (!plantProgressDiv) {
            console.warn('plantProgressDiv not found on page.');
            return;
        }

        try {
            const progress = await apiGetCurrentWeeklyProgress(); // Assumes api.js is loaded

            let goalAchievedText = 'Not yet!';
            if (progress.goal_achieved_date) {
                goalAchievedText = `Yes (on ${new Date(progress.goal_achieved_date).toLocaleDateString()})`;
            }

            const weekStartDate = new Date(progress.week_start_date + 'T00:00:00Z');

            plantProgressDiv.innerHTML = `
                <p><strong>Week of:</strong> ${weekStartDate.toLocaleDateString()}</p>
                <p><strong>Your Progress:</strong> ${progress.distinct_plant_count.toFixed(2)} / 30 plants</p>
                <p><strong>Goal Met:</strong> ${goalAchievedText}</p>
            `;
        } catch (error) {
            console.error('Error fetching weekly progress:', error);
            if (plantProgressDiv) {
                plantProgressDiv.innerHTML = '<p style="color: red;">Could not load weekly progress. ' + (error.message || '') + '</p>';
            }
        }
    }

    function addMealItemRow() {
        if (!mealItemsContainer) {
            console.warn('mealItemsContainer not found for addMealItemRow.');
            return;
        }

        const itemRow = document.createElement('div');
        itemRow.classList.add('meal-item-row');
        itemRow.style.marginBottom = '10px';
        itemRow.style.padding = '10px';
        itemRow.style.border = '1px solid #ccc';

        const typeSelect = document.createElement('select');
        typeSelect.classList.add('mealItemType');
        typeSelect.innerHTML = `
            <option value="plant">Plant</option>
            <option value="recipe">Recipe</option>
        `;

        const nameSelect = document.createElement('select');
        nameSelect.classList.add('mealItemName');
        nameSelect.innerHTML = `<option value="">-- Select Type First --</option>`;

        const quantityInput = document.createElement('input');
        quantityInput.type = 'number';
        quantityInput.classList.add('mealItemQuantity');
        quantityInput.value = '1';
        quantityInput.min = '0.25';
        quantityInput.step = '0.25';
        quantityInput.style.width = '60px';

        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.classList.add('removeMealItemButton');
        removeButton.textContent = 'Remove';
        removeButton.style.marginLeft = '10px';

        itemRow.appendChild(document.createTextNode('Type: '));
        itemRow.appendChild(typeSelect);
        itemRow.appendChild(document.createTextNode(' Name: '));
        itemRow.appendChild(nameSelect);
        itemRow.appendChild(document.createTextNode(' Qty: '));
        itemRow.appendChild(quantityInput);
        itemRow.appendChild(removeButton);

        mealItemsContainer.appendChild(itemRow);

        typeSelect.addEventListener('change', () => populateNameSelect(itemRow, typeSelect.value));
        removeButton.addEventListener('click', () => itemRow.remove());
        populateNameSelect(itemRow, typeSelect.value); // Initial population
    }

    function populateNameSelect(itemRowElement, type) {
        const nameSelect = itemRowElement.querySelector('.mealItemName');
        const quantityInput = itemRowElement.querySelector('.mealItemQuantity');

        nameSelect.innerHTML = '';

        if (type === 'plant') {
            if (availablePlants.length === 0) {
                nameSelect.innerHTML = `<option value="">-- No plants available --</option>`;
            } else {
                availablePlants.forEach(plant => {
                    const option = document.createElement('option');
                    option.value = plant.id;
                    option.textContent = plant.name;
                    nameSelect.appendChild(option);
                });
            }
            quantityInput.style.display = 'inline-block';
            quantityInput.disabled = false;
        } else if (type === 'recipe') {
            if (userRecipes.length === 0) {
                nameSelect.innerHTML = `<option value="">-- No recipes available --</option>`;
            } else {
                userRecipes.forEach(recipe => {
                    const option = document.createElement('option');
                    option.value = recipe.id;
                    option.textContent = recipe.name;
                    nameSelect.appendChild(option);
                });
            }
            quantityInput.style.display = 'none';
            quantityInput.disabled = true;
            quantityInput.value = '1';
        } else {
            nameSelect.innerHTML = `<option value="">-- Select Type First --</option>`;
            quantityInput.style.display = 'none';
            quantityInput.disabled = true;
        }
    }

    async function handleLogMealSubmit(event) {
        event.preventDefault();
        if (!logMealMessage) {
            console.warn('logMealMessage div not found.');
            return;
        }
        logMealMessage.textContent = '';

        const itemsArray = [];
        const itemRows = mealItemsContainer.querySelectorAll('.meal-item-row');

        if (itemRows.length === 0) {
            logMealMessage.textContent = 'Please add at least one item to the meal.';
            logMealMessage.style.color = 'red';
            return;
        }

        let validItemsExist = false;
        itemRows.forEach(row => {
            const type = row.querySelector('.mealItemType').value;
            const id = row.querySelector('.mealItemName').value;
            const quantity = parseFloat(row.querySelector('.mealItemQuantity').value);

            if (!id) { // Check if an actual plant/recipe is selected
                return; // Skip this row if no name is selected
            }
            validItemsExist = true;

            if (type === 'plant') {
                itemsArray.push({ plant_id: parseInt(id), quantity: quantity });
            } else if (type === 'recipe') {
                itemsArray.push({ recipe_id: parseInt(id) });
            }
        });

        if (!validItemsExist || itemsArray.length === 0) {
            logMealMessage.textContent = 'No valid items selected for the meal. Ensure a name is chosen for each item.';
            logMealMessage.style.color = 'red';
            return;
        }

        try {
            await apiLogMeal(itemsArray); // Assumes api.js is loaded
            logMealMessage.textContent = 'Meal logged successfully!';
            logMealMessage.style.color = 'green';
            mealItemsContainer.innerHTML = ''; // Clear all item rows
            // addMealItemRow(); // Optional: add a fresh empty row after logging
            await displayWeeklyProgress(); // Refresh progress display

            // After successfully logging a meal, also refresh user points
            const updatedUserData = await apiGetCurrentUser();
            const userPointsElement = document.getElementById('userPoints');
            if (userPointsElement && updatedUserData.total_points !== undefined) {
                userPointsElement.textContent = updatedUserData.total_points;
            }

        } catch (error) {
            logMealMessage.textContent = `Error logging meal: ${error.message || 'Unknown error'}`;
            logMealMessage.style.color = 'red';
        }
    }

    async function initializeDashboard() {
        const authToken = localStorage.getItem('authToken');
        const welcomeMessageElement = document.getElementById('welcomeMessage');
        const logoutButton = document.getElementById('logoutButton');
        const userPointsElement = document.getElementById('userPoints'); // Get points element

        if (!authToken) {
            window.location.href = '/login';
            return;
        }

        if (logoutButton) {
            logoutButton.addEventListener('click', function () {
                localStorage.removeItem('authToken');
                window.location.href = '/login';
            });
        } else {
            console.warn('logoutButton not found on page.');
        }

        try {
            const userData = await apiGetCurrentUser();
            if (welcomeMessageElement) {
                welcomeMessageElement.textContent = `Welcome, ${userData.username}! (ID: ${userData.id}, Email: ${userData.email})`;
            } else {
                console.warn('welcomeMessageElement not found on page.');
            }

            // Display initial points
            if (userPointsElement && userData.total_points !== undefined) {
                userPointsElement.textContent = userData.total_points;
            } else if (userPointsElement) {
                userPointsElement.textContent = 'N/A';
            } else {
                console.warn('userPointsElement not found on page.')
            }

            await displayWeeklyProgress();

            availablePlants = await apiGetPlants();
            userRecipes = await apiGetUserRecipes();

            if (addMealItemButton) {
                addMealItemButton.addEventListener('click', addMealItemRow);
            } else {
                console.warn('addMealItemButton not found.');
            }
            if (logMealForm) {
                logMealForm.addEventListener('submit', handleLogMealSubmit);
            } else {
                console.warn('logMealForm not found.');
            }

        } catch (error) {
            console.error('Dashboard initialization error:', error);
            if (error.status === 401 || error.status === 403) {
                 localStorage.removeItem('authToken');
                 window.location.href = '/login';
            } else if (welcomeMessageElement) {
                 welcomeMessageElement.textContent = 'Could not load dashboard data. ' + (error.message || 'Please try logging in again.');
            } else {
                console.error('Critical dashboard elements missing or fatal error: ' + (error.message || ''));
            }
        }
    }

    initializeDashboard();

    console.log("main.js for dashboard loaded and executing with meal logging and initializeDashboard structure.");
});
