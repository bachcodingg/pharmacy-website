import {
  getToken, login, register, logout, getMe, updateProfile, changePassword,
  forgotPassword, resetPassword, listAddresses, createAddress, deleteAddress, listOrders,
} from '../api.js';
import { escapeHtml, formatVnd } from '../shared.js';
import { t } from '../i18n.js';
import { refreshCurrentRoute } from '../router.js';
import { updateNavAuthState } from '../nav.js';

export async function render(root) {
  if (!getToken()) {
    renderSignedOut(root);
    return;
  }

  let user;
  try {
    user = await getMe();
  } catch (err) {
    renderSignedOut(root);
    return;
  }
  await renderSignedIn(root, user);
}

function renderSignedOut(root) {
  root.innerHTML = `
    <div class="auth-card">
      <div class="auth-tabs">
        <button type="button" class="auth-tab active" data-tab="login">${t('account.signIn')}</button>
        <button type="button" class="auth-tab" data-tab="register">${t('account.register')}</button>
      </div>

      <form id="login-form" class="auth-form">
        <label>${t('account.email')} <input type="email" name="email" required autocomplete="email" /></label>
        <label>${t('account.password')} <input type="password" name="password" required autocomplete="current-password" /></label>
        <div class="form-error" id="login-error" role="alert"></div>
        <button type="submit">${t('account.signIn')}</button>
        <button type="button" class="link-btn" id="forgot-link">${t('account.forgot')}</button>
      </form>

      <form id="register-form" class="auth-form" hidden>
        <label>${t('account.name')} <input type="text" name="name" required autocomplete="name" /></label>
        <label>${t('account.email')} <input type="email" name="email" required autocomplete="email" /></label>
        <label>${t('account.password')} <input type="password" name="password" required minlength="8" autocomplete="new-password" /></label>
        <div class="form-error" id="register-error" role="alert"></div>
        <button type="submit">${t('account.createAccount')}</button>
      </form>

      <form id="forgot-form" class="auth-form" hidden>
        <p class="hint-text">${t('account.forgotHint')}</p>
        <label>${t('account.email')} <input type="email" name="email" required /></label>
        <div class="form-error" id="forgot-error" role="alert"></div>
        <div class="form-note" id="forgot-note" role="status"></div>
        <button type="submit">${t('account.sendReset')}</button>
      </form>
    </div>
  `;

  const loginForm = root.querySelector('#login-form');
  const registerForm = root.querySelector('#register-form');
  const forgotForm = root.querySelector('#forgot-form');
  const tabs = root.querySelectorAll('.auth-tab');

  function showForm(name) {
    loginForm.hidden = name !== 'login';
    registerForm.hidden = name !== 'register';
    forgotForm.hidden = name !== 'forgot';
    tabs.forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
  }

  tabs.forEach((tab) => tab.addEventListener('click', () => showForm(tab.dataset.tab)));
  root.querySelector('#forgot-link').addEventListener('click', () => showForm('forgot'));

  loginForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(loginForm);
    const errorEl = root.querySelector('#login-error');
    errorEl.textContent = '';
    try {
      await login(data.get('email'), data.get('password'));
      updateNavAuthState();
      refreshCurrentRoute();
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });

  registerForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(registerForm);
    const errorEl = root.querySelector('#register-error');
    errorEl.textContent = '';
    try {
      await register(data.get('email'), data.get('password'), data.get('name'));
      updateNavAuthState();
      refreshCurrentRoute();
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });

  forgotForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(forgotForm);
    const errorEl = root.querySelector('#forgot-error');
    const noteEl = root.querySelector('#forgot-note');
    errorEl.textContent = '';
    try {
      const result = await forgotPassword(data.get('email'));
      noteEl.textContent = result.dev_only_reset_token
        ? t('account.resetDevToken', { token: result.dev_only_reset_token })
        : t('account.resetSent');
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });
}

