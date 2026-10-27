/**
 * Fee Management System - Professional Administrative Client Script
 * Handles responsive layout, sidebar state, theme switching, 
 * live student lookup autocomplete, and payment voucher interactions.
 */

// Theme Management
const ThemeManager = {
    init() {
        const savedTheme = localStorage.getItem('theme') || 'light';
        this.setTheme(savedTheme);
        this.bindEvents();
    },

    setTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        this.updateToggleButton(theme);
    },

    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        this.setTheme(newTheme);
    },

    updateToggleButton(theme) {
        const btn = document.getElementById('themeToggle');
        if (btn) {
            const icon = btn.querySelector('i');
            const text = btn.querySelector('span');
            if (theme === 'dark') {
                if (icon) icon.className = 'bi bi-sun';
                if (text) text.textContent = 'Light';
            } else {
                if (icon) icon.className = 'bi bi-moon';
                if (text) text.textContent = 'Dark';
            }
        }
    },

    bindEvents() {
        const btn = document.getElementById('themeToggle');
        if (btn) {
            btn.addEventListener('click', () => this.toggleTheme());
        }
    }
};

// Sidebar Layout Manager (Desktop Collapse & Mobile Drawer)
const SidebarManager = {
    init() {
        this.sidebar = document.querySelector('.sidebar');
        this.toggleBtn = document.getElementById('sidebarToggle');
        this.overlay = document.getElementById('mobileDrawerOverlay');
        
        // Restore desktop collapse preference
        const isCollapsed = localStorage.getItem('sidebar_collapsed') === 'true';
        if (isCollapsed && window.innerWidth > 768) {
            document.body.classList.add('sidebar-collapsed');
        }

        this.bindEvents();
    },

    bindEvents() {
        if (this.toggleBtn) {
            this.toggleBtn.addEventListener('click', () => {
                if (window.innerWidth <= 768) {
                    this.toggleMobileDrawer();
                } else {
                    this.toggleDesktopCollapse();
                }
            });
        }

        if (this.overlay) {
            this.overlay.addEventListener('click', () => {
                this.closeMobileDrawer();
            });
        }

        window.addEventListener('resize', () => {
            if (window.innerWidth > 768) {
                this.closeMobileDrawer();
            }
        });
    },

    toggleDesktopCollapse() {
        const isCollapsed = document.body.classList.toggle('sidebar-collapsed');
        localStorage.setItem('sidebar_collapsed', isCollapsed ? 'true' : 'false');
    },

    toggleMobileDrawer() {
        if (this.sidebar) {
            this.sidebar.classList.toggle('mobile-open');
            if (this.overlay) {
                this.overlay.classList.toggle('show');
            }
        }
    },

    closeMobileDrawer() {
        if (this.sidebar) {
            this.sidebar.classList.remove('mobile-open');
        }
        if (this.overlay) {
            this.overlay.classList.remove('show');
        }
    }
};

// Mobile Bottom Menu Toggle
const MobileMenuManager = {
    init() {
        this.moreMenu = document.getElementById('mobileMoreMenu');
        this.bindEvents();
    },

    toggle() {
        if (this.moreMenu) {
            this.moreMenu.classList.toggle('show');
        }
    },

    close() {
        if (this.moreMenu) {
            this.moreMenu.classList.remove('show');
        }
    },

    bindEvents() {
        document.addEventListener('click', (e) => {
            if (this.moreMenu && this.moreMenu.classList.contains('show')) {
                const moreContainer = document.querySelector('.mobile-nav-more');
                if (moreContainer && !moreContainer.contains(e.target)) {
                    this.close();
                }
            }
        });
    }
};

function toggleMobileMenu() {
    MobileMenuManager.toggle();
}

// Flash Message Auto-dismiss
const FlashMessages = {
    init() {
        const alerts = document.querySelectorAll('.alert[data-auto-dismiss]');
        alerts.forEach(alert => {
            const timeout = parseInt(alert.dataset.autoDismiss, 10) || 5000;
            setTimeout(() => {
                alert.style.opacity = '0';
                alert.style.transform = 'translateY(-4px)';
                setTimeout(() => alert.remove(), 250);
            }, timeout);
        });
    }
};

