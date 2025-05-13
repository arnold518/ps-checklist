import * as _state from './state.js';

// Initialize Firebase
const firebaseConfig = {
    apiKey: "AIzaSyD6MxdZTBOmboCgPGB7Y_gNogHeljm7RVM",
    authDomain: "ps-checklist-v1.firebaseapp.com",
    projectId: "ps-checklist-v1",
    storageBucket: "ps-checklist-v1.appspot.com",
    messagingSenderId: "822272041679",
    appId: "1:822272041679:web:4aeb518ef0b9e8dd868dba",
    measurementId: "G-QP73JXLSXH"
};

const app = firebase.initializeApp(firebaseConfig);
const auth = firebase.auth();
const googleProvider = new firebase.auth.GoogleAuthProvider();
const db = firebase.firestore();

// Auth state management
let authState = {
    isLogin: true,
    user: null
};

// DOM Elements
let authContainer, emailInput, passwordInput, authForm, authTitle, 
    authSubmitBtn, authToggleBtn, authStatus, userInfo, googleAuthBtn;

export function createAuthPage() {
    console.log('Creating auth page');
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
                Continue with Google
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

    // Set up auth state listener
    auth.onAuthStateChanged(user => {
        if (user) {
            authState.user = user;
            showUserInfo(user.email);
        }
    });
}

function toggleAuthMode() {
    authState.isLogin = !authState.isLogin;
    createAuthPage();
}

async function handleAuthSubmit(e) {
    e.preventDefault();
    
    const email = emailInput.value;
    const password = passwordInput.value;
    
    try {
        if (authState.isLogin) {
            await loginWithEmail(email, password);
            showAuthStatus('Login successful!', 'success');
        } else {
            await signUpWithEmail(email, password);
            showAuthStatus('Account created successfully!', 'success');
        }
    } catch (error) {
        showAuthStatus(error.message, 'error');
    }
}

async function handleGoogleAuth() {
    try {
        await auth.signInWithPopup(googleProvider);
        showAuthStatus('Google authentication successful!', 'success');
        authState.isLogin = true;
        createAuthPage();
    } catch (error) {
        showAuthStatus(error.message, 'error');
        console.error('Google Sign-In error:', error);
    }
}

async function loginWithEmail(email, password) {
    try {
        await auth.signInWithEmailAndPassword(email, password);
    } catch (error) {
        throw new Error(getFriendlyAuthError(error.code));
    }
}

async function signUpWithEmail(email, password) {
    try {
        await auth.createUserWithEmailAndPassword(email, password);
    } catch (error) {
        throw new Error(getFriendlyAuthError(error.code));
    }
}

async function logout() {
    try {
        await auth.signOut();
        _state.clearUserData();
        authState.user = null;
        createAuthPage();
    } catch (error) {
        console.error('Error during logout:', error);
    }
}

function showAuthStatus(message, type) {
    authStatus.textContent = message;
    authStatus.className = `auth-status auth-${type}`;
    authStatus.style.display = 'block';
    
    setTimeout(() => {
        authStatus.style.display = 'none';
    }, 5000);
}

function showUserInfo(email) {
    userInfo.innerHTML = `
        <p>Logged in as: ${email}</p>
        <button id="logout-btn" class="btn">Logout</button>
    `;
    userInfo.style.display = 'block';
    
    authForm.style.display = 'none';
    googleAuthBtn.style.display = 'none';
    document.querySelector('.divider').style.display = 'none';
    document.querySelector('.auth-toggle').style.display = 'none';
    
    document.getElementById('logout-btn').addEventListener('click', logout);
}

function getFriendlyAuthError(errorCode) {
    const errors = {
        'auth/invalid-email': 'Invalid email address',
        'auth/user-disabled': 'This account has been disabled',
        'auth/user-not-found': 'No account found with this email',
        'auth/wrong-password': 'Incorrect password',
        'auth/email-already-in-use': 'Email already in use',
        'auth/operation-not-allowed': 'Email/password accounts are not enabled',
        'auth/weak-password': 'Password should be at least 6 characters',
        'auth/too-many-requests': 'Too many attempts. Try again later',
        'auth/network-request-failed': 'Network error. Please check your connection'
    };
    
    return errors[errorCode] || 'Authentication failed. Please try again';
}

// Auth State Listener
firebase.auth().onAuthStateChanged(user => {
    if (user) {
        console.log('User signed in:', user.email);
        _state.clearUserData();
        _state.fetchUserData();
    } else {
        _state.clearUserData();
    }
});

export function saveData(key, value) {
    const user = auth.currentUser;
    if (user) {
        return db.collection('users').doc(user.uid).get()
            .then(doc => {
                if (doc.exists) {
                    const data = doc.data();
                    data[key] = value;
                    return db.collection('users').doc(user.uid).set(data)
                        .then(() => {
                            console.log('Data updated!');
                            return true;
                        });
                } else {
                    const newData = { [key]: value };
                    return db.collection('users').doc(user.uid).set(newData)
                        .then(() => {
                            console.log('New document created and data saved!');
                            return true;
                        });
                }
            })
            .catch(error => {
                console.error('Error updating data:', error);
                return false;
            });
    } else {
        console.error('No authenticated user found');
        return Promise.resolve(false);
    }
}

export async function loadData(key) {
    const user = auth.currentUser;
    if (user) {
        return db.collection('users').doc(user.uid).get()
            .then(doc => {
                if (doc.exists) {
                    const data = doc.data();
                    return data[key] || null;
                }
            })
            .catch(error => {
                console.error('Error loading data:', error);
                return null;
            });
    } else {
        console.error('No authenticated user found');
        return null;
    }
}