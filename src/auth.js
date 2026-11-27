// Email/password form and account panel based on the prototype's Auth screen.
import * as store from './userStore.js';
import {config} from './api.js';
import * as cloud from './cloudAuth.js';
import {showJudgeSync} from './judgeSync.js';

let isLogin = true;

export function updateAccountButton() {
    const button = document.getElementById('account-button');
    button.textContent = store.user ? 'Account' : 'Sign in';
    button.title = store.user?.email || 'Sign in to save your progress';
}

export function showAccount() {
    document.getElementById('sidebar').classList.add('hidden');
    const main = document.getElementById('main-content');
    main.setAttribute('aria-busy','false');
    if (store.user) {
        main.innerHTML = `<div class="account-page"><div class="account-shell">
            <header class="account-header">
                <div><h1>Account</h1><p id="account-email"></p></div>
                <button id="signout-button" class="secondary-btn" type="button">Sign out</button>
            </header>
            <div id="auth-status" class="status" role="status"></div>
            <div id="account-connections"></div>
            <details class="account-settings">
                <summary>Account settings</summary>
                <p class="account-id">Account ID <code></code></p>
            </details>
        </div></div>`;
        document.getElementById('account-email').textContent = store.user.email;
        main.querySelector('.account-id code').textContent = store.user.id;
        document.getElementById('signout-button').addEventListener('click',async event => {
            const button = event.currentTarget;
            button.disabled = true;
            try { await store.signOut(); } catch (error) { showError(error); }
            finally { button.disabled = false; }
        });
        if (store.hosted) {
            const settings = main.querySelector('.account-settings');
            settings.open = cloud.recovering;
            const form = document.createElement('form');
            form.className = 'auth-form';
            form.innerHTML = `<label class="form-label" for="new-password">${cloud.recovering ? 'Set your new password' : 'Change password'}</label>
                <input id="new-password" type="password" minlength="8" required autocomplete="new-password" class="form-input">
                <button class="primary-btn" type="submit">Save password</button>`;
            form.addEventListener('submit', async event => {
                event.preventDefault();
                const button = form.querySelector('button'); button.disabled = true;
                try {
                    await store.updatePassword(form.querySelector('input').value);
                    form.reset();
                    const output = document.getElementById('auth-status');
                    output.className = 'status success show'; output.textContent = 'Password updated.';
                } catch (error) { showError(error); }
                finally { button.disabled = false; }
            });
            settings.appendChild(form);
        }
        if (store.user.isAdmin) showJudgeSync(main.querySelector('#account-connections'));
        return;
    }
    main.innerHTML = `<div class="auth-container">
        <h1 class="auth-title">${isLogin ? 'Login' : 'Sign Up'}</h1>
        <form id="auth-form" class="auth-form">
            <div class="form-group"><label for="email" class="form-label">Email</label>
                <input type="email" id="email" class="form-input" required autocomplete="email"></div>
            <div class="form-group"><label for="password" class="form-label">Password</label>
                <input type="password" id="password" class="form-input" required minlength="8"
                    autocomplete="${isLogin ? 'current-password' : 'new-password'}"></div>
            <button type="submit" id="auth-submit-btn" class="primary-btn" ${store.enabled ? '' : 'disabled'}>${isLogin ? 'Login' : 'Sign Up'}</button>
        </form>
        <div class="auth-toggle">${isLogin ? 'Need an account?' : 'Already have an account?'}
            <button id="auth-toggle-btn" class="toggle-link">${isLogin ? 'Sign up' : 'Login'}</button></div>
        <div id="auth-status" class="status" role="status"></div>
    </div>`;
    if (!store.enabled) showError(new Error('Account storage is currently unavailable.'));
    if (store.hosted) {
        const panel = main.querySelector('.auth-container');
        const providers = config.authProviders || ['google','github'];
        for (const provider of providers.filter(value => ['google','github'].includes(value))) {
            const button = document.createElement('button');
            button.className = 'secondary-btn';
            button.textContent = `Continue with ${provider === 'google' ? 'Google' : 'GitHub'}`;
            button.addEventListener('click', async () => {
                button.disabled = true;
                try { await store.signInProvider(provider); }
                catch (error) { showError(error); button.disabled = false; }
            });
            panel.appendChild(button);
        }
        const reset = document.createElement('button');
        reset.className = 'toggle-link'; reset.textContent = 'Forgot password?';
        reset.addEventListener('click', async () => {
            const email = document.getElementById('email');
            if (!email.reportValidity()) return;
            reset.disabled = true;
            try {
                await store.resetPassword(email.value.trim());
                const output = document.getElementById('auth-status');
                output.className = 'status success show'; output.textContent = 'Check your email for the password reset link.';
            } catch (error) { showError(error); }
            finally { reset.disabled = false; }
        });
        panel.appendChild(reset);
    }
    document.getElementById('auth-toggle-btn').addEventListener('click',() => { isLogin = !isLogin; showAccount(); });
    document.getElementById('auth-form').addEventListener('submit',async event => {
        event.preventDefault();
        const button = document.getElementById('auth-submit-btn');
        button.disabled = true;
        try {
            const result = await store.signIn(document.getElementById('email').value.trim(),document.getElementById('password').value,!isLogin);
            if (result.confirmationRequired) {
                const output = document.getElementById('auth-status');
                output.className = 'status success show';
                output.textContent = 'Check your email to confirm your account, then log in.';
            } else {
                isLogin = true;
                window.location.hash = 'icpc';
            }
        } catch (error) {
            showError(error);
        } finally { if (button.isConnected) button.disabled = false; }
    });
}

function showError(error) {
    if (error.name === 'AbortError') return;
    const output = document.getElementById('auth-status');
    if (output) {
        output.className = 'status error show';
        output.textContent = error.message;
    }
}
