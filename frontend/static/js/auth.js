console.log("auth.js loaded");

document.addEventListener('DOMContentLoaded', function () {
    const loginForm = document.getElementById('loginForm');
    const loginErrorDiv = document.getElementById('loginError');

    if (loginForm) {
        loginForm.addEventListener('submit', async function (event) {
            event.preventDefault();

            const username = loginForm.username.value;
            const password = loginForm.password.value;

            if (loginErrorDiv) loginErrorDiv.textContent = '';

            try {
                const data = await apiLogin(username, password); // Use helper
                if (data.token) {
                    localStorage.setItem('authToken', data.token);
                    window.location.href = '/dashboard';
                } else {
                    // This case should ideally not be reached if apiLogin ensures token or throws error
                    if (loginErrorDiv) loginErrorDiv.textContent = 'Login successful, but no token received.';
                }
            } catch (error) {
                console.error('Login error:', error);
                if (loginErrorDiv) loginErrorDiv.textContent = error.message || 'Login failed.';
            }
        });
    }

    // Registration form logic
    const registerForm = document.getElementById('registerForm');
    const registerErrorDiv = document.getElementById('registerError');

    if (registerForm) {
        registerForm.addEventListener('submit', async function (event) {
            event.preventDefault();

            const username = registerForm.username.value;
            const email = registerForm.email.value;
            const password = registerForm.password.value;

            if (registerErrorDiv) registerErrorDiv.textContent = '';

            try {
                await apiRegister(username, email, password); // Use helper
                // alert('Registration successful! Please login.'); // Optional
                window.location.href = '/login';
            } catch (error) {
                console.error('Registration error:', error);
                if (registerErrorDiv) registerErrorDiv.textContent = error.message || 'Registration failed.';
            }
        });
    }
});
