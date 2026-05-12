// static/app.js — Исправленная версия
// Все event listeners защищены проверками на null
// API запросы используют относительные пути (работает на любом порту)

document.addEventListener('DOMContentLoaded', function() {
    
    // === Глобальные элементы (могут отсутствовать на некоторых страницах) ===
    const sign_in_btn = document.querySelector("#sign-in-btn");
    const sign_up_btn = document.querySelector("#sign-up-btn");
    const container = document.querySelector(".container");
    const adminBtn = document.querySelector('.admin-btn');

    // === Функция показа админ-формы ===
    function showAdminLogin() {
        if (!container) return;
        container.classList.add("admin-mode");
        container.classList.remove("sign-up-mode");
        const adminForm = document.querySelector('.admin-form-container');
        if (adminForm) adminForm.style.display = 'flex';
    }

    // === Переключение панелей (только если элементы есть) ===
    if (sign_up_btn) {
        sign_up_btn.addEventListener("click", () => {
            if (container) {
                container.classList.add("sign-up-mode");
                container.classList.remove("admin-mode");
            }
        });
    }

    if (sign_in_btn) {
        sign_in_btn.addEventListener("click", () => {
            if (container) {
                container.classList.remove("sign-up-mode");
                container.classList.remove("admin-mode");
            }
        });
    }

    // === Кнопка админа ===
    if (adminBtn) {
        adminBtn.addEventListener('click', (e) => {
            e.preventDefault();
            showAdminLogin();
        });
    }

    // === Сделаем функцию доступной глобально, чтобы inline onclick тоже работал ===
    window.showAdminLogin = showAdminLogin;

    // === Обработка формы входа (только на главной странице) ===
    const signInForm = document.querySelector(".sign-in-form");
    if (signInForm && window.location.pathname === '/') {
        signInForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = {
                username: formData.get("username"),
                password: formData.get("password"),
            };

            try {
                const response = await fetch("/api/login", {  // ✅ Относительный путь
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(data),
                    credentials: "include"
                });
                let result = {};
                try {
                    result = await response.json();
                } catch (err) {
                    result = { error: response.statusText || 'Ошибка сервера' };
                }
                const messageContainer = document.querySelector(".sign-in-form .message-container");
                if (messageContainer) messageContainer.textContent = "";

                if (response.ok) {
                    if (messageContainer) {
                        messageContainer.textContent = result.message;
                        messageContainer.style.color = "green";
                    }
                    setTimeout(() => { window.location.href = "/chat"; }, 1000);
                } else {
                    if (messageContainer) {
                        messageContainer.textContent = result.error || "Ошибка входа";
                        messageContainer.style.color = "red";
                    }
                }
            } catch (error) {
                console.error("Login error:", error);
                const messageContainer = document.querySelector(".sign-in-form .message-container");
                if (messageContainer) {
                    messageContainer.textContent = "Ошибка сервера";
                    messageContainer.style.color = "red";
                }
            }
        });
    }

    // === Обработка формы регистрации (только на главной странице) ===
    const signUpForm = document.querySelector(".sign-up-form");
    if (signUpForm && window.location.pathname === '/') {
        signUpForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = {
                username: formData.get("username"),  // ✅ Точно как в Pydantic
                email: formData.get("email"),
                password: formData.get("password"),
            };

            try {
                const response = await fetch("/api/register", {  // ✅ Относительный путь
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(data),
                });
                let result = {};
                try {
                    result = await response.json();
                } catch (err) {
                    result = { error: response.statusText || 'Ошибка сервера' };
                }
                
                if (response.ok) {
                    alert(result.message || "Регистрация успешна!");
                    setTimeout(() => { window.location.href = "/"; }, 1000);
                } else {
                    alert(result.error || "Ошибка регистрации");
                }
            } catch (error) {
                console.error("Register error:", error);
                alert("Ошибка сервера при регистрации");
            }
        });
    }

    // === Обработка формы входа админа (ЕДИНСТВЕННЫЙ обработчик) ===
    const adminForm = document.querySelector(".admin-sign-in-form");
    if (adminForm) {
        adminForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const username = adminForm.querySelector('input[name="username"]')?.value || '';
            const password = adminForm.querySelector('input[name="password"]')?.value || '';
            
            const data = { username, password };

            try {
                const response = await fetch("/api/admin/login", {  // ✅ Относительный путь
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(data),
                    credentials: "include"
                });
                
                let result = {};
                try {
                    result = await response.json();
                } catch (err) {
                    result = { error: response.statusText || 'Ошибка сервера' };
                }
                const messageContainer = adminForm.querySelector(".message-container");
                if (messageContainer) messageContainer.textContent = "";

                if (response.ok) {
                    if (messageContainer) {
                        messageContainer.textContent = result.message || "Успешно!";
                        messageContainer.style.color = "green";
                    }
                    setTimeout(() => { window.location.href = "/admin"; }, 1000);
                } else {
                    if (messageContainer) {
                        messageContainer.textContent = result.error || "Ошибка авторизации";
                        messageContainer.style.color = "red";
                    }
                }
            } catch (error) {
                console.error("Admin login error:", error);
                const messageContainer = adminForm.querySelector(".message-container");
                if (messageContainer) {
                    messageContainer.textContent = "Ошибка сервера";
                    messageContainer.style.color = "red";
                }
            }
        });
    }

    // === Проверка параметра админ-ошибки в URL ===
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('admin_error') === 'true') {
        showAdminLogin();
        const adminForm = document.querySelector(".admin-sign-in-form");
        const messageContainer = adminForm?.querySelector(".message-container");
        if (messageContainer) {
            messageContainer.textContent = "Для доступа к админ-панели необходима авторизация";
            messageContainer.style.color = "red";
        }
    }

    // === Дополнительные переключатели (если есть) ===
    const extraSignUpBtn = document.querySelector('.sign-up-btn');
    const extraSignInBtn = document.querySelector('.sign-in-btn');
    
    if (extraSignUpBtn && container) {
        extraSignUpBtn.addEventListener('click', () => {
            container.classList.add('sign-up-mode');
        });
    }
    if (extraSignInBtn && container) {
        extraSignInBtn.addEventListener('click', () => {
            container.classList.remove('sign-up-mode');
        });
    }
});