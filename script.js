// Firebase configuration (replace with your own)


const firebaseConfig = {
    apiKey: "AIzaSyD6MxdZTBOmboCgPGB7Y_gNogHeljm7RVM",
    authDomain: "ps-checklist-v1.firebaseapp.com",
    projectId: "ps-checklist-v1",
    storageBucket: "ps-checklist-v1.firebasestorage.app",
    messagingSenderId: "822272041679",
    appId: "1:822272041679:web:4aeb518ef0b9e8dd868dba",
    measurementId: "G-QP73JXLSXH"
};

// Initialize Firebase
const app = firebase.initializeApp(firebaseConfig);
const auth = firebase.auth();
const db = firebase.firestore();

// UI Elements
const loginForm = document.getElementById('login-form');
const signupForm = document.getElementById('signup-form');
const appContent = document.getElementById('app-content');
const userEmailDisplay = document.getElementById('user-email');
const dataInput = document.getElementById('data-input');
const dataOutput = document.getElementById('data-output');

// Auth State Listener
auth.onAuthStateChanged(user => {
    if (user) {
        // User is signed in
        showAppContent(user);
        loadData(user.uid);
    } else {
        // User is signed out
        showAuthForms();
    }
});

// Auth Functions
function signup() {
    const email = document.getElementById('signup-email').value;
    const password = document.getElementById('signup-password').value;

    auth.createUserWithEmailAndPassword(email, password)
        .then((userCredential) => {
            // Signed in
            const user = userCredential.user;
            console.log('Sign up successful:', user);
        })
        .catch((error) => {
            console.error('Sign up error:', error);
            document.getElementById('signup-error').textContent = error.message;
            document.getElementById('signup-error').classList.remove('hidden');
        });
}

function login() {
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;

    auth.signInWithEmailAndPassword(email, password)
        .then((userCredential) => {
            // Signed in
            const user = userCredential.user;
            console.log('Login successful:', user);
        })
        .catch((error) => {
            console.error('Login error:', error);
            document.getElementById('login-error').textContent = error.message;
            document.getElementById('login-error').classList.remove('hidden');
        });
}

function logout() {
    auth.signOut();
}

// Firestore Functions
function saveData() {
    const user = auth.currentUser;
    if (user) {
        const data = dataInput.value;
        try {
            JSON.parse(data); // Check if it's valid JSON
            db.collection('users').doc(user.uid).set({ data: data })
                .then(() => {
                    console.log('Data saved!');
                    loadData(user.uid); // Refresh the display
                })
                .catch(error => console.error('Error saving data:', error));
        } catch (e) {
            alert('Invalid JSON!');
        }
    }
}

function loadData(uid) {
    db.collection('users').doc(uid).get()
        .then(doc => {
            if (doc.exists) {
                const data = doc.data().data;
                dataOutput.textContent = data;
            } else {
                dataOutput.textContent = 'No data yet!';
            }
        })
        .catch(error => console.error('Error loading data:', error));
}

// UI Helper Functions
function showAppContent(user) {
    loginForm.classList.add('hidden');
    signupForm.classList.add('hidden');
    appContent.classList.remove('hidden');
    userEmailDisplay.textContent = user.email;
}

function showAuthForms() {
    loginForm.classList.remove('hidden');
    signupForm.classList.remove('hidden');
    appContent.classList.add('hidden');
}