// Form Validation
const FormValidator = {
    init() {
        const forms = document.querySelectorAll('form[data-validate]');
        forms.forEach(form => {
            form.addEventListener('submit', (e) => this.validate(e, form));
        });
    },

    validate(e, form) {
        let isValid = true;
        const required = form.querySelectorAll('[required]');

        required.forEach(field => {
            this.clearError(field);
            if (!field.value.trim()) {
                isValid = false;
                this.showError(field, 'This field is required');
            }
        });

        // Email validation
        const emails = form.querySelectorAll('input[type="email"]');
        emails.forEach(field => {
            if (field.value && !this.isValidEmail(field.value)) {
                isValid = false;
                this.showError(field, 'Please enter a valid email address');
            }
        });

        if (!isValid) {
            e.preventDefault();
        }
    },

    showError(field, message) {
        field.classList.add('is-invalid');
        let error = field.parentNode.querySelector('.text-danger.form-text');
        if (!error) {
            error = document.createElement('div');
            error.className = 'form-text text-danger';
            field.parentNode.appendChild(error);
        }
        error.textContent = message;
    },

    clearError(field) {
        field.classList.remove('is-invalid');
        const error = field.parentNode.querySelector('.text-danger.form-text');
        if (error) error.remove();
    },

    isValidEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }
};

// Student Search Autocomplete
const StudentSearch = {
    init() {
        const searchInputs = document.querySelectorAll('[data-student-search]');
        searchInputs.forEach(input => this.setupSearch(input));
    },

    setupSearch(input) {
        const resultsContainer = document.createElement('div');
        resultsContainer.className = 'search-results';
        resultsContainer.style.cssText = `
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            border-radius: var(--radius-sm);
            max-height: 280px;
            overflow-y: auto;
            z-index: 1050;
            display: none;
            margin-top: 2px;
        `;
        input.parentNode.style.position = 'relative';
        input.parentNode.appendChild(resultsContainer);

        let debounceTimer;
        input.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => this.search(input, resultsContainer), 250);
        });

        document.addEventListener('click', (e) => {
            if (!input.contains(e.target) && !resultsContainer.contains(e.target)) {
                resultsContainer.style.display = 'none';
            }
        });
    },

    async search(input, container) {
        const query = input.value.trim();
        if (query.length < 2) {
            container.style.display = 'none';
            return;
        }

        try {
            const response = await fetch(`/students/api/search?q=${encodeURIComponent(query)}`);
            const students = await response.json();

            if (students.length === 0) {
                container.innerHTML = '<div style="padding: 10px 14px; font-size: 12px; color: var(--text-muted);">No student matches found</div>';
            } else {
                container.innerHTML = students.map(s => `
                    <div class="search-result-item"
                         data-id="${s.id}"
                         data-name="${s.name}"
                         style="padding: 9px 14px; cursor: pointer; border-bottom: 1px solid var(--border-color); font-size: 12.5px;">
                        <strong style="color: var(--text-primary);">${s.name}</strong>
                        <div style="color: var(--text-muted); font-size: 11px; margin-top: 1px;">
                            ID: ${s.student_id} &bull; Class: ${s.batch || 'Not Assigned'}
                        </div>
                    </div>
                `).join('');

                container.querySelectorAll('.search-result-item').forEach(item => {
                    item.addEventListener('click', () => {
                        const targetSelector = input.dataset.studentSearch;
                        const hiddenInput = document.querySelector(targetSelector);
                        if (hiddenInput) {
                            hiddenInput.value = item.dataset.id;
                            hiddenInput.dispatchEvent(new Event('change'));
                        }
                        input.value = item.dataset.name;
                        container.style.display = 'none';
                    });
                });
            }

            container.style.display = 'block';
        } catch (error) {
            console.error('Student search error:', error);
        }
    }
};

// Date Default Setup
const DateHelper = {
    init() {
        document.querySelectorAll('input[type="date"][data-default-today]').forEach(input => {
            if (!input.value) {
                input.value = new Date().toISOString().split('T')[0];
            }
        });
    }
};

// Global Initialization
document.addEventListener('DOMContentLoaded', () => {
    ThemeManager.init();
    SidebarManager.init();
    MobileMenuManager.init();
    FlashMessages.init();
    FormValidator.init();
    StudentSearch.init();
    DateHelper.init();
});

window.toggleMobileMenu = toggleMobileMenu;
window.ThemeManager = ThemeManager;
window.SidebarManager = SidebarManager;
