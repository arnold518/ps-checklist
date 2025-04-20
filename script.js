// Auth state management
let authState = {
    isLogin: true, // Toggle between login/signup
    user: null
};

// DOM Elements
let authContainer, emailInput, passwordInput, authForm, authTitle, 
    authSubmitBtn, authToggleBtn, authStatus, userInfo, googleAuthBtn;

// Initialize auth page
function createAuthPage() {
    const mainContent = document.getElementById('main-content');
    mainContent.innerHTML = `
        <div class="auth-container">
            <h1 class="auth-title">${authState.isLogin ? 'Login' : 'Sign Up'}</h1>
            
            <div id="auth-status" class="auth-status" style="display: none;"></div>
            
            <button id="google-auth-btn" class="btn btn-google">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="white">
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                </svg>
                ${authState.isLogin ? 'Login' : 'Sign up'} with Google
            </button>
            
            <div class="divider">or</div>
            
            <form id="auth-form" class="auth-form">
                <div class="form-group">
                    <label for="email" class="form-label">Email</label>
                    <input type="email" id="email" class="form-input" required>
                </div>
                
                <div class="form-group">
                    <label for="password" class="form-label">Password</label>
                    <input type="password" id="password" class="form-input" required minlength="6">
                </div>
                
                <button type="submit" class="btn btn-primary" id="auth-submit-btn">
                    ${authState.isLogin ? 'Login' : 'Sign Up'}
                </button>
            </form>
            
            <div class="auth-toggle">
                ${authState.isLogin ? 'Need an account?' : 'Already have an account?'}
                <span id="auth-toggle-btn" class="toggle-link">
                    ${authState.isLogin ? 'Sign up' : 'Login'}
                </span>
            </div>
            
            <div id="user-info" class="user-info" style="display: none;"></div>
        </div>
    `;

    // Initialize DOM references
    authContainer = document.querySelector('.auth-container');
    emailInput = document.getElementById('email');
    passwordInput = document.getElementById('password');
    authForm = document.getElementById('auth-form');
    authTitle = document.querySelector('.auth-title');
    authSubmitBtn = document.getElementById('auth-submit-btn');
    authToggleBtn = document.getElementById('auth-toggle-btn');
    authStatus = document.getElementById('auth-status');
    userInfo = document.getElementById('user-info');
    googleAuthBtn = document.getElementById('google-auth-btn');

    // Event listeners
    authToggleBtn.addEventListener('click', toggleAuthMode);
    authForm.addEventListener('submit', handleAuthSubmit);
    googleAuthBtn.addEventListener('click', handleGoogleAuth);

    // Check if user is already logged in
    checkAuthState();
}

// Toggle between login/signup
function toggleAuthMode() {
    authState.isLogin = !authState.isLogin;
    createAuthPage();
}

// Handle form submission
async function handleAuthSubmit(e) {
    e.preventDefault();
    
    const email = emailInput.value;
    const password = passwordInput.value;
    
    try {
        if (authState.isLogin) {
            // Simulate login (replace with actual auth API call)
            await loginWithEmail(email, password);
            showAuthStatus('Login successful!', 'success');
            showUserInfo(email);
        } else {
            // Simulate signup (replace with actual auth API call)
            await signUpWithEmail(email, password);
            showAuthStatus('Account created successfully!', 'success');
            showUserInfo(email);
        }
    } catch (error) {
        showAuthStatus(error.message, 'error');
    }
}

// Handle Google auth
async function handleGoogleAuth() {
    try {
        // Simulate Google auth (replace with actual implementation)
        const email = await authenticateWithGoogle();
        showAuthStatus('Google authentication successful!', 'success');
        showUserInfo(email);
    } catch (error) {
        showAuthStatus('Google authentication failed', 'error');
    }
}

// Mock auth functions (replace with real implementations)
async function loginWithEmail(email, password) {
    return new Promise((resolve, reject) => {
        setTimeout(() => {
            // Simulate successful login
            if (email && password.length >= 6) {
                authState.user = { email };
                localStorage.setItem('authUser', JSON.stringify(authState.user));
                resolve();
            } else {
                reject(new Error('Invalid email or password'));
            }
        }, 800);
    });
}

async function signUpWithEmail(email, password) {
    return new Promise((resolve, reject) => {
        setTimeout(() => {
            // Simulate successful signup
            if (email && password.length >= 6) {
                authState.user = { email };
                localStorage.setItem('authUser', JSON.stringify(authState.user));
                resolve();
            } else {
                reject(new Error('Please provide a valid email and password (min 6 characters)'));
            }
        }, 800);
    });
}

async function authenticateWithGoogle() {
    return new Promise((resolve) => {
        setTimeout(() => {
            // Simulate Google auth returning a user
            const email = `user${Math.floor(Math.random() * 1000)}@example.com`;
            authState.user = { email };
            localStorage.setItem('authUser', JSON.stringify(authState.user));
            resolve(email);
        }, 800);
    });
}

// Check if user is already authenticated
function checkAuthState() {
    const savedUser = localStorage.getItem('authUser');
    if (savedUser) {
        authState.user = JSON.parse(savedUser);
        showUserInfo(authState.user.email);
    }
}

// Show auth status message
function showAuthStatus(message, type) {
    authStatus.textContent = message;
    authStatus.className = `auth-status auth-${type}`;
    authStatus.style.display = 'block';
    
    // Hide after 5 seconds
    setTimeout(() => {
        authStatus.style.display = 'none';
    }, 5000);
}

// Show user info
function showUserInfo(email) {
    userInfo.textContent = `Logged in as: ${email}`;
    userInfo.style.display = 'block';
    
    // Update UI for logged in state
    authForm.style.display = 'none';
    googleAuthBtn.style.display = 'none';
    document.querySelector('.divider').style.display = 'none';
    document.querySelector('.auth-toggle').style.display = 'none';
    
    // Add logout button
    if (!document.getElementById('logout-btn')) {
        const logoutBtn = document.createElement('button');
        logoutBtn.id = 'logout-btn';
        logoutBtn.className = 'btn';
        logoutBtn.textContent = 'Logout';
        logoutBtn.style.marginTop = '1rem';
        logoutBtn.addEventListener('click', handleLogout);
        authContainer.appendChild(logoutBtn);
    }
}

// Handle logout
function handleLogout() {
    authState.user = null;
    localStorage.removeItem('authUser');
    createAuthPage();
}

// Initialize the page
document.addEventListener('DOMContentLoaded', createAuthPage);