async function renderSignedIn(root, user) {
  const [addresses, orders] = await Promise.all([listAddresses(), listOrders()]);

  root.innerHTML = `
    <div class="account-grid">
      <section class="account-card">
        <h2>${t('account.profile')}</h2>
        <form id="profile-form" class="auth-form">
          <label>${t('account.name')} <input type="text" name="name" value="${escapeHtml(user.name)}" required /></label>
          <label>${t('account.email')} <input type="email" name="email" value="${escapeHtml(user.email)}" required /></label>
          <div class="form-error" id="profile-error" role="alert"></div>
          <div class="form-note" id="profile-note" role="status"></div>
          <button type="submit">${t('account.saveProfile')}</button>
        </form>
        <button type="button" id="sign-out" class="secondary-btn">${t('account.signOut')}</button>
      </section>

      <section class="account-card">
        <h2>${t('account.changePassword')}</h2>
        <form id="password-form" class="auth-form">
          <label>${t('account.currentPassword')} <input type="password" name="old_password" required autocomplete="current-password" /></label>
          <label>${t('account.newPassword')} <input type="password" name="new_password" required minlength="8" autocomplete="new-password" /></label>
          <div class="form-error" id="password-error" role="alert"></div>
          <div class="form-note" id="password-note" role="status"></div>
          <button type="submit">${t('account.updatePassword')}</button>
        </form>
      </section>

      <section class="account-card">
        <h2>${t('account.addresses')}</h2>
        <div id="address-list" class="address-list"></div>
        <form id="address-form" class="auth-form">
          <label>${t('account.label')} <input type="text" name="label" placeholder="${t('account.labelPlaceholder')}" required /></label>
          <label>${t('account.recipient')} <input type="text" name="recipient_name" required autocomplete="name" /></label>
          <label>${t('account.phone')} <input type="tel" name="phone" required autocomplete="tel" /></label>
          <label>${t('account.line1')} <input type="text" name="line1" required autocomplete="address-line1" /></label>
          <label>${t('account.city')} <input type="text" name="city" required autocomplete="address-level2" /></label>
          <label class="checkbox-label"><input type="checkbox" name="is_default" /> ${t('account.setDefault')}</label>
          <div class="form-error" id="address-error" role="alert"></div>
          <button type="submit">${t('account.addAddress')}</button>
        </form>
      </section>

      <section class="account-card">
        <h2>${t('account.orderHistory')}</h2>
        <div id="order-list"></div>
      </section>
    </div>
  `;

  const addressList = root.querySelector('#address-list');
  function renderAddresses() {
    addressList.innerHTML = addresses.length
      ? addresses.map((a) => `
        <div class="address-item">
          <div>
            <strong>${escapeHtml(a.label)}</strong>${a.is_default ? `<span class="estimate-tag">${t('account.default')}</span>` : ''}
            <div class="address-lines">${escapeHtml(a.recipient_name)} · ${escapeHtml(a.phone)}<br/>${escapeHtml(a.line1)}, ${escapeHtml(a.city)}</div>
          </div>
          <button type="button" class="link-btn" data-delete-address="${a.id}">${t('common.remove')}</button>
        </div>`).join('')
      : `<div class="empty-state">${t('account.noAddresses')}</div>`;
  }
  renderAddresses();

  addressList.addEventListener('click', async (event) => {
    const btn = event.target.closest('[data-delete-address]');
    if (!btn) return;
    await deleteAddress(btn.dataset.deleteAddress);
    const idx = addresses.findIndex((a) => String(a.id) === btn.dataset.deleteAddress);
    if (idx >= 0) addresses.splice(idx, 1);
    renderAddresses();
  });

  // Same key space as the order detail view, so a status never reads one way
  // in the list and another way on the page it links to.
  const STATUSES = ['placed', 'pending_payment', 'awaiting_prescription', 'shipped', 'delivered', 'cancelled'];
  root.querySelector('#order-list').innerHTML = orders.length
    ? `<div class="order-history-list">${orders
        .map(
          (o) => `
        <a href="#/order/${o.id}" class="order-history-item">
          <div>
            <strong>${t('account.orderLabel', { id: o.id })}</strong>
            <span class="status-pill status-corrected">${escapeHtml(STATUSES.includes(o.status) ? t(`order.status.${o.status}`) : o.status)}</span>
          </div>
          <div class="hint-text">${t('account.orderSummary', { n: o.items.length, total: formatVnd(o.total) })}</div>
        </a>`
        )
        .join('')}</div>`
    : `<div class="empty-state">${t('account.noOrders')}</div>`;

  root.querySelector('#profile-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(event.target);
    const errorEl = root.querySelector('#profile-error');
    const noteEl = root.querySelector('#profile-note');
    errorEl.textContent = '';
    noteEl.textContent = '';
    try {
      await updateProfile({ name: data.get('name'), email: data.get('email') });
      noteEl.textContent = t('account.saved');
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });

  root.querySelector('#password-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(event.target);
    const errorEl = root.querySelector('#password-error');
    const noteEl = root.querySelector('#password-note');
    errorEl.textContent = '';
    noteEl.textContent = '';
    try {
      await changePassword(data.get('old_password'), data.get('new_password'));
      noteEl.textContent = t('account.passwordUpdated');
      event.target.reset();
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });

  root.querySelector('#address-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(event.target);
    const errorEl = root.querySelector('#address-error');
    errorEl.textContent = '';
    try {
      const created = await createAddress({
        label: data.get('label'),
        recipient_name: data.get('recipient_name'),
        phone: data.get('phone'),
        line1: data.get('line1'),
        city: data.get('city'),
        is_default: data.get('is_default') === 'on',
      });
      if (created.is_default) addresses.forEach((a) => (a.is_default = false));
      addresses.push(created);
      renderAddresses();
      event.target.reset();
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });

  root.querySelector('#sign-out').addEventListener('click', async () => {
    await logout();
    updateNavAuthState();
    refreshCurrentRoute();
  });
}